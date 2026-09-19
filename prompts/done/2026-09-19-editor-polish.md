---
name: 2026-09-19-editor-polish
status: completed
created: 2026-09-19
model: sonnet            # coding task (frontend TS + CSS)
completed: 2026-09-19
result: Backstopped the clamp on object:modified/mouse:up (issue #42), moved per-selection controls into a fixed-height contextual row so the toolbar never reflows, added Fabric snapAngle/snapThreshold rotation snapping plus a Rotate 90° button, and (per mid-session user feedback) made the elements-panel "off canvas" flag a per-element recovery button with "Bring all on-canvas" relocated to the panel header, shown only when needed. All 14 Playwright checks pass against the live app; frontend build and backend gate (ruff/mypy/pytest) are clean.
---

# Task: Editor polish — fix the clamp leak, stop the toolbar jumping, snap rotation to 90°

Three defects found by using the editor after the usability work landed (`1c539ef`).
All three are frontend-only and belong in one commit.

1. **Bounds clamping leaks** — GitHub issue #42. An element dragged hard past a
   corner ends up outside the label and persists that way.
2. **The toolbar reflows on every selection change**, pushing Save/Preview onto a
   second row and shifting the whole canvas down. The page visibly jumps.
3. **Element rotation is undiscoverable and doesn't snap.** The Fabric rotate
   handle works and the backend honors `angle`, but nothing snaps to 90° and
   there's no obvious way to rotate.

## Before you start

- Read `docs/features/templates.md`, `CLAUDE.md`, and GitHub issue #42
  (`gh issue view 42`).
- **Frontend-only.** Do not modify anything under `backend/`. The backend already
  honors per-element `angle` (`render/template.py:355` and `:122-126`) — verified
  working, leave it alone.
- **No new dependencies.**
- You are on `dev`. Stay on it.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files
this plan needs to modify. If any have uncommitted changes, list them and ask before
touching them. Surface unrelated dirty files once; don't block. This file is exempt.

## 1. Fix the clamp leak (issue #42)

**Reproduced behavior:** drag an element hard past the bottom-right corner and it
persists at e.g. `left 605.08, top 235.76 → right 748, bottom 290` on a 696×271
label. Unclamped it would be `right 996`, so clamping is partially working but does
not hold the boundary. The overshoot tracks the drag step size and grows with total
travel.

Established facts — do not re-derive:
- `object:moving` IS registered (1 listener) and DOES fire (30 times in a drag).
- `currentDesignW/H` are correct (696/271).
- `obj.getBoundingRect()` returns scene coordinates correctly at rest.

**Suspected cause (unproven):** in the `object:moving` handler
(`template-editor.ts:251-254`), `applyMoveSnap` mutates the object's position and
then `clampObjectToCanvas` calls `obj.getBoundingRect()` — which may be reading
geometry that lags the current frame because nothing called `obj.setCoords()` in
between.

Do this:
- Call `obj.setCoords()` before measuring in `clampObjectToCanvas` and
  `isObjectOutOfBounds` (`canvas.ts:93` and `:104`), and after `applyMoveSnap`
  mutates position.
- Add a **backstop**: clamp again on `object:modified` (and/or `mouse:up`), so the
  final committed position is always in bounds regardless of any frame-lag subtlety
  during the drag. This is the part that must not be skipped — it's what guarantees
  the invariant.
- Verify by driving the app, not by reasoning (see "Verification" below). The
  element's bounding box must end inside the label after a deliberately violent
  drag, and must still be inside after Save + reload.

Keep the existing recovery path working — the elements panel flagging and
"Bring all on-canvas" both function correctly today and are verified; don't
regress them.

## 2. Stop the toolbar reflowing

Selecting a text element unhides `#sep-color` and `#text-color` via
`showTextControls` (`template-editor.ts:296-299`); QR and barcode controls do the
same. The toolbar grows, wraps, and everything below shifts.

Do this:
- Give the contextual per-element controls **their own dedicated row** below the
  main toolbar, always present with a **fixed height** so it never changes the
  layout. Its contents swap by selection type (text / QR / barcode / nothing).
  When nothing is selected, show a short hint rather than collapsing the row.
- Make the main toolbar non-reflowing: it must never wrap. Save / Preview / Save As
  must not move when selection changes. If it overflows at narrow widths, scroll it
  horizontally rather than wrapping.
- The canvas must not shift vertically when selection changes. This is the
  acceptance criterion — measure it (see Verification).

## 3. Rotation: snap to 90°, and make it discoverable

**Use Fabric's built-in angle snapping** rather than writing custom math:
`obj.snapAngle = 90` with `obj.snapThreshold = 8` (degrees) gives exactly the
requested behavior — snaps to 0/90/180/270 when within ~8° of them, free rotation
everywhere else. Apply it to:
- every element created by `addTextElement`, `addQrElement`, `addBarcodeElement`
  (`canvas.ts`), and
- every object restored in `loadCanvasJSON` (`canvas.ts:358`), so loaded templates
  get it too.

Put the snap values in one exported constant so there's a single place to tune them.

Discoverability — add both:
- A **"Rotate 90°"** button in the new contextual row that turns the current
  selection by 90° per click (mod 360). This is the obvious affordance for "I want
  this text sideways" and needs no handle-dragging.
- A small **angle readout** while rotating (reuse the snap-guide overlay mechanism
  in `grid-snap.ts` if that's a natural fit), so it's clear rotation is happening
  and where it snapped.

Note in `docs/features/templates.md` that the rotate handle exists, that it snaps
to 90° within ~8°, and that free rotation is available outside that window.

**Do not confuse this with template orientation.** Per-element `angle` rotates one
element; the orientation dropdown rotates the whole label. Both must keep working
independently — check that rotating an element on a `rotated` template still
renders correctly.

## Verification — drive the app, don't just reason

A headless-browser harness already exists and works; reuse it rather than starting
over. It lives in the session scratchpad at
`/tmp/claude-1000/-home-manderse-projects-labelforge/2529705e-2a7e-42e0-a3b8-0cb91007e40c/scratchpad/qa/`
(`qa2.mjs` is the full checklist, `probe*.mjs` are focused experiments). It uses
`playwright-core` against the cached Chromium at
`/home/manderse/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`.

Servers are already running and must be reachable:
- backend: `http://127.0.0.1:8001` (uvicorn, `DISABLE_AUTH=true`, scratch DATA_DIR)
- frontend: `http://localhost:5174` (Vite dev server)

If they aren't up, restart them the same way (see the scratchpad logs
`backend.log` / `vite.log` for the exact invocations).

**Two traps that already cost time — read these before writing assertions:**
- **Fabric 7 defaults object origin to `center`.** Assertions about bounds must be
  origin-aware, mirroring the backend's `_origin_top_left`. `qa2.mjs` has a correct
  `bbox()` helper — reuse it.
- **An element that doesn't move is not proof of clamping.** Confirm the drag
  actually grabbed the object (position changed from its seed) before concluding
  the clamp held.

Must pass, driving the real UI:
1. Violent drag past the bottom-right corner → bounding box inside the label, and
   still inside after Save + page reload.
2. Same off the top-left (negative coords).
3. Canvas Y-position does not change when selecting text / QR / barcode / nothing.
4. Rotate handle near 90° snaps exactly to 90; rotating to ~45° stays ~45 (free).
5. "Rotate 90°" button sets `angle` to 90 then 180 on a second click, and the
   server preview still returns 200.
6. The elements panel still flags off-canvas elements and "Bring all on-canvas"
   still recovers them.

Also run `npm run build` in `frontend/` (tsc + vite) and confirm the backend gate
is untouched: `ruff check .`, `ruff format --check .`, `mypy backend`, `pytest -q`.

Report honestly which checks you actually observed versus reasoned about.

## Conventions to honor

- `CHANGELOG.md` entry under `## [Unreleased]`, user-facing language.
- Docs ship in the same commit as the code.
- Record non-obvious decisions in `docs/decisions.md`, newest at top — especially
  the real root cause of the clamp leak once you find it, and the contextual-row
  layout choice.
- Match the existing vanilla-TS style; keep helpers in `frontend/src/editor/*`.
- No giant explainer comments.

## When done

1. Update this file's frontmatter: `status`, `completed`, `result`.
2. Move this file into `prompts/done/` (plain `mv` — it is untracked) or
   `prompts/failed/`.
3. **You are a spawned agent: do not commit.** Prepare the working tree and report
   back: files changed, a proposed one-line `fix:` commit message, the verification
   output, which checks were observed vs reasoned, and any deviations.
   Never `git add -A`, never push, never auto-commit.
