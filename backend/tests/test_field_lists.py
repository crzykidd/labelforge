"""Tests for global, reusable value lists (`type: "list"` fields).

Also covers the `PUT /api/templates/{name}` fix this feature depended on: the
route used to silently discard any `field_schema` the caller sent whenever
`canvas_json` was also present in the same request — which is every Save from
the editor — reverting type/increment edits made in that same request.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from labelforge import config, db
from labelforge.models import LabelEntry

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
    # Point the app at an isolated DB without running the full app lifespan
    # (catalog reconcile / font loading / retention loop aren't needed here —
    # TestClient(app) used outside a `with` block skips lifespan entirely).
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    db.init_db(tmp_path / "data" / "app.db")

    from labelforge.main import app

    monkeypatch.setattr("labelforge.routes.templates.get_label", _fake_label)

    return TestClient(app)


def _canvas_with_field(field_name: str) -> dict:
    return {
        "objects": [
            {
                "type": "i-text",
                "text": f"{{{field_name}}}",
                "labelforge_raw_content": f"{{{field_name}}}",
            }
        ]
    }


def _default_list_spec(name: str, **overrides) -> dict:
    spec = {
        "name": name,
        "type": "list",
        "required": True,
        "default": None,
        "increment": False,
        "enum_values": [],
    }
    spec.update(overrides)
    return spec


# ── Field list CRUD ────────────────────────────────────────────────────────


def test_field_list_crud_round_trips(client):
    r = client.post("/api/field-lists", json={"name": "room", "values": ["Kitchen", "Office"]})
    assert r.status_code == 201, r.text
    assert r.json() == {"name": "room", "values": ["Kitchen", "Office"]}

    r = client.get("/api/field-lists/room")
    assert r.status_code == 200
    assert r.json()["values"] == ["Kitchen", "Office"]

    r = client.get("/api/field-lists")
    assert r.status_code == 200
    assert any(fl["name"] == "room" for fl in r.json())

    r = client.put("/api/field-lists/room", json={"values": ["Kitchen", "Office", "Garage"]})
    assert r.status_code == 200
    assert r.json()["values"] == ["Kitchen", "Office", "Garage"]

    r = client.delete("/api/field-lists/room")
    assert r.status_code == 204

    assert client.get("/api/field-lists/room").status_code == 404


def test_field_list_create_duplicate_conflicts(client):
    assert client.post("/api/field-lists", json={"name": "room", "values": []}).status_code == 201
    r = client.post("/api/field-lists", json={"name": "room", "values": []})
    assert r.status_code == 409


def test_field_list_update_missing_404s(client):
    assert client.put("/api/field-lists/nope", json={"values": ["a"]}).status_code == 404


def test_field_list_delete_missing_404s(client):
    assert client.delete("/api/field-lists/nope").status_code == 404


def test_field_list_invalid_name_rejected(client):
    r = client.post("/api/field-lists", json={"name": "not valid!", "values": []})
    assert r.status_code == 400


def test_field_lists_require_auth_when_enabled(client, monkeypatch):
    monkeypatch.setattr(config.settings, "disable_auth", False)
    monkeypatch.setattr(config.settings, "api_token", "secret")
    assert client.get("/api/field-lists").status_code == 401


# ── The whole point: editing a global list changes every template's options ─


def test_two_templates_share_edits_to_the_same_global_list(client):
    assert (
        client.post("/api/field-lists", json={"name": "room", "values": ["Kitchen"]}).status_code
        == 201
    )

    for name in ("label-a", "label-b"):
        r = client.post(
            "/api/templates",
            json={
                "name": name,
                "label_media": "62",
                "canvas_json": _canvas_with_field("room"),
                "field_schema": [{"name": "room", "type": "list"}],
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["field_schema"] == [_default_list_spec("room")]

    # Editing the global list is the whole feature — both templates only ever
    # store the field *name*, never a copy of the values, so this single edit
    # is what every recall of either template will offer next time.
    r = client.put("/api/field-lists/room", json={"values": ["Kitchen", "Office", "Garage"]})
    assert r.status_code == 200
    assert r.json()["values"] == ["Kitchen", "Office", "Garage"]

    assert client.get("/api/field-lists/room").json()["values"] == [
        "Kitchen",
        "Office",
        "Garage",
    ]
    for name in ("label-a", "label-b"):
        tmpl = client.get(f"/api/templates/{name}").json()
        assert tmpl["field_schema"] == [_default_list_spec("room")]


def test_list_field_with_no_matching_global_list_is_not_an_error(client):
    """A `list` field whose named list doesn't exist is a valid template — the
    recall page degrades it to free text; the backend never errors on it."""
    r = client.post(
        "/api/templates",
        json={
            "name": "no-list",
            "label_media": "62",
            "canvas_json": _canvas_with_field("nonexistent"),
            "field_schema": [{"name": "nonexistent", "type": "list"}],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["field_schema"] == [_default_list_spec("nonexistent")]
    assert client.get("/api/field-lists/nonexistent").status_code == 404


def test_deleting_a_list_does_not_affect_existing_template_or_history(client):
    from labelforge.history import get_latest_field_values, insert_job_with_preview
    from PIL import Image

    client.post("/api/field-lists", json={"name": "room", "values": ["Kitchen", "Office"]})
    r = client.post(
        "/api/templates",
        json={
            "name": "spool3",
            "label_media": "62",
            "canvas_json": _canvas_with_field("room"),
            "field_schema": [{"name": "room", "type": "list"}],
        },
    )
    assert r.status_code == 201, r.text

    insert_job_with_preview(
        image=Image.new("1", (10, 10), 1),
        payload_json="{}",
        label_media="62",
        template_name="spool3",
        field_values={"room": "Kitchen"},
    )

    assert client.delete("/api/field-lists/room").status_code == 204

    tmpl = client.get("/api/templates/spool3").json()
    assert tmpl["field_schema"] == [_default_list_spec("room")]

    values, _ = get_latest_field_values("spool3")
    assert values == {"room": "Kitchen"}


# ── enum (per-template) keeps working unchanged ─────────────────────────────


def test_enum_field_unaffected_by_the_list_feature(client):
    r = client.post(
        "/api/templates",
        json={
            "name": "enum-tmpl",
            "label_media": "62",
            "canvas_json": _canvas_with_field("color"),
            "field_schema": [{"name": "color", "type": "enum", "enum_values": ["Red", "Blue"]}],
        },
    )
    assert r.status_code == 201, r.text
    spec = r.json()["field_schema"][0]
    assert spec["type"] == "enum"
    assert spec["enum_values"] == ["Red", "Blue"]


# ── PUT /api/templates/{name} field_schema-preservation fix ─────────────────


def test_update_template_preserves_field_schema_edits_sent_with_canvas(client):
    r = client.post(
        "/api/templates",
        json={"name": "spool", "label_media": "62", "canvas_json": _canvas_with_field("room")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["field_schema"][0]["type"] == "text"  # default, not yet edited

    # This mirrors the editor's Save: canvas_json AND an edited field_schema
    # arrive in the same PUT. Before the fix, canvas_json's presence made the
    # route ignore field_schema entirely and recompute from the OLD stored
    # schema, discarding the type=list edit below.
    r = client.put(
        "/api/templates/spool",
        json={
            "canvas_json": _canvas_with_field("room"),
            "field_schema": [
                {"name": "room", "type": "list", "required": False, "increment": True}
            ],
        },
    )
    assert r.status_code == 200, r.text
    spec = r.json()["field_schema"][0]
    assert spec["type"] == "list"
    assert spec["required"] is False
    assert spec["increment"] is True


def test_update_template_drops_fields_no_longer_detected(client):
    r = client.post(
        "/api/templates",
        json={"name": "spool2", "label_media": "62", "canvas_json": _canvas_with_field("room")},
    )
    assert r.status_code == 201, r.text

    # Placeholder removed from canvas — the field drops even though the
    # caller's field_schema still lists it (matches merge_schema's existing
    # "detected wins" contract; the fix only changed which schema is the base).
    r = client.put(
        "/api/templates/spool2",
        json={"canvas_json": {"objects": []}, "field_schema": [{"name": "room", "type": "list"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["field_schema"] == []


def test_update_template_field_schema_only_still_recomputes_against_canvas(client):
    """field_schema sent with no canvas_json change still merges against the
    template's *existing* canvas — new field-only PUTs aren't a way to smuggle
    in a name the canvas never declared."""
    r = client.post(
        "/api/templates",
        json={"name": "spool4", "label_media": "62", "canvas_json": _canvas_with_field("room")},
    )
    assert r.status_code == 201, r.text

    r = client.put(
        "/api/templates/spool4",
        json={
            "field_schema": [{"name": "room", "type": "list"}, {"name": "ghost", "type": "text"}]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["field_schema"] == [_default_list_spec("room")]
