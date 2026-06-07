---
name: 2026-06-07-render-honor-origin
status: completed
created: 2026-06-07
model: sonnet
completed: 2026-06-07
result: Added _origin_top_left helper applied at all 3 render sites; 3 regression tests pass; docs/changelog/ADR updated.
---

# Task: Make the server renderer honor Fabric `originX` / `originY`

The server render (and print) places every element using its `left`/`top` as the
top-left corner, ignoring `originX`/`originY`. Fabric stores `left`/`top` *relative
to the origin* — when `originX: 'center'`, `left` is the element's **center x**, not
its left edge. Templates that were saved with center origins therefore render
shifted right (and down) by half the element's size, fanning wider elements out
further than narrow ones. This is the "everything fans out / not left-aligned"
bug seen on the `testt` template; its three text objects all have
`originX: 'center', originY: 'center'`.

The fix is server-side and origin-agnostic, so it corrects every existing template
(any origin) and all future ones. Do **not** mutate stored templates or change the
frontend in this task.

## Before you start

- Read `docs/architecture.md` and `docs/features/templates.md` (esp. the
  "canvas_json" / coordinate sections, ~lines 84–108).
- The only code file to change is `backend/labelforge/render/template.py`. Plus a
  new/extended test, a `docs/features/templates.md` note, `CHANGELOG.md`, and a
  `docs/decisions.md` ADR entry.
- Coordinate system: `canvas_json` is in label-dot coordinates at print DPI. Element
  box size = `width * scaleX` by `height * scaleY` (already computed as `box_w` /
  `box_h` in `render_template`).
- Context for *why* this is server-only: nothing in `frontend/src` sets
  `originX`/`originY`; the center origins on `testt` came from an older build or a
  manual interaction. Making the server honor origin is the robust fix regardless of
  provenance. (Confirmed: Fabric 7.4.0; other templates serialize `left`/`top`.)

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files
this plan needs to modify. If any have uncommitted changes, list them and ask before
touching them. Surface unrelated dirty files once as awareness; don't block. This
prompt file is exempt.

## What to do

1. In `backend/labelforge/render/template.py`, add a small helper that converts an
   element's stored `left`/`top` into the true **top-left** corner given its origin
   and box size:

   ```python
   def _origin_top_left(obj: dict, left: int, top: int, box_w: int, box_h: int) -> tuple[int, int]:
       """Translate Fabric left/top (origin-relative) to the top-left corner.

       Fabric stores left/top relative to originX/originY. The renderer pastes at the
       top-left, so shift by half/full box for center/right (x) and center/bottom (y).
       Defaults (left/top) are a no-op.
       """
       ox = str(obj.get("originX", "left")).lower()
       oy = str(obj.get("originY", "top")).lower()
       if ox == "center":
           left -= box_w // 2
       elif ox == "right":
           left -= box_w
       if oy == "center":
           top -= box_h // 2
       elif oy == "bottom":
           top -= box_h
       return left, top
   ```

2. Apply it at **all three** sites that consume `left`/`top`:

   - **Main draw loop** (`for i, obj in enumerate(objects)` ~L289). After `box_w` /
     `box_h` are computed, call `left, top = _origin_top_left(obj, left, top, box_w, box_h)`
     *before* the type dispatch. This single translation then flows into the text
     paste, the `rect` paste, and the `line` endpoints (`x1 = left + ...`). Use the
     **Fabric box** (`box_w`/`box_h` = `width*scaleX` / `height*scaleY`) for the
     offset — not the PIL-measured `real_w` of the text sub-image. For left-aligned
     text the text starts at the box's left edge, which is exactly the corner we just
     computed, so pasting the sub there is correct.

   - **Continuous-height calc** (~L268–279). The `bottommost` accumulation uses raw
     `top`. Compute the origin-adjusted top there too (an `originY: 'center'` element's
     real top is `top - h/2`), so continuous canvas length is correct. Reuse `h`
     (PIL height for text, Fabric height otherwise) as the `box_h` for the offset, and
     `box_w` from `width*scaleX`.

   - **`detect_overflow`** (~L205–222). It compares `top + h` against printable height
     using raw `top`. Apply the same origin-adjusted top so overflow detection is
     accurate for center/bottom-origin elements.

3. Keep behavior identical for the common `left`/`top` case (the helper is a no-op
   there) — verify the existing templates that already use `left`/`top` are unchanged.

4. Add a regression test (there are currently **no** render tests). Create
   `backend/tests/test_render_origin.py`:
   - Build a minimal `Template` with one text element at a known center point
     (`originX: 'center', originY: 'center'`, e.g. `left=200, top=100`, a fixed
     `width`/`height`, `DejaVuSans-Bold`, on a die-cut media like `62x29`).
   - Render it, then render an equivalent element expressed with `originX: 'left',
     originY: 'top'` at the computed top-left (`left - width//2`, `top - height//2`).
   - Assert the two output images are pixel-identical (or that the inked bounding box
     matches within ±1px). This proves origin handling reduces to the left/top case.
   - Use whatever font is guaranteed present in CI (DejaVuSans-Bold ships in the
     image / `/usr/share/fonts/truetype`); if tests must run without it, skip with a
     clear reason rather than hard-failing.

5. Run the backend test suite and `ruff`/`mypy` as the repo configures them; fix any
   issues without bypassing hooks.

## Conventions to honor

- `docs/features/templates.md` element list (~L92) names `left, top, width, height,
  angle, scaleX, scaleY` but omits origin. Add a short sentence noting the renderer
  honors `originX`/`originY` (defaulting to `left`/`top`) so `left`/`top` are
  interpreted as Fabric does. Doc change ships in the **same commit** as the code.
- `CHANGELOG.md`: add a concise, user-facing entry under `## [Unreleased]`, e.g.
  `fix: render templates at the correct position when elements use centered origins`.
- Commit prefix `fix:`. No `Co-authored-by:` trailers. Work on `dev`. Commit, don't push.

## When done

1. Update this file's frontmatter: `status`, `completed` (2026-06-07 or actual date),
   `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the decision in `docs/decisions.md` as an ADR entry: "Server renderer
   honors Fabric origin" — why (Fabric stores left/top origin-relative; some templates
   carry center origins), and that the fix is server-only and origin-agnostic.
4. Propose ONE commit covering the modified files (including this prompt's move).
   Present the file list and a one-line `fix:` message; ask `commit these as
   "<message>"? (y/n)`. On `y`, stage those specific paths and commit on `dev`. Never
   `git add -A`. Never push.
