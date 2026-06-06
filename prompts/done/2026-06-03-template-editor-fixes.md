---
name: 2026-06-03-template-editor-fixes
status: completed
created: 2026-06-03
model: sonnet
completed: 2026-06-03
result: All three parts implemented — canvas portrait fix (DEFAULT_CONTINUOUS_LENGTH_DOTS 400→1000), Save As toolbar button with modal, full two-color RGB rendering + red text control gated to color-capable media. One deviation: canvas width could not be visually reproduced (headless env); fix is based on scale-math analysis.
---

# Task: Fix template editor — canvas width, Save As (retarget media), red text

Three issues on the canvas editor (`/templates/{name}`), all reported together after the
recent "text renders now" fixes:

1. **Canvas is too wide / wrong aspect** — the editing area looks stretched; the width
   regressed somewhere.
2. **No way to choose a different label** from the editor. (NB: this control was never in
   the editor — see the design note below. The faithful fix is to surface the documented
   **Save As** flow, not a live media-mutation dropdown.)
3. **No way to set text to red** — two-color rolls (`62red` / DK-2251) support black+red,
   but there's no color control and the renderer is hardcoded mono. The user wants the
   **full** slice: UI control + RGB render + actual two-color print.

Do these as three separate, independently-committable parts in this order (width → Save As
→ red). If context runs short, stop after a completed part and update this prompt's status
so the remainder can be picked up.

## Before you start

- Read `docs/features/templates.md` (canvas size, toolbar, "locked to media" rule),
  `docs/architecture.md`, and `docs/glossary.md`. Skim `docs/decisions.md` for the existing
  two-color note.
- Read the existing two-color print decision context: `render_template` in
  `backend/labelforge/render/template.py` has a docstring saying *"Two-color (62red)
  rendering is a later slice; always renders mono."* — Part 3 re-opens that. It needs an
  ADR entry.
- **Design constraint (do NOT violate):** `templates.md` states a template is *locked to
  its label media*; the sanctioned way to use a design on different media is **Save As
  (clone to a new name + new media)**. The documented toolbar is: undo, redo, zoom, fit,
  save, **save-as**, preview, print. So Part 2 = add Save As, **not** a control that mutates
  the current template's media. If you become convinced a live media switch is genuinely
  wanted, STOP and ask — it needs a PRD/ADR change first.
- This project adopts `code-checkin-and-pr`: work on `dev`, Conventional-Commits prefixes,
  no `Co-authored-by:`, docs ship in the same commit as the code. Changelog entry required.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files this
plan touches. If any have uncommitted changes, list them and ask before touching. This
prompt file is exempt.

## Key files

- `frontend/src/pages/template-editor.ts` — editor page (toolbar, bootstrap, save/preview)
- `frontend/src/editor/canvas.ts` — `initCanvas`, `addTextElement`, scale math, custom props
- `frontend/src/style.css` — `#app.editor-mode` (max-width 1100px), `.editor-canvas-wrap`,
  `.editor-canvas-inner` (~lines 18, 302–315)
- `frontend/src/labels.ts` — `mountLabelMediaSelect` (reuse for the Save As modal media picker)
- `frontend/src/pages/templates-list.ts` — `showNewTemplateModal` (copy its modal pattern)
- `frontend/src/api.ts` / `frontend/src/types.ts` — add a `duplicateTemplate` API call; the
  `LabelEntry.color` field (`1` = two-color media) gates the red control
- `backend/labelforge/render/template.py` — `render_template`, `_render_text_element`,
  `_paste_onto`, `_canvas_color_to_l` (Part 3)
- `backend/labelforge/printer/client.py:259-272` — print path already does
  `convert(..., red=red)` reading the red plane from an RGB image; **no change needed there**,
  it just needs `render_template` to actually emit red pixels
- `backend/labelforge/routes/preview.py`, `routes/template_print.py` — preview/print entry
  points; verify the preview PNG carries color (it should, once the renderer returns RGB)
- `backend/labelforge/routes/templates.py:82` + `templates/store.py:150` — the
  `POST /api/templates/{name}/duplicate` endpoint already exists (used by Save As)

## What to do

### Part 1 — Fix the canvas width/aspect regression

1. Reproduce first. Run the app (use the `/run` skill or `npm run dev` in `frontend/` against
   the backend) and open the editor on **both** a die-cut label (e.g. `29x90`) and a
   continuous roll (`62`). Screenshot each. The canvas should match the label's aspect ratio,
   scaled to fit the viewport, with no horizontal overflow.
2. Diagnose. Likely suspects, in order:
   - `initCanvas` scale math in `canvas.ts:26-41`:
     `scale = Math.min(1, (containerW - 48) / labelW, maxDisplayH / labelH)`. For a 62mm roll
     `labelW≈696`; with `editor-mode` container ≈1100 the width term exceeds 1 so scale clamps
     to 1 and the canvas renders at native 696px — check whether that, combined with the
     continuous default length (`DEFAULT_CONTINUOUS_LENGTH_DOTS = 400`), is what reads as
     "too wide / wrong shape."
   - `getContainerWidth()` timing — it reads `canvasWrap.clientWidth` inside the post-fetch
     bootstrap; confirm the element is laid out (non-zero, ~1100) at that point, not 0/garbage.
   - `#app.editor-mode { max-width: 1100px }` vs the canvas — is the *page* what got wide, or
     the *canvas*? Fix whichever is actually wrong.
3. Fix so the displayed canvas matches the label proportions and fits without overflow.
   Acceptance: a wide-short address label looks wide and short; a tall `29x90` looks tall and
   narrow; no horizontal scrollbar at normal window width.

### Part 2 — Save As in the editor toolbar (retarget media the sanctioned way)

1. Add a **Save As** button to the editor toolbar (between Save and Preview is fine).
2. On click, open a modal mirroring `showNewTemplateModal` in `templates-list.ts`: slug-
   validated new name + a label-media picker via `mountLabelMediaSelect`. Pre-fill the media
   with the current template's media.
3. Add `duplicateTemplate(name, { name, label_media })` to `api.ts` calling
   `POST /api/templates/{name}/duplicate` (endpoint already exists). The current editor must
   be **saved first** (so the clone copies the latest canvas) — reuse the existing save path.
4. On success, navigate to the new template's editor (`/templates/{newName}`).
5. Also surface the **current media** read-only in the toolbar (e.g. next to the title) so the
   user can see what they're editing. Do **not** add a dropdown that mutates the open
   template's media.

### Part 3 — Full two-color (red) text

**Backend (`render/template.py`):**
1. Branch the canvas mode on media color: if `label.color == 1` (two-color), render onto an
   **RGB** white canvas; otherwise keep the current mode-`L` path unchanged (preserve existing
   mono behavior exactly).
2. Add a `_canvas_color_to_rgb(fill)` helper mapping element `fill` → `(0,0,0)` (black) or
   `(255,0,0)` (red). Treat `#ff0000`, `#f00`, `red`, `rgb(255,0,0)` as red; everything else as
   black. Pure `(255,0,0)` is what `convert(red=True)` routes to the red plane.
3. `_render_text_element` currently returns an `L` coverage mask (text=0 on 255). Keep
   producing that mask, then composite a solid color through it: on RGB,
   `canvas.paste(Image.new("RGB", sub.size, rgb), (left, top), mask=ImageOps.invert(sub))`.
   Refactor `_paste_onto` to take a target color (or add an RGB variant) so rotation/antialias
   handling is shared. Text color comes from the element's `fill`.
4. Lines and rects: on the RGB path, honor their color too (`draw.line(..., fill=rgb)`, rect
   fill/outline). Don't regress the mono path.
5. Update the `render_template` docstring — remove "always renders mono"; describe the
   two-color path.

**Preview/print:**
6. Verify `POST /api/preview/{name}` (Part of `routes/preview.py` / `template_print.py`) returns
   a PNG that shows red for two-color media. If a threshold/`_threshold_preview` step is in the
   template-preview path, make sure it doesn't crush color to mono (that helper is for
   quick-print exact-bitmap, not template color preview).
7. The print path (`printer/client.py`) already promotes to RGB and passes `red=True` for
   two-color media — confirm an actual red-plane print results now that the renderer emits red.
   Test print (or at least raster-convert) a `62red` template with one black and one red text
   element.

**Frontend (`template-editor.ts` + `canvas.ts`):**
8. Add a text-color control to the toolbar (a Black/Red toggle or `<select>`). Show/enable it
   **only when the loaded label is two-color** (`label.color === 1`); hide or disable for mono
   media (mono = black only).
9. On change, set the active text object's `fill` to `#000000` / `#ff0000` and `renderAll()`.
   `fill` is a standard Fabric prop already included in `toJSON()` — no custom property needed.
10. Sync the control in `updateFontControls` (reflect the selected object's current fill), and
    make `addTextElement` default new text to the currently-selected color.

## Conventions to honor

- One concern per commit; three commits is fine (`fix:` width, `feat:` Save As, `feat:` red
  text) — or fewer if you prefer, but keep docs with their code.
- Changelog: add `[Unreleased]` entries; update the **Known Issues** block — two-color text now
  prints (QR/barcode remain the open item).
- Update `docs/features/templates.md`: document the red text control, that two-color media
  enables it, and that Save As lives in the toolbar.
- Match existing TS style (no framework, `esc()` for HTML, vanilla DOM) and Python style
  (type hints, terse "why" comments only).
- Note the container-image rebuild requirement for any frontend change in the changelog, as
  prior entries do.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the non-obvious decisions in `docs/decisions.md` — at minimum an ADR re-opening
   **two-color template rendering** (supersedes the "later slice" note), and the decision that
   media retargeting stays **Save As only** (template locked to media), not a live switch.
4. Propose commits (per part). Present the file list + one-line message(s); ask
   `commit these as "<message>"? (y/n)`. On `y`, stage those specific paths and commit on
   `dev`. Never `git add -A`. Never push.
