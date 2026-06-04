---
name: 2026-06-03-template-preview-and-media-edit
status: completed
created: 2026-06-03
model: sonnet            # coding slice
completed: 2026-06-03
result: preview route now fills missing fields with sample values; color control always visible with Red disabled on mono
---

# Task: Fix editor Preview with variables and surface the color control

Two follow-ups on the canvas editor (`/templates/{name}`), after the Save As + two-color
slice (commit c960e92) landed:

1. **Preview fails when the template has a variable** (e.g. `{type}`). Preview returns
   *"Missing required field: 'type'"* — you can't preview layout without inventing values.
2. **The text-color control is invisible on most templates** — it only appears for two-color
   media (`62red`), and is fully `hidden` otherwise, so the feature is undiscoverable.

(Changing an existing template's media is already covered by **Save As** — pick a new label
when cloning — so it is intentionally out of scope here.)

Do them in order (preview → color discoverability). Both are small and independent.

## Before you start

- Read `docs/features/templates.md` (esp. "locked to media", canvas size, field detection),
  `docs/glossary.md`, and `docs/decisions.md`.
- **Placeholder syntax is single-brace `{name}`** (`backend/labelforge/templates/fields.py:5`,
  regex `\{([a-zA-Z0-9_]+)\}`). The user typed `{{type}}`; the regex still matches the inner
  `{type}`, so `type` becomes a required field. Part 1 must work for the correct `{type}` form;
  optionally add a one-line syntax hint in the editor (see Part 1, step 4) to stop the
  double-brace confusion.
- `code-checkin-and-pr`: work on `dev`, Conventional-Commits prefixes, no `Co-authored-by:`,
  docs ship with code, changelog entry required.

## Working tree check

Run `git status --porcelain` first; if any file this plan touches has uncommitted changes, list
them and ask before editing. This prompt file is exempt.

## Key files

- `backend/labelforge/routes/template_print.py` — `_apply_defaults` (raises on missing
  required), `preview_template` (`POST /preview/{name}`, line ~120). **Print paths must keep
  requiring real values — only preview gets sample-fill.**
- `backend/labelforge/templates/fields.py` — `detect_fields`, `resolve_content`
- `backend/labelforge/models/__init__.py:94` — `PrintRequest { fields }`
- `frontend/src/pages/template-editor.ts` — `doPreview` (sends empty `fields`, line ~255),
  the `#text-color` control + `labelColorCapable` gating (lines ~57, 128, 174, 190),
  `initEditor`, the toolbar, `showSaveAsModal`
- `frontend/src/editor/canvas.ts` — `initCanvas`, `addTextElement`
- `frontend/src/labels.ts` — `mountLabelMediaSelect`
- `frontend/src/api.ts` — `previewTemplate`, `updateTemplate`, `duplicateTemplate`

## What to do

### Part 1 — Preview must not require field values

The editor's Preview is a *layout* check; it should render with sample values, never demand
real ones. Fix server-side so the behavior is consistent for any caller previewing.

1. In `preview_template` (`template_print.py`), stop calling the strict `_apply_defaults`.
   Instead fill values so nothing is missing: for each field in `tmpl.field_schema`, use the
   provided value if present, else `field.default` if set, else a **sample = the field name
   itself** (so `{type}` renders as the literal text `type`). Never raise "Missing required
   field" from the preview route. Add a small helper (e.g. `_apply_sample_defaults`) next to
   `_apply_defaults`; leave `_apply_defaults` unchanged for the print routes.
2. Any field value the caller *did* pass still wins (so the recall/print preview that passes
   real values keeps showing them).
3. Confirm `resolve_content` won't raise: since every detected field now has a value, the
   `ValueError("Missing required field")` path in `fields.py` can't trigger from preview.
4. (Nice-to-have, same commit) Add a tiny hint in the editor toolbar or status area noting the
   placeholder syntax is `{fieldname}` (single braces) — this is what tripped up `{{type}}`.

Acceptance: open a template containing `{type}`, click Preview with no values entered — the PNG
renders (showing `type` where the variable is) instead of an error.

### Part 2 — Make the color control discoverable

Right now `#text-color` is `hidden` unless the media is two-color, so users never learn it
exists. Always show it; gate only the *red* option on media capability.

1. Remove the blanket `hidden` on the color control + its separator (`template-editor.ts:57-61,
   128-131`). Always render it.
2. On mono media: keep the **Red** `<option>` present but `disabled`, with a `title`/tooltip
   like "Requires a two-color label (e.g. 62red)". Black is the only selectable value.
3. On two-color media: Red is selectable (current behavior).
4. Keep the existing selection-sync (`updateFontControls`) and `addTextElement` default-fill
   logic working for both states.

Acceptance: on a `62` template the color dropdown is visible with Red greyed-out + tooltip; on
`62red` Red is selectable and applies.

## Conventions to honor

- Separate commits per part is fine (`fix:` preview, `feat:` color discoverability).
- Changelog `[Unreleased]` entries for each. Note the container-image rebuild requirement for the
  frontend changes, as prior entries do.
- Match existing vanilla-TS style (`esc()`, plain DOM) and Python style (type hints, terse "why"
  comments only). No framework.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decisions in `docs/decisions.md`.
4. Propose commits (per part). Present file list + one-line message(s); ask
   `commit these as "<message>"? (y/n)`. On `y`, stage those specific paths and commit on `dev`.
   Never `git add -A`. Never push.
