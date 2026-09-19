---
name: 2026-09-19-field-lists
status: done
created: 2026-09-19
model: sonnet            # coding task (backend Python + frontend TS)
completed: 2026-09-19
result: |
  Implemented. New `field_lists` table (backend/labelforge/db.py) + store
  (backend/labelforge/field_lists/store.py) + CRUD router
  (backend/labelforge/routes/field_lists.py) at /api/field-lists, name-keyed
  by field name (same charset as {placeholder}). FieldSpec.type gained "list"
  alongside the existing "enum". Fixed a blocking bug in
  PUT /api/templates/{name}: it recomputed field_schema from the stored
  schema whenever canvas_json was present, discarding any field_schema the
  caller sent in the same request — which is every editor Save — so panel
  edits could never persist; now merges onto whichever schema the caller
  sent, falling back to stored only when absent.
  Editor: new FIELDS panel (frontend/src/editor/fields-panel.ts) below
  ELEMENTS lists every field with type/required/default/increment controls;
  type=list shows an E button opening a right-side drawer to add/remove/
  reorder the *global* list's values (explicit "this is global" warning);
  type=enum gets an inline comma-separated values input. Panel schema is
  sent with canvas_json on every Save/Preview and replaced from the server's
  response afterward (server is the source of truth for detected fields).
  Recall (template-recall.ts) renders type=list as a <select> populated from
  GET /api/field-lists/{name}, degrading to free text on 404 (list never
  created or since deleted) — same as an unset enum, never an error.
  Verified with Playwright screenshots (FIELDS panel, E button appearing,
  drawer empty/filled/after-save states, recall selects) — actually viewed,
  not just DOM-asserted. Core proof (editing the global "room" list changes
  what two different templates offer at recall) confirmed both via a
  screenshot-backed Playwright script and a backend pytest
  (test_two_templates_share_edits_to_the_same_global_list).
  Backend: 13 new tests in backend/tests/test_field_lists.py (CRUD
  round-trip, dup/404s, name validation, auth, the shared-list proof,
  absent-list is not an error, delete is non-retroactive vs. print history,
  enum unchanged, three tests pinning the update_template fix). Full suite
  85/85 green; ruff check/format clean (pinned 0.16.8); mypy clean;
  `npm run build` (tsc + vite) clean.
  Docs: docs/PRD.md (In scope), docs/features/api.md (new Field lists
  section + corrected an inaccurate "enum values enforced server-side"
  validation claim while touching that list), docs/features/templates.md
  (new "Value lists (list vs enum)" section, field-detection rewrite to
  match the FIELDS panel's actual update-on-Save behavior, corrected the
  "increment requires type: number" claim), docs/glossary.md (Field list
  entry + Field type list), CHANGELOG.md Unreleased, docs/decisions.md
  (global-keyed-by-name / two-flavor / non-retroactive-delete decisions +
  the update_template fix, newest at top).
---

# Task: Reusable value lists for variable fields, and a Fields panel to author them

A variable can currently only be free text at recall time. Add **named, reusable
value lists**: mark `{room}` as a list field and recall shows a dropdown of the
allowed rooms. The list is global and keyed by the field name, so every template
using `{room}` shares it — edit it once, every room label picks it up. A
different set means a different field name (`{room2}`).

Operator's words: *"if I select room as my variable it is global, so if I wanted
a different list I could do room1list or something"* and *"we have a small E for
edit button that pulls out a drawer to add remove values and saves."*

## What already exists (verified — build on it, do not duplicate)

- `FieldSpec` (`backend/labelforge/models/__init__.py:59`) already has
  `type: Literal["text","number","date","enum"]` and `enum_values: list[str]`.
- **Recall already renders a `<select>`** for `type == "enum"`, with options from
  `enum_values`, honouring `required` and `default`
  (`frontend/src/pages/template-recall.ts:423-439`).
- `merge_schema` (`backend/labelforge/templates/fields.py`) already preserves
  user edits to a field's spec when placeholders change.

**What is missing is the authoring UI.** `grep field_schema frontend/src/` returns
two read-only hits — there is no way to set a field's type, values, `required`,
`default` or `increment` from the editor. `increment` in particular is read at
recall but can never be set, even though batch/increment printing is a v1 PRD
success criterion. This task closes that gap.

## Design decisions (settled — implement these, do not re-litigate)

- **Two list flavours coexist.** `type: "list"` resolves its options from a
  **global list named after the field**. `type: "enum"` keeps today's
  per-template `enum_values` for a one-off set. Global for reuse, per-template
  for genuinely template-specific values.
- **Global lists are keyed by name** and stored independently of any template.
- **Deletion is not retroactive.** Print history stores literal `field_values`
  already, so past prints keep what they printed. Recall shows the list as it is
  now. No validation sweep over templates, no dangling-reference state. A list
  field whose named list does not exist renders as a free-text input, not an
  error.

## What to do

### 1. Storage and API for global lists

- New table via the schema in `backend/labelforge/db.py`. Follow the existing
  idempotent migration pattern (`_migrate_print_jobs` / `_migrate_templates`) —
  read `PRAGMA table_info`, add what is missing, log it. Existing databases must
  upgrade in place.
- A small store module beside `templates/store.py`. Name is a list name
  (validate like template names — see `_validate_name`), value is an ordered
  list of strings.
- CRUD routes under `/api/field-lists` following the shape and auth of the
  existing routers in `backend/labelforge/routes/`. Every route is protected by
  `require_auth` like the rest of the API except the documented open ones.
- Update `docs/features/api.md`. That doc was corrected in v0.1.4 specifically
  because it had drifted from the implementation — keep it accurate.

### 2. Fields panel in the editor

A **FIELDS** section below the existing ELEMENTS panel on the right
(`frontend/src/pages/template-editor.ts`, styles in `frontend/src/style.css`).

- Lists the placeholders detected in the template. Reuse the existing detection
  rather than re-implementing it — `detect_fields` is the backend source of
  truth, and the template's `field_schema` already round-trips.
- Per field, allow setting: **type** (text / number / date / list / enum),
  **required**, **default**, and **increment**.
- For `type: "list"`, show a small **E** button that opens a **drawer** over the
  canvas to add / remove / reorder values and save them to the global list. The
  drawer edits the *global* list, so make that unmistakable in the UI — changes
  affect every template using that field name.
- Saving the template must persist `field_schema`. `PUT /api/templates/{name}`
  already accepts it via `TemplateUpdate`.

### 3. Recall

Render `type: "list"` as a `<select>` populated from the global list, alongside
the existing `type: "enum"` path. Keep both working. Follow the existing
`fieldInput` structure; do not fork it into two divergent renderers.

### 4. Tests

- Global list CRUD round-trips through the API.
- A template with a `list` field recalls with the current list's values, and
  picking one prints that value.
- Editing a global list changes what two different templates offer — this is the
  whole point of global lists, so prove it.
- A `list` field whose named list is absent degrades to free text.
- Deleting a list does not break an existing template or its history rows.
- `enum` (per-template) still works unchanged.
- The existing suite stays green.

### 5. Docs — both the PRD and the feature doc

The operator explicitly asked for both.

- `docs/PRD.md` — add to **In scope** a line for reusable value lists: a variable
  can be restricted to a named, user-managed list of allowed values shared across
  templates.
- `docs/features/templates.md` — document the **field schema** properly. It is
  currently undocumented: field types, required/default/increment, the two list
  flavours, the global-list keying rule, and the non-retroactive deletion
  semantics.
- `CHANGELOG.md` under `## [Unreleased]`, user-facing. Mention that the Fields
  panel also makes `increment` settable for the first time.
- `docs/decisions.md`, newest at top — the global-keyed-by-name choice, why both
  list flavours exist, and the non-retroactive deletion rule.

## Working tree check

`git status --porcelain` first; cross-reference and ask before touching anything
already modified. This file is exempt. You are on `dev`.

Note: a wrap-max-lines change may have landed just before this task and also
touched `template-editor.ts` and its contextual control row. Build on whatever
is there; do not revert or duplicate it.

## Verification

- `ruff check .`, `ruff format --check .`, `mypy backend`, `pytest -q`, and
  `npm run build` in `frontend/`.
- **Use the project's pinned ruff** (`pip install -e ".[dev]"` in a venv →
  0.16.8). The bare `ruff` on PATH is 0.8.4 and reports false formatting failures
  on `backend/tests/`.
- This is UI-heavy, so DOM assertions are not sufficient. A Playwright harness
  and reusable scripts live in
  `/tmp/claude-1000/-home-manderse-projects-labelforge/2529705e-2a7e-42e0-a3b8-0cb91007e40c/scratchpad/qa/`
  (`qa2.mjs`, `shot*.mjs`) using `playwright-core` against the cached Chromium at
  `/home/manderse/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`.
  **Take a screenshot of the Fields panel and the drawer and actually look at
  it.** A click on a selector succeeds whether or not a human can find or reach
  the control — that exact gap previously hid Save and Preview being scrolled
  off-screen.
  Servers: backend on :8001 (`DISABLE_AUTH=true`, scratch `DATA_DIR`), frontend
  Vite on :5174. Restart them if they are down; see the scratchpad logs for the
  invocations used.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. Move it to `prompts/done/` (plain `mv` — untracked) or `prompts/failed/`.
3. **You are a spawned agent: do not commit.** Prepare the tree and report back:
   files changed, a proposed one-line commit message, verification output,
   which checks you observed versus reasoned about, and deviations. Never
   `git add -A`, never push, never auto-commit.
