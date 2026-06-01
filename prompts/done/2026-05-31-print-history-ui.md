---
name: 2026-05-31-print-history-ui
status: completed
created: 2026-05-31
model: sonnet
completed: 2026-05-31
result: /history page (list, reprint, pin, delete, load-more, filters) and /settings retention UI built; frontend build passes
---

# Task: Print history UI + retention settings UI

Build the **frontend** half of the History feature (Slice B). The backend API landed in
commit `d5fc08f` (`prompts/done/2026-05-31-print-history-backend.md`). This slice adds the
`/history` page (browse, reprint, pin, delete) and a retention-policy section in settings,
completing v1 success criteria 6 (reprint) and 7 (pin) end-to-end in the UI.

## Before you start

- Read `docs/features/history.md` (user flow) and `docs/features/settings.md` (retention
  config). Read `CLAUDE.md` "Code check-in" + "Working style" (vanilla TS, no frameworks).
- This repo uses **vexp**: call `run_pipeline` first; prefer `get_skeleton` over `Read`;
  don't grep/glob.
- Frontend facts (verified during planning):
  - Vanilla Vite + TS, **no React/Vue**. Fabric.js is only for the canvas editor — not
    needed here.
  - Custom router in `frontend/src/router.ts`: `register(path, mountFn)` for exact paths,
    `registerPrefix(prefix, mountFn)` for parameterised ones. Routes are wired in
    `frontend/src/main.ts` (e.g. `register('/templates', mountTemplates)`). Nav links use
    `data-route="..."` anchors.
  - Pages live in `frontend/src/pages/*.ts` and export a `mountX(root)` function. Model the
    new page on an existing one — `pages/templates-list.ts` (list + per-row actions) and
    `pages/template-recall.ts` (preview image + form + print) are the closest analogues.
  - API helpers live in `frontend/src/api.ts` (`apiFetch<T>(path, opts)` handles the bearer
    token + errors). Add history calls there. Types go in `frontend/src/types.ts`.
  - Styles in `frontend/src/style.css` (plain CSS; match existing class conventions).

### Backend API this UI consumes (already live, all require the bearer token)
- `GET /api/history?limit=&offset=&template=&pinned=&from=&to=` → `HistoryItem[]`.
  `HistoryItem` = `{ id, template_id (name|null), is_quick_print, field_values (object),
  label_media, pinned, created_at, reprint_of (id|null), batch_id, preview_url }`.
- `GET /api/history/{id}` → `HistoryDetail` (= `HistoryItem` + `payload_json`).
- `GET /api/history/{id}/preview.png` → PNG (use directly as `<img src>`; **note the token**
  — see "Preview auth" below). Returns 404 when no preview exists.
- `POST /api/history/{id}/reprint` → `{ job_id, status, reprint_of }`. 409 if the template
  is hard-deleted or the label media left the catalog — surface the error message.
- `POST /api/history/{id}/pin` body `{ "pinned": true|false }` → updated `HistoryItem`.
- `DELETE /api/history/{id}` → 204.
- Retention settings via existing `GET/PUT /api/settings`: keys `retention_mode`
  (`forever` | `last_n` | `last_days`), `retention_count` (int), `retention_days` (int).

## Working tree check

Run `git status --porcelain` first; cross-reference the files below and ask before
touching any that are already dirty (this prompt file exempt). Files this plan touches:
- `frontend/src/pages/history.ts` (new)
- `frontend/src/pages/settings.ts` (new) *or* extend an existing settings page if one
  exists — check first
- `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/main.ts`,
  `frontend/src/style.css`
- the nav markup (wherever the `data-route` links live — likely `index.html` or `main.ts`)
- `CHANGELOG.md`

## What to do

### 1. API + types
- Add to `types.ts`: `HistoryItem`, `HistoryDetail` (match the shapes above), and a
  retention-settings shape.
- Add to `api.ts`: `listHistory(params)`, `getHistory(id)`, `reprintHistory(id)`,
  `pinHistory(id, pinned)`, `deleteHistory(id)`, plus `getSettings()` / `updateSettings(patch)`
  if not already present.

### 2. Preview auth
`/api/history/{id}/preview.png` requires the bearer token, so a bare `<img src="/api/...">`
will 401. Mirror however the editor/recall pages already load authed images (likely
`fetch` → `blob` → `URL.createObjectURL`). Reuse that pattern; **don't** put the token in a
query string. Revoke object URLs on unmount/refresh to avoid leaks. Show a placeholder box
on 404 / load error.

### 3. `/history` page (`pages/history.ts`, `register('/history', mountHistory)` in `main.ts`)
- Reverse-chronological, paginated list (use `limit`/`offset`; a "Load more" button or
  prev/next is fine — keep it simple).
- Each row: thumbnail (authed, step 2), template name or a "Quick print" badge, compact
  `key=value` rendering of `field_values`, timestamp, a pin toggle, a Reprint button, a
  Delete button. Show a small "↩ reprint of #N" marker when `reprint_of` is set.
- Pin toggle → `pinHistory`; reflect the returned `pinned` state without a full reload.
- Reprint → `reprintHistory`; on success prepend/refresh so the new row appears; on 409
  show the server's error message (e.g. "label media no longer in catalog"). Reprint hits a
  real printer — make the button state clear (disable while in flight).
- Delete → confirm, then `deleteHistory`, remove the row.
- Filters: at minimum a template filter and a pinned-only toggle (date range optional —
  implement if cheap, else leave a TODO comment, don't fake it).
- Empty state when there are no jobs.
- Add a **History** nav link (`data-route="/history"`) alongside the existing nav entries.

### 4. Retention settings UI
- Add a settings page/section (check whether a settings page already exists; if so, extend
  it rather than creating a parallel one).
- Controls: a mode selector (`Keep forever` / `Keep last N` / `Keep N days`) that
  shows/enables the relevant number input (`retention_count` for `last_n`,
  `retention_days` for `last_days`). Load current values from `GET /api/settings`; save via
  `PUT /api/settings` (send only the changed keys). Confirm-on-save feedback.
- Make clear (helper text) that pinned prints are never pruned.

### Out of scope (do NOT build here)
- "Use as starting point for new template" (the history.md action that opens the editor) —
  deferred with the QR / canvas-elements work. A `// TODO` placeholder is fine; don't wire
  it.
- Any backend change. If you find an API gap, **stop and ask** rather than editing backend.

## Conventions to honor

- Vanilla TS, match the structure/idioms of existing `pages/*.ts` (no framework, no new
  deps). Reuse `apiFetch` and existing CSS classes; don't introduce a CSS framework.
- Changelog: concise user-facing entry under `## [Unreleased]` → `### Added` ("Print
  history page — browse, reprint, pin, and delete past prints; retention policy in
  settings").
- Verify the build: `cd frontend && npm run build` (and `npm run dev` for a manual click-
  through if a backend is reachable). Leave a one-line "run this to verify" in your summary.
- Commit on `dev`, prefix `feat:`, no `Co-authored-by:`, never push, never `git add -A`.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decisions in `docs/decisions.md` (e.g. the authed-image-loading
   approach, pagination style chosen).
4. Propose ONE commit covering the modified files (including this prompt's move). Present
   the file list + a one-line `feat:` message and ask `commit these as "<message>"? (y/n)`.
   On `y`, stage those specific paths and commit on `dev`. Never push.
