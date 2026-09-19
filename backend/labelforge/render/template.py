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


def _render_text_element(obj: dict, values: dict[str, str], box_w: int, box_h: int) -> Image.Image:
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
    return sub


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


def detect_overflow(template: Template, media_id: str) -> bool:
    """True when any element falls outside the printable area for a die-cut media.

    Bounds are taken in *design space*, which is transposed for a rotated template —
    the same swap render_template applies — so a rotated design is checked against
    the axes it was actually authored on.

    Continuous media never overflows (canvas length is content-driven). Returns False
    for continuous media or when the media is unknown.
    """
    label = get_label(media_id)
    if label is None:
        return False
    if label.form_factor in _CONTINUOUS_FORM_FACTORS:
        return False
    head_width, length = label.dots_printable
    if template.orientation == "rotated":
        max_w, max_h = length, head_width
    else:
        max_w, max_h = head_width, length
    for obj in template.canvas_json.get("objects", []):
        raw_left = int(obj.get("left", 0))
        raw_top = int(obj.get("top", 0))
        w = int(obj.get("width", 0) * float(obj.get("scaleX", 1.0)))
        h = int(obj.get("height", 0) * float(obj.get("scaleY", 1.0)))
        angle = float(obj.get("angle", 0))
        _, _, x1, y1 = _rotated_aabb(raw_left, raw_top, obj, w, h, angle)
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
                text_subs[i] = _render_text_element(obj, values, box_w, box_h)
            except RenderError:
                raise
            except Exception as exc:
                raise RenderError(f"Failed to render element 'text': {exc}") from exc

    if is_continuous:
        # Standard: length grows downward, tracked via the bottommost extent.
        # Rotated: the design canvas is transposed, so length is the design's
        # rightmost extent instead. Either way, a rotated *element* can push
        # extent along either design axis, so the full rotated AABB is needed —
        # not just the element's unrotated height (standard) or width (rotated).
        extent = 0.0
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
            _, _, ext_x1, ext_y1 = _rotated_aabb(raw_left, raw_top, obj, ext_w, ext_h, angle)
            extent = max(extent, ext_x1 if rotated else ext_y1)
        length = max(int(math.ceil(extent)) + _PADDING, 1)
    else:
        length = label.dots_printable[1]

    canvas_w, canvas_h = (length, head_width) if rotated else (head_width, length)

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
        anchor_x = int(obj.get("left", 0))
        anchor_y = int(obj.get("top", 0))
        angle = float(obj.get("angle", 0))
        box_w = max(1, int(obj.get("width", 10) * float(obj.get("scaleX", 1.0))))
        box_h = max(1, int(obj.get("height", 10) * float(obj.get("scaleY", 1.0))))
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
