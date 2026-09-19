import json
import re
import sqlite3
from datetime import UTC, datetime

from labelforge.config import settings
from labelforge.db import get_connection
from labelforge.models import FieldList, FieldListCreate, FieldListUpdate

# Same charset as the {placeholder} field-name regex in templates/fields.py — a
# list is always named after the field it belongs to, never a free-typed id.
_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def _db_path():
    return settings.data_dir / "data" / "app.db"


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise ValueError(
            f"Field list name '{name}' is invalid — use the same characters allowed in a "
            "{placeholder} name: letters, digits, and underscores."
        )


def _row_to_field_list(row: sqlite3.Row) -> FieldList:
    return FieldList(name=row["name"], values=json.loads(row["values_json"]))


def list_field_lists() -> list[FieldList]:
    conn = get_connection(_db_path())
    try:
        rows = conn.execute("SELECT * FROM field_lists ORDER BY name").fetchall()
        return [_row_to_field_list(r) for r in rows]
    finally:
        conn.close()


def get_field_list(name: str) -> FieldList | None:
    conn = get_connection(_db_path())
    try:
        row = conn.execute("SELECT * FROM field_lists WHERE name = ?", (name,)).fetchone()
        return _row_to_field_list(row) if row else None
    finally:
        conn.close()


def create_field_list(data: FieldListCreate) -> FieldList:
    _validate_name(data.name)
    conn = get_connection(_db_path())
    try:
        if conn.execute("SELECT 1 FROM field_lists WHERE name = ?", (data.name,)).fetchone():
            raise ValueError(f"Field list '{data.name}' already exists.")
        now = _now_utc()
        conn.execute(
            "INSERT INTO field_lists (name, values_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (data.name, json.dumps(data.values), now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM field_lists WHERE name = ?", (data.name,)).fetchone()
        return _row_to_field_list(row)
    finally:
        conn.close()


def update_field_list(name: str, data: FieldListUpdate) -> FieldList | None:
    conn = get_connection(_db_path())
    try:
        if not conn.execute("SELECT 1 FROM field_lists WHERE name = ?", (name,)).fetchone():
            return None
        conn.execute(
            "UPDATE field_lists SET values_json = ?, updated_at = ? WHERE name = ?",
            (json.dumps(data.values), _now_utc(), name),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM field_lists WHERE name = ?", (name,)).fetchone()
        return _row_to_field_list(row)
    finally:
        conn.close()


def delete_field_list(name: str) -> bool:
    """Hard-delete. Not retroactive: existing templates keep `type: "list"` field
    specs pointing at this name (they degrade to free text at recall), and print
    history keeps the literal values it already printed — see docs/decisions.md.
    """
    conn = get_connection(_db_path())
    try:
        cursor = conn.execute("DELETE FROM field_lists WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
