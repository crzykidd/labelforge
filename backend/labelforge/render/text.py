import logging

from PIL import Image, ImageDraw, ImageFont

from labelforge.catalog.loader import get_label
from labelforge.render.fonts import get_font_path

logger = logging.getLogger(__name__)

# Horizontal and vertical padding in pixels applied inside the label bounds.
_PADDING = 20

# form_factor values that represent continuous (endless) media.
_CONTINUOUS_FORM_FACTORS = {2, 4}  # ENDLESS=2, PTOUCH_ENDLESS=4


class RenderError(Exception):
    pass


def render_text(
    text: str,
    font_name: str,
    font_size: int,
    alignment: str,
    orientation: str,
    bold: bool,  # noqa: ARG001 — reserved for future bold-variant font selection
    italic: bool,  # noqa: ARG001 — reserved for future italic-variant font selection
    label_media: str,
) -> Image.Image:
    """Render *text* onto a white PIL Image sized for *label_media*.

    For continuous media the height expands to fit the text.
    For die-cut media the height is fixed; raises RenderError if text overflows.
    """
    label = get_label(label_media)
    if label is None:
        raise RenderError(f"Unknown label media: {label_media}")

    font_path = get_font_path(font_name)
    if font_path is None:
        raise RenderError(f"Font not available: {font_name}")

    try:
        pil_font = ImageFont.truetype(font_path, font_size)
    except Exception as exc:
        raise RenderError(f"Could not load font '{font_name}': {exc}") from exc

    width_px = label.dots_printable[0]
    usable_width = width_px - 2 * _PADDING

    # Measure and wrap using a throw-away draw surface.
    _probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines = _wrap_text(text, pil_font, usable_width, _probe)
    line_height = _measure_line_height(pil_font, _probe)
    total_text_height = len(lines) * line_height
    total_height = total_text_height + 2 * _PADDING

    is_continuous = label.form_factor in _CONTINUOUS_FORM_FACTORS

    if is_continuous:
        height_px = max(total_height, 1)
    else:
        height_px = label.dots_printable[1]
        if total_height > height_px:
            raise RenderError(
                f"Text exceeds label dimensions at requested font size "
                f"({total_height}px rendered, {height_px}px available). "
                "Reduce font size or shorten the text."
            )

    img = Image.new("L", (width_px, height_px), 255)
    draw = ImageDraw.Draw(img)

    y = _PADDING
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=pil_font)
        text_width = bbox[2] - bbox[0]

        if alignment == "center":
            x = (width_px - text_width) // 2
        elif alignment == "right":
            x = width_px - text_width - _PADDING
        else:
            x = _PADDING

        draw.text((x, y), line, fill=0, font=pil_font)
        y += line_height

    if orientation == "rotated":
        img = img.rotate(90, expand=True)

    return img


def _measure_line_height(font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw) -> int:
    bbox = draw.textbbox((0, 0), "Ag|", font=font)
    return (bbox[3] - bbox[1]) + 4  # +4px inter-line gap


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """Word-wrap *text* to fit within *max_width* pixels."""
    output: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            output.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = candidate
            else:
                if current:
                    output.append(current)
                current = word
        if current:
            output.append(current)
    return output or [""]
