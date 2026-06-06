"""Tests for the catalog 3-way merge logic.

merge_catalog is pure (no file IO), so these tests run without any filesystem setup.
reconcile_catalog_files tests use tmp_path.
"""

import shutil

import yaml
from labelforge.catalog.reconcile import merge_catalog, reconcile_catalog_files


def _doc(*entries):
    return {"labels": list(entries)}


def _e(id, **kwargs):
    return {"id": id, **kwargs}


# ── merge_catalog (pure function) ────────────────────────────────────────────


def test_default_unchanged_no_op():
    entry = _e("62", display_name="62mm", brother_part="DK-2205")
    doc = _doc(entry)
    result, changes = merge_catalog(doc, doc, doc)
    assert result["labels"] == [dict(entry)]
    assert changes == []


def test_new_default_entry_added():
    existing = _e("62", display_name="62mm")
    new_entry = _e("29", display_name="29mm")
    op = _doc(existing)
    old_default = _doc(existing)
    new_default = _doc(existing, new_entry)

    result, changes = merge_catalog(op, old_default, new_default)
    ids = [e["id"] for e in result["labels"]]
    assert "62" in ids
    assert "29" in ids
    assert "added 29" in changes


def test_operator_customized_field_preserved():
    """op != baseline → operator wins even when default changed it."""
    old = _e("62", brother_part="DK-OLD", display_name="62mm")
    op_entry = _e("62", brother_part="DK-OP", display_name="62mm")  # customized
    new = _e("62", brother_part="DK-NEW", display_name="62mm")

    result, changes = merge_catalog(_doc(op_entry), _doc(old), _doc(new))
    found = next(e for e in result["labels"] if e["id"] == "62")
    assert found["brother_part"] == "DK-OP"
    assert not any("brother_part" in c for c in changes)


def test_uncustomized_field_updated_from_default():
    """SKU correction: op == baseline, so the corrected default value is taken."""
    old = _e("62x29", brother_part="DK-WRONG", display_name="62x29mm")
    op_entry = _e("62x29", brother_part="DK-WRONG", display_name="62x29mm")  # unchanged
    new = _e("62x29", brother_part="DK-1209", display_name="62x29mm")

    result, changes = merge_catalog(_doc(op_entry), _doc(old), _doc(new))
    found = next(e for e in result["labels"] if e["id"] == "62x29")
    assert found["brother_part"] == "DK-1209"
    assert "updated 62x29.brother_part" in changes


def test_operator_only_custom_entry_preserved():
    default_entry = _e("62", display_name="62mm")
    custom = _e("custom-roll", display_name="My Roll")
    op = _doc(default_entry, custom)
    default = _doc(default_entry)

    result, changes = merge_catalog(op, default, default)
    ids = [e["id"] for e in result["labels"]]
    assert "custom-roll" in ids
    assert "62" in ids


def test_default_removed_entry_preserved():
    """An entry the default dropped must never be deleted from operator's file."""
    entry_62 = _e("62", display_name="62mm")
    entry_29 = _e("29", display_name="29mm")
    op = _doc(entry_62, entry_29)
    old_default = _doc(entry_62, entry_29)
    new_default = _doc(entry_62)  # 29 dropped from default

    result, changes = merge_catalog(op, old_default, new_default)
    ids = [e["id"] for e in result["labels"]]
    assert "29" in ids
    assert "62" in ids


def test_new_entries_appended_after_operator_entries():
    """Brand-new default entries appear after the operator's existing entries."""
    op_entry = _e("62", display_name="62mm")
    new_entry = _e("29", display_name="29mm")
    op = _doc(op_entry)
    old_default = _doc(op_entry)
    new_default = _doc(op_entry, new_entry)

    result, _ = merge_catalog(op, old_default, new_default)
    ids = [e["id"] for e in result["labels"]]
    assert ids.index("62") < ids.index("29")


def test_operator_extra_fields_kept():
    """Fields the operator added that aren't in the default are preserved."""
    old = _e("62", display_name="62mm")
    op_entry = _e("62", display_name="62mm", custom_note="rack shelf 3")
    new = _e("62", display_name="62mm")

    result, changes = merge_catalog(_doc(op_entry), _doc(old), _doc(new))
    found = next(e for e in result["labels"] if e["id"] == "62")
    assert found.get("custom_note") == "rack shelf 3"
    assert changes == []


# ── reconcile_catalog_files (file IO) ────────────────────────────────────────


def _write_yaml(path, data):
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def test_no_baseline_transition(tmp_path):
    """Upgrade from pre-reconcile: adds new entries only, existing untouched, baseline written."""
    default_path = tmp_path / "default.yml"
    yml_path = tmp_path / "labels.yml"
    baseline_path = tmp_path / "data" / "labels.default.yml"

    _write_yaml(
        default_path,
        _doc(
            _e("62", display_name="62mm", brother_part="DK-2205"),
            _e("29", display_name="29mm", brother_part="DK-2210"),
        ),
    )
    _write_yaml(
        yml_path,
        _doc(
            _e("62", display_name="My Custom 62mm", brother_part="DK-2205"),
        ),
    )

    summary = reconcile_catalog_files(default_path, yml_path, baseline_path)

    assert summary["added"] == 1
    assert summary["wrote"] is True
    assert baseline_path.exists()
    assert baseline_path.read_bytes() == default_path.read_bytes()

    result = yaml.safe_load(yml_path.read_text())
    entry_62 = next(e for e in result["labels"] if e["id"] == "62")
    assert entry_62["display_name"] == "My Custom 62mm"  # operator value preserved
    ids = [e["id"] for e in result["labels"]]
    assert "29" in ids


def test_no_baseline_no_new_entries(tmp_path):
    """No-baseline transition with no new entries: no write, baseline still created."""
    default_path = tmp_path / "default.yml"
    yml_path = tmp_path / "labels.yml"
    baseline_path = tmp_path / "data" / "labels.default.yml"

    doc = _doc(_e("62", display_name="62mm"))
    _write_yaml(default_path, doc)
    _write_yaml(yml_path, doc)

    original_bytes = yml_path.read_bytes()
    summary = reconcile_catalog_files(default_path, yml_path, baseline_path)

    assert summary["wrote"] is False
    assert yml_path.read_bytes() == original_bytes
    assert baseline_path.exists()


def test_first_run_copies_default(tmp_path):
    """No operator file: default is copied to both yml_path and baseline_path."""
    default_path = tmp_path / "default.yml"
    yml_path = tmp_path / "labels.yml"
    baseline_path = tmp_path / "data" / "labels.default.yml"

    _write_yaml(default_path, _doc(_e("62", display_name="62mm")))
    reconcile_catalog_files(default_path, yml_path, baseline_path)

    assert yml_path.exists()
    assert baseline_path.exists()
    assert yml_path.read_bytes() == default_path.read_bytes()
    assert baseline_path.read_bytes() == default_path.read_bytes()


def test_baseline_unchanged_noop(tmp_path):
    """Default bytes == baseline bytes: no write."""
    default_path = tmp_path / "default.yml"
    yml_path = tmp_path / "labels.yml"
    baseline_path = tmp_path / "data" / "labels.default.yml"
    baseline_path.parent.mkdir(parents=True)

    doc = _doc(_e("62", display_name="62mm"))
    _write_yaml(default_path, doc)
    _write_yaml(yml_path, doc)
    shutil.copy(default_path, baseline_path)

    original_bytes = yml_path.read_bytes()
    summary = reconcile_catalog_files(default_path, yml_path, baseline_path)

    assert summary["wrote"] is False
    assert yml_path.read_bytes() == original_bytes


def test_full_merge_on_changed_default(tmp_path):
    """Baseline differs from default: 3-way merge runs, backup written, baseline updated."""
    default_path = tmp_path / "default.yml"
    yml_path = tmp_path / "labels.yml"
    baseline_path = tmp_path / "data" / "labels.default.yml"
    baseline_path.parent.mkdir(parents=True)

    old_doc = _doc(_e("62", brother_part="DK-OLD", display_name="62mm"))
    op_doc = _doc(_e("62", brother_part="DK-OLD", display_name="62mm"))  # not customized
    new_doc = _doc(
        _e("62", brother_part="DK-2205", display_name="62mm"),
        _e("29", display_name="29mm"),
    )

    _write_yaml(yml_path, op_doc)
    _write_yaml(baseline_path, old_doc)
    _write_yaml(default_path, new_doc)

    summary = reconcile_catalog_files(default_path, yml_path, baseline_path)

    assert summary["wrote"] is True
    assert summary["backed_up"] is True
    assert summary["added"] == 1
    assert summary["updated"] >= 1

    result = yaml.safe_load(yml_path.read_text())
    entry_62 = next(e for e in result["labels"] if e["id"] == "62")
    assert entry_62["brother_part"] == "DK-2205"  # corrected
    assert any(e["id"] == "29" for e in result["labels"])  # new entry added
    assert baseline_path.read_bytes() == default_path.read_bytes()
    assert (yml_path.parent / (yml_path.name + ".bak")).exists()
