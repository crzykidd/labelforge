---
name: 2026-09-18-template-orientation
status: completed
created: 2026-09-18
model: sonnet            # coding task (backend Python + frontend TS)
completed: 2026-09-18
result: Added template orientation (standard/rotated); canvas rotated 270° (not 90°, see docs/decisions.md) at render time; editor transposes design canvas with no-reflow toggle.
---

# Task: Add a rotated orientation option to templates

Quick Print can already print rotated 90° (`orientation: "standard" | "rotated"`),
but templates cannot — `render_template` always rasterizes at the print-head
width and has no rotation step. Add the same orientation concept to templates:
you design upright in the editor, and the rendered/printed output is rotated 90°.

The whole point is that **the editor canvas is transposed** so text is typed in
natural reading orientation, while Preview shows the as-printed (sideways)
bitmap.

## Before you start

- Read `docs/features/templates.md`, `docs/architecture.md`, `docs/glossary.md`,
  and `CLAUDE.md`. Do not load the rest of `docs/`.
- **Rotate the finished canvas, not individual elements.** Every per-element
  renderer stays untouched. This mirrors how Quick Print already does it and is
  the single most important constraint in this prompt.
- No new dependencies, backend or frontend.

### The existing implementation to mirror

- `backend/labelforge/render/text.py:90-91` — the entire Quick Print rotation:
  ```python
  if orientation == "rotated":
      img = img.rotate(90, expand=True)
  ```
- `backend/labelforge/models/__init__.py:44` — `orientation: Literal["standard",
  "rotated"] = "standard"` on the quick-print request model. Reuse this exact
  literal type and default for templates.
- `backend/labelforge/settings_store.py:22-25` — the `default_orientation`
  setting already exists. **Do not** wire templates into it; template
  orientation is stored per template, not taken from settings.

### Why the print path already works

`backend/labelforge/printer/client.py:275-280` passes `rotate="0"` and relies on
the rendered image's width being the print-head width. A design canvas of
`(length × head_width)` rotated 90° with `expand=True` becomes
`(head_width × length)` — so the rotated output satisfies that invariant by
construction. Verify this holds in your implementation; do not change
`client.py`.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files
this plan needs to modify. If any of those files have uncommitted changes, list them
and ask the user before touching them. Surface unrelated dirty files once as
awareness; don't block. This file (the handoff prompt itself) is exempt.

Note: `prompts/2026-09-18-template-editor-usability.md` is expected to be present
and untracked. It is a separate task — **do not touch it or its subject matter.**

## What to do

### 1. Persistence

- `backend/labelforge/db.py:23-33` — add `orientation TEXT NOT NULL DEFAULT
  'standard'` to the `templates` table in `_SCHEMA`.
- Add a `_migrate_templates(conn)` function mirroring `_migrate_print_jobs`
  (`db.py:44-61`) exactly: read `PRAGMA table_info(templates)`, `ALTER TABLE
  templates ADD COLUMN orientation ...` when absent, log what was added. Call it
  from `init_db` next to the existing migration call. Existing templates must
  keep working and default to `standard`.

### 2. Models

`backend/labelforge/models/__init__.py` — add `orientation: Literal["standard",
"rotated"] = "standard"` to `Template` and `TemplateCreate`, and
`orientation: Literal["standard", "rotated"] | None = None` to `TemplateUpdate`.

### 3. Store

`backend/labelforge/templates/store.py` — thread the new column through
`_row_to_template` (:21), the `create_template` INSERT (:81), and the
`duplicate` INSERT (:166). Check how `update_template` (:101) builds its
`set_clause` and make sure `orientation` participates the same way the other
optional fields do.

### 4. Renderer — the fiddly part

`backend/labelforge/render/template.py`, `render_template` (:251):

- Design dimensions are the **transposed** label dimensions when
  `orientation == "rotated"`: design width is the label's length axis, design
  height is `label.dots_printable[0]` (the head width).
- **Continuous auto-length flips axis.** Today `canvas_h` is content-driven from
  `bottommost` (:296-310) while `canvas_w` is fixed. Rotated, the content-driven
  dimension becomes the design **width** — derived from the rightmost element
  extent, the mirror of the current `bottommost` logic. Die-cut media stays
  fixed on both axes, just transposed.
- Rotate once at the very end, immediately before returning, with
  `img.rotate(90, expand=True)` — after all elements are drawn and after the
  two-color handling. Confirm the rotation direction produces upright text when
  the label is read normally; if 90 is wrong, use 270 and say so in the ADR.
- Two-color RGB and mono L images must both rotate correctly. `Image.rotate`
  handles both, but the fill color for exposed corners must stay white
  (`255` / `(255,255,255)`) — check that `expand=True` on an exact 90° turn does
  not introduce a black border.

### 5. Editor

`frontend/src/pages/template-editor.ts`:

- Add an orientation control to the toolbar (a `<select>` with Standard /
  Rotated 90°, next to the media badge). Follow the existing toolbar markup
  style at :55-95.
- When orientation is rotated, pass **transposed** dimensions to `initCanvas`
  (`canvas.ts:222`), which is called at :170 with `label.dots_printable`. The
  canvas you design on is the transposed one.
- Changing orientation on an existing template **must not move or reflow
  elements** — coordinates are preserved. Show a one-time inline warning in
  `#editor-status` that the layout will need adjusting. Auto-reflow is
  explicitly rejected: visibly wrong beats mysteriously rearranged.
- Orientation must be included in save/create/update calls, and restored when an
  existing template loads (:459).

`frontend/src/types.ts:70-85` — add `orientation` to `Template` and
`TemplateCreate`.

Preview (`#btn-preview`) needs no special handling: it shows the server render,
which is already rotated. That is the intended "type upright, preview sideways"
behavior — confirm it reads that way and don't add a client-side rotation.

### 6. Tests

Add to `backend/tests/` (a new `test_render_orientation.py` alongside the
existing `test_render_origin.py`):

- A rotated die-cut template renders to exactly the same dimensions as the
  equivalent standard one with axes swapped.
- A rotated **continuous** template's length grows with content along the
  correct axis.
- Rotated output width equals `label.dots_printable[0]` (the print-head
  invariant from `client.py`).
- An existing template with no stored orientation defaults to `standard` and
  renders byte-identically to before this change. This is the regression guard
  that matters most.

### 7. Docs

- `docs/features/templates.md` — add an orientation section: what it does, that
  the editor canvas is transposed, that toggling preserves coordinates, and how
  it relates to (but does not read from) the quick-print `default_orientation`
  setting. Also update the element/data-model description to include the new
  field.
- `docs/features/api.md` — `orientation` is now part of the template create /
  update / response shape. Keep it accurate; that doc was corrected in v0.1.4
  specifically because it had drifted.

## Conventions to honor

- `CHANGELOG.md` entry under `## [Unreleased]`, user-facing language.
- Docs ship in the same commit as the code.
- No giant explainer comments; comment only non-obvious *why* (the axis flip and
  the rotation direction both qualify).
- Run `ruff check .`, `ruff format --check .`, `mypy backend`, and `pytest -q`
  before reporting. Frontend: `npm run build` in `frontend/` must pass.
- Work on the `dev` branch.

## When done

1. Update this file's frontmatter: set `status` (completed/failed), `completed`
   (the date), and `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/`
   (failure).
3. Record non-obvious decisions in `docs/decisions.md`, newest at top —
   especially the rotation direction, the continuous axis flip, and the
   no-reflow-on-toggle choice.
4. **You are a spawned agent: do not commit.** Prepare the working tree, then
   report back the file list and a proposed one-line `feat:` commit message.
   Never `git add -A`, never push, never auto-commit.
