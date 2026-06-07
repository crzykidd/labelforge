import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS print_jobs (
    id           INTEGER PRIMARY KEY,
    template_id  TEXT    NULL,
    payload_json TEXT    NOT NULL,
    label_media  TEXT    NOT NULL,
    preview_path TEXT    NULL,
    pinned       INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id           INTEGER PRIMARY KEY,
    name         TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    label_media  TEXT NOT NULL,
    canvas_json  TEXT NOT NULL,
    field_schema TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at   TEXT NULL
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_print_jobs(conn: sqlite3.Connection) -> None:
    """Idempotently add columns to print_jobs that post-date the initial schema."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(print_jobs)")}
    added = []
    if "field_values" not in existing:
        conn.execute("ALTER TABLE print_jobs ADD COLUMN field_values TEXT NULL")
        added.append("field_values")
    if "batch_id" not in existing:
        conn.execute("ALTER TABLE print_jobs ADD COLUMN batch_id TEXT NULL")
        added.append("batch_id")
    if "reprint_of" not in existing:
        conn.execute("ALTER TABLE print_jobs ADD COLUMN reprint_of INTEGER NULL")
        added.append("reprint_of")
    conn.commit()
    if added:
        logger.info("Applied print_jobs migrations: added column(s) %s", ", ".join(added))


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not db_path.exists()
    conn = get_connection(db_path)
    conn.executescript(_SCHEMA)
    _migrate_print_jobs(conn)
    conn.close()
    if is_new:
        logger.info("Database created at %s", db_path)
    else:
        logger.info("Database opened (existing) at %s", db_path)
