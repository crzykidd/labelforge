"""Tests for capped text wrapping (`labelforge_wrap_max_lines`) and the
orientation-aware wrap target width.

Wrap shipped in v0.1.8 as an uncapped on/off checkbox (see
prompts/done/2026-09-19-text-wrap-option.md and docs/decisions.md). This caps it
at a chosen number of lines, truncating with a visible `detect_overflow` warning
when content needs more lines than the cap, and fixes the wrap target width to
follow the axis text actually runs along instead of always clamping to the
print-head width.

Font fixture pattern follows test_render_orientation.py.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from labelforge.models import LabelEntry, Template

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

pytestmark = pytest.mark.skipif(
    not os.path.exists(_FONT_PATH),
    reason=f"DejaVuSans-Bold not found at {_FONT_PATH}; skipping wrap-cap render tests",
)

# Measured (verified, see prompts/done/2026-09-19-wrap-max-lines.md): 62mm
# continuous, DejaVuSans-Bold 90pt, box 650 wide, unrotated, uncapped wrap:
#   "Master Bedroom"                              -> 2 lines   canvas 696x217
#   "Upstairs Guest Bedroom Closet"                -> 4 lines   canvas 696x393
#   "The Big Upstairs Guest Bedroom Storage Closet" -> 6 lines  canvas 696x569
#   "Supercalifragilistic" (one word too wide)     -> 1 line, not split
_BOX_W = 650
_FONT_SIZE = 90


def _continuous_label() -> LabelEntry:
    return LabelEntry(
        id="62",
        display_name="62mm",
        dots_printable=(696, 0),
        tape_size=(62, 0),
        form_factor=2,
        color=0,
        supported=True,
    )


def _make_template(canvas_json: dict, *, orientation: str = "standard") -> Template:
    return Template(
        name="wrap-cap-test",
        display_name="Wrap Cap Test",
        label_media="62",
        canvas_json=canvas_json,
        field_schema=[],
        orientation=orientation,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def _text_obj(
    text: str,
    *,
    box_w: int = _BOX_W,
    wrap: bool = True,
    max_lines: int | None = None,
    angle: float = 0,
) -> dict:
    obj: dict = {
        "type": "IText",
        "text": text,
        "left": 20,
        "top": 20,
        "width": box_w,
        "height": 800,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "angle": angle,
        "originX": "left",
        "originY": "top",
        "fontFamily": "DejaVuSans-Bold",
        "fontSize": _FONT_SIZE,
        "fontWeight": "bold",
        "fontStyle": "",
        "textAlign": "left",
        "fill": "#000000",
        "labelforge_raw_content": text,
    }
    if wrap:
        obj["labelforge_wrap"] = True
    if max_lines is not None:
        obj["labelforge_wrap_max_lines"] = max_lines
    return obj


@pytest.fixture(autouse=True)
def _dejavu_font():
    from labelforge.render.fonts import FontInfo, _font_cache

    font_info = FontInfo(
        name="DejaVuSans-Bold", path=_FONT_PATH, family="DejaVu Sans", style="Bold"
    )
    original_cache = list(_font_cache)
    _font_cache.clear()
    _font_cache.append(font_info)
    try:
        yield
    finally:
        _font_cache.clear()
        _font_cache.extend(original_cache)


_TEXT_2_LINES = "Master Bedroom"
_TEXT_4_LINES = "Upstairs Guest Bedroom Closet"
_TEXT_6_LINES = "The Big Upstairs Guest Bedroom Storage Closet"
_TEXT_1_WORD_TOO_WIDE = "Supercalifragilistic"


# ── 1. Baseline measurements pinned (uncapped, byte-for-byte the v0.1.8 path) ─


@pytest.mark.parametrize(
    ("text", "expected_lines", "expected_canvas"),
    [
        (_TEXT_2_LINES, 2, (696, 217)),
        (_TEXT_4_LINES, 4, (696, 393)),
        (_TEXT_6_LINES, 6, (696, 569)),
        (_TEXT_1_WORD_TOO_WIDE, 1, (696, 147)),
    ],
)
def test_uncapped_wrap_matches_measured_baseline(text, expected_lines, expected_canvas):
    from labelforge.render.fonts import get_font_path
    from labelforge.render.template import _wrap_text
    from PIL import ImageFont

    font_path = get_font_path("DejaVuSans-Bold")
    font = ImageFont.truetype(font_path, _FONT_SIZE)
    wrapped, truncated = _wrap_text(text, font, _BOX_W)
    assert wrapped.count("\n") + 1 == expected_lines
    assert truncated is False

    label = _continuous_label()
    tmpl = _make_template({"objects": [_text_obj(text)]})
    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import render_template

        img = render_template(tmpl, {})
    assert img.size == expected_canvas


# ── 2. Cap truncates and flags overflow ──────────────────────────────────────


def test_cap_of_2_on_content_needing_4_lines_truncates_and_flags_overflow():
    """Uncapped, this text is 4 lines / 393 canvas height (measured baseline
    above); capped at 2, exactly 2 lines must render — pinned by comparing
    against a template whose *source text* only ever needed 2 lines."""
    label = _continuous_label()
    tmpl_capped = _make_template({"objects": [_text_obj(_TEXT_4_LINES, max_lines=2)]})
    tmpl_2line_reference = _make_template({"objects": [_text_obj(_TEXT_2_LINES)]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow, render_template

        img_capped = render_template(tmpl_capped, {})
        img_reference = render_template(tmpl_2line_reference, {})
        overflow = detect_overflow(tmpl_capped, "62", {})

    assert img_capped.size[1] < 393, (
        f"expected a shorter canvas than the uncapped 4-line render: {img_capped.size}"
    )
    # Exactly 2 lines render: same line count as a naturally-2-line text, so the
    # canvas height (driven by rendered text height) matches — not 3 or 4.
    assert img_capped.size[1] == img_reference.size[1]
    assert overflow is True


def test_cap_of_2_on_content_fitting_in_2_is_byte_identical_to_uncapped():
    """Regression bar: a cap that isn't hit changes nothing."""
    label = _continuous_label()
    tmpl_capped = _make_template({"objects": [_text_obj(_TEXT_2_LINES, max_lines=2)]})
    tmpl_uncapped = _make_template({"objects": [_text_obj(_TEXT_2_LINES)]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow, render_template

        img_capped = render_template(tmpl_capped, {})
        img_uncapped = render_template(tmpl_uncapped, {})
        overflow_capped = detect_overflow(tmpl_capped, "62", {})

    assert img_capped.tobytes() == img_uncapped.tobytes()
    assert img_capped.size == img_uncapped.size == (696, 217)
    assert overflow_capped is False


def test_cap_of_5_on_content_needing_6_lines_truncates_and_flags_overflow():
    label = _continuous_label()
    tmpl = _make_template({"objects": [_text_obj(_TEXT_6_LINES, max_lines=5)]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow, render_template

        img = render_template(tmpl, {})
        overflow = detect_overflow(tmpl, "62", {})

    assert img.size[1] < 569, (
        f"expected a shorter canvas than the uncapped 6-line render: {img.size}"
    )
    assert overflow is True


# ── 3. v0.1.8 compatibility: wrap on, no cap key at all ──────────────────────


def test_v018_template_wrap_true_no_max_lines_key_wraps_unlimited_byte_identical():
    """A template saved before this feature has `labelforge_wrap: true` and no
    `labelforge_wrap_max_lines` key at all (not even 0) — must render exactly as
    it did in v0.1.8: unlimited wrap, no truncation, no overflow from the cap."""
    label = _continuous_label()
    legacy_obj = _text_obj(_TEXT_6_LINES)
    assert "labelforge_wrap_max_lines" not in legacy_obj

    explicit_uncapped_obj = _text_obj(_TEXT_6_LINES, max_lines=0)

    tmpl_legacy = _make_template({"objects": [legacy_obj]})
    tmpl_explicit = _make_template({"objects": [explicit_uncapped_obj]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow, render_template

        img_legacy = render_template(tmpl_legacy, {})
        img_explicit = render_template(tmpl_explicit, {})
        overflow_legacy = detect_overflow(tmpl_legacy, "62", {})

    assert img_legacy.tobytes() == img_explicit.tobytes()
    assert img_legacy.size == (696, 569)  # the measured 6-line baseline, unchanged
    assert overflow_legacy is False


# ── 4. Orientation-aware wrap width ──────────────────────────────────────────


def test_rotated_template_wrap_width_follows_free_axis_not_head_width():
    """The concrete, observable bug: an element on a rotated template with a
    box wide enough to hold its content on the free (length) axis must not be
    force-wrapped to the fixed 696-dot head width — doing so forces so many
    short lines that their stacked height overflows the *head-width* axis
    (the transposed y-axis in a rotated design), which is a false overflow
    that the correctly-unclamped wrap avoids entirely.

    Mechanism, pinned directly (see the two `_render_text_element` calls
    below): at the old `min(box_w, head_width)` clamp this text wraps to many
    lines whose combined height is 793 dots — already past the 696-dot head
    width before any element/canvas geometry is even considered. Using the
    element's own (much wider) box as the free-axis target instead wraps it
    to a handful of lines totalling 177 dots, comfortably inside 696.
    """
    from labelforge.render.template import _render_text_element

    text = (
        "The Big Old Rustic Upstairs Guest Bedroom Storage Closet Room Area Section Cabinet Shelf"
    )
    obj = _text_obj(text, box_w=3000)

    sub_clamped, _ = _render_text_element(dict(obj), {}, 3000, 1500, head_width=696, rotated=False)
    sub_free, _ = _render_text_element(dict(obj), {}, 3000, 1500, head_width=696, rotated=True)
    assert sub_clamped.height > 696, (
        f"expected the head-width-clamped wrap to overflow 696 vertically: {sub_clamped.height}"
    )
    assert sub_free.height < 696, (
        f"expected the free-axis wrap to comfortably fit under 696: {sub_free.height}"
    )

    # End-to-end: on an actual rotated template, this must NOT be flagged as
    # overflow — the pre-fix clamp would have reported True here.
    label = _continuous_label()
    tmpl_rotated = _make_template({"objects": [dict(obj)]}, orientation="rotated")
    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow

        overflow = detect_overflow(tmpl_rotated, "62", {})
    assert overflow is False, (
        "rotated wrap should use the free-axis target, not the head-width clamp"
    )


def test_element_angle_90_in_rotated_template_maps_back_onto_head_axis():
    """The element's own angle composes with template orientation again: a 90°
    element inside a *rotated* template puts box_w's axis back onto the
    head-bound axis, so the head_width clamp should apply once more."""
    from labelforge.render.template import _wrap_target_width

    # angle=0, standard: box_w axis == head axis -> clamped.
    assert _wrap_target_width(1000, 696, 0, rotated=False) == 696
    # angle=0, rotated: box_w axis == free axis -> unclamped.
    assert _wrap_target_width(1000, 696, 0, rotated=True) == 1000
    # angle=90, standard: box_w axis == free axis -> unclamped.
    assert _wrap_target_width(1000, 696, 90, rotated=False) == 1000
    # angle=90, rotated: box_w axis == head axis again -> clamped.
    assert _wrap_target_width(1000, 696, 90, rotated=True) == 696


def test_wrap_target_width_no_head_width_returns_box_w_unclamped():
    from labelforge.render.template import _wrap_target_width

    assert _wrap_target_width(1000, None, 0, rotated=False) == 1000
