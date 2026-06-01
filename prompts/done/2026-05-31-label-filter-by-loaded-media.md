---
name: 2026-05-31-label-filter-by-loaded-media
status: completed
created: 2026-05-31
model: sonnet
completed: 2026-05-31
result: Added mountLabelMediaSelect shared control with Show all / Loaded in printer toggle; wired up to Quick Print and New Template modal; tsc + build pass.
---

# Task: "Show all" vs "Loaded in printer" filter on the label-media selector

Add a mode toggle to the label-media selector: **Show all** (default) lists the whole
catalog as today; **Loaded in printer** queries the printer and narrows the options to
the roll actually mounted. Build it as a **shared control in `labels.ts`** so every
selector that uses it gets the behavior.

## Before you start

- Read `CLAUDE.md`. Load `docs/features/printer-status.md`, `docs/features/label-catalog.md`,
  `docs/architecture.md`, `docs/glossary.md`.
- `run_pipeline` first (vexp rule — don't grep/glob). Pass this task in.
- Work on `dev`. Commit, don't push. No `Co-authored-by:` trailers.
- This is **frontend-only** — the backend already provides everything (see Verified facts).

## Working tree check

Run `git status --porcelain` and cross-reference the files below. There may be an
uncommitted `.gitignore` change unrelated to this work — surface it once as awareness,
don't touch it. If any *frontend* file below is dirty, list it and ask before editing.
This prompt file is exempt.

## Decisions already made (do not relitigate)

- **Scope: build it shared in `labels.ts`.** A reusable control both current selectors
  (and future ones) call — not a per-page copy.
- **Default mode is "Show all."** Loaded mode is opt-in per page load; no persistence
  required.
- **Match rule = same physical dimensions ("exact id + color sibling").** A label
  matches the loaded media iff `label.tape_size[0] === loaded.width_mm &&
  label.tape_size[1] === loaded.length_mm`. This naturally yields the mono + two-color
  pair for one roll (e.g. loaded `62` → `62` **and** `62red`, both `tape_size [62, 0]`)
  and excludes die-cut variants of the same width (`62x29` is `[62, 29]`). Match on
  `tape_size`, **not** by string-munging the `red` suffix.

## Verified facts (already in the codebase — don't rebuild)

- `frontend/src/api.ts`:
  - `getLabels(): Promise<LabelEntry[]>` → `GET /api/labels`.
  - `getPrinterStatus(): Promise<{ ok: boolean; body: Record<string, unknown> }>` →
    `GET /api/printer/status`. `ok` is false on 503/unreachable. On success `body`
    includes `loaded_media` which is either `null` or
    `{ id, display_name, width_mm, length_mm, color_capable }` (see
    `backend/labelforge/routes/printer.py`).
- `frontend/src/types.ts` `LabelEntry` has `id`, `tape_size: [number, number]`
  (= `[width_mm, length_mm]`, length 0 = continuous), `color`, `supported`,
  `incompatible_reason`, `display_name`.
- `frontend/src/labels.ts` — `buildLabelOptionsHtml(labels)` is the SINGLE place
  `<option>` markup is rendered (renders unsupported entries `disabled` + tooltip), and
  `firstSupportedId(labels)` exists for default-selection fallback.
- Call sites that pick label media: `frontend/src/pages/quick-print.ts` and the New
  Template modal in `frontend/src/pages/templates-list.ts`. (Template editor has no
  media selector.)

## What to do

### labels.ts — the shared control
1. Add a match helper, e.g. `matchesLoadedMedia(label, loaded): boolean` returning
   `label.tape_size[0] === loaded.width_mm && label.tape_size[1] === loaded.length_mm`.
2. Add a reusable mount function (name your call, e.g.
   `mountLabelMediaSelect(opts)`), that owns:
   - a **mode toggle** (segmented buttons or radios: "Show all" | "Loaded in printer"),
     defaulting to "Show all", rendered adjacent to the `<select>`;
   - the `<select>`, populated via the existing `buildLabelOptionsHtml(...)` on the
     **filtered** list (Show all = full list; Loaded = matches only);
   - an inline **status/notice** line for the Loaded-mode edge cases below;
   - selection management: an `onChange(id)` callback and the ability to read/set the
     current value. When switching to Loaded mode, if the current selection isn't in the
     filtered set, auto-select the first match.
   Keep `buildLabelOptionsHtml` and `firstSupportedId` as the rendering/fallback
   primitives — the control composes them.
3. Loaded-mode behavior: call `getPrinterStatus()` **once** when the user switches to
   Loaded (cache the result for the control's lifetime — do not poll). Then:
   - `ok` + `loaded_media` present → filter to matches; if zero matches (loaded roll
     isn't in the catalog), show notice "Loaded media not in catalog — showing all" and
     fall back to the full list.
   - `ok` + `loaded_media` null → notice "Printer reports no media loaded" + fall back
     to Show all.
   - `!ok` (unreachable/timeout) → notice "Couldn't reach printer — showing all" and
     revert the toggle to Show all.
   Never leave the user with a silently empty selector.

### Wire up the call sites
4. Refactor `quick-print.ts` and `templates-list.ts` (New Template modal) to use the
   shared control instead of calling `buildLabelOptionsHtml` directly. Preserve current
   behavior in Show-all mode: the `firstSupportedId` default/restore guard, and the
   disabled/greyed unsupported rendering must still work.

### Types / styles / docs
5. If helpful, add a `PrinterStatus` / `LoadedMedia` interface to `types.ts` and type
   `getPrinterStatus` against it (optional but preferred over `Record<string, unknown>`).
6. Style the toggle + notice in `frontend/src/style.css`, matching existing controls.
7. Update the relevant feature doc — add a short "loaded-media filter" note to
   `docs/features/label-catalog.md` (UI behavior) and/or `docs/features/printer-status.md`
   (UI section already mentions the loaded-media chip). Ship doc edits in the SAME commit.
8. `CHANGELOG.md` `## [Unreleased]`: one concise user-facing line.
9. Only add an ADR to `docs/decisions.md` if a non-obvious decision arises beyond the
   dimensional match rule (which is captured here).

## Verification

- `cd frontend && npx tsc --noEmit && npm run build` must pass.
- Manual (`npm run dev`): toggle to "Loaded in printer" with the printer reachable →
  options narrow to the mounted roll (and its red/mono sibling); switch back → full
  list. With the printer off/unreachable → notice shows and it stays on Show all.

## When done

1. Update this file's frontmatter: `status`, `completed` (date), `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decision in `docs/decisions.md` as an ADR.
4. Propose ONE commit on `dev` covering the modified files (incl. the prompt move).
   Present the file list + a one-line `feat:` message and ask
   `commit these as "<message>"? (y/n)`. Stage those specific paths only — never
   `git add -A`, never push.
