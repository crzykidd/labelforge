import io
import logging

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
    rgb: tuple[int, int, int] | None = None,
) -> None:
    """Paste sub-image (mode-L coverage mask) onto canvas.

    sub must be mode-L: 0 = ink (opaque), 255 = paper (transparent).
    rgb: when set, composites a solid RGB patch through the coverage mask onto
    an RGB canvas — used for coloured text/shapes on two-color media. When None,
    pastes the grayscale sub directly (mono path).
    """
    if abs(angle) > 0.01:
        # Preserve centre point across expand-rotation.
        cx = left + sub.width // 2
        cy = top + sub.height // 2
        sub = sub.rotate(-angle, expand=True, resample=Image.BICUBIC, fillcolor=255)
        left = cx - sub.width // 2
        top = cy - sub.height // 2
    # Dark pixels (value≈0) → mask 255 (opaque); white (255) → mask 0 (skip).
    # Preserves antialiasing in intermediate greys.
    mask = sub.point(lambda p: 255 - p)
    if rgb is not None:
        canvas.paste(Image.new("RGB", sub.size, rgb), (left, top), mask=mask)
    else:
        canvas.paste(sub, (left, top), mask=mask)


def _render_text_element(
    obj: dict, values: dict[str, str], box_w: int, box_h: int
) -> Image.Image:
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

    sub = Image.new("L", (max(box_w, 1), max(box_h, 1)), 255)
    draw = ImageDraw.Draw(sub)
    draw.multiline_text((0, 0), text, font=pil_font, fill=0, align=align)
    return sub


# TODO: re-enable when QR/barcode 1-bit print bug is fixed
def _render_qr_element(
    payload: str, correction: str, box_w: int, box_h: int
) -> Image.Image:
    if not payload:
        raise RenderError("QR payload is empty after field substitution")
    ec = _QR_CORRECTION.get((correction or "M").upper(), ERROR_CORRECT_M)
    # box_size=1 gives the smallest natural image (1px per module) so the
    # integer scale factor below is maximised and module edges stay crisp.
    qr = qrcode.QRCode(error_correction=ec, border=1, box_size=1)
    qr.add_data(payload)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color=0, back_color=255).save(buf, "PNG")
    buf.seek(0)
    nat = Image.open(buf).convert("L")
    nat.load()
    nat_w, nat_h = nat.size  # always square
    scale = min(box_w // nat_w, box_h // nat_h)
    if scale >= 1:
        # Integer-multiple upscale: every module maps to exactly scale×scale pixels,
        # pure black/white — no grey edges that the print threshold could crush.
        scaled_w, scaled_h = nat_w * scale, nat_h * scale
        scaled = nat.resize((scaled_w, scaled_h), Image.NEAREST)
        result = Image.new("L", (box_w, box_h), 255)
        result.paste(scaled, ((box_w - scaled_w) // 2, (box_h - scaled_h) // 2))
        return result
    # Fallback: box smaller than natural QR; NEAREST keeps pixels pure B/W.
    return nat.resize((max(box_w, 1), max(box_h, 1)), Image.NEAREST)


# TODO: re-enable when QR/barcode 1-bit print bug is fixed
def _render_barcode_element(
    payload: str, symbology: str, box_w: int, box_h: int
) -> Image.Image:
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
    return bw.resize((max(box_w, 1), max(box_h, 1)), Image.NEAREST)


def render_template(template: Template, values: dict[str, str]) -> Image.Image:
    """Rasterize *template* with *values* substituted for placeholders.

    Returns a PIL Image sized for the print head. Mode is 'L' (0=black, 255=white)
    for mono media. For two-color media (label.color == 1, e.g. 62red / DK-2251)
    mode is 'RGB': black pixels are (0,0,0), red pixels are (255,0,0), paper is
    (255,255,255). The print path promotes L→RGB and passes red=True for two-color
    media; an RGB image here means red pixels land on the red print plane.
    """
    label = get_label(template.label_media)
    if label is None:
        raise RenderError(f"Unknown label media: {template.label_media!r}")

    canvas_w = label.dots_printable[0]
    objects = template.canvas_json.get("objects", [])
    is_continuous = label.form_factor in _CONTINUOUS_FORM_FACTORS
    two_color = label.color == 1

    if is_continuous:
        bottommost = 0
        for obj in objects:
            t = int(obj.get("top", 0))
            h = int(obj.get("height", 0) * float(obj.get("scaleY", 1.0)))
            bottommost = max(bottommost, t + h)
        canvas_h = max(bottommost + _PADDING, 1)
    else:
        canvas_h = label.dots_printable[1]

    if two_color:
        canvas: Image.Image = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    else:
        canvas = Image.new("L", (canvas_w, canvas_h), 255)
    draw = ImageDraw.Draw(canvas)

    for obj in objects:
        obj_type = obj.get("type", "")
        # Fabric v6 serializes `type` as the PascalCase class name (IText, Line,
        # Rect, Image); v5 used lowercase/hyphenated (i-text). Normalize both.
        norm_type = obj_type.lower().replace("-", "")
        left = int(obj.get("left", 0))
        top = int(obj.get("top", 0))
        angle = float(obj.get("angle", 0))
        box_w = max(1, int(obj.get("width", 10) * float(obj.get("scaleX", 1.0))))
        box_h = max(1, int(obj.get("height", 10) * float(obj.get("scaleY", 1.0))))

        try:
            if norm_type in ("itext", "text", "textbox"):
                sub = _render_text_element(obj, values, box_w, box_h)
                if two_color:
                    rgb = _canvas_color_to_rgb(obj.get("fill")) or (0, 0, 0)
                    _paste_onto(canvas, sub, left, top, angle, rgb=rgb)
                else:
                    _paste_onto(canvas, sub, left, top, angle)

            elif norm_type == "image":
                if obj.get("labelforge_qr_payload") is not None:
                    raise RenderError(
                        "QR elements are not yet supported for printing"
                        " (known bug: prints as a solid block)"
                    )
                elif obj.get("labelforge_barcode_payload") is not None:
                    raise RenderError(
                        "Barcode elements are not yet supported for printing"
                        " (known bug: prints as a solid block)"
                    )
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
                draw.line([(x1, y1), (x2, y2)], fill=stroke_color, width=max(1, int(obj.get("strokeWidth", 1))))

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
                        _paste_onto(canvas, fill_sub, left, top, angle, rgb=fill_rgb)
                    outline_sub = Image.new("L", (box_w, box_h), 255)
                    outline_sub_draw = ImageDraw.Draw(outline_sub)
                    outline_sub_draw.rectangle([0, 0, box_w - 1, box_h - 1], outline=0, width=sw)
                    _paste_onto(canvas, outline_sub, left, top, angle, rgb=outline_rgb)
                else:
                    fill_v = _canvas_color_to_l(obj.get("fill"))
                    sub = Image.new("L", (box_w, box_h), 255)
                    sub_draw = ImageDraw.Draw(sub)
                    sub_draw.rectangle([0, 0, box_w - 1, box_h - 1], fill=fill_v, outline=0, width=sw)
                    _paste_onto(canvas, sub, left, top, angle)

            else:
                logger.debug("Skipping unhandled element type %r", obj_type)

        except RenderError:
            raise
        except Exception as exc:
            raise RenderError(f"Failed to render element '{obj_type}': {exc}") from exc

    return canvas
