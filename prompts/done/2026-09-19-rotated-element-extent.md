---
name: 2026-09-19-rotated-element-extent
status: done
created: 2026-09-19
model: sonnet            # coding task (backend Python)
completed: 2026-09-19
result: >
  Fixed. Added _rotated_aabb helper (backend/labelforge/render/template.py) used by
  continuous auto-length, detect_overflow, and _paste_onto's pivot. angle == 0 output
  verified byte-identical (existing 43 tests + new fixture-based regression tests pass).
  6 new tests in backend/tests/test_render_rotation.py. Docs and decisions.md updated.
  Not committed — tree left for orchestrator to review and commit.
---

# Task: Make the renderer account for element rotation in extent and position

Rotating a text element 90° (the editor's "Rotate 90°" button, or the rotate
handle) produces a wrong print: on continuous media the label length does not
grow to fit the rotated text, so the text is clipped; the content also sits
lower than the editor shows, leaving a large blank area.

Operator report: *"if I just hit rotate 90 button and leave everything the same
on a working label, it puts the text at the bottom of the label not the top so
it prints a huge blank spot. When we rotate 90 it should start the print at the
top of the label and it should be variable length based on the length of text."*

**This is backend-only.** The editor is fine — it is the server renderer that
ignores `angle` when computing extents.

## Measured evidence (reproduced; do not re-derive)

Text "Spool 1234", fontSize 48, box 400×60 at left=20 top=20, DejaVuSans-Bold.

Continuous 62mm (auto length):
```
angle=  0   canvas=696x99   ink=(24,20)-(319,66)   blankTop=20  blankBot=33
angle= 90   canvas=696x99   ink=(213,23)-(250,99)  blankTop=23  blankBot=0   ← clipped
```
The canvas height is **identical** at both angles. Auto-length used the
element's unrotated height (~46px) while the rotated text needs ~295px.

Die-cut 62x29 (fixed 696×271):
```
angle=  0, origin left/top       ink=(24,20)-(319,66)    blankTop=20 blankBot=205
angle= 90, origin left/top       ink=(213,23)-(250,148)  blankTop=23 blankBot=123
angle= 90, origin center/center  ink=(341,0)-(378,233)   blankTop=0  blankBot=38
```

## Root causes

1. **Extent ignores rotation.** In `render_template`
   (`backend/labelforge/render/template.py`), the continuous auto-length loop
   uses the element's unrotated `height × scaleY` (or `text_subs[i].height`),
   never its rotated bounding box. `text_subs[i]` is the *unrotated* sub-image —
   rotation happens later, in `_paste_onto`. So a rotated element contributes
   the wrong extent and the label is sized wrongly.

2. **Rotation pivot may not match Fabric.** `_paste_onto` always rotates the
   sub-image about **its own centre** and re-centres
   (`cx = left + sub.width // 2`, etc.). Fabric rotates an object about its
   **origin point** (`originX`/`originY`). Fabric 7 defaults origin to `center`,
   so centre-pivot is right for those objects — but elements carrying
   `originX: "left", originY: "top"` (QR and barcode elements do; see
   `addQrElement`/`addBarcodeElement` in `frontend/src/editor/canvas.ts`) rotate
   about the wrong point, so the print does not match the editor.

## What to do

### 1. A single rotated-bounding-box helper

Add one helper that, given an element's unrotated box (`w`, `h`), its
`angle`, and its origin-resolved top-left, returns the axis-aligned bounding box
after rotation about the correct pivot. For angle θ the AABB size is
`w' = |w·cosθ| + |h·sinθ|`, `h' = |w·sinθ| + |h·cosθ|`. Handle θ = 0 as an exact
no-op (no floating-point drift on the overwhelmingly common case) and keep it
correct for arbitrary angles, not just multiples of 90 — the editor allows free
rotation.

Use `_origin_top_left` (already present) to resolve the origin first; do not
duplicate that logic.

### 2. Use it in all three places that reason about extent

- **Continuous auto-length** in `render_template` — both the standard and the
  rotated-orientation branches. This is what makes the label length follow the
  rotated text, which is the operator's stated expectation.
- **`detect_overflow`** — a rotated element that overhangs the label must be
  flagged. It currently measures the unrotated box.
- **`_paste_onto`** — pivot about the origin-resolved point rather than always
  the sub-image centre, so the rendered position matches what the editor shows.

Keep `angle == 0` byte-identical to today's output. That is the regression bar:
the overwhelming majority of existing templates have no rotation and must not
shift by even a pixel.

### 3. Tests

Add to `backend/tests/` (extend `test_render_orientation.py` or add
`test_render_rotation.py`):

- Continuous media: a 90°-rotated text element produces a canvas whose length
  follows the text's *rotated* extent, and the ink is **not** clipped — assert
  there is non-zero blank margin below the ink, not `blankBot == 0`.
- The rotated element's ink starts near the top of the label rather than after a
  large blank gap (the operator's "huge blank spot").
- `detect_overflow` returns True for a rotated element that overhangs and False
  for one that fits.
- **Regression guard:** an unrotated template renders byte-identically before and
  after this change (`img.tobytes()` comparison against a fixture built in the
  test itself).
- Arbitrary angle (e.g. 37°) produces a sane, non-clipped extent — proving the
  helper is not special-cased to multiples of 90.

Tests need a font; follow the existing pattern in `test_render_orientation.py`
(`_FONT_PATH`, `FontInfo`, `_font_cache`) and skip when the font is absent.

### 4. Docs

- `docs/features/templates.md` — note that element rotation participates in
  continuous auto-length and overflow detection.
- `CHANGELOG.md` under `## [Unreleased]` — user-facing. This is a **fix** to
  shipped v0.1.6 behavior, so it belongs under `### Fixed` and should describe
  the symptom the operator saw.

## Working tree check

Run `git status --porcelain` first and cross-reference the files this plan
touches. If any have uncommitted changes, list them and ask before touching
them. This file is exempt. You are on `dev`; stay on it.

## Verification

- `ruff check .`, `ruff format --check .`, `mypy backend`, `pytest -q` must all
  pass. **Use the project's pinned ruff** (`pip install -e ".[dev]"` in a venv,
  ruff 0.16.8) — a bare system `ruff` on this machine is 0.8.4 and reports false
  formatting failures on `backend/tests/`.
- Reproduce the operator's case end-to-end and show before/after numbers in the
  same shape as the measured evidence above (canvas size, ink bbox, blank
  margins) for: continuous + 90°, die-cut + 90°, and continuous + 0° (unchanged).
- A useful starting point is the scratchpad repro at
  `/tmp/claude-1000/-home-manderse-projects-labelforge/2529705e-2a7e-42e0-a3b8-0cb91007e40c/scratchpad/qa/rot90b.py`.

## Conventions to honor

- Docs ship in the same commit as the code.
- Record the decision in `docs/decisions.md`, newest at top — especially the
  pivot-point choice and how it maps to Fabric's origin semantics.
- No giant explainer comments; comment the non-obvious *why* (the AABB formula
  and the pivot rationale qualify).

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. Move it to `prompts/done/` (plain `mv` — untracked) or `prompts/failed/`.
3. **You are a spawned agent: do not commit.** Prepare the tree and report back:
   files changed, a proposed one-line `fix:` commit message, the verification
   output including the before/after measurements, and any deviations.
   Never `git add -A`, never push, never auto-commit.
