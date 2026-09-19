"""Tests for element-level rotation (the `angle` property on a canvas object).

Rotating an element (the editor's "Rotate 90°" button, or the free rotate
handle) must be reflected in every place the renderer reasons about extent:
continuous auto-length must grow to fit the rotated bounding box, not the
unrotated one, and `detect_overflow` must flag a rotated element that
overhangs a fixed die-cut label. `_paste_onto` must also pivot the rotated
sub-image about the element's Fabric origin (its anchor point), not always
its own centre, so left/top-origin elements (QR, barcode) land where the
editor shows them.

See docs/decisions.md for the pivot-point derivation and
prompts/done/2026-09-19-rotated-element-extent.md for the operator report and
measured evidence this fixes.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from labelforge.models import LabelEntry, Template
from PIL import Image, ImageDraw

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

pytestmark = pytest.mark.skipif(
    not os.path.exists(_FONT_PATH),
    reason=f"DejaVuSans-Bold not found at {_FONT_PATH}; skipping rotation render tests",
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _continuous_label() -> LabelEntry:
    return LabelEntry(
        id="62",
        display_name="62mm",
        dots_printable=(696, 0),
        tape_size=(62, 0),
        form_factor=2,  # continuous
        color=0,
        supported=True,
    )


def _die_cut_label() -> LabelEntry:
    return LabelEntry(
        id="62x29",
        display_name="62x29",
        dots_printable=(696, 271),
        tape_size=(62, 29),
        form_factor=1,  # die-cut
        color=0,
        supported=True,
    )


def _make_template(canvas_json: dict, label_media: str) -> Template:
    return Template(
        name="rotation-test",
        display_name="Rotation Test",
        label_media=label_media,
        canvas_json=canvas_json,
        field_schema=[],
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def _text_obj(*, left: int, top: int, angle: float, width: int = 400, height: int = 60) -> dict:
    return {
        "type": "IText",
        "text": "Spool 1234",
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "angle": angle,
        "fontFamily": "DejaVuSans-Bold",
        "fontSize": 48,
        "fontWeight": "bold",
        "fontStyle": "",
        "textAlign": "left",
        "fill": "#000000",
        "labelforge_raw_content": "Spool 1234",
    }


def _rect_obj(*, left: int, top: int, width: int, height: int, angle: float = 0) -> dict:
    return {
        "type": "Rect",
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "angle": angle,
        "strokeWidth": 1,
        "fill": "#000000",
        "stroke": "#000000",
    }


def _render(canvas_json: dict, label: LabelEntry) -> Image.Image:
    from labelforge.render.fonts import FontInfo, _font_cache

    font_info = FontInfo(
        name="DejaVuSans-Bold", path=_FONT_PATH, family="DejaVu Sans", style="Bold"
    )
    original_cache = list(_font_cache)
    _font_cache.clear()
    _font_cache.append(font_info)
    try:
        with patch("labelforge.render.template.get_label", return_value=label):
            from labelforge.render.template import render_template

            return render_template(_make_template(canvas_json, label.id), {}).convert("L")
    finally:
        _font_cache.clear()
        _font_cache.extend(original_cache)


def _ink_bbox(img: Image.Image) -> tuple[int, int, int, int] | None:
    return img.point(lambda p: 255 if p < 128 else 0).getbbox()


# ── 1. Continuous auto-length follows the rotated extent, not clipped ───────


def test_continuous_rotated_text_grows_and_is_not_clipped():
    label = _continuous_label()

    img_flat = _render({"objects": [_text_obj(left=220, top=50, angle=0)]}, label)
    img_rotated = _render({"objects": [_text_obj(left=220, top=50, angle=90)]}, label)

    assert img_rotated.size[0] == img_flat.size[0] == 696

    bbox = _ink_bbox(img_rotated)
    assert bbox is not None, "rotated text produced no visible ink at all"
    _, y0, _, y1 = bbox
    blank_bottom = img_rotated.size[1] - y1

    # The old bug: canvas length never grew for rotation, so a 90°-rotated
    # element (now ~400px tall instead of ~60px) ran straight off the bottom.
    assert img_rotated.size[1] > img_flat.size[1], (
        "auto-length did not grow for a 90°-rotated element"
    )
    assert blank_bottom > 0, "rotated text is clipped at the bottom of the label"
    # And it should start near the top, not after a huge blank gap (the
    # operator's "huge blank spot" complaint).
    assert y0 < img_rotated.size[1] // 4, (
        f"rotated ink starts too far down (y0={y0}, canvas height={img_rotated.size[1]})"
    )


def test_continuous_arbitrary_angle_is_not_clipped():
    """The helper must not be special-cased to multiples of 90."""
    label = _continuous_label()
    img = _render({"objects": [_text_obj(left=220, top=50, angle=37)]}, label)

    bbox = _ink_bbox(img)
    assert bbox is not None
    _, y0, _, y1 = bbox
    assert y1 < img.size[1], "37°-rotated text touches the bottom edge (clipped)"
    assert img.size[1] - y1 > 0
    assert y0 >= 0


# ── 2. detect_overflow accounts for the rotated footprint ───────────────────


def test_detect_overflow_true_for_overhanging_rotated_element():
    from labelforge.render.template import detect_overflow

    label = _die_cut_label()
    # Fine unrotated (300x20 near the top-left), but Fabric rotates a left/top-
    # origin element about that corner: swinging 90° clockwise turns the 300px
    # width into a 300px *vertical* run starting at top=200, well past the
    # label's 271px length.
    canvas_json = {"objects": [_rect_obj(left=10, top=200, width=300, height=20, angle=90)]}
    tmpl = _make_template(canvas_json, label.id)

    with patch("labelforge.render.template.get_label", return_value=label):
        assert detect_overflow(tmpl, label.id) is True


def test_detect_overflow_false_for_fitting_rotated_element():
    from labelforge.render.template import detect_overflow

    label = _die_cut_label()
    canvas_json = {"objects": [_rect_obj(left=10, top=10, width=50, height=20, angle=90)]}
    tmpl = _make_template(canvas_json, label.id)

    with patch("labelforge.render.template.get_label", return_value=label):
        assert detect_overflow(tmpl, label.id) is False


# ── 3. Regression guard: angle == 0 output is untouched ─────────────────────


def test_unrotated_rect_byte_identical_to_independent_fixture():
    """A plain, unrotated rect must render pixel-identically to a fixture built
    with bare PIL primitives (not via any of the code paths this change touches).
    This pins angle == 0 output regardless of how the rotation-aware helpers evolve.
    """
    label = _die_cut_label()
    left, top, w, h = 40, 30, 90, 50
    img = _render({"objects": [_rect_obj(left=left, top=top, width=w, height=h)]}, label)

    expected = Image.new("L", (696, 271), 255)
    ImageDraw.Draw(expected).rectangle([left, top, left + w - 1, top + h - 1], fill=0)

    assert img.tobytes() == expected.tobytes()


def test_unrotated_continuous_length_matches_independent_computation():
    """Pin the angle == 0 auto-length formula: top + rendered-height + padding,
    computed here independently of the (rewritten) extent loop by calling the
    text-rendering primitive directly."""
    from labelforge.render.fonts import FontInfo, _font_cache
    from labelforge.render.template import _PADDING, _render_text_element

    label = _continuous_label()
    left, top = 220, 50
    obj = _text_obj(left=left, top=top, angle=0)

    font_info = FontInfo(
        name="DejaVuSans-Bold", path=_FONT_PATH, family="DejaVu Sans", style="Bold"
    )
    original_cache = list(_font_cache)
    _font_cache.clear()
    _font_cache.append(font_info)
    try:
        sub = _render_text_element(obj, {}, obj["width"], obj["height"])
    finally:
        _font_cache.clear()
        _font_cache.extend(original_cache)

    expected_height = top + sub.height + _PADDING
    img = _render({"objects": [obj]}, label)

    assert img.size == (696, expected_height)
