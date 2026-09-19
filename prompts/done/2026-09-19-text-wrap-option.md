---
name: 2026-09-19-text-wrap-option
status: done
created: 2026-09-19
model: sonnet            # coding task (backend Python + frontend TS)
completed: 2026-09-19
result: |
  Implemented. Primary bug (centre-origin element clipped when resolved value
  wider than placeholder) fixed and verified byte-for-byte against the
  prompt's measured evidence. Second defect (rotated orientation + 90°
  element angle collapsing to ~41 dots) improved from a near-total blank
  collapse to a correctly-sized-and-flagged overflow — see docs/decisions.md
  for why that specific combination cannot be made to fully "fit" (it drives
  content onto the fixed print-head-width axis, not the free length axis).
  Wrap option, extended detect_overflow, tests, docs, and CHANGELOG all done.
  Not committed — proposed commit left for the orchestrating session.
---

# Task: Per-element text wrapping, and make overflow detection see resolved values

A template designed around a short placeholder prints clipped when the field
value is longer. Designing with `{name}` at 150pt looks right in the editor, but
printing with `name = "Master Bedroom"` silently cuts the text off at the label
edge — **with no warning**.

Add an opt-in **wrap** setting on text elements (wrap at spaces), and fix
overflow detection so it measures the *resolved* text rather than the stored
placeholder.

## Measured evidence (reproduced; do not re-derive)

62mm continuous = **696 dots** wide. DejaVuSans-Bold. Template orientation
**Rotated 90°**, element angle 0, value `name = "Master Bedroom"` at 150pt,
element box still sized for the placeholder `{name}` (680 wide):

```
origin left/top  @ (20,20)     canvas=696x1439  ink  32 -> 1405   fits
origin CENTER    @ (500,348)   canvas=696x1220  ink   0 -> 1046   CLIPPED
origin CENTER    @ (340,348)   canvas=696x1060  ink   0 -> 1046   CLIPPED
control "Master", origin CENTER canvas=696x860  ink 114 ->  686   fits
```

**Centre origin is the editor's default** (Fabric 7), so this is the common case.

Text widths for reference:
```
"{name}"         @150pt ->  680 dots   <- fits, so the editor looks correct
"Master"         @150pt ->  587 dots
"Master Bedroom" @150pt -> 1399 dots
"Bedroom"        @150pt ->  760 dots   <- one word, still wider than 696
```

Also broken, found while investigating — **template orientation Rotated 90° AND
element angle 90 together** collapse the label to nothing:
```
both rotated, "Master Bedroom"  ->  canvas=696x41   CLIPPED
either one alone                ->  canvas=696x1439 fits
```

## What to do

### 1. Grow the canvas in BOTH directions (the reported bug — do this first)

The continuous auto-length loop in `render_template` measures only each element's
**far** edge (`pos + size`). When a centre-origin element's *resolved* value is
wider than the placeholder it was designed around, the content also grows
backwards past the start of the label — and that part is silently cut off. The
label does get longer (860 -> 1220 above), just not in the direction that would
save the text.

Fix: track the **minimum** extent as well as the maximum. If the minimum is
negative, the canvas must cover `[min, max]` — grow the length and offset all
content by `-min` so nothing falls off the start. Continuous media has a free
length axis; use it in both directions. This is what the operator asked for:
"if the label is a continuous label it should just print longer."

Die-cut media cannot grow — there, out-of-bounds content must be reported by
overflow detection (part 2) rather than silently clipped.

Also fix the **combined-rotation** case in the same pass: template orientation
`rotated` plus an element `angle` of 90 collapses the length to 41 dots. Either
rotation alone is correct, so the two are composing wrongly when the extent axis
is chosen.

The regression bar throughout: a template whose content already fits renders
**byte-identically**. Only content that is currently being clipped may move.

### 2. Wrap as a per-element option

- New custom prop `labelforge_wrap` (boolean, **default false** so existing
  templates are untouched). Register it in `CUSTOM_PROPS` in
  `frontend/src/editor/canvas.ts` — this is the allow-list that makes a prop
  survive `toJSON()`. **Forgetting this is a known past bug** (see the
  2026-06-24 ADR about barcode props silently vanishing).
- Editor: a "Wrap" checkbox in the contextual control row
  (`frontend/src/pages/template-editor.ts`) shown when a text element is
  selected, alongside font/size/colour. Follow how the existing per-type
  controls are wired.
- Renderer: in `_render_text_element` (`backend/labelforge/render/template.py`),
  when the element has `labelforge_wrap` true, break the **resolved** text at
  spaces so each line fits the target width, then render the lines. The existing
  code already uses `multiline_textbbox` / `multiline_text`, so multi-line
  rendering works once newlines are inserted — you are adding the line-breaking,
  not a new render path.

**Wrap target width**: the element's own box width (`width × scaleX`), clamped
to the space actually available on the label. This makes the wrap width
something the user controls by sizing the element, which is why it is an
element-level option.

**A single word wider than the target cannot be wrapped.** Do not hyphenate or
force-break mid-word. Leave it on its own line, overflowing, and let overflow
detection (below) report it. `"Bedroom"` at 150pt is exactly this case.

### 3. Overflow detection must see resolved values

`detect_overflow(template, media_id)` currently measures the stored element box —
which was sized for `{name}` — so it returns False for a value that clips. It is
also die-cut only.

- Give it access to the resolved field values so it measures what will actually
  print. Check the call sites in `backend/labelforge/routes/template_print.py`
  (around lines 157 and 191) — they already have the values in hand.
- It must also catch **horizontal** overflow on continuous media (a line wider
  than the print head), which today it skips entirely by returning False for
  continuous form factors. Vertical/length overflow on continuous remains
  correctly "never overflows" — the label grows.
- Keep the existing signature working, or update all call sites; do not leave a
  half-migrated API.

This half is a bug fix and matters even more than the wrap feature: printing
silently-clipped labels wastes media. The existing `overflow` field is already
returned by the print/preview endpoints, so surfacing it needs no new API.

### 4. Tests

- A value longer than its placeholder, wrap **off**: `detect_overflow` returns
  True (this is the reported bug — it currently returns False).
- Same value, wrap **on**: breaks at spaces, the rendered canvas grows in length
  to fit the extra line, and the ink is not clipped.
- A single word wider than the label with wrap on: still reported as overflowing
  (documents the known limit rather than pretending it is solved).
- Wrap on but the value already fits: output is **byte-identical** to wrap off.
  That is the regression bar.
- Existing unrotated/unwrapped templates render byte-identically — the whole
  existing suite must stay green.

Follow the font fixture pattern in `backend/tests/test_render_orientation.py`
(`_FONT_PATH`, `FontInfo`, `_font_cache`, skip when absent).

### 5. Docs

- `docs/features/templates.md` — document the wrap option, that it breaks at
  spaces only, that a single over-wide word still overflows, and that rotated
  orientation is the way to print text longer than the tape width.
- `CHANGELOG.md` under `## [Unreleased]`: an `### Added` entry for the wrap
  option and a `### Fixed` entry for the missing overflow warning, in
  user-facing language.

## Working tree check

Run `git status --porcelain` first; cross-reference the files this touches. If
any have uncommitted changes, list them and ask. `prompts/startnewsession.md`
is expected to be modified and uncommitted — leave it alone. You are on `dev`.

## Verification

- `ruff check .`, `ruff format --check .`, `mypy backend`, `pytest -q`, and
  `npm run build` in `frontend/` must pass.
- **Use the project's pinned ruff** (`pip install -e ".[dev]"` in a venv →
  0.16.8). The bare `ruff` on this machine is 0.8.4 and reports false formatting
  failures on `backend/tests/`.
- Reproduce the operator's case and report before/after numbers in the same
  shape as the measured evidence: canvas size, ink right edge, and
  `detect_overflow`, for `"Master Bedroom"` @150pt with wrap off and wrap on.
- A starting point is the scratchpad repro at
  `/tmp/claude-1000/-home-manderse-projects-labelforge/2529705e-2a7e-42e0-a3b8-0cb91007e40c/scratchpad/qa/varfit.py`.

## Conventions to honor

- Docs ship in the same commit as the code.
- Record the decision in `docs/decisions.md`, newest at top — especially the
  wrap-target-width choice and the no-mid-word-break rule.
- Match the existing vanilla-TS style; no new dependencies either side.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. Move it to `prompts/done/` (plain `mv` — untracked) or `prompts/failed/`.
3. **You are a spawned agent: do not commit.** Prepare the tree and report back:
   files changed, a proposed one-line commit message, verification output with
   the before/after measurements, what you observed versus reasoned about, and
   any deviations. Never `git add -A`, never push, never auto-commit.
