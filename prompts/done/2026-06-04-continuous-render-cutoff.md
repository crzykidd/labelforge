---
name: 2026-06-04-continuous-render-cutoff
status: completed
created: 2026-06-04
model: sonnet            # coding + reproduce
completed: 2026-06-04
result: Pre-render text subs from PIL metrics; continuous canvas height uses sub.height; die-cut unchanged
---

# Task: Fix continuous-label render cutting off (length under-extends with large text)

On a **continuous** roll (e.g. `62`, `62red`), the server render/preview of a template comes out
too short — the bottom is cut off. It's worse when the last line uses a large font: the label
doesn't extend all the way to fit it.

## Root cause (verify, then fix)

In `backend/labelforge/render/template.py`, both the continuous canvas height and the text raster
box trust Fabric's serialized `height`, which is a **browser font-metric** value. The server
draws text with **PIL**, whose pixel height for the same `fontSize` differs (and the gap widens
with font size). Two coupled symptoms:

- **Canvas too short (continuous):** `render_template` computes
  `canvas_h = max(top + height*scaleY) + _PADDING` (lines ~220-225) from Fabric's `height`. When
  PIL renders taller than that, the last line spills past `canvas_h` and is cut.
- **Text clipped inside its box:** `_render_text_element` sizes its sub-image to
  `box_h = height*scaleY` (line ~244) and draws into it; PIL text taller than `box_h` is clipped
  at the bottom even before compositing.

The fix is to size both from the **actual PIL-measured** text height, not Fabric's `height`.

## Before you start

- Read `docs/features/templates.md` (Canvas size — continuous length is content-driven
  server-side) and skim `docs/decisions.md` (server-side render decision).
- `code-checkin-and-pr`: work on `dev`, Conventional-Commits prefixes, no `Co-authored-by:`,
  docs ship with code, changelog entry required.
- Backend-only change (`render/template.py`). The frontend editor canvas uses a fixed working
  length (`DEFAULT_CONTINUOUS_LENGTH_DOTS`) and is *not* authoritative for print length — don't
  touch it; the server render is the source of truth for continuous length.

## Working tree check

Run `git status --porcelain` first; if `render/template.py` (or anything else this touches) has
uncommitted changes, list them and ask before editing. This prompt file is exempt.

## What to do

1. **Reproduce.** Run the app (`/run` skill or backend + `npm run dev`). Create/open a continuous
   (`62`) template with a couple of text lines where the **last** line uses a large font
   (e.g. 100+). Preview it (`POST /api/preview/{name}`) and confirm the bottom is cut off.
   Capture the rendered PNG so you can confirm the fix later.

2. **Measure real text height.** In `_render_text_element`, after building the PIL font, measure
   the rendered text box with `ImageDraw.Draw(scratch).multiline_textbbox((0, 0), text,
   font=pil_font, align=align, spacing=...)` (use the same `spacing` you pass to
   `multiline_text`, default 4). Size the sub-image to the measured extent (not Fabric `box_h`):
   - height = `ceil(bbox_bottom)` plus a few px descender allowance; width = `max(box_w,
     ceil(bbox_right))` so alignment within the box is preserved.
   - If the bbox top offset (`bbox[1]`) is non-zero, draw at `(0, -bbox[1])` so the ink isn't
     shifted down. Keep `left/top` paste position unchanged (Fabric `top` is still the element's
     top) so existing die-cut layouts don't move.

3. **Size the continuous canvas from real extents.** Change the `is_continuous` height calc so the
   bottommost extent uses the **measured** rendered height for text elements (reuse the same
   measurement helper), falling back to `height*scaleY` for non-text elements (line/rect/image,
   whose `height` is reliable). Cleanest: factor a small two-pass — compute each element's
   `(top + real_height)` once, take the max, add `_PADDING`. Avoid measuring the font twice per
   element if easy (cache or compute once), but correctness first.

4. **Keep die-cut behavior unchanged.** For non-continuous media `canvas_h` stays
   `label.dots_printable[1]`; text that overflows a fixed die-cut should still clip to the label
   (don't grow the canvas there). Only continuous media grows to fit.

5. **Verify, don't build a harness.** This project has **no** Python test setup (no
   `pyproject.toml`, no `tests/`, no pytest) — do **not** stand one up for this fix. Instead
   verify behaviorally: re-run the reproduction preview and confirm the full last line is visible
   and the continuous label extends to fit it, and confirm a die-cut template renders unchanged.
   A short throwaway `python -c`/scratch script calling `render_template` on a crafted
   continuous template to assert the output height covers the last line is fine as a sanity check,
   but don't commit a test file or a harness.

Acceptance: the reproduction template previews with the full last line visible and the label
extends to fit it; die-cut renders are unchanged.

## Conventions to honor

- One `fix:` commit (code + test + changelog). Keep the changelog entry user-facing.
- Changelog `[Unreleased]` → Fixed: continuous templates now extend to fit large text; previously
  a large last line was cut off because the render trusted the editor's font metrics instead of
  measuring the rasterized text.
- Match existing Python style (type hints, terse "why"-only comments). No new deps.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decision in `docs/decisions.md` (e.g. "continuous length measured from
   rasterized text, not Fabric metrics").
4. Propose ONE commit. Present the file list + one-line message; ask
   `commit these as "<message>"? (y/n)`. On `y`, stage those specific paths and commit on `dev`.
   Never `git add -A`. Never push.
