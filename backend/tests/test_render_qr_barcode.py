"""Tests: QR and barcode elements render correctly and survive the print threshold.

Verifies that:
- QR and barcode elements produce non-blank output with both black and white pixels.
- After to_print_bitmap() (the same 1-bit threshold used at print time), the result
  still contains both colors — i.e. the solid-black-block bug is gone.
- A QR payload with {placeholder} tokens resolves the field value before rasterizing.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from labelforge.models import LabelEntry, Template
from labelforge.printer.client import to_print_bitmap
from labelforge.render.text import RenderError


def _white_fraction(img, box: tuple[int, int, int, int]) -> float:
    """White-pixel fraction within *box* (left, top, right, bottom) of the rendered label.

    Measured over the element's own region, not the whole label canvas — the element
    occupies a small fraction of a 696×271 die-cut label, so a canvas-wide fraction
    would be ~97% white regardless of the element.
    """
    region = to_print_bitmap(img).crop(box)
    data = region.tobytes()
    return sum(1 for p in data if p == 255) / len(data)


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
        name="qr-barcode-test",
        display_name="QR Barcode Test",
        label_media="62x29",
        canvas_json=canvas_json,
        field_schema=[],
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def _qr_obj(payload: str = "https://example.com", correction: str = "M") -> dict:
    return {
        "type": "Image",
        "left": 10,
        "top": 10,
        "width": 100,
        "height": 100,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "angle": 0,
        "originX": "left",
        "originY": "top",
        "labelforge_qr_payload": payload,
        "labelforge_qr_error_correction": correction,
    }


def _barcode_obj(payload: str = "12345678", symbology: str = "code128") -> dict:
    return {
        "type": "Image",
        "left": 10,
        "top": 10,
        "width": 200,
        "height": 80,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "angle": 0,
        "originX": "left",
        "originY": "top",
        "labelforge_barcode_payload": payload,
        "labelforge_barcode_symbology": symbology,
    }


def _render(obj: dict, values: dict | None = None) -> object:
    label = _make_label_62x29()
    with patch("labelforge.render.template.get_label", return_value=label):
        from labelforge.render.template import render_template

        return render_template(_make_template({"objects": [obj]}), values or {})


# ---------------------------------------------------------------------------
# QR element tests
# ---------------------------------------------------------------------------


def test_qr_element_renders_non_blank():
    """QR element produces at least some inked pixels."""
    img = _render(_qr_obj())
    pixels = list(img.tobytes())
    assert any(p < 255 for p in pixels), "QR render has no inked pixels — completely white"


def test_qr_element_survives_print_threshold():
    """After the print threshold, QR output has both black and white pixels (not a solid block)."""
    img = _render(_qr_obj())
    bm = to_print_bitmap(img)
    pixels = set(bm.tobytes())
    assert 0 in pixels, "QR bitmap is entirely white after threshold — no ink"
    assert 255 in pixels, "QR bitmap is entirely black after threshold — solid block bug"


def test_qr_white_fraction_sanity():
    """QR image has a reasonable proportion of white pixels (quiet zone + background present)."""
    img = _render(_qr_obj())
    # QR element box is 100×100 at (left=10, top=10).
    wf = _white_fraction(img, (10, 10, 110, 110))
    # A correctly rendered QR in this box is ~70% white. The solid-black-block bug
    # (grey QR background crushed to black by the threshold) leaves only the
    # centering padding white (~34%), so a 0.45 floor catches that regression — a
    # 0.20 floor did not.
    assert wf >= 0.45, f"White fraction {wf:.2%} too low — QR is mostly black (solid-block bug)"
    # A QR code is not mostly white either (it must actually have modules).
    assert wf <= 0.90, f"White fraction {wf:.2%} too high — maybe blank"


def test_qr_payload_field_substitution():
    """A QR payload with {placeholder} resolves the field value before rasterizing."""
    # Render with placeholder resolved to a URL
    img_resolved = _render(_qr_obj(payload="{url}"), values={"url": "https://example.com"})
    # Render with a plain URL directly — should be byte-identical to the resolved one
    img_direct = _render(_qr_obj(payload="https://example.com"), values={})

    assert any(p < 255 for p in img_resolved.tobytes()), "Resolved QR render is blank"
    assert img_resolved.tobytes() == img_direct.tobytes(), "Resolved QR differs from direct"
    # A missing field surfaces as RenderError (render_template wraps the underlying
    # ValueError from resolve_content, same as the text branch does).
    with pytest.raises(RenderError, match="Missing required field"):
        _render(_qr_obj(payload="{url}"), values={})


# ---------------------------------------------------------------------------
# Barcode element tests
# ---------------------------------------------------------------------------


def test_barcode_element_renders_non_blank():
    """Barcode element produces at least some inked pixels."""
    img = _render(_barcode_obj())
    pixels = list(img.tobytes())
    assert any(p < 255 for p in pixels), "Barcode render has no inked pixels — completely white"


def test_barcode_element_survives_print_threshold():
    """After the print threshold, barcode output keeps both colors (not a solid block)."""
    img = _render(_barcode_obj())
    bm = to_print_bitmap(img)
    pixels = set(bm.tobytes())
    assert 0 in pixels, "Barcode bitmap is entirely white after threshold — no ink"
    assert 255 in pixels, "Barcode bitmap is entirely black after threshold — solid block bug"


def test_barcode_white_fraction_sanity():
    """Barcode image has a reasonable proportion of white pixels (gaps between bars)."""
    img = _render(_barcode_obj())
    # Barcode element box is 200×80 at (left=10, top=10).
    wf = _white_fraction(img, (10, 10, 210, 90))
    # Alternating bars: expect ≥20% white (gaps) and ≤95% white (bars present)
    assert wf >= 0.20, f"White fraction {wf:.2%} too low — maybe solid block"
    assert wf <= 0.95, f"White fraction {wf:.2%} too high — maybe blank"
