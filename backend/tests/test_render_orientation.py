"""Tests for template orientation ("standard" vs "rotated").

Rotated orientation designs on a canvas transposed to the label's length axis
and rotates the finished render 90° once at the end (see render_template's
docstring for why 90, not 270). These tests check the geometry invariants
that rotation must preserve, not per-element rendering (which is untouched).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from labelforge.models import LabelEntry, Template
from labelforge.render.template import _PADDING

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_label(
    id_: str,
    *,
    form_factor: int,
    dots_printable: tuple[int, int],
    tape_size: tuple[int, int],
    color: int = 0,
) -> LabelEntry:
    return LabelEntry(
        id=id_,
        display_name=id_,
        dots_printable=dots_printable,
        tape_size=tape_size,
        form_factor=form_factor,
        color=color,
        supported=True,
    )


def _make_template(
    canvas_json: dict,
    *,
    label_media: str = "62x29",
    orientation: str | None = "standard",
) -> Template:
    kwargs = dict(
        name="orientation-test",
        display_name="Orientation Test",
        label_media=label_media,
        canvas_json=canvas_json,
        field_schema=[],
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    if orientation is not None:
        kwargs["orientation"] = orientation
    return Template(**kwargs)


def _rect(left: int, top: int, width: int, height: int) -> dict:
    return {
        "type": "Rect",
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "fill": "#000000",
    }


# ── 1. Die-cut: rotated matches standard dimensions, axes swapped internally ──


def test_rotated_die_cut_matches_standard_dimensions():
    label = _make_label("62x100", form_factor=1, dots_printable=(696, 1109), tape_size=(62, 100))
    canvas_json = {"objects": [_rect(10, 10, 50, 50)]}

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62x100": label}.get(id_)

    tmpl_standard = _make_template(canvas_json, label_media="62x100", orientation="standard")
    tmpl_rotated = _make_template(canvas_json, label_media="62x100", orientation="rotated")

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import render_template

        img_standard = render_template(tmpl_standard, {})
        img_rotated = render_template(tmpl_rotated, {})

    assert img_standard.size == (696, 1109)
    assert img_rotated.size == img_standard.size, (
        "A die-cut's physical dimensions don't change with orientation — only "
        "which axis the content is authored against does."
    )


# ── 2. Continuous: rotated auto-length grows along the correct (final) axis ──


def test_rotated_continuous_length_grows_along_correct_axis():
    label = _make_label("62", form_factor=2, dots_printable=(696, 0), tape_size=(62, 0))

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62": label}.get(id_)

    short_canvas = {"objects": [_rect(10, 10, 50, 50)]}
    long_canvas = {"objects": [_rect(500, 10, 50, 50)]}

    tmpl_short = _make_template(short_canvas, label_media="62", orientation="rotated")
    tmpl_long = _make_template(long_canvas, label_media="62", orientation="rotated")

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import render_template

        img_short = render_template(tmpl_short, {})
        img_long = render_template(tmpl_long, {})

    # Final width is always the fixed head-width axis, regardless of content.
    assert img_short.size[0] == 696
    assert img_long.size[0] == 696
    # Final height is the content-driven length axis — it must grow with the
    # rightmost element extent in the (transposed) design, mirroring how the
    # standard orientation grows with the bottommost extent.
    assert img_long.size[1] > img_short.size[1]
    assert img_long.size[1] == 500 + 50 + _PADDING


def test_rotated_continuous_length_grows_with_rendered_text_width():
    """The fiddly part: for text, use the PIL-measured width (not the nominal
    box width) when computing the rotated auto-length extent — mirroring how
    the standard orientation uses PIL-measured height."""
    if not os.path.exists(_FONT_PATH):
        pytest.skip(f"DejaVuSans-Bold not found at {_FONT_PATH}")

    from labelforge.render.fonts import FontInfo, _font_cache

    font_info = FontInfo(
        name="DejaVuSans-Bold", path=_FONT_PATH, family="DejaVu Sans", style="Bold"
    )
    original_cache = list(_font_cache)
    _font_cache.clear()
    _font_cache.append(font_info)

    label = _make_label("62", form_factor=2, dots_printable=(696, 0), tape_size=(62, 0))

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62": label}.get(id_)

    # A nominal box far narrower than the text it must render — the rendered
    # width overflows the declared box, so the extent calc must use the actual
    # rendered width, not the box's.
    text_obj = {
        "type": "IText",
        "text": "A much longer line of text than the box declares",
        "left": 10,
        "top": 10,
        "width": 20,
        "height": 30,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "angle": 0,
        "fontFamily": "DejaVuSans-Bold",
        "fontSize": 20,
        "fontWeight": "bold",
        "fontStyle": "",
        "textAlign": "left",
        "fill": "#000000",
        "labelforge_raw_content": "A much longer line of text than the box declares",
    }

    tmpl = _make_template({"objects": [text_obj]}, label_media="62", orientation="rotated")

    try:
        with patch("labelforge.render.template.get_label", side_effect=_get_label):
            from labelforge.render.template import render_template

            img = render_template(tmpl, {})
    finally:
        _font_cache.clear()
        _font_cache.extend(original_cache)

    # If the extent calc had used the 20px nominal box width instead of the
    # rendered text width, the final length would be far too short to contain
    # the actual glyphs and this would fail.
    assert img.size[1] > 20 + 10 + _PADDING


# ── 3. Print-head invariant: rotated output width == dots_printable[0] ───────


@pytest.mark.parametrize(
    ("form_factor", "dots_printable", "tape_size", "media_id"),
    [
        (2, (696, 0), (62, 0), "62"),
        (1, (696, 271), (62, 29), "62x29"),
    ],
)
def test_rotated_output_width_equals_print_head_width(
    form_factor, dots_printable, tape_size, media_id
):
    label = _make_label(
        media_id, form_factor=form_factor, dots_printable=dots_printable, tape_size=tape_size
    )

    def _get_label(id_: str) -> LabelEntry | None:
        return {media_id: label}.get(id_)

    canvas_json = {"objects": [_rect(5, 5, 20, 20)]}
    tmpl = _make_template(canvas_json, label_media=media_id, orientation="rotated")

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import render_template

        img = render_template(tmpl, {})

    assert img.size[0] == dots_printable[0]


# ── 4. Regression guard: no stored orientation defaults to standard ─────────


def test_missing_orientation_defaults_to_standard_and_renders_unchanged():
    label = _make_label("62x29", form_factor=1, dots_printable=(696, 271), tape_size=(62, 29))

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62x29": label}.get(id_)

    canvas_json = {"objects": [_rect(10, 10, 40, 40)]}
    tmpl_no_orientation = _make_template(canvas_json, label_media="62x29", orientation=None)
    tmpl_explicit_standard = _make_template(
        canvas_json, label_media="62x29", orientation="standard"
    )

    assert tmpl_no_orientation.orientation == "standard"

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import render_template

        img_default = render_template(tmpl_no_orientation, {})
        img_explicit = render_template(tmpl_explicit_standard, {})

    assert img_default.size == (696, 271)
    assert img_default.tobytes() == img_explicit.tobytes()


# ── 7. Rotation direction: the design's top edge must land on the label's left ─


def test_rotated_direction_design_top_lands_on_label_left():
    """The design's top edge must end up on the printed label's LEFT edge.

    This pins the rotation *direction*, which the dimension tests above cannot
    catch: 90° and 270° produce identical output sizes but differ by 180°, so a
    flipped constant renders every rotated label upside down. Reported by the
    operator against the original 270°.
    """
    label = _make_label("62x29", form_factor=1, dots_printable=(696, 271), tape_size=(62, 29))
    # Design canvas for a rotated 62x29 is 271 wide x 696 tall. Band across its top.
    canvas_json = {"objects": [_rect(0, 0, 271, 60)]}
    tmpl = _make_template(canvas_json, orientation="rotated")

    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import render_template

        img = render_template(tmpl, {}).convert("L")

    w, h = img.size
    assert (w, h) == (696, 271)
    px = img.load()

    def dark_fraction(x0: int, x1: int) -> float:
        total = dark = 0
        for x in range(x0, x1):
            for y in range(0, h, 4):
                total += 1
                if px[x, y] < 128:
                    dark += 1
        return dark / max(total, 1)

    left = dark_fraction(0, w // 5)
    right = dark_fraction(w - w // 5, w)
    assert left > 0.2, f"expected the design's top band on the label's left edge, got {left:.2f}"
    assert right < 0.05, f"nothing should be on the right edge, got {right:.2f}"
