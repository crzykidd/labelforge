"""Regression test: server renderer honors Fabric originX/originY.

A center-origin element at (left, top) must render pixel-identically to an
equivalent left-origin element placed at the computed top-left corner
(left - width//2, top - height//2).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from labelforge.models import LabelEntry, Template
from PIL import Image  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

pytestmark = pytest.mark.skipif(
    not os.path.exists(_FONT_PATH),
    reason=f"DejaVuSans-Bold not found at {_FONT_PATH}; skipping origin render tests",
)


def _make_label_62x29() -> LabelEntry:
    return LabelEntry(
        id="62x29",
        display_name="62x29",
        dots_printable=(696, 271),
        tape_size=(62, 29),
        form_factor=1,  # die-cut
        color=0,
        supported=True,
    )


def _make_template(canvas_json: dict) -> Template:
    return Template(
        name="origin-test",
        display_name="Origin Test",
        label_media="62x29",
        canvas_json=canvas_json,
        field_schema=[],
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


# Element geometry: center point used as the Fabric anchor when originX/Y = 'center'
_CENTER_X = 200
_CENTER_Y = 100
_WIDTH = 120
_HEIGHT = 40
_FONT_SIZE = 20

# Equivalent top-left corner for originX='left', originY='top'
_LEFT_X = _CENTER_X - _WIDTH // 2
_LEFT_Y = _CENTER_Y - _HEIGHT // 2

_TEXT = "Hello"


def _center_origin_obj() -> dict:
    return {
        "type": "IText",
        "text": _TEXT,
        "left": _CENTER_X,
        "top": _CENTER_Y,
        "width": _WIDTH,
        "height": _HEIGHT,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "angle": 0,
        "originX": "center",
        "originY": "center",
        "fontFamily": "DejaVuSans-Bold",
        "fontSize": _FONT_SIZE,
        "fontWeight": "bold",
        "fontStyle": "",
        "textAlign": "left",
        "fill": "#000000",
        "labelforge_raw_content": _TEXT,
    }


def _left_origin_obj() -> dict:
    return {
        "type": "IText",
        "text": _TEXT,
        "left": _LEFT_X,
        "top": _LEFT_Y,
        "width": _WIDTH,
        "height": _HEIGHT,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "angle": 0,
        "originX": "left",
        "originY": "top",
        "fontFamily": "DejaVuSans-Bold",
        "fontSize": _FONT_SIZE,
        "fontWeight": "bold",
        "fontStyle": "",
        "textAlign": "left",
        "fill": "#000000",
        "labelforge_raw_content": _TEXT,
    }


def _render(obj: dict) -> Image.Image:
    label = _make_label_62x29()

    # Pre-load the font so get_font_path resolves without the full app startup.
    from labelforge.render.fonts import FontInfo, _font_cache

    font_info = FontInfo(
        name="DejaVuSans-Bold",
        path=_FONT_PATH,
        family="DejaVu Sans",
        style="Bold",
    )
    original_cache = list(_font_cache)
    _font_cache.clear()
    _font_cache.append(font_info)

    try:
        with patch("labelforge.render.template.get_label", return_value=label):
            from labelforge.render.template import render_template

            return render_template(_make_template({"objects": [obj]}), {})
    finally:
        _font_cache.clear()
        _font_cache.extend(original_cache)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_center_origin_matches_left_origin_pixel_identical():
    """Center-origin element renders at the same position as an equivalent left-origin element."""
    img_center = _render(_center_origin_obj())
    img_left = _render(_left_origin_obj())

    assert img_center.size == img_left.size

    # Compare raw pixel bytes — must be identical.
    assert img_center.tobytes() == img_left.tobytes(), (
        "Center-origin and left-origin text elements at equivalent positions "
        "should produce pixel-identical renders, but they differ."
    )


def test_center_origin_element_is_not_blank():
    """Sanity check: the rendered image has at least some inked pixels (font loaded correctly)."""
    img = _render(_center_origin_obj())
    assert any(p < 255 for p in img.tobytes()), (
        "Rendered image has no inked pixels — font may not have loaded correctly."
    )


def test_left_origin_is_default_no_op():
    """An element with no origin keys should behave the same as explicit left/top origins."""
    obj_no_origin = _left_origin_obj()
    del obj_no_origin["originX"]
    del obj_no_origin["originY"]

    img_explicit = _render(_left_origin_obj())
    img_default = _render(obj_no_origin)

    assert img_explicit.tobytes() == img_default.tobytes(), (
        "Default (no originX/Y) should behave identically to explicit left/top origins."
    )
