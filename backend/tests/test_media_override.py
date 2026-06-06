"""Tests for print-time media override: render on a non-stored media, reprint
binds to the history row's media, and overflow detection on die-cut targets.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from labelforge.models import LabelEntry, Template
from PIL import Image

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_label(
    id_: str,
    *,
    form_factor: int = 2,  # 2 = continuous
    dots_printable: tuple[int, int] = (696, 0),
    tape_size: tuple[int, int] = (62, 0),
    color: int = 0,
    supported: bool = True,
) -> LabelEntry:
    return LabelEntry(
        id=id_,
        display_name=id_,
        dots_printable=dots_printable,
        tape_size=tape_size,
        form_factor=form_factor,
        color=color,
        supported=supported,
    )


def _make_template(label_media: str = "62red", canvas_json: dict | None = None) -> Template:
    return Template(
        name="test-tmpl",
        display_name="Test Template",
        label_media=label_media,
        canvas_json=canvas_json or {"objects": []},
        field_schema=[],
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


# ── render_template with media_override ───────────────────────────────────────


def test_render_template_override_uses_effective_media():
    """Rendering with media_override='62' (mono) should return an L-mode image."""
    label_62red = _make_label("62red", color=1, form_factor=2)
    label_62 = _make_label("62", color=0, form_factor=2)

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62red": label_62red, "62": label_62}.get(id_)

    tmpl = _make_template(label_media="62red")

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import render_template

        img = render_template(tmpl, {}, media_override="62")

    assert img.mode == "L", "Mono override should produce a grayscale image"


def test_render_template_no_override_is_unchanged():
    """No override should behave as before (two-color template → RGB image)."""
    label_62red = _make_label("62red", color=1, form_factor=2)

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62red": label_62red}.get(id_)

    tmpl = _make_template(label_media="62red")

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import render_template

        img = render_template(tmpl, {})

    assert img.mode == "RGB", "Two-color template without override should produce RGB image"


def test_render_template_override_die_cut_sizes_to_label():
    """Rendering with a die-cut override sizes the canvas to the die-cut dimensions."""
    label_62red = _make_label("62red", color=1, form_factor=2, dots_printable=(696, 0))
    # 62x29 die-cut: 696 × 271 printable dots
    label_62x29 = _make_label(
        "62x29", color=0, form_factor=1, dots_printable=(696, 271), tape_size=(62, 29)
    )

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62red": label_62red, "62x29": label_62x29}.get(id_)

    tmpl = _make_template(label_media="62red")

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import render_template

        img = render_template(tmpl, {}, media_override="62x29")

    assert img.size == (696, 271), f"Expected (696, 271), got {img.size}"


# ── detect_overflow ────────────────────────────────────────────────────────────


def test_detect_overflow_continuous_never_overflows():
    """Continuous media should never be reported as overflowing."""
    label_62 = _make_label("62", form_factor=2, dots_printable=(696, 0))

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62": label_62}.get(id_)

    # Template with an object that would overflow a die-cut
    canvas = {"objects": [{"type": "Rect", "top": 0, "height": 5000, "scaleY": 1.0}]}
    tmpl = _make_template(canvas_json=canvas)

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import detect_overflow

        assert detect_overflow(tmpl, "62") is False


def test_detect_overflow_die_cut_within_bounds():
    """Content that fits within the die-cut should not be flagged."""
    label_62x29 = _make_label("62x29", form_factor=1, dots_printable=(696, 271), tape_size=(62, 29))

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62x29": label_62x29}.get(id_)

    canvas = {"objects": [{"type": "Rect", "top": 10, "height": 100, "scaleY": 1.0}]}
    tmpl = _make_template(canvas_json=canvas)

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import detect_overflow

        assert detect_overflow(tmpl, "62x29") is False


def test_detect_overflow_die_cut_exceeds_bounds():
    """Content extending past the die-cut height should be flagged."""
    label_62x29 = _make_label("62x29", form_factor=1, dots_printable=(696, 271), tape_size=(62, 29))

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62x29": label_62x29}.get(id_)

    # top=200 + height=200 = 400 > 271 printable dots
    canvas = {"objects": [{"type": "Rect", "top": 200, "height": 200, "scaleY": 1.0}]}
    tmpl = _make_template(canvas_json=canvas)

    with patch("labelforge.render.template.get_label", side_effect=_get_label):
        from labelforge.render.template import detect_overflow

        assert detect_overflow(tmpl, "62x29") is True


def test_detect_overflow_unknown_media_returns_false():
    """Unknown media should not raise — return False."""
    with patch("labelforge.render.template.get_label", return_value=None):
        from labelforge.render.template import detect_overflow

        tmpl = _make_template()
        assert detect_overflow(tmpl, "nonexistent") is False


# ── reprint uses history row's media ──────────────────────────────────────────


def test_reprint_uses_row_media_not_template_media():
    """_reprint_template should render on the history row's label_media, not
    the template's stored label_media. This ensures one-off overrides at recall
    time are reproduced faithfully on reprint.
    """
    label_62 = _make_label("62", color=0, form_factor=2)
    label_62red = _make_label("62red", color=1, form_factor=2)

    def _get_label(id_: str) -> LabelEntry | None:
        return {"62": label_62, "62red": label_62red}.get(id_)

    tmpl = _make_template(label_media="62red")  # template stored on 62red
    row = {
        "template_id": "test-tmpl",
        "label_media": "62",  # was printed on mono 62
        "field_values": json.dumps({}),
        "payload_json": json.dumps({}),
        "reprint_of": None,
    }

    calls: list[dict] = []

    def _mock_render(template, values, *, media_override=None):
        calls.append({"media_override": media_override})
        # Return a tiny mono image so downstream code doesn't crash.
        return Image.new("L", (10, 10), 255)

    with (
        patch("labelforge.routes.history.store") as mock_store,
        patch("labelforge.routes.history.get_label", side_effect=_get_label),
        patch("labelforge.routes.history.render_template", side_effect=_mock_render),
        patch("labelforge.routes.history.print_image", return_value="sent"),
        patch("labelforge.routes.history.insert_job_with_preview", return_value=99),
    ):
        mock_store.get_template.return_value = tmpl

        from labelforge.routes.history import _reprint_template

        result = asyncio.run(_reprint_template(99, row))

    assert len(calls) == 1, "render_template should have been called once"
    assert calls[0]["media_override"] == "62", (
        "reprint should render on the history row's media ('62'), not the template's ('62red')"
    )
    assert result["reprint_of"] == 99
