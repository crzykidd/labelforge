import json
import re
import sqlite3
from datetime import datetime, timezone

from labelforge.config import settings
from labelforge.db import get_connection
from labelforge.models import FieldSpec, Template, TemplateCreate, TemplateUpdate

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _db_path():
    return settings.data_dir / "data" / "app.db"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_template(row: sqlite3.Row) -> Template:
    return Template(
        name=row["name"],
        display_name=row["display_name"],
        label_media=row["label_media"],
        canvas_json=json.loads(row["canvas_json"]),
        field_schema=[FieldSpec(**f) for f in json.loads(row["field_schema"])],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise ValueError(
            f"Template name '{name}' is invalid — use lowercase letters, digits, "
            "and hyphens only; must start with a letter or digit."
        )


def list_templates() -> list[Template]:
    conn = get_connection(_db_path())
    try:
        rows = conn.execute(
            "SELECT * FROM templates WHERE deleted_at IS NULL ORDER BY name"
        ).fetchall()
        return [_row_to_template(r) for r in rows]
    finally:
        conn.close()


def get_template(name: str, include_deleted: bool = False) -> Template | None:
    conn = get_connection(_db_path())
    try:
        if include_deleted:
            row = conn.execute(
                "SELECT * FROM templates WHERE lower(name) = lower(?)", (name,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM templates WHERE lower(name) = lower(?) AND deleted_at IS NULL",
                (name,),
            ).fetchone()
        return _row_to_template(row) if row else None
    finally:
        conn.close()


def create_template(data: TemplateCreate) -> Template:
    _validate_name(data.name)
    conn = get_connection(_db_path())
    try:
        if conn.execute(
            "SELECT 1 FROM templates WHERE lower(name) = lower(?)", (data.name,)
        ).fetchone():
            raise ValueError(f"Template name '{data.name}' already exists.")

        display_name = data.display_name or data.name
        now = _now_utc()
        conn.execute(
            """INSERT INTO templates
               (name, display_name, label_media, canvas_json, field_schema, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                data.name,
                display_name,
                data.label_media,
                json.dumps(data.canvas_json),
                json.dumps([f.model_dump() for f in data.field_schema]),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM templates WHERE name = ?", (data.name,)
        ).fetchone()
        return _row_to_template(row)
    finally:
        conn.close()


def update_template(name: str, data: TemplateUpdate) -> Template | None:
    conn = get_connection(_db_path())
    try:
        if not conn.execute(
            "SELECT 1 FROM templates WHERE lower(name) = lower(?) AND deleted_at IS NULL",
            (name,),
        ).fetchone():
            return None

        updates: dict[str, object] = {"updated_at": _now_utc()}
        if data.display_name is not None:
            updates["display_name"] = data.display_name
        if data.label_media is not None:
            updates["label_media"] = data.label_media
        if data.canvas_json is not None:
            updates["canvas_json"] = json.dumps(data.canvas_json)
        if data.field_schema is not None:
            updates["field_schema"] = json.dumps([f.model_dump() for f in data.field_schema])

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE templates SET {set_clause} WHERE lower(name) = lower(?)",  # noqa: S608
            (*updates.values(), name),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM templates WHERE lower(name) = lower(?)", (name,)
        ).fetchone()
        return _row_to_template(row) if row else None
    finally:
        conn.close()


def soft_delete(name: str) -> bool:
    conn = get_connection(_db_path())
    try:
        cursor = conn.execute(
            "UPDATE templates SET deleted_at = ? "
            "WHERE lower(name) = lower(?) AND deleted_at IS NULL",
            (_now_utc(), name),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def duplicate(name: str, new_name: str, new_label_media: str) -> Template:
    _validate_name(new_name)
    conn = get_connection(_db_path())
    try:
        orig = conn.execute(
            "SELECT * FROM templates WHERE lower(name) = lower(?) AND deleted_at IS NULL",
            (name,),
        ).fetchone()
        if not orig:
            raise ValueError(f"Template '{name}' not found.")

        if conn.execute(
            "SELECT 1 FROM templates WHERE lower(name) = lower(?)", (new_name,)
        ).fetchone():
            raise ValueError(f"Template name '{new_name}' already exists.")

        now = _now_utc()
        conn.execute(
            """INSERT INTO templates
               (name, display_name, label_media, canvas_json, field_schema, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                new_name,
                new_name,
                new_label_media,
                orig["canvas_json"],
                orig["field_schema"],
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM templates WHERE name = ?", (new_name,)
        ).fetchone()
        return _row_to_template(row)
    finally:
        conn.close()
