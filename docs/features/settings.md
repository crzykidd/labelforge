# Feature: Settings

User-configurable preferences. Single user, so "settings" = "the operator's preferences."

## Storage

```
settings
  key      text primary key
  value    text                   -- JSON-encoded
```

Single-row-per-setting. Values are JSON strings to handle non-text types (booleans, numbers, lists) without per-key schema changes.

Defaults live in code; the DB only stores overrides. Reading a setting that has no row returns the default.

## Settings list

| Key | Type | Default | Description |
|---|---|---|---|
| `retention_mode` | enum | `forever` | `forever` / `last_n` / `last_days` |
| `retention_count` | int | `500` | When mode = `last_n`, keep this many unpinned rows (the most recent print per template is always kept regardless) |
| `retention_days` | int | `90` | When mode = `last_days`, keep unpinned rows newer than N days (the most recent print per template is always kept regardless) |
| `default_label_media` | string | `"62"` | Pre-selected in quick-print and new-template flows |
| `default_font` | string | `"DejaVuSans"` | Pre-selected in quick-print |
| `default_font_size` | int | `48` | Pre-selected in quick-print |
| `default_orientation` | enum | `standard` | `standard` / `rotated` |
| `printer_status_check` | bool | `true` | Query printer before printing |
| `printer_status_timeout_ms` | int | `2000` | How long to wait for status response |
| `last_quick_print` | json | `null` | Snapshot of last quick-print settings (used to restore form state) |

`last_quick_print` is a special case: written automatically on every quick-print, read on quick-print page load. Not user-editable through the settings UI.

## UI

A single settings page (`/settings`) grouped into sections:

### History & retention
- Retention mode selector (radio: forever / last N / last days)
- Conditional inputs based on mode
- "Run cleanup now" button (calls a manual prune endpoint)

### Defaults
- Default label media (dropdown from catalog)
- Default font (dropdown from fonts directory)
- Default font size (number)
- Default orientation

### Printer
- Printer host (read-only, from `.env`)
- Printer model (read-only, from `.env` or auto-detected via status)
- Status check enabled toggle
- Status timeout (number)
- **Test printer** button

### About
- App version
- Library version (`brother-ql-inventree`)
- Catalog status (total label media, count of yml-only / library-only / merged)
- Database location & size
- Link to docs

## API

```
GET    /api/settings                     All settings (current values, with defaults filled in)
PUT    /api/settings                     Partial update
POST   /api/admin/prune-history          Manually run retention cleanup
```

PUT body is a partial object:
```json
{
  "retention_mode": "last_n",
  "retention_count": 1000
}
```

Validation: unknown keys → 400. Invalid values for a key → 400 with field details.

## Edge cases

- Setting a retention mode for the first time → no immediate prune; next scheduled run picks it up. UI exposes "Run cleanup now" if the user wants instant effect.
- Changing default_label_media to an id no longer in the catalog → save the value anyway; UI shows it as "missing" in selectors and falls back to "first available" at use time.
- Concurrent writes to the same setting → last-write-wins. Single user, no conflict expected.
