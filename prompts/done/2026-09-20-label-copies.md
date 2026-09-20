---
name: 2026-09-20-label-copies
status: completed
created: 2026-09-20
model: sonnet
completed: 2026-09-20
result: Added copies (1-100) to Quick Print, template print, and batch print, plus per-template default_copies; backend/frontend tests and typecheck/build pass; verified in the running app via screenshots.
---

# Task: Add a copies count to Quick Print and template print, plus a per-template default

Today every print produces exactly one label. Add an explicit **copies** count to both
print pages (default 1, remembered per browser), and give saved templates a
`default_copies` that seeds — but can be overridden at — print time.

**Copies is not batch/increment.** Batch prints N *different* labels (incrementing a
field); copies prints N *identical* labels. They are independent controls and they
multiply: 3 batch labels × 2 copies = 6 printed labels.

## Before you start

- Read `CLAUDE.md`, then `docs/architecture.md`, `docs/glossary.md`,
  `docs/features/quick-print.md`, `docs/features/templates.md`, `docs/features/api.md`.
- The relevant code is already located for you — don't re-explore from scratch:
  - Models: `backend/labelforge/models/__init__.py`
  - Schema + migrations: `backend/labelforge/db.py`
  - Template persistence: `backend/labelforge/templates/store.py`
  - Raster/send: `backend/labelforge/printer/client.py` (`print_image`, line ~250)
  - Routes: `backend/labelforge/routes/print.py`, `routes/template_print.py`,
    `routes/history.py`
  - Quick Print page: `frontend/src/pages/quick-print.ts`
  - Template print page: `frontend/src/pages/template-recall.ts` (**not** `templates.ts`,
    which is a one-line re-export of the list page)
  - Template editor: `frontend/src/pages/template-editor.ts`
  - Browser-persistence precedent to mirror: `frontend/src/lastLabel.ts`

### Traps that have already cost this project real time

- **The system `ruff` is 0.8.4; the project pins 0.16.8.** The stale binary reports false
  formatting failures on `backend/tests/`. Validate with the pinned one
  (`pip install -e ".[dev]"` in a venv). Three separate agents have reported those false
  failures as "pre-existing" — do not repeat that.
- **DOM assertions do not prove a UI works.** A Playwright click succeeds whether or not
  a human can see or reach the control. Screenshot the page and *look* at it.
  `playwright-core` plus cached Chromium at `~/.cache/ms-playwright/` works without
  installing browsers. Dev servers: backend `uvicorn` on **:8001** with `DISABLE_AUTH=true`
  and a scratch `DATA_DIR`; frontend Vite on **:5174** (5173 is taken by another project).

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files this
plan needs to modify. If any have uncommitted changes, list them and ask the user before
touching them. Surface unrelated dirty files once as awareness; don't block. This file is
exempt.

## Decisions already made — implement these, don't re-litigate

1. **Copies print as ONE raster job**, not N sequential jobs:
   `convert(qlr, [img] * copies, ...)`. The printer cuts between labels; no re-feed gap.
2. **Copies and batch are separate controls that multiply** (per the user's explicit call).
3. **Per-template remembered count wins over `default_copies`.** `default_copies` seeds the
   input the first time you print that template; your last-used count for that template
   wins thereafter. Quick Print keeps its own separate remembered value.
4. **Persist in `localStorage`** (survives across visits, matching `lf:last-label`), not
   `sessionStorage`.
5. **Reprint from history always prints exactly 1 copy.** Reprint means "give me that label
   again"; silently re-printing 5 wastes media. Pass `copies=1` explicitly — note that once
   `copies` is on `QuickPrintRequest`, `_reprint_quick` would otherwise inherit it from the
   stored payload.
6. **No history UI change.** `copies` lands in `payload_json` automatically; don't add a
   "×3" badge to the history list. Keeps scope tight and avoids contradicting decision 5.
7. **Bounds: `ge=1, le=100`** on every copies field. Batch keeps its 1000 cap, applied to
   the *total*: reject when `len(labels) * copies > 1000`.

## What to do

### Backend

1. `models/__init__.py`:
   - `copies: int = Field(1, ge=1, le=100)` on `QuickPrintRequest`, `PrintRequest`, and
     `BatchPrintRequest` (on batch it means copies *per* label).
   - `default_copies: int = Field(1, ge=1, le=100)` on `Template` and `TemplateCreate`;
     `default_copies: int | None = None` on `TemplateUpdate`.
2. `db.py`: add `default_copies INTEGER NOT NULL DEFAULT 1` to the `templates` block of
   `_SCHEMA`, **and** to `_migrate_templates()` following the existing `orientation`
   pattern exactly (idempotent `PRAGMA table_info` check, append to `added`, log).
3. `templates/store.py`: carry `default_copies` through `_row_to_template`,
   `create_template`'s INSERT, `update_template`'s `updates` dict, and `duplicate`'s INSERT.
4. `printer/client.py`: `print_image(..., copies: int = 1)`. Build `[img] * copies` for
   `convert()`. Clamp/validate `copies >= 1`. Leave the docstring's `sent` vs `printed`
   caveat intact.
5. `routes/print.py`: pass `copies=request.copies` to `print_image`.
6. `routes/template_print.py`:
   - `print_template`: pass `copies=body.copies`.
   - `batch_print`: pass `copies=body.copies` on each label's `print_image`; add the total
     guard from decision 7 next to the existing count checks, with a clear 400 message.
   - `preview_template`: unchanged — copies does not alter the rendered image.
7. `routes/history.py`: `_reprint_quick` and `_reprint_template` pass `copies=1` explicitly.

### Frontend

8. `types.ts`: add `copies` to the quick-print / print request types and `default_copies` to
   the `Template` / `TemplateCreate` / `TemplateUpdate` types.
9. `api.ts`: thread `copies` through `quickPrint`, `printTemplate`, and `batchPrint`.
   `printTemplate` already takes positional args — if adding another positional param makes
   the call sites unreadable, switch that function to an options object and update callers.
10. New `frontend/src/copies.ts`, mirroring `lastLabel.ts` (same try/catch-around-storage
    style, same terse comments — do not over-comment):
    - `getLastCopies(key: string): number | null` / `setLastCopies(key: string, n: number): void`
    - Key helpers for `lf:last-copies:quick` and `lf:last-copies:tpl:<template-name>`.
    - Guard against garbage in storage: non-numeric, `< 1`, or `> 100` reads return `null`.
11. `pages/quick-print.ts`: a **Copies** number input (`min=1 max=100`, default 1) in the
    form near the other controls. Seed from `lf:last-copies:quick`. Save on a *successful*
    print only. Include it in `buildRequest()`.
12. `pages/template-recall.ts`: a **Copies** number input that is **always visible** — it
    must not be gated on `canBatch`, since most templates have no increment fields. Seed
    from `lf:last-copies:tpl:<name>`, falling back to `tpl.default_copies`, falling back to
    1. Save on successful print. Send `copies` on **both** the single-print and batch paths.
    Leave the existing Batch fieldset's markup and behaviour alone.
13. `pages/template-editor.ts`: a **Default copies** number input (`min=1 max=100`) in the
    template settings area, persisted via `TemplateCreate` / `TemplateUpdate`.

### Tests

14. Add `backend/tests/test_copies.py` covering:
    - `copies` defaults to 1 on all three request models; out-of-range values are rejected.
    - `print_image` receives a list of exactly N images when `copies=N` (monkeypatch
      `convert` / `send` — follow the mocking style already used in
      `backend/tests/test_media_override.py`).
    - **Regression bar: `copies=1` must produce byte-identical instructions to today.**
      Nearly every existing use is `copies=1`; that path must not shift.
    - Batch total guard: `len(labels) * copies > 1000` → 400.
    - `default_copies` round-trips through create → get → update → duplicate.
    - The migration adds `default_copies` to a pre-existing DB built without it, and is
      idempotent on a second `init_db`.
    - Reprint prints 1 copy even when the stored payload says otherwise.
15. Run the full backend suite and the frontend typecheck/build.

### Verify in the real app

16. Start the dev servers, print-preview through both pages with the printer backend
    stubbed, and **screenshot both pages** to confirm the Copies input is visible and
    reachable without scrolling past the Print button. A DOM query passing is not evidence.

### Docs — same commit as the code

17. `docs/features/quick-print.md` — the Copies control and its `localStorage` persistence.
18. `docs/features/templates.md` — `default_copies`, and that it seeds rather than forces.
19. `docs/features/api.md` — `copies` on the three request bodies, `default_copies` on the
    template object, the batch total cap, and that reprint is always 1 copy.
20. `docs/PRD.md` — one line adding copies to scope. It is currently absent; the owner asked
    for this feature directly, so record it rather than leaving the docs contradicting code.
21. `CHANGELOG.md` under `## [Unreleased]` — user-facing release-note language. One entry
    for the feature. Do **not** write separate "Fixed" entries for anything that only ever
    existed unreleased within this task.

## Conventions to honor

- `docs/` is the source of truth — don't invent behaviour beyond this prompt; ask instead.
- No giant explainer comments. Comments only for non-obvious *why*. Match the terse style of
  `lastLabel.ts` and the existing route handlers.
- Keep the diff focused: do not refactor unrelated code, and do not touch the batch/increment
  logic beyond passing `copies` through.
- LF line endings only.

## When done

1. Update this file's frontmatter: `status`, `completed` (2026-09-20), `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the non-obvious decisions in `docs/decisions.md`, newest at top — at minimum:
   copies as a single multi-image raster job; copies × batch multiplying; reprint pinned to
   1 copy; per-template remembered count overriding `default_copies`.
4. You are a spawned agent: **do not commit.** Prepare the working tree, then report the
   exact file list plus a one-line `feat:` message back to the orchestrating session, which
   surfaces the `y/n` to the user. Never `git add -A`, never push, never auto-commit, no
   `Co-authored-by:` trailers (CLAUDE.md forbids them even when the harness suggests one).
