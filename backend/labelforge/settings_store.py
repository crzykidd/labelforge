import json
import logging
from typing import Any

from labelforge.config import settings as app_settings
from labelforge.db import get_connection

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, dict] = {
    "retention_mode": {
        "default": "forever",
        "vtype": str,
        "enum": frozenset({"forever", "last_n", "last_days"}),
    },
    "retention_count": {"default": 500, "vtype": int},
    "retention_days": {"default": 90, "vtype": int},
    # default falls back to config.settings.default_label_media, not a hardcoded literal
    "default_label_media": {"default": None, "vtype": str, "nullable": True},
    "default_font": {"default": "DejaVuSans", "vtype": str},
    "default_font_size": {"default": 48, "vtype": int},
    "default_orientation": {
        "default": "standard",
        "vtype": str,
        "enum": frozenset({"standard", "rotated"}),
    },
    "printer_status_check": {"default": True, "vtype": bool},
    "printer_status_timeout_ms": {"default": 2000, "vtype": int},
    "last_quick_print": {"default": None, "vtype": dict, "nullable": True},
}


def _db_path():
    return app_settings.data_dir / "data" / "app.db"


def _default(key: str) -> Any:
    if key == "default_label_media":
        return app_settings.default_label_media
    return _REGISTRY[key]["default"]


def validate(key: str, value: Any) -> None:
    """Raise ValueError if key is unknown or value fails type/enum check."""
    if key not in _REGISTRY:
        raise ValueError(f"Unknown setting: {key}")
    entry = _REGISTRY[key]
    if value is None:
        if not entry.get("nullable", False):
            raise ValueError(f"Setting '{key}' cannot be null")
        return
    vtype = entry["vtype"]
    if vtype is int:
        # bool is a subclass of int — reject booleans for int fields
        if not (isinstance(value, int) and not isinstance(value, bool)):
            raise ValueError(f"Setting '{key}' expects int, got {type(value).__name__}")
    elif not isinstance(value, vtype):
        raise ValueError(f"Setting '{key}' expects {vtype.__name__}, got {type(value).__name__}")
    if "enum" in entry and value not in entry["enum"]:
        raise ValueError(f"Setting '{key}' must be one of {sorted(entry['enum'])}, got {value!r}")


def get_all() -> dict[str, Any]:
    conn = get_connection(_db_path())
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        db_vals = {row["key"]: json.loads(row["value"]) for row in rows}
    finally:
        conn.close()
    return {key: db_vals.get(key, _default(key)) for key in _REGISTRY}


def get(key: str) -> Any:
    if key not in _REGISTRY:
        raise ValueError(f"Unknown setting: {key}")
    conn = get_connection(_db_path())
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else _default(key)
    finally:
        conn.close()


def set(key: str, value: Any) -> None:  # noqa: A001
    validate(key, value)
    conn = get_connection(_db_path())
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        conn.commit()
    finally:
        conn.close()
