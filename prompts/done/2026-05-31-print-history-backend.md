---
name: 2026-05-31-print-history-backend
status: completed
created: 2026-05-31
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-05-31
result: History API backend live — preview-on-every-print, 6 routes, retention pruning every 6 hours
---

# Task: Print history backend (list, reprint, pin, retention)

Build the **backend** half of the History feature: persist a preview for every print,
expose the `/api/history` routes (list, detail, preview PNG, reprint, pin, delete), and
run retention pruning on a schedule. This closes v1 success criteria 6 (reprint) and 7
(pin) at the API level. **No frontend in this slice** — the `/history` page and retention
settings UI are a separate follow-up (Slice B).

## Before you start

- Read `docs/features/history.md` (the design) and `docs/features/settings.md` (retention
  is configured there). Read `CLAUDE.md` "Code check-in" + "Session workflow".
- This repo uses **vexp**: call `run_pipeline` first for context; prefer `get_skeleton`
  over `Read`. Do not grep/glob (guard hook blocks it).
- Stack facts you can rely on (already verified during planning):
  - Print rows are written today by `backend/labelforge/routes/print.py` (quick) and
    `backend/labelforge/routes/template_print.py` (`/print/{name}` and `/print/{name}/batch`).
    Both currently leave `preview_path` NULL.
  - `print_jobs` columns today: `id, template_id, payload_json, label_media, preview_path,
    pinned, created_at, field_values, batch_id`. **Gotcha:** `template_id` stores the
    template *name* (TEXT), not a numeric id. `field_values` is JSON. `payload_json` is the
    original request JSON.
  - Schema + idempotent migrations live in `backend/labelforge/db.py`
    (`_migrate_print_jobs`). Add new columns there, never with a fresh CREATE.
  - Rendering: `render_text(...)` and `render_template(tmpl, values)` both return a PIL
    `Image`. `to_print_bitmap(image)` (in `printer/client.py`) is the canonical PNG path —
    the existing preview routes already `to_print_bitmap(image).save(buf, "PNG")`.
  - Retention **settings keys already exist** in `settings_store._REGISTRY`:
    `retention_mode` (`forever` | `last_n` | `last_days`), `retention_count` (default 500),
    `retention_days` (default 90). Consume them; do **not** redefine.
  - Preview files go under `${DATA_DIR}/label-previews/` (per CLAUDE.md data-path
    contract). `settings.data_dir` is a `Path`.
  - Routers are registered in `backend/labelforge/main.py` via `app.include_router(...,
    prefix="/api")`. The app lifespan there is the place to start the retention task.
  - There is **no test suite**. Verify manually with `curl` (see "Verify").

## Working tree check

Before editing, run `git status --porcelain` and cross-reference the files below. If any
have uncommitted changes, list them and ask before touching. This prompt file is exempt.
Files this plan modifies/creates:
- `backend/labelforge/db.py` (add `reprint_of` column)
- `backend/labelforge/routes/print.py`, `routes/template_print.py` (persist preview)
- `backend/labelforge/routes/history.py` (new)
- `backend/labelforge/history.py` or similar shared helper (new — see step 2)
- `backend/labelforge/main.py` (register router + start retention task)
- `backend/labelforge/models/__init__.py` (history response models)
- `CHANGELOG.md`, `docs/decisions.md`

## What to do

### 1. Schema: add `reprint_of`
In `db.py::_migrate_print_jobs`, idempotently add `reprint_of INTEGER NULL` (references
`print_jobs(id)` logically; no FK needed). Keep the existing column-add pattern.

### 2. Persist a preview on every print
Decision (already made — see ADR step): store previews as **files on disk**, not BLOBs.
Add a small shared helper (e.g. `backend/labelforge/history.py`) used by all three print
paths so the insert+preview logic isn't duplicated:

- After a successful `print_image(...)`, persist the row, then write the preview PNG.
- `job_id` is only known after INSERT, so: INSERT (preview_path NULL) → get `job_id` →
  write `to_print_bitmap(image)` to `${DATA_DIR}/label-previews/{job_id}.png` → UPDATE the
  row's `preview_path` with the path (store a path relative to `data_dir`, or just the
  filename — pick one and be consistent; the preview route resolves it back).
- Create `${DATA_DIR}/label-previews/` on demand (mkdir parents, exist_ok).
- Wire this into `routes/print.py` (quick), and both `_insert_job` call sites in
  `routes/template_print.py` (single + batch). Refactor `_insert_job` to go through the
  shared helper rather than duplicating the SQL. Keep behavior identical otherwise.
- If preview write fails, log a warning but do **not** fail the print (the label already
  printed). Row keeps `preview_path` NULL → list/detail handle missing preview gracefully.

### 3. New `routes/history.py` (register in `main.py`, `prefix="/api"`)
All routes require auth (`Depends(require_auth)`), matching the other routers. Newest
first (`ORDER BY created_at DESC, id DESC`).

- `GET /api/history?limit=50&offset=0&template={name}&pinned={true|false}&from={iso}&to={iso}`
  — paginated list. Each item: `id, template_id` (name or null), `is_quick_print`
  (derive: `template_id IS NULL`), `field_values` (parsed), `label_media`, `pinned`,
  `created_at`, `reprint_of`, `batch_id`, `preview_url` = `/api/history/{id}/preview.png`.
  Do not inline the image bytes in the list response. Clamp `limit` (e.g. 1..200).
- `GET /api/history/{job_id}` — full detail (same fields + `payload_json` parsed). 404 if
  absent.
- `GET /api/history/{job_id}/preview.png` — `FileResponse` of the stored file. If the row
  or file is missing, return 404 (the frontend renders a placeholder). Never 500 on a
  missing preview.
- `POST /api/history/{job_id}/reprint` — re-execute the original print and insert a **new**
  row with `reprint_of = job_id`:
  - Template rows (`template_id` not null): look up the template by name **ignoring
    `deleted_at`** (reprint must work for soft-deleted templates), re-render with the
    stored `field_values`, print. If the template row is truly gone (hard-deleted), 409
    with a clear message. If `label_media` is no longer in the catalog, 409 with a warning
    message (frontend will offer override later; backend just refuses cleanly for now).
  - Quick rows: rebuild `QuickPrintRequest` from `payload_json` and re-run the quick-print
    render+print.
  - Reuse the shared helper from step 2 so the reprint also gets a fresh preview.
- `POST /api/history/{job_id}/pin` — body `{"pinned": true|false}`; update the row; 404 if
  absent; return the updated row.
- `DELETE /api/history/{job_id}` — delete the row **and** its preview file (best-effort
  unlink). 404 if absent; 204 on success.

Add the Pydantic response models to `models/__init__.py` (e.g. `HistoryItem`,
`HistoryDetail`, `PinRequest`) following the existing model style.

### 4. Retention pruning (background task)
Add a `prune_history()` function (in the shared helper module) that:
- Reads `retention_mode` / `retention_count` / `retention_days` from `settings_store`.
- `forever` → no-op. `last_n` → keep the `retention_count` most recent **unpinned** rows,
  delete older unpinned. `last_days` → delete unpinned rows older than `retention_days`.
- **Pinned rows are never pruned**, regardless of mode.
- Delete the preview files for pruned rows (best-effort).
- If >10% of total rows were pruned, run `VACUUM` afterward.
- Log: count pruned, DB file size before/after.

Run it once at startup (in `main.py` lifespan, after `init_db`) and then every 6 hours via
an `asyncio` task created in the lifespan; cancel the task cleanly on shutdown (after
`yield`). Keep it defensive — a pruning error must not crash the app; log and continue.

### Out of scope (do NOT build here)
- Any frontend (`/history` page, retention settings UI) — that's Slice B.
- "Use as starting point for new template" — touches the editor; deferred with the QR /
  canvas-elements work.

## Conventions to honor

- Match surrounding code style (raw `sqlite3` via `get_connection`, `APIRouter` with
  `Depends(require_auth)`, Pydantic v2 models). One connection per operation, `finally:
  conn.close()` like the existing routes.
- Changelog: add a concise, user-facing entry under `## [Unreleased]` → `### Added`
  ("Print history API — browse, reprint, pin, and auto-prune past prints…"). Doc + code in
  the **same commit**.
- Commit on `dev`, Conventional-Commits prefix `feat:`, no `Co-authored-by:` trailers,
  never push, never `git add -A`.

## Verify

There's no test suite, so verify by hand (the planning owner runs the printer):
```
cd backend && uvicorn labelforge.main:app --reload   # or use compose.dev.yml on :8001
# with $API_TOKEN exported:
curl -s -H "Authorization: Bearer $API_TOKEN" localhost:8000/api/history | jq
curl -s -H "Authorization: Bearer $API_TOKEN" localhost:8000/api/history/1 | jq
curl -s -H "Authorization: Bearer $API_TOKEN" -X POST localhost:8000/api/history/1/pin -d '{"pinned":true}' -H 'content-type: application/json'
# reprint requires a reachable printer; confirm a new row appears with reprint_of set.
```
Leave a one-line "run this to verify" in your final summary.

## When done

1. Update this file's frontmatter: `status` (completed/failed), `completed` (date),
   `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record non-obvious decisions in `docs/decisions.md` as ADR entries — at minimum:
   - **Preview storage = file-on-disk** (`${DATA_DIR}/label-previews/{job_id}.png`),
     diverging from `history.md` which specified an inline `preview_png` BLOB. Rationale:
     the live schema already chose `preview_path`, the data-path contract already reserves
     `label-previews/`, and files keep the SQLite DB small. Update `docs/features/history.md`
     to match (or note the divergence).
   - History frontend + "use as starting point" deferred to a later slice.
4. Propose ONE commit covering the modified files (including this prompt's move). Present
   the file list + a one-line `feat:` message and ask `commit these as "<message>"? (y/n)`.
   On `y`, stage those specific paths and commit on `dev`. Never push.
