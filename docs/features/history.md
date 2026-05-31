# Feature: History

Every print operation is logged. The user can browse, reprint, pin to retain, and configure retention policy.

## Goal

The user can answer:
- "What did I print last week?"
- "Print that spool label I made yesterday again."
- "Save this print so retention cleanup never removes it."

## User flow

1. Navigate to `/history`
2. Reverse-chronological list of print jobs (newest first), paginated
3. Each row shows:
   - Thumbnail preview
   - Template name (or "Quick print" badge)
   - Field values (compact key=value rendering)
   - Timestamp
   - Pin toggle
   - Reprint button
4. Click a row to expand: full-size preview, all values, "Reprint" and "Use as starting point for new template" actions
5. Filters: by template, by date range, pinned-only toggle, search across field values

## Data model

```
print_jobs
  id                   integer primary key
  template_id          text nullable              -- template name (TEXT), null for quick prints
  payload_json         text                      -- original request JSON snapshot
  field_values         text (json) nullable      -- {"number": "047", ...}
  label_media          text                      -- snapshot at print time
  preview_path         text nullable             -- filename under ${DATA_DIR}/label-previews/
  batch_id             text nullable
  reprint_of           integer nullable          -- references print_jobs(id) logically
  pinned               integer default 0
  created_at           text                      -- ISO 8601, UTC
```

**Note**: `template_id` stores the template *name* (TEXT), not a numeric id. `is_quick_print` is derived: `template_id IS NULL`.

Preview images are stored as PNG files under `${DATA_DIR}/label-previews/{id}.png` (file-on-disk, not a BLOB — see ADR 2026-05-31). `preview_path` stores the filename only; the preview route resolves the full path. A NULL or missing `preview_path` means the preview is unavailable — the route returns 404 and the frontend should render a placeholder.

## Reprint

`POST /api/history/{job_id}/reprint`

Behavior:
- For template prints: load template, validate that the template still exists and the label media still matches its current binding, render with the same field values, print
- For quick prints: re-execute the quick-print payload as-is
- A reprint creates a new `print_jobs` row (so history shows both); the new row's `reprint_of` field points to the original

Add `reprint_of` column:
```
print_jobs
  ...
  reprint_of           integer nullable references print_jobs(id)
```

## Pinning

Toggling `pinned = true` exempts the row from retention cleanup. No other effect — pinned rows are not promoted in the list, not visually emphasized (beyond a pin icon).

Pin can be toggled on any row, including reprints.

`POST /api/history/{job_id}/pin` (body: `{pinned: true|false}`)

## Retention

User-configurable via Settings ([`settings.md`](settings.md)). Two modes, choose one:

- **Keep last N**: retain the N most recent unpinned rows, prune older
- **Keep N days**: retain unpinned rows newer than N days, prune older
- **Keep forever**: no pruning (default until the user configures otherwise)

Pinned rows are never pruned regardless of mode.

### Pruning execution

A background task runs on app startup and every 6 hours thereafter. Pruning is a single SQL DELETE based on the active policy. After deletion, run `VACUUM` if more than 10% of rows were pruned (avoids the SQLite file growing unboundedly even as logical rows shrink).

Logged: count pruned, file size before/after.

## "Use as starting point for new template"

From a history row, opens the template editor with:

- For template-based history: clone of the source template
- For quick-print history: a single text element matching the printed text + same font/size

User picks a new name, edits, saves. Original template (if any) untouched.

## API

- `GET /api/history?limit=50&offset=0&template={name}&pinned={true|false}&from={iso}&to={iso}`
- `GET /api/history/{job_id}` — full detail
- `GET /api/history/{job_id}/preview.png` — preview image (also embedded in the JSON response as data URL, but PNG endpoint is more efficient for the list view)
- `POST /api/history/{job_id}/reprint`
- `POST /api/history/{job_id}/pin`
- `DELETE /api/history/{job_id}` — manual delete (requires API token)

## Edge cases

- Template referenced by history is deleted → row remains, displays template name as `"(deleted) <name>"`, reprint still works (looks up template ignoring `deleted_at`)
- Label media in history entry no longer in catalog → reprint shows a warning; user can override or cancel
- Preview blob missing (manually deleted from DB) → list view shows a placeholder; detail view shows "Preview unavailable"
- Pruning hits a row that's currently being viewed → the next refresh just won't have it; no special handling needed
