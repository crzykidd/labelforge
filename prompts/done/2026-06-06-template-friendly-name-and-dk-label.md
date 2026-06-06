---
name: 2026-06-06-template-friendly-name-and-dk-label
status: completed
created: 2026-06-06
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-06-06
result: frontend-only; friendly name modal (slug auto-derived), DK-part label in list, display_name threaded through editor create flow
---

# Task: Template friendly names + DK-part label in the list

Two template UX improvements (frontend-only — the backend already supports both):

1. **Friendly name.** When creating a template the user should type a human name like
   `Spool Label`; the URL slug (`spool-label`) is derived from it automatically. The friendly
   name is stored as `display_name` and shown in the list and editor.
2. **Real label in the list.** The templates list currently shows the raw media id
   (`<code>62x29</code>`). Show the Brother **DK part number with size and a Red suffix**
   instead — e.g. `DK-1209 (62×29mm)` for a die-cut, `DK-2251 (62mm) Red` for two-color.

## Before you start

- **No backend changes needed.** `Template` / `TemplateCreate` / `TemplateUpdate` already
  carry `display_name` (`backend/labelforge/models/__init__.py`), and `store.create_template`
  already persists it (defaulting `display_name = data.name` when omitted). The list already
  renders `t.display_name || t.name`. The gaps are entirely in the frontend.
- Anchors to read:
  - `frontend/src/pages/templates-list.ts` — the New Template modal (collects `Name (slug)`
    at ~line 129, validates against `SLUG_RE`, then navigates
    `/templates/<name>?new=1&media=<media>` — creation is deferred to the editor's first Save)
    and the list table (media cell at ~line 64).
  - `frontend/src/pages/template-editor.ts` — `parsePath()` reads `new`/`media` from the URL;
    `createTemplate({ name, label_media, canvas_json })` at ~line 218 (the create-on-save path)
    and the editor title/media badge at ~lines 47-48.
  - `frontend/src/labels.ts` — `LabelEntry` shape; `tape_size: [width_mm, length_mm]`,
    `color` (1 = two-color), `brother_part`, `display_name`. Reuse for the DK formatter.
  - `frontend/src/api.ts` — `createTemplate`, `getLabels`; confirm the frontend `TemplateCreate`
    type in `types.ts` includes `display_name` (add it if missing).
- Work on `dev`. Conventional-Commits, no `Co-authored-by:`, docs ship with code.

## Working tree check

`git status --porcelain` first. This touches `frontend/src/pages/templates-list.ts`,
`frontend/src/pages/template-editor.ts`, maybe `frontend/src/api.ts` / `types.ts`, plus docs.
If anything unexpected is dirty, list it and ask.

## What to do

### 1. Friendly name on create

- In the New Template modal, relabel the input from **"Name (slug)"** to **"Name"** with
  placeholder `Spool Label`. The user types a free-form friendly name.
- Add a small `slugify(s)` helper: `s.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-')
  .replace(/^-+|-+$/g, '')`. Show the derived slug live as a read-only hint beneath the input
  (e.g. *"URL: `spool-label`"*), so the user sees what it becomes.
- Validate the **derived slug** (non-empty, matches the existing `SLUG_RE`
  `^[a-z0-9][a-z0-9-]*$`); show the error against the friendly input. Keep the OK button gated
  on a valid slug + a selected media. Server-side uniqueness still applies on create.
- Thread the friendly name through to creation. Since creation is deferred to the editor,
  pass it in the navigation URL alongside `media`, e.g.
  `/templates/<slug>?new=1&media=<media>&display_name=<encodeURIComponent(friendly)>`.
- In `template-editor.ts`: parse `display_name` from the URL in `parsePath()`, and include it
  in the create call — `createTemplate({ name, display_name, label_media, canvas_json })`.
  Make sure the frontend `TemplateCreate` type allows `display_name?`.
- Editor title: show the friendly `display_name` (fall back to the slug) instead of the bare
  slug. The slug can remain visible as secondary text if it reads cleanly; don't overbuild.
- Out of scope: renaming `display_name` after creation (the model supports it via
  `TemplateUpdate`, but leave a rename UI for later — note it in the changelog as not-yet).

### 2. DK-part label in the list

- In `templates-list.ts`, fetch the catalog once (`getLabels()`) when rendering the list and
  build an `id → LabelEntry` map. (The list currently only fetches templates.)
- Add a `formatMediaLabel(label: LabelEntry): string`:
  - `part = label.brother_part || label.display_name || label.id`
  - size from `tape_size = [w, h]`: die-cut → `(${w}×${h}mm)`; continuous (`h` is `0`) →
    `(${w}mm)`
  - red suffix: `label.color === 1 ? ' Red' : ''`
  - result e.g. `DK-1209 (62×29mm)`, `DK-2251 (62mm) Red`
- Render the media cell using this instead of the raw id. **Fallback**: if `label_media` isn't
  in the catalog (deleted/unknown media), show the raw id in `<code>` as today so nothing
  breaks. Keep the cell readable (it need not be `<code>` for the formatted case).

## Conventions to honor

- LF endings. Reuse `LabelEntry`/`getLabels`; don't duplicate catalog logic. Match existing
  templates-list / editor style.
- **Docs**: `docs/features/templates.md` — note that New Template takes a friendly name (slug
  derived), and the list shows the DK part number + size (+ Red for two-color).
- **Changelog** (`### Added` under `## [Unreleased]`): friendly template names (type a name,
  slug auto-derived, shown in list + editor); the template list now shows the Brother DK part
  number with size and a Red marker for two-color media instead of the raw media id. Note the
  container-rebuild requirement.

## When done

1. Verify: `cd frontend && npm run build` compiles; `ruff check . && mypy backend && pytest -q`
   still green (no backend change, but confirm nothing regressed). Manually: create a template
   named `Spool Label` → slug `spool-label`, list shows the friendly name + e.g.
   `DK-1209 (62×29mm)`; a `62red` template shows `… (62mm) Red`. One-line "run this to verify".
2. Update this file's frontmatter (`status`, `completed` = 2026-06-06, `result`).
3. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
4. ADR only if a non-obvious decision arose (likely none — note in the summary if so).
5. Stage everything but **do not commit** — leave it staged-and-ready and report: the file
   list, the proposed one-line commit message
   (`feat: friendly template names and DK-part label in the template list`), verification
   results, and any decisions/deviations. The human reviews and commits.
