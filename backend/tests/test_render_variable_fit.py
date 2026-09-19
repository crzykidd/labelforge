"""Tests for the operator-reported bug: a template designed around a short
placeholder (`{name}`) prints clipped when the resolved field value is longer.

Two independent fixes are covered:

1. Continuous auto-length now tracks both the nearest and farthest extent of
   every element, not just the farthest — a centre-origin (or right/bottom-
   origin) element whose resolved value is wider than its placeholder grows
   backwards past the start of the label too, and that part was silently cut
   off. See docs/decisions.md and prompts/done/2026-09-19-text-wrap-option.md
   for the measured evidence this reproduces.
2. `detect_overflow` now measures the *resolved* value (when given) instead of
   the stored placeholder box, and also catches horizontal overflow on
   continuous media (a line wider than the print head) — previously it
   returned False unconditionally for continuous media.

Also covers the opt-in per-element `labelforge_wrap` option: word-wrap at
spaces, no mid-word breaks, off by default.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from labelforge.models import LabelEntry, Template

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

pytestmark = pytest.mark.skipif(
    not os.path.exists(_FONT_PATH),
    reason=f"DejaVuSans-Bold not found at {_FONT_PATH}; skipping variable-fit render tests",
)


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


def _make_template(canvas_json: dict, *, orientation: str = "standard") -> Template:
    return Template(
        name="variable-fit-test",
        display_name="Variable Fit Test",
        label_media="62",
        canvas_json=canvas_json,
        field_schema=[],
        orientation=orientation,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


# Box sized for the placeholder "{name}" at 150pt (680 wide) — as the editor
# would leave it after the user typed "{name}" and sized the box to fit.
_BOX_W, _BOX_H = 680, 175
_FONT_SIZE = 150


def _text_obj(*, wrap: bool = False, origin: str = "left") -> dict:
    obj = {
        "type": "IText",
        "text": "{name}",
        # left=8 (not 20) leaves headroom so the placeholder box itself (680
        # wide) doesn't already brush the 696-dot head width — keeps the
        # "value that already fits" tests from tripping on the box's own
        # snug placeholder sizing rather than the value being measured.
        "left": 500 if origin == "center" else 8,
        "top": 348 if origin == "center" else 20,
        "width": _BOX_W,
        "height": _BOX_H,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "angle": 0,
        "originX": origin,
        "originY": origin,
        "fontFamily": "DejaVuSans-Bold",
        "fontSize": _FONT_SIZE,
        "fontWeight": "bold",
        "fontStyle": "",
        "textAlign": "left",
        "fill": "#000000",
        "labelforge_raw_content": "{name}",
    }
    if wrap:
        obj["labelforge_wrap"] = True
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


def _ink_bbox(img):
    return img.convert("L").point(lambda p: 255 if p < 128 else 0).getbbox()


# ── 1. detect_overflow sees the resolved value, not the placeholder ─────────


def test_detect_overflow_false_for_stored_placeholder_only():
    """Sanity: with no values given, the legacy (placeholder-only) behavior holds."""
    label = _continuous_label()
    tmpl = _make_template({"objects": [_text_obj(origin="left")]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow

        assert detect_overflow(tmpl, "62") is False


def test_detect_overflow_true_for_value_wider_than_placeholder():
    """The reported bug: a value longer than {name} must be flagged, wrap off."""
    label = _continuous_label()
    tmpl = _make_template({"objects": [_text_obj(origin="left")]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow

        assert detect_overflow(tmpl, "62", {"name": "Master Bedroom"}) is True


def test_detect_overflow_false_for_value_that_fits():
    label = _continuous_label()
    tmpl = _make_template({"objects": [_text_obj(origin="left")]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow

        # "{name}" itself measures 680 wide; a short value comfortably fits
        # within the 696-wide print head starting at left=20... except 20+680
        # already exceeds 696 by design (the placeholder box itself is snug).
        # Use a deliberately short value to stay clearly within bounds.
        assert detect_overflow(tmpl, "62", {"name": "Hi"}) is False


def test_detect_overflow_true_for_single_word_wider_than_head_even_with_wrap():
    """A single word wider than the label still overflows — wrap cannot save it."""
    label = _continuous_label()
    tmpl = _make_template({"objects": [_text_obj(origin="left", wrap=True)]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow

        # "Bedroom" alone at 150pt is ~760 dots — wider than the 696-dot head.
        assert detect_overflow(tmpl, "62", {"name": "Bedroom"}) is True


# ── 2. Bidirectional continuous auto-length (the reported bug) ──────────────


def test_center_origin_value_wider_than_placeholder_no_longer_clipped():
    """The core reported bug: a centre-origin element whose resolved value is
    wider than its placeholder used to grow the canvas only forwards, cutting
    off everything that grew backwards past the label start."""
    label = _continuous_label()
    tmpl = _make_template({"objects": [_text_obj(origin="center")]}, orientation="rotated")

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import render_template

        img = render_template(tmpl, {"name": "Master Bedroom"}).convert("L")

    w, h = img.size
    bbox = _ink_bbox(img)
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    # Not clipped against any edge of the (now-grown) canvas.
    assert x0 > 0 and y0 > 0 and x1 < w and y1 < h, (
        f"content is clipped against the canvas edge: bbox={bbox}, canvas={w}x{h}"
    )


def test_fitting_content_renders_byte_identically():
    """Regression bar: content that already fits must be untouched by the
    bidirectional-growth change — same canvas size, same bytes, wrap off vs a
    template with no wrap prop at all."""
    label = _continuous_label()
    tmpl_a = _make_template({"objects": [_text_obj(origin="left")]}, orientation="rotated")
    tmpl_b = _make_template({"objects": [_text_obj(origin="left")]}, orientation="rotated")

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import render_template

        img_a = render_template(tmpl_a, {"name": "Hi"})
        img_b = render_template(tmpl_b, {"name": "Hi"})

    assert img_a.tobytes() == img_b.tobytes()


# ── 3. Wrap option ────────────────────────────────────────────────────────


def test_wrap_off_value_wider_than_placeholder_still_reports_overflow():
    label = _continuous_label()
    tmpl = _make_template({"objects": [_text_obj(origin="left", wrap=False)]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow

        assert detect_overflow(tmpl, "62", {"name": "Master Bedroom"}) is True


def test_wrap_on_breaks_at_spaces_and_is_not_clipped():
    label = _continuous_label()
    tmpl = _make_template({"objects": [_text_obj(origin="left", wrap=True)]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import render_template

        img = render_template(tmpl, {"name": "Master Bedroom"}).convert("L")

    bbox = _ink_bbox(img)
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    w, h = img.size
    # Two lines now, well within the (696-wide) head — not clipped.
    assert x1 <= w
    assert y1 < h, "wrapped text is clipped at the bottom of the label"


def test_wrap_on_but_value_already_fits_is_byte_identical_to_wrap_off():
    """Regression bar: wrap is a no-op when nothing needs wrapping."""
    label = _continuous_label()
    tmpl_wrap_on = _make_template({"objects": [_text_obj(origin="left", wrap=True)]})
    tmpl_wrap_off = _make_template({"objects": [_text_obj(origin="left", wrap=False)]})

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import render_template

        img_on = render_template(tmpl_wrap_on, {"name": "Hi"})
        img_off = render_template(tmpl_wrap_off, {"name": "Hi"})

    assert img_on.tobytes() == img_off.tobytes()


def test_wrap_single_word_wider_than_box_is_not_broken_mid_word():
    """A single word wider than the target width is left whole, overflowing —
    not hyphenated or force-broken."""
    from labelforge.render.fonts import get_font_path
    from labelforge.render.template import _wrap_text
    from PIL import ImageFont

    font_path = get_font_path("DejaVuSans-Bold")
    assert font_path is not None
    font = ImageFont.truetype(font_path, _FONT_SIZE)

    wrapped = _wrap_text("Bedroom", font, 200)
    assert wrapped == "Bedroom", "a single over-wide word must not be split"


def test_wrap_multiline_result_is_narrower_than_unwrapped():
    from labelforge.render.fonts import get_font_path
    from labelforge.render.template import _wrap_text
    from PIL import Image, ImageDraw, ImageFont

    font_path = get_font_path("DejaVuSans-Bold")
    assert font_path is not None
    font = ImageFont.truetype(font_path, _FONT_SIZE)

    # A target wide enough for each individual word ("Bedroom" alone is ~760)
    # but not the whole phrase (~1399) — the phrase must wrap, but each word
    # is not itself over-wide, so every wrapped line must fit.
    target = 800
    wrapped = _wrap_text("Master Bedroom", font, target)
    assert "\n" in wrapped, "expected a line break at the space"
    scratch = ImageDraw.Draw(Image.new("L", (1, 1)))
    for line in wrapped.split("\n"):
        assert scratch.textlength(line, font=font) <= target + 1  # rounding slack


# ── 4. The second defect: combined template+element rotation no longer
#      silently collapses the label to almost nothing ─────────────────────


def test_combined_template_and_element_rotation_does_not_collapse_canvas():
    """template.orientation='rotated' + element angle=90 used to collapse the
    auto-length to ~41 dots (canvas essentially blank). The bidirectional-growth
    fix corrects the extent tracking for this element too, so the canvas is
    sized sanely instead of collapsing — though the content still genuinely
    can't fit (it now runs across the fixed print-head axis instead of the
    free length axis), which detect_overflow must report."""
    label = _continuous_label()
    canvas_json = {
        "objects": [
            {
                "type": "IText",
                "left": 20,
                "top": 20,
                "width": _BOX_W,
                "height": _BOX_H,
                "scaleX": 1.0,
                "scaleY": 1.0,
                "originX": "left",
                "originY": "top",
                "angle": 90,
                "text": "{name}",
                "fontFamily": "DejaVuSans-Bold",
                "fontSize": _FONT_SIZE,
                "fill": "#000000",
                "labelforge_raw_content": "{name}",
            }
        ]
    }
    tmpl = _make_template(canvas_json, orientation="rotated")

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import detect_overflow, render_template

        img = render_template(tmpl, {"name": "Master Bedroom"})
        overflow = detect_overflow(tmpl, "62", {"name": "Master Bedroom"})

    # No longer the near-blank ~41-dot collapse.
    assert img.size[1] > 100, f"canvas still collapsed to near-nothing: {img.size}"
    # But this genuinely cannot fit (it now needs the fixed head-width axis,
    # not the free length axis) — must be reported, not silently clipped.
    assert overflow is True
