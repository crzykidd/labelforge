---
name: 2026-09-18-template-editor-usability
status: completed
created: 2026-09-18
model: sonnet            # coding task (frontend TS + CSS)
completed: 2026-09-18
result: Added elements panel, drag/resize clamping + Bring-all-on-canvas repair, CSS-background grid with edge/centerline/grid snap, keyboard shortcuts, and 50-entry undo/redo restoring via loadCanvasJSON; frontend build/backend checks pass.
---

# Task: Make the template editor usable — recover lost elements, grid/snap, undo

The canvas editor has **no canvas event handling at all** beyond selection and
text-change. There is no bounds logic, no keyboard handling, and no undo. An
element dragged off the canvas cannot be selected (nothing to click) and
`deleteSelected` requires a selection, so it is unrecoverable — and it is not
merely invisible:

- it **still renders server-side** at its off-canvas coordinates, and
- on continuous media a stray element inflates `bottommost` in
  `render/template.py:296-310`, so auto-length silently prints a very long label.

Fix the data-loss problem first, then add the precision and safety tools.

## Before you start

- Read `docs/features/templates.md`, `docs/glossary.md`, and `CLAUDE.md`. Do not
  load the rest of `docs/`.
- **Frontend-only.** Do not modify anything under `backend/`.
- **No new dependencies.** `frontend/package.json` has only `fabric`. Everything
  here is Fabric API + DOM + CSS.

### Two traps — get these wrong and the bug is expensive to find

1. **The grid must never enter `canvas_json`.** If it is drawn as Fabric
   objects, `canvas.toJSON()` serializes it and the backend will faithfully
   render grid lines onto printed labels. Draw the grid as a **CSS background**
   on `.editor-canvas-inner` (`style.css:376`), never as canvas objects.
2. **Snap and clamp must work in label-pixel coordinates, not display pixels.**
   `initCanvas` (`canvas.ts:222-236`) sets a zoom of
   `min(1, (containerW - 48) / labelW, 600 / labelH)`, so the two differ almost
   always. Fabric object coordinates are already in label pixels (the zoom is a
   viewport transform) — verify this before writing the math and do not
   double-apply the scale.

### Current state (exact anchors)

- `frontend/src/pages/template-editor.ts:179-181` — the only canvas handlers:
  `selection:created`, `selection:updated`, `selection:cleared`.
- `frontend/src/editor/canvas.ts:193` — `text:changed` syncs
  `labelforge_raw_content`.
- `canvas.ts:341` — `deleteSelected` requires an active selection.
- `canvas.ts:352` — `getCanvasJSON` is `canvas.toJSON()`; custom props are
  auto-included via `CUSTOM_PROPS` registration at :22.
- `canvas.ts:358` — `loadCanvasJSON` re-attaches text handlers and regenerates
  QR/barcode placeholders after `loadFromJSON`.
- Toolbar markup: `template-editor.ts:55-95`. Editor CSS: `style.css:325-388`.
- There are **no** keyboard handlers anywhere in `template-editor.ts`.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files
this plan needs to modify. If any of those files have uncommitted changes, list them
and ask the user before touching them. Surface unrelated dirty files once as
awareness; don't block. This file (the handoff prompt itself) is exempt.

Note: `prompts/2026-09-18-template-orientation.md` covers template rotation and
may already be completed on `dev`. If an `orientation` control and transposed
canvas dimensions exist, **build on them** — clamp, snap and grid all work off
`canvas.width`/`canvas.height`, so they should be orientation-agnostic. Do not
re-implement or alter orientation behavior.

## What to do

### 1. Elements panel — the fix for lost elements

A list beside the canvas showing every object: type label (Text / QR / Barcode /
Line / Rect / Image) plus a short content snippet (text content, or payload for
QR/barcode). Clicking a row selects that object on the canvas.

This is what makes an off-canvas element recoverable, so it must list objects
regardless of position. Re-render the list on `object:added`, `object:removed`,
`object:modified`, and `text:changed`. Use the existing `isTextType`,
`isQrType`, `isBarcodeType` helpers (`canvas.ts:32-56`) for classification —
do not re-derive type logic.

Mark rows whose object currently lies outside the canvas bounds with a visible
warning affordance, so an existing broken template shows the problem plainly.

### 2. Clamp on drag

An `object:moving` handler that keeps the object's bounding box inside the
canvas. Account for `originX`/`originY` — elements may be centered
(`render/template.py` has `_origin_top_left` precisely because centered origins
are in use), so do not assume top-left. Use Fabric's bounding-rect API rather
than raw `left`/`top` arithmetic.

Also clamp on resize/scale (`object:scaling`) so an element can't be grown out
of bounds.

### 3. "Bring all on-canvas" repair action

A toolbar button that clamps every out-of-bounds object back inside and selects
the first one it moved. This repairs templates that are already broken; clamping
alone only prevents new breakage.

### 4. Grid overlay + snap

- Grid drawn as a CSS background (see trap 1). Default spacing 10 label pixels,
  scaled to display by the canvas zoom so it lines up visually.
- Toggle button in the toolbar; remember the choice in `localStorage` (follow
  the existing pattern in `frontend/src/lastLabel.ts`).
- Snap-to-grid on move and resize when the toggle is on.
- Snap to canvas edges and to horizontal/vertical centerlines within a few
  pixels, with a brief visual guide line while snapping. Centerline snapping is
  the one people actually want for labels — don't skip it.

### 5. Keyboard

There are none today, so add: arrow keys nudge the selection by 1 label pixel,
Shift+arrow by 10, `Delete`/`Backspace` removes the selection, `Escape`
deselects.

**Critical:** these must not fire while a text element is in inline editing mode,
or typing in a text box will move/delete it. Check Fabric's editing state on the
active object before handling any key, and ignore keys when the event target is
an `<input>` or `<select>` in the toolbar.

### 6. Undo / redo

A bounded snapshot stack (50 entries) of `getCanvasJSON(canvas)`.

- Push a snapshot on `object:added`, `object:removed`, `object:modified`, and
  `text:changed` (debounce text so a snapshot isn't pushed per keystroke — one
  per editing session is right).
- `Ctrl/Cmd+Z` undo, `Ctrl/Cmd+Shift+Z` redo. Toolbar buttons too, disabled when
  their stack is empty.
- **Restore via the existing `loadCanvasJSON` (`canvas.ts:358`), not a bare
  `loadFromJSON`.** It re-attaches the text `changed` handlers and regenerates
  QR/barcode placeholders; a bare `loadFromJSON` silently breaks both. This is
  the single most important detail in this section.
- Guard against the restore itself pushing a new snapshot (a re-entrancy flag),
  or undo will loop.
- `loadCanvasJSON` is async — make sure rapid Ctrl+Z presses can't interleave
  and corrupt the stack.

### 7. Layout and docs

- The panel needs somewhere to live. `.editor-canvas-wrap` (`style.css:366`) is
  the container; a two-column layout with the panel on the right is fine. Keep
  it working at narrow widths — the app is used on a laptop, so don't let the
  canvas get squeezed to nothing.
- `docs/features/templates.md` — document the editor interaction model: the
  elements panel, clamping, grid/snap, keyboard shortcuts, undo depth. The
  existing editor description is thin and should cover this properly.

## Conventions to honor

- `CHANGELOG.md` entry under `## [Unreleased]`, user-facing language.
- Docs ship in the same commit as the code.
- Match the existing vanilla-TS style — no framework, no state library. Keep new
  canvas helpers in `frontend/src/editor/canvas.ts` and page wiring in
  `frontend/src/pages/template-editor.ts`, consistent with how the QR and
  barcode features were split.
- `template-editor.ts` is already 551 lines. If a new module is cleaner (e.g.
  `editor/history.ts` for undo), create one rather than growing it further.
- No giant explainer comments; comment only non-obvious *why*.
- `npm run build` in `frontend/` must pass (it runs `tsc`).
- Work on the `dev` branch.

## Manual verification before reporting

These are behavioral and not unit-testable; check them by hand:

1. Drag an element hard toward every edge — it cannot leave the canvas.
2. Load a template that already has an off-canvas element: the panel lists it,
   flags it, clicking selects it, and "Bring all on-canvas" recovers it.
3. Inline-edit a text element and type arrow keys and Backspace — the element is
   edited, not moved or deleted.
4. Add a QR element, undo, redo — the placeholder bitmap still renders and the
   payload survives (this is the `loadCanvasJSON` trap).
5. Save, reload the page, Preview — output is unchanged and **no grid lines
   appear** on the rendered label.

## When done

1. Update this file's frontmatter: set `status` (completed/failed), `completed`
   (the date), and `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/`
   (failure).
3. Record non-obvious decisions in `docs/decisions.md`, newest at top —
   especially the CSS-background grid choice, the clamp behavior with centered
   origins, and the undo snapshot strategy.
4. **You are a spawned agent: do not commit.** Prepare the working tree, then
   report back the file list and a proposed one-line `feat:` commit message.
   Never `git add -A`, never push, never auto-commit.
