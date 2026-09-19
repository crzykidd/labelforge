import io
import logging
import math

import barcode as _barcode_lib
import qrcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q

from labelforge.catalog.loader import get_label
from labelforge.models import Template
from labelforge.render.fonts import get_font_path
from labelforge.render.text import RenderError
from labelforge.templates.fields import resolve_content

logger = logging.getLogger(__name__)

_PADDING = 20
_CONTINUOUS_FORM_FACTORS = {2, 4}

_QR_CORRECTION = {
    "L": ERROR_CORRECT_L,
    "M": ERROR_CORRECT_M,
    "Q": ERROR_CORRECT_Q,
    "H": ERROR_CORRECT_H,
}


def _origin_top_left(obj: dict, left: int, top: int, box_w: int, box_h: int) -> tuple[int, int]:
    """Translate Fabric left/top (origin-relative) to the top-left corner.

    Fabric stores left/top relative to originX/originY. The renderer pastes at the
    top-left, so shift by half/full box for center/right (x) and center/bottom (y).
    Defaults (left/top) are a no-op.
    """
    ox = str(obj.get("originX", "left")).lower()
    oy = str(obj.get("originY", "top")).lower()
    if ox == "center":
        left -= box_w // 2
    elif ox == "right":
        left -= box_w
    if oy == "center":
        top -= box_h // 2
    elif oy == "bottom":
        top -= box_h
    return left, top


def _rotated_aabb(
    anchor_x: float, anchor_y: float, obj: dict, box_w: float, box_h: float, angle: float
) -> tuple[float, float, float, float]:
    """World-space AABB of a box_w×box_h element after rotating by `angle` degrees.

    (anchor_x, anchor_y) is the element's stored left/top — Fabric's pivot for
    rotation is that origin point, not the box's own centre (see
    docs/decisions.md), so the box's *unrotated* centre is first found via
    `_origin_top_left` and then swung around the anchor by `angle` to get the
    true centre; the AABB size is the standard rotated-rectangle formula
    (pivot-independent — rotating a rigid box never changes its bounding size,
    only its position). angle == 0 is an exact no-op: no trig, no float drift
    on the overwhelmingly common unrotated case.
    """
    left, top = _origin_top_left(obj, int(anchor_x), int(anchor_y), int(box_w), int(box_h))
    if angle == 0:
        return left, top, left + box_w, top + box_h
    rad = math.radians(angle)
    c, s = math.cos(rad), math.sin(rad)
    cx, cy = left + box_w / 2, top + box_h / 2
    dx, dy = cx - anchor_x, cy - anchor_y
    wcx = anchor_x + dx * c - dy * s
    wcy = anchor_y + dx * s + dy * c
    rw = abs(box_w * c) + abs(box_h * s)
    rh = abs(box_w * s) + abs(box_h * c)
    return wcx - rw / 2, wcy - rh / 2, wcx + rw / 2, wcy + rh / 2


def _canvas_color_to_l(color: str | None) -> int | None:
    """Map a CSS color string to mode-L pixel value; None means no fill."""
    if not color or color in ("transparent", "rgba(0,0,0,0)", "none"):
        return None
    lc = color.lower().strip()
    if lc in ("#fff", "#ffffff", "white", "rgb(255,255,255)"):
        return 255
    return 0


def _canvas_color_to_rgb(color: str | None) -> tuple[int, int, int] | None:
    """Map a CSS color to an RGB tuple for two-color rendering.

    Returns None for transparent/no-fill, (255,0,0) for red, (0,0,0) for black
    (the only two ink colors on a two-color DK roll). White is treated as the
    paper color (opaque white — use None for transparent backgrounds instead).
    """
    if not color or color.lower().strip() in ("transparent", "rgba(0,0,0,0)", "none"):
        return None
    lc = color.lower().strip()
    if lc in ("#fff", "#ffffff", "white", "rgb(255,255,255)"):
        return (255, 255, 255)
    if lc in ("#ff0000", "#f00", "red", "rgb(255,0,0)"):
        return (255, 0, 0)
    return (0, 0, 0)


def _resolve_font_path(family: str, weight: str | None, style: str | None) -> str | None:
    """Return the best matching font file path, falling back to base family on miss."""
    bold = bool(weight and str(weight).lower() in ("bold", "700", "800", "900"))
    italic = bool(style and str(style).lower() in ("italic", "oblique"))

    # Normalise family name into candidate stems (CSS name, no-space, hyphen-joined).
    bases: list[str] = list(
        dict.fromkeys([family, family.replace(" ", ""), family.replace(" ", "-")])
    )
    candidates: list[str] = []
    for base in bases:
        if bold and italic:
            candidates += [f"{base}-BoldItalic", f"{base}BoldItalic"]
        if bold:
            candidates += [f"{base}-Bold", f"{base}Bold"]
        if italic:
            candidates += [f"{base}-Italic", f"{base}Italic", f"{base}-Oblique"]
        candidates.append(base)

    seen: set[str] = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        path = get_font_path(name)
        if path:
            return path
    return None


def _paste_onto(
    canvas: Image.Image,
    sub: Image.Image,
    left: int,
    top: int,
    angle: float,
    anchor_x: float,
    anchor_y: float,
    rgb: tuple[int, int, int] | None = None,
) -> None:
    """Paste sub-image (mode-L coverage mask) onto canvas.

    sub must be mode-L: 0 = ink (opaque), 255 = paper (transparent).
    rgb: when set, composites a solid RGB patch through the coverage mask onto
    an RGB canvas — used for coloured text/shapes on two-color media. When None,
    pastes the grayscale sub directly (mono path).

    (anchor_x, anchor_y) is the element's raw (pre-origin-resolution) left/top —
    Fabric rotates an object about that origin point, not its own centre (Fabric
    7 defaults new objects to centre origin, where the two coincide, but QR and
    barcode elements use left/top origin — see docs/decisions.md). `sub.rotate`
    below always rotates about the sub-image's own centre and expands around it,
    so the fix is to find where that centre *actually* lands once the box
    pivots about the anchor, and paste the expanded/rotated image there instead
    of just re-centring on the untransformed box.
    """
    if abs(angle) > 0.01:
        cx = left + sub.width / 2
        cy = top + sub.height / 2
        rad = math.radians(angle)
        c, s = math.cos(rad), math.sin(rad)
        dx, dy = cx - anchor_x, cy - anchor_y
        cx = anchor_x + dx * c - dy * s
        cy = anchor_y + dx * s + dy * c
        sub = sub.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC, fillcolor=255)
        left = round(cx - sub.width / 2)
        top = round(cy - sub.height / 2)
    # Dark pixels (value≈0) → mask 255 (opaque); white (255) → mask 0 (skip).
    # Preserves antialiasing in intermediate greys.
    mask = sub.point(lambda p: 255 - p)
    if rgb is not None:
        canvas.paste(Image.new("RGB", sub.size, rgb), (left, top), mask=mask)
    else:
        canvas.paste(sub, (left, top), mask=mask)


def _wrap_text(
    text: str, font: ImageFont.FreeTypeFont, target_width: int, max_lines: int = 0
) -> tuple[str, bool]:
    """Word-wrap *text* at spaces so each line's rendered width fits target_width.

    A paragraph (an existing "\\n"-delimited segment) that already fits is returned
    completely unchanged — exact original spacing preserved — so wrap-on-but-fitting
    content renders byte-identically to wrap-off (see docs/decisions.md). Only a
    paragraph that needs wrapping is rebuilt, joining words with a single space. A
    single word wider than target_width is never split — it is left on its own line,
    overflowing, for overflow detection to report.

    max_lines: 0 (default) means unlimited — the v0.1.8 behavior, and the code path
    below is untouched byte-for-byte in that case (the `remaining` budget is always
    None, so no truncation branch is ever taken). When positive, it caps the *total*
    number of lines across every paragraph combined: each line is still greedily
    filled first ("go to the first break that uses all the space" — the operator's
    words), and once the cumulative budget runs out the remainder — whether the rest
    of the current paragraph's lines, or entire following paragraphs — is dropped and
    the second return value is True. Truncation is never silent: the caller must
    surface that flag as overflow (see docs/decisions.md).
    """
    scratch = ImageDraw.Draw(Image.new("L", (1, 1)))
    out_paragraphs: list[str] = []
    lines_used = 0
    truncated = False
    for paragraph in text.split("\n"):
        if max_lines and lines_used >= max_lines:
            truncated = True
            break
        remaining = max_lines - lines_used if max_lines else None
        if scratch.textlength(paragraph, font=font) <= target_width:
            out_paragraphs.append(paragraph)
            lines_used += 1
            continue
        words = paragraph.split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if current and scratch.textlength(candidate, font=font) > target_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
        if remaining is not None and len(lines) > remaining:
            lines = lines[:remaining]
            truncated = True
        out_paragraphs.append("\n".join(lines))
        lines_used += len(lines)
    return "\n".join(out_paragraphs), truncated


def _wrap_target_width(box_w: float, head_width: int | None, angle: float, rotated: bool) -> float:
    """The wrap target width: the axis the text actually runs along.

    Text runs along the element's own local x-axis (`box_w`'s direction). Composing
    the element's own rotation (`angle`) with the template's orientation (which
    transposes the whole design canvas onto the length axis — see render_template's
    docstring) determines whether that local axis lands on the print head's fixed
    ceiling or the free length axis. This reuses the same rotation composition
    `_rotated_aabb` uses (radians, cos/sin) rather than a second, divergent formula.

    - angle ~ 0/180 in a standard template, or angle ~ 90/270 in a rotated
      template: box_w's axis coincides with the head-width axis, so it's a hard
      ceiling — `min(box_w, head_width)`, the original (pre-orientation-aware)
      behavior, preserved byte-for-byte for the common unrotated case.
    - Otherwise the local x-axis has been transposed onto the free length axis
      (unbounded for continuous media, and this is exactly the "rotated template"
      case the wrap width was wrapping too early on) — box_w alone governs, with
      no head_width clamp.
    """
    if head_width is None:
        return box_w
    rad = math.radians(angle)
    box_w_is_x_axis = abs(math.cos(rad)) >= abs(math.sin(rad))
    head_axis_is_x = not rotated
    if box_w_is_x_axis == head_axis_is_x:
        return min(box_w, head_width)
    return box_w


def _render_text_element(
    obj: dict,
    values: dict[str, str],
    box_w: int,
    box_h: int,
    *,
    head_width: int | None = None,
    rotated: bool = False,
) -> tuple[Image.Image, bool]:
    raw = obj.get("labelforge_raw_content") or obj.get("text", "")
    text = resolve_content(raw, values)

    family = obj.get("fontFamily", "")
    font_path = _resolve_font_path(family, obj.get("fontWeight"), obj.get("fontStyle"))
    if not font_path:
        raise RenderError(f"Font not available: {family!r}")

    font_size = max(6, int(obj.get("fontSize", 20)))
    try:
        pil_font = ImageFont.truetype(font_path, font_size)
    except Exception as exc:
        raise RenderError(f"Could not load font '{family}': {exc}") from exc

    align = obj.get("textAlign", "left")
    if align not in ("left", "center", "right"):
        align = "left"

    truncated = False
    if obj.get("labelforge_wrap"):
        angle = float(obj.get("angle", 0))
        target_w = _wrap_target_width(box_w, head_width, angle, rotated)
        max_lines = int(obj.get("labelforge_wrap_max_lines") or 0)
        text, truncated = _wrap_text(text, pil_font, max(int(target_w), 1), max_lines)

    # Measure actual PIL text extent — browser font metrics in Fabric differ from PIL's.
    scratch = Image.new("L", (1, 1))
    bbox = ImageDraw.Draw(scratch).multiline_textbbox(
        (0, 0), text, font=pil_font, align=align, spacing=4
    )
    real_w = max(box_w, math.ceil(bbox[2]))
    real_h = math.ceil(bbox[3]) + 4  # +4px descender margin

    sub = Image.new("L", (max(real_w, 1), max(real_h, 1)), 255)
    draw = ImageDraw.Draw(sub)
    # Cancel any positive ascender gap so ink starts at y=0, not shifted down.
    draw.multiline_text((0, -bbox[1]), text, font=pil_font, fill=0, align=align, spacing=4)
    return sub, truncated


def _render_qr_element(payload: str, correction: str, box_w: int, box_h: int) -> Image.Image:
    if not payload:
        raise RenderError("QR payload is empty after field substitution")
    ec = _QR_CORRECTION.get((correction or "M").upper(), ERROR_CORRECT_M)
    # box_size=1 gives the smallest natural image (1px per module) so the
    # integer scale factor below is maximised and module edges stay crisp.
    qr = qrcode.QRCode(error_correction=ec, border=1, box_size=1)
    qr.add_data(payload)
    qr.make(fit=True)
    buf = io.BytesIO()
    # Use color names, not ints: qrcode's PIL factory renders back_color=255 as a
    # grey background (~76 after L-convert), which the hard-threshold below then
    # crushes to black — turning the whole QR into a solid block.
    qr.make_image(fill_color="black", back_color="white").save(buf, "PNG")
    buf.seek(0)
    nat = Image.open(buf).convert("L")
    nat.load()
    nat_w, nat_h = nat.size  # always square
    scale = min(box_w // nat_w, box_h // nat_h)
    if scale >= 1:
        # Integer-multiple upscale: every module maps to exactly scale×scale pixels,
        # pure black/white — no grey edges that the print threshold could crush.
        scaled_w, scaled_h = nat_w * scale, nat_h * scale
        scaled = nat.resize((scaled_w, scaled_h), Image.Resampling.NEAREST)
        result = Image.new("L", (box_w, box_h), 255)
        result.paste(scaled, ((box_w - scaled_w) // 2, (box_h - scaled_h) // 2))
    else:
        # Fallback: box smaller than natural QR; NEAREST keeps pixels pure B/W.
        result = nat.resize((max(box_w, 1), max(box_h, 1)), Image.Resampling.NEAREST)
    # Hard-threshold insurance: guarantee strictly 0/255 before paste so the print
    # threshold (any L ≤ 179 prints black) cannot crush an accidentally grey edge.
    return result.point(lambda x: 0 if x < 128 else 255)


def _render_barcode_element(payload: str, symbology: str, box_w: int, box_h: int) -> Image.Image:
    if not payload:
        raise RenderError("Barcode payload is empty after field substitution")
    symb = (symbology or "code128").lower().replace("-", "").replace("_", "")
    try:
        bc_class = _barcode_lib.get_barcode_class(symb)
    except Exception:
        bc_class = _barcode_lib.get_barcode_class("code128")
    try:
        bc = bc_class(payload, writer=ImageWriter())
    except Exception as exc:
        raise RenderError(f"Invalid barcode payload for {symbology!r}: {exc}") from exc
    buf = io.BytesIO()
    bc.write(buf, options={"write_text": False})
    buf.seek(0)
    img = Image.open(buf)
    img.load()
    # Force pure black/white before scaling; NEAREST keeps bars as whole-pixel
    # columns with no anti-aliased grey that the print threshold could merge.
    bw = img.convert("L").point(lambda x: 0 if x < 128 else 255)
    return bw.resize((max(box_w, 1), max(box_h, 1)), Image.Resampling.NEAREST)


def detect_overflow(
    template: Template, media_id: str, values: dict[str, str] | None = None
) -> bool:
    """True when any element's *printed* content falls outside the printable area.

    values: resolved field values. When given, text elements are measured at their
    actual rendered size (same as render_template) rather than the stored
    placeholder box — this is what catches a value longer than the placeholder it
    was designed around. When omitted, text is measured by its stored box only
    (legacy behavior).

    Bounds are taken in *design space*, which is transposed for a rotated template —
    the same swap render_template applies — so a rotated design is checked against
    the axes it was actually authored on.

    Die-cut: any element extending past the far edge on either axis is flagged.
    (A negative-origin excursion from element rotation is not flagged here — that's
    an editor/off-canvas concern, not a print-overflow one; see docs/decisions.md.)

    Continuous: length never overflows (the label prints longer — see
    render_template). The print-head-width axis is still fixed, though — that's the
    x axis normally, or y in a rotated template's transposed design frame — so a
    line wider than the head is flagged even on continuous media.

    Wrap truncation: when `values` is given and a wrapped element's content needed
    more lines than its `labelforge_wrap_max_lines` cap, the excess is dropped by
    `_render_text_element`/`_wrap_text` — that never shrinks the element's AABB
    below the printable area, so it can't be caught by the bounds checks above. It
    is reported directly instead: any truncated element makes this return True. See
    docs/decisions.md (truncate-with-warning, not shrink-to-fit).
    """
    label = get_label(media_id)
    if label is None:
        return False
    rotated = template.orientation == "rotated"
    head_width, die_length = label.dots_printable
    is_continuous = label.form_factor in _CONTINUOUS_FORM_FACTORS
    if not is_continuous:
        max_w, max_h = (die_length, head_width) if rotated else (head_width, die_length)

    for obj in template.canvas_json.get("objects", []):
        raw_left = int(obj.get("left", 0))
        raw_top = int(obj.get("top", 0))
        angle = float(obj.get("angle", 0))
        norm_type = obj.get("type", "").lower().replace("-", "")
        w = int(obj.get("width", 0) * float(obj.get("scaleX", 1.0)))
        h = int(obj.get("height", 0) * float(obj.get("scaleY", 1.0)))
        if values is not None and norm_type in ("itext", "text", "textbox"):
            try:
                sub, truncated = _render_text_element(
                    obj, values, max(w, 1), max(h, 1), head_width=head_width, rotated=rotated
                )
                w, h = sub.width, sub.height
                if truncated:
                    return True
            except RenderError:
                pass  # fall back to the stored box; render_template will raise properly
        _, _, x1, y1 = _rotated_aabb(raw_left, raw_top, obj, w, h, angle)
        if is_continuous:
            head_edge = y1 if rotated else x1
            if head_edge > head_width:
                return True
        else:
            if y1 > max_h or x1 > max_w:
                return True
    return False


def render_template(
    template: Template,
    values: dict[str, str],
    *,
    media_override: str | None = None,
) -> Image.Image:
    """Rasterize *template* with *values* substituted for placeholders.

    media_override: when set, render as if the template were on this media rather
    than template.label_media. The stored template is never mutated. Used for
    print-time one-off media selection (e.g. print a 62red design on 62x29).

    Returns a PIL Image sized for the print head. Mode is 'L' (0=black, 255=white)
    for mono media. For two-color media (label.color == 1, e.g. 62red / DK-2251)
    mode is 'RGB': black pixels are (0,0,0), red pixels are (255,0,0), paper is
    (255,255,255). The print path promotes L→RGB and passes red=True for two-color
    media; an RGB image here means red pixels land on the red print plane.
    On mono media any red element is rendered as black (via _canvas_color_to_l/rgb).

    template.orientation == "rotated": elements are drawn on a canvas transposed
    to the label's length axis (matching the editor, which designs upright on the
    same transposed canvas) and the finished canvas is rotated 270° once at the
    end, restoring the print-head-width invariant client.py relies on. See the
    rotation direction comment near the end of this function for why 270, not 90.
    """
    effective_media = media_override or template.label_media
    label = get_label(effective_media)
    if label is None:
        raise RenderError(f"Unknown label media: {effective_media!r}")

    rotated = template.orientation == "rotated"
    head_width = label.dots_printable[0]
    objects = template.canvas_json.get("objects", [])
    is_continuous = label.form_factor in _CONTINUOUS_FORM_FACTORS
    two_color = label.color == 1

    # Pre-render text elements once so PIL-measured extents inform the continuous
    # auto-length axis below.
    text_subs: dict[int, Image.Image] = {}
    for i, obj in enumerate(objects):
        norm_type = obj.get("type", "").lower().replace("-", "")
        if norm_type in ("itext", "text", "textbox"):
            box_w = max(1, int(obj.get("width", 10) * float(obj.get("scaleX", 1.0))))
            box_h = max(1, int(obj.get("height", 10) * float(obj.get("scaleY", 1.0))))
            try:
                # Truncation (if any) is surfaced separately by detect_overflow's own
                # call to this function — the print/preview routes always re-run it
                # against the same values, so it's the single source of the warning.
                text_subs[i] = _render_text_element(
                    obj, values, box_w, box_h, head_width=head_width, rotated=rotated
                )[0]
            except RenderError:
                raise
            except Exception as exc:
                raise RenderError(f"Failed to render element 'text': {exc}") from exc

    shift = 0
    if is_continuous:
        # Standard: length grows downward, tracked via the bottommost extent.
        # Rotated: the design canvas is transposed, so length is the design's
        # rightmost extent instead. Either way, a rotated *element* can push
        # extent along either design axis, so the full rotated AABB is needed —
        # not just the element's unrotated height (standard) or width (rotated).
        #
        # A centre-origin (or right/bottom-origin) element whose *resolved* value
        # is wider than the placeholder it was designed around grows backwards
        # past the start of the label too, not just forwards — so both the
        # nearest and farthest edges are tracked. If the nearest edge is
        # negative, the label wasn't long enough to hold what grew off its
        # start: grow the canvas to cover it and shift every element forward by
        # the same amount so nothing is lost off the front. This is a no-op
        # (shift stays 0) whenever nothing goes negative, which is every
        # template that already fit — see docs/decisions.md.
        min_lo = 0.0
        max_hi = 0.0
        seen_any = False
        for i, obj in enumerate(objects):
            angle = float(obj.get("angle", 0))
            raw_left = int(obj.get("left", 0))
            raw_top = int(obj.get("top", 0))
            if i in text_subs:
                ext_w: float = text_subs[i].width
                ext_h: float = text_subs[i].height
            else:
                ext_w = max(1, int(obj.get("width", 10) * float(obj.get("scaleX", 1.0))))
                ext_h = max(1, int(obj.get("height", 10) * float(obj.get("scaleY", 1.0))))
            ext_x0, ext_y0, ext_x1, ext_y1 = _rotated_aabb(
                raw_left, raw_top, obj, ext_w, ext_h, angle
            )
            lo, hi = (ext_x0, ext_x1) if rotated else (ext_y0, ext_y1)
            if not seen_any:
                min_lo, max_hi = lo, hi
                seen_any = True
            else:
                min_lo = min(min_lo, lo)
                max_hi = max(max_hi, hi)
        if seen_any and min_lo < 0:
            shift = int(math.ceil(-min_lo))
        length = max(int(math.ceil(max_hi)) + shift + _PADDING, 1)
    else:
        length = label.dots_printable[1]

    canvas_w, canvas_h = (length, head_width) if rotated else (head_width, length)
    # The shift (if any) always applies to the free/growing axis: x when the
    # template's design frame is transposed (rotated), y otherwise. Die-cut
    # media never shifts (shift is 0 there) — it can't grow, so an out-of-bounds
    # element is reported by detect_overflow instead of silently repositioned.
    shift_x = shift if rotated else 0
    shift_y = 0 if rotated else shift

    if two_color:
        canvas: Image.Image = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    else:
        canvas = Image.new("L", (canvas_w, canvas_h), 255)
    draw = ImageDraw.Draw(canvas)

    for i, obj in enumerate(objects):
        obj_type = obj.get("type", "")
        # Fabric v6 serializes `type` as the PascalCase class name (IText, Line,
        # Rect, Image); v5 used lowercase/hyphenated (i-text). Normalize both.
        norm_type = obj_type.lower().replace("-", "")
        anchor_x = int(obj.get("left", 0)) + shift_x
        anchor_y = int(obj.get("top", 0)) + shift_y
        angle = float(obj.get("angle", 0))
        box_w = max(1, int(obj.get("width", 10) * float(obj.get("scaleX", 1.0))))
        box_h = max(1, int(obj.get("height", 10) * float(obj.get("scaleY", 1.0))))
        if i in text_subs:
            # Grow (never shrink) to the actual rendered size for origin-relative
            # placement (center/right/bottom) — a resolved value wider/taller than
            # the placeholder must be centered on what's really being pasted,
            # matching the extent calc above. Real text height routinely differs
            # (usually smaller) from the arbitrary design box height even when
            # everything fits, so this is a max, not a replace: shrinking the
            # effective box would shift already-fitting center/right/bottom-origin
            # text and break byte-identical output for the common case.
            box_w = max(box_w, text_subs[i].width)
            box_h = max(box_h, text_subs[i].height)
        left, top = _origin_top_left(obj, anchor_x, anchor_y, box_w, box_h)

        try:
            if norm_type in ("itext", "text", "textbox"):
                sub = text_subs[i]  # pre-rendered above
                if two_color:
                    rgb = _canvas_color_to_rgb(obj.get("fill")) or (0, 0, 0)
                    _paste_onto(canvas, sub, left, top, angle, anchor_x, anchor_y, rgb=rgb)
                else:
                    _paste_onto(canvas, sub, left, top, angle, anchor_x, anchor_y)

            elif norm_type == "image":
                if obj.get("labelforge_qr_payload") is not None:
                    raw_payload = str(obj["labelforge_qr_payload"])
                    qr_payload = resolve_content(raw_payload, values)
                    correction = str(obj.get("labelforge_qr_error_correction") or "M").upper()
                    if correction not in _QR_CORRECTION:
                        correction = "M"
                    sub = _render_qr_element(qr_payload, correction, box_w, box_h)
                    if two_color:
                        _paste_onto(
                            canvas, sub, left, top, angle, anchor_x, anchor_y, rgb=(0, 0, 0)
                        )
                    else:
                        _paste_onto(canvas, sub, left, top, angle, anchor_x, anchor_y)
                elif obj.get("labelforge_barcode_payload") is not None:
                    raw_payload = str(obj["labelforge_barcode_payload"])
                    bc_payload = resolve_content(raw_payload, values)
                    symbology = str(obj.get("labelforge_barcode_symbology") or "code128")
                    sub = _render_barcode_element(bc_payload, symbology, box_w, box_h)
                    if two_color:
                        _paste_onto(
                            canvas, sub, left, top, angle, anchor_x, anchor_y, rgb=(0, 0, 0)
                        )
                    else:
                        _paste_onto(canvas, sub, left, top, angle, anchor_x, anchor_y)
                else:
                    raise RenderError("Image elements not yet supported")

            elif norm_type == "line":
                x1 = left + int(obj.get("x1", 0))
                y1 = top + int(obj.get("y1", 0))
                x2 = left + int(obj.get("x2", box_w))
                y2 = top + int(obj.get("y2", box_h))
                stroke_color: tuple[int, int, int] | int
                if two_color:
                    stroke_color = _canvas_color_to_rgb(obj.get("stroke") or "#000000") or (0, 0, 0)
                else:
                    stroke_color = 0
                draw.line(
                    [(x1, y1), (x2, y2)],
                    fill=stroke_color,
                    width=max(1, int(obj.get("strokeWidth", 1))),
                )

            elif norm_type == "rect":
                sw = max(1, int(obj.get("strokeWidth", 1)))
                if two_color:
                    fill_rgb = _canvas_color_to_rgb(obj.get("fill"))
                    outline_rgb = _canvas_color_to_rgb(obj.get("stroke") or "#000000") or (0, 0, 0)
                    # Draw fill and outline as separate L masks so each can carry its own
                    # color and rotation is handled by _paste_onto.
                    if fill_rgb is not None:
                        fill_sub = Image.new("L", (box_w, box_h), 255)
                        fill_sub_draw = ImageDraw.Draw(fill_sub)
                        fill_sub_draw.rectangle([sw, sw, box_w - 1 - sw, box_h - 1 - sw], fill=0)
                        _paste_onto(
                            canvas, fill_sub, left, top, angle, anchor_x, anchor_y, rgb=fill_rgb
                        )
                    outline_sub = Image.new("L", (box_w, box_h), 255)
                    outline_sub_draw = ImageDraw.Draw(outline_sub)
                    outline_sub_draw.rectangle([0, 0, box_w - 1, box_h - 1], outline=0, width=sw)
                    _paste_onto(
                        canvas, outline_sub, left, top, angle, anchor_x, anchor_y, rgb=outline_rgb
                    )
                else:
                    fill_v = _canvas_color_to_l(obj.get("fill"))
                    sub = Image.new("L", (box_w, box_h), 255)
                    sub_draw = ImageDraw.Draw(sub)
                    sub_draw.rectangle(
                        [0, 0, box_w - 1, box_h - 1], fill=fill_v, outline=0, width=sw
                    )
                    _paste_onto(canvas, sub, left, top, angle, anchor_x, anchor_y)

            else:
                logger.debug("Skipping unhandled element type %r", obj_type)

        except RenderError:
            raise
        except Exception as exc:
            raise RenderError(f"Failed to render element '{obj_type}': {exc}") from exc

    if rotated:
        # 90, so the design's top edge lands on the label's left edge: turning
        # the printed label a quarter turn clockwise then reads it the same way
        # up as the editor showed it. 270 puts the design's top on the right,
        # which reads upside down relative to the canvas — reported as wrong by
        # the operator. See docs/decisions.md; this outranks the feed-order
        # argument that originally motivated 270.
        white = 255 if canvas.mode == "L" else (255, 255, 255)
        canvas = canvas.rotate(90, expand=True, fillcolor=white)

    return canvas
