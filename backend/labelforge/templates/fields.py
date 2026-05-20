import re

from labelforge.models import FieldSpec

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Trailing-digit pattern for advance(): splits "spool-047" into ("spool-", "047")
_TRAILING_DIGITS_RE = re.compile(r"^(.*?)(\d+)$")


def detect_fields(canvas_json: dict) -> list[str]:
    """Return ordered unique field names found in canvas element content."""
    seen: dict[str, None] = {}  # ordered set via dict
    for obj in canvas_json.get("objects", []):
        raw: str | None = None
        t = obj.get("type", "")
        if t in ("i-text", "text", "textbox"):
            raw = obj.get("labelforge_raw_content") or obj.get("text", "")
        elif obj.get("labelforge_qr_payload") is not None:
            raw = obj["labelforge_qr_payload"]
        elif obj.get("labelforge_barcode_payload") is not None:
            raw = obj["labelforge_barcode_payload"]
        if raw:
            for name in _PLACEHOLDER_RE.findall(raw):
                seen[name] = None
    return list(seen)


def merge_schema(detected: list[str], existing: list[FieldSpec]) -> list[FieldSpec]:
    """Merge detected field names with the stored schema.

    - Keeps existing specs for names still detected (preserves user edits).
    - Adds newly-detected names with defaults (type=text, required=True).
    - Drops specs whose name is no longer detected.
    """
    existing_by_name = {f.name: f for f in existing}
    result: list[FieldSpec] = []
    for name in detected:
        if name in existing_by_name:
            result.append(existing_by_name[name])
        else:
            result.append(FieldSpec(name=name))
    return result


def resolve_content(raw: str, values: dict[str, str]) -> str:
    """Substitute {name} placeholders with values. Raises ValueError for missing keys."""

    def replacer(m: re.Match) -> str:
        name = m.group(1)
        if name not in values:
            raise ValueError(f"Missing required field: '{name}'")
        return values[name]

    return _PLACEHOLDER_RE.sub(replacer, raw)


def advance(value: str) -> str:
    """Increment the trailing numeric portion of *value* by 1.

    Pure number:      "47"     → "48"
    Zero-padded:      "047"    → "048"  (width preserved; grows on overflow: "099" → "100")
    Suffix-numeric:   "spool-047" → "spool-048"
    Non-numeric:      returned unchanged.
    """
    m = _TRAILING_DIGITS_RE.match(value)
    if not m:
        return value
    prefix, digits = m.group(1), m.group(2)
    next_num = int(digits) + 1
    # Preserve zero-padding width; allow growth on overflow (e.g. 099 → 100)
    next_str = str(next_num).zfill(len(digits)) if digits.startswith("0") else str(next_num)
    return prefix + next_str
