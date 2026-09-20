"""Tests for the `copies` count: per-print on Quick Print / template print /
batch print, `default_copies` on templates, and that reprint always sends 1
copy regardless of what the original request asked for.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from labelforge import config, db
from labelforge.models import (
    BatchPrintRequest,
    LabelEntry,
    PrintRequest,
    QuickPrintRequest,
)
from PIL import Image
from pydantic import ValidationError

_KNOWN_MEDIA = {"62"}


def _fake_label(media_id: str) -> LabelEntry | None:
    if media_id not in _KNOWN_MEDIA:
        return None
    return LabelEntry(
        id=media_id,
        display_name=media_id,
        dots_printable=(696, 0),
        tape_size=(62, 0),
        form_factor=2,  # continuous
        color=0,
        supported=True,
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    db.init_db(tmp_path / "data" / "app.db")

    from labelforge.main import app

    monkeypatch.setattr("labelforge.routes.templates.get_label", _fake_label)
    monkeypatch.setattr("labelforge.routes.template_print.get_label", _fake_label)
    monkeypatch.setattr("labelforge.render.template.get_label", _fake_label)

    return TestClient(app)


def _canvas() -> dict:
    return {"objects": [{"type": "i-text", "text": "hello", "labelforge_raw_content": "hello"}]}


# ── copies defaults + bounds on the request models ─────────────────────────


def test_copies_defaults_to_one_on_all_request_models():
    assert QuickPrintRequest(text="x", font="F", label_media="62").copies == 1
    assert PrintRequest().copies == 1
    assert BatchPrintRequest(labels=[{}]).copies == 1


@pytest.mark.parametrize("bad", [0, -1, 101, 1000])
def test_copies_out_of_range_rejected(bad):
    with pytest.raises(ValidationError):
        QuickPrintRequest(text="x", font="F", label_media="62", copies=bad)
    with pytest.raises(ValidationError):
        PrintRequest(copies=bad)
    with pytest.raises(ValidationError):
        BatchPrintRequest(labels=[{}], copies=bad)


# ── print_image sends copies as one multi-image raster job ─────────────────


def test_print_image_sends_n_images_for_copies_n():
    from labelforge.printer.client import print_image

    img = Image.new("L", (10, 10), 255)
    captured: dict = {}

    def _fake_convert(qlr, images, label, **kwargs):
        captured["images"] = list(images)
        return b"INSTR"

    with (
        patch("labelforge.printer.client.convert", side_effect=_fake_convert),
        patch("labelforge.printer.client.send", return_value={"outcome": "sent"}),
    ):
        outcome = print_image(img, "62", "QL-820NWB", "network", "printer.local", copies=3)

    assert outcome == "sent"
    assert len(captured["images"]) == 3
    assert all(im is img for im in captured["images"])


def test_print_image_copies_one_matches_pre_feature_single_image_call():
    """Regression bar: copies=1 (the default, and nearly every existing caller)
    must build convert() with exactly [img], byte-identical to the raster job
    produced before `copies` existed. Runs the real brother_ql convert() (not
    mocked) so the comparison is on actual instruction bytes, not call args.
    """
    from brother_ql.conversion import convert as real_convert
    from brother_ql.raster import BrotherQLRaster
    from labelforge.printer.client import PRINT_THRESHOLD, print_image

    img = Image.new("L", (696, 100), 255)

    expected_qlr = BrotherQLRaster("QL-820NWB")
    expected = real_convert(
        expected_qlr, [img], "62", cut=True, rotate="0", threshold=PRINT_THRESHOLD, red=False
    )

    captured: dict = {}

    def _capture_send(instructions, **kwargs):
        captured["instructions"] = instructions
        return {"outcome": "sent"}

    with patch("labelforge.printer.client.send", side_effect=_capture_send):
        print_image(img, "62", "QL-820NWB", "network", "printer.local", copies=1)
        print_image(img, "62", "QL-820NWB", "network", "printer.local")  # no copies kwarg at all

    assert captured["instructions"] == expected


# ── Batch total guard: labels x copies > 1000 ───────────────────────────────


def test_batch_total_guard_rejects_over_1000(client):
    r = client.post(
        "/api/templates",
        json={"name": "counter", "label_media": "62", "canvas_json": _canvas()},
    )
    assert r.status_code == 201, r.text

    labels = [{} for _ in range(20)]
    r = client.post("/api/print/counter/batch", json={"labels": labels, "copies": 51})
    assert r.status_code == 400
    assert "1000" in r.json()["detail"]


def test_batch_total_guard_allows_exactly_1000(client):
    r = client.post(
        "/api/templates",
        json={"name": "counter2", "label_media": "62", "canvas_json": _canvas()},
    )
    assert r.status_code == 201, r.text

    labels = [{} for _ in range(10)]
    with (
        patch("labelforge.routes.template_print.print_image", return_value="sent"),
        patch(
            "labelforge.routes.template_print.render_template",
            return_value=Image.new("L", (10, 10), 255),
        ),
    ):
        r = client.post("/api/print/counter2/batch", json={"labels": labels, "copies": 100})
    assert r.status_code == 200, r.text
    assert r.json()["succeeded"] == 10


# ── default_copies round-trips through create -> get -> update -> duplicate ─


def test_default_copies_round_trips(client):
    r = client.post(
        "/api/templates",
        json={
            "name": "spool",
            "label_media": "62",
            "canvas_json": _canvas(),
            "default_copies": 5,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["default_copies"] == 5

    r = client.get("/api/templates/spool")
    assert r.json()["default_copies"] == 5

    r = client.put("/api/templates/spool", json={"default_copies": 7})
    assert r.status_code == 200, r.text
    assert r.json()["default_copies"] == 7

    r = client.post("/api/templates/spool/duplicate", json={"name": "spool-2", "label_media": "62"})
    assert r.status_code == 201, r.text
    assert r.json()["default_copies"] == 7


def test_default_copies_defaults_to_one(client):
    r = client.post(
        "/api/templates",
        json={"name": "plain", "label_media": "62", "canvas_json": _canvas()},
    )
    assert r.status_code == 201, r.text
    assert r.json()["default_copies"] == 1


# ── Migration adds default_copies to a pre-existing DB, idempotently ───────


def test_migration_adds_default_copies_column(tmp_path):
    db_path = tmp_path / "data" / "app.db"
    db_path.parent.mkdir(parents=True)

    # Build a templates table matching the pre-default_copies schema.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE templates (
            id           INTEGER PRIMARY KEY,
            name         TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            label_media  TEXT NOT NULL,
            canvas_json  TEXT NOT NULL,
            field_schema TEXT NOT NULL DEFAULT '[]',
            orientation  TEXT NOT NULL DEFAULT 'standard',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
            deleted_at   TEXT NULL
        )"""
    )
    conn.execute(
        "INSERT INTO templates (name, display_name, label_media, canvas_json) "
        "VALUES ('t', 't', '62', '{}')"
    )
    conn.commit()
    conn.close()

    db.init_db(db_path)

    conn = db.get_connection(db_path)
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(templates)")}
        assert "default_copies" in cols
        row = conn.execute("SELECT default_copies FROM templates WHERE name = 't'").fetchone()
        assert row["default_copies"] == 1
    finally:
        conn.close()

    # Idempotent: running init_db again must not error or duplicate the column.
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    try:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(templates)")]
        assert cols.count("default_copies") == 1
    finally:
        conn.close()


# ── Reprint always sends 1 copy ─────────────────────────────────────────────


def test_reprint_template_always_sends_one_copy_even_if_payload_had_more(client):
    import asyncio
    import json

    from labelforge.models import Template

    tmpl = Template(
        name="spool",
        display_name="Spool",
        label_media="62",
        canvas_json=_canvas(),
        field_schema=[],
        orientation="standard",
        default_copies=1,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    row = {
        "template_id": "spool",
        "label_media": "62",
        "field_values": json.dumps({}),
        # Original request asked for 5 copies — reprint must not honor this.
        "payload_json": json.dumps({"fields": {}, "copies": 5}),
        "reprint_of": None,
    }

    captured_copies = []

    def _fake_print_image(**kwargs):
        captured_copies.append(kwargs.get("copies"))
        return "sent"

    with (
        patch("labelforge.routes.history.store") as mock_store,
        patch("labelforge.routes.history.get_label", side_effect=_fake_label),
        patch(
            "labelforge.routes.history.render_template",
            return_value=Image.new("L", (10, 10), 255),
        ),
        patch("labelforge.routes.history.print_image", side_effect=_fake_print_image),
        patch("labelforge.routes.history.insert_job_with_preview", return_value=99),
    ):
        mock_store.get_template.return_value = tmpl

        from labelforge.routes.history import _reprint_template

        asyncio.run(_reprint_template(1, row))

    assert captured_copies == [1]


def test_reprint_quick_always_sends_one_copy_even_if_payload_had_more(client):
    import asyncio
    import json

    row = {
        "payload_json": json.dumps(
            {
                "text": "hello",
                "font": "DejaVuSans",
                "font_size": 32,
                "alignment": "left",
                "orientation": "standard",
                "label_media": "62",
                "bold": False,
                "italic": False,
                "copies": 9,
            }
        ),
    }

    captured_copies = []

    def _fake_print_image(**kwargs):
        captured_copies.append(kwargs.get("copies"))
        return "sent"

    with (
        patch("labelforge.routes.history.get_label", side_effect=_fake_label),
        patch(
            "labelforge.routes.history.render_text",
            return_value=Image.new("L", (10, 10), 255),
        ),
        patch("labelforge.routes.history.print_image", side_effect=_fake_print_image),
        patch("labelforge.routes.history.insert_job_with_preview", return_value=100),
    ):
        from labelforge.routes.history import _reprint_quick

        asyncio.run(_reprint_quick(1, row))

    assert captured_copies == [1]
