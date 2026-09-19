---
name: 2026-09-19-wrap-max-lines
status: done
created: 2026-09-19
model: sonnet            # coding task (backend Python + frontend TS)
completed: 2026-09-19
result: |
  Implemented. labelforge_wrap_max_lines (int, default 0 = unlimited) caps
  wrapped output; excess lines are truncated and detect_overflow returns True
  via a truncated flag threaded through _render_text_element/_wrap_text -
  verified by a dedicated test file (11 new tests, all passing). Wrap target
  width is now orientation-aware via a new _wrap_target_width helper that
  composes element angle with template orientation (same cos/sin approach as
  _rotated_aabb); the angle=0/standard case is byte-identical to the old
  min(box_w, head_width) clamp. Editor Wrap checkbox replaced with an
  Off/No limit/2/3/4/5 select; CUSTOM_PROPS updated so the new prop survives
  toJSON(). Recall UI overflow notice wording generalized (was
  height-overflow-specific) and the print (not just preview) success path now
  also surfaces the overflow flag, since print can currently fire without a
  preceding Preview. Full backend suite green (72/72, pinned ruff 0.16.8),
  mypy clean, frontend tsc+vite build clean. Not committed - proposed commit
  left for the orchestrating session.
---

# Task: Cap text wrapping at a chosen number of lines, and make the wrap width orientation-aware

Wrapping shipped in v0.1.8 as an on/off checkbox with no line limit, so a long
value can balloon a label to six lines. Turn the control into **Off / 2 / 3 / 4 /
5 lines**, truncate with a warning when the content needs more than the cap, and
fix the wrap target width so it is correct on rotated templates.

Operator's words: *"if 2 lines we need to calculate lines one and 2 length. if
the label is 90 degrees we split both lines accordingly. if it is not rotated and
we have a hard length limit then we go to the first break that uses all the space
and then do second line and truncate with warning."*

## Current state (verified — do not re-derive)

`_wrap_text(text, font, target_width)` in `backend/labelforge/render/template.py`
is a greedy word-wrap with **no line cap**. Measured on 62mm continuous at 90pt,
box 650 wide:

```
"Master Bedroom"                            -> 2 lines   canvas 696x217
"Upstairs Guest Bedroom Closet"             -> 4 lines   canvas 696x393
"The Big Upstairs Guest Bedroom Storage..." -> 6 lines   canvas 696x569
"Supercalifragilistic" (one word too wide)  -> 1 line, not split
```

The wrap target is `min(box_w, head_width)` — a deliberate simplification
recorded in `docs/decisions.md`. It is wrong for rotated templates (see part 2).

## What to do

### 1. Max-lines cap, with truncation that warns

- Add `labelforge_wrap_max_lines` (integer, **0 = no limit**, default 0).
  **Keep the existing `labelforge_wrap` boolean as the on/off switch** so
  templates already saved in v0.1.8 with wrap on behave exactly as they do today
  rather than silently acquiring a cap. Register the new prop in `CUSTOM_PROPS`
  in `frontend/src/editor/canvas.ts` — a prop missing from that allow-list is
  silently dropped by `toJSON()`, which has bitten this repo before (see the
  2026-06-24 barcode ADR).
- Greedy fill stays: each line takes as many words as fit the target width, so
  line 1 uses all the space it can before line 2 starts. That is the operator's
  "go to the first break that uses all the space".
- When the wrapped result exceeds the cap: keep the first N lines, **truncate the
  remainder, and report it**. The truncation must not be silent — see part 3.
- A single word wider than the target is still never split mid-word (existing
  behavior, keep it).

### 2. Orientation-aware wrap width

The current clamp to `head_width` assumes text always runs across the fixed
print-head axis. That is only true for an unrotated template. On a **rotated**
template the design canvas is transposed and the text runs along the tape, where
the run is effectively unbounded — clamping to 696 wraps far too early.

Compute the wrap target from the axis the text actually runs along:
- unrotated: the print-head width is a hard ceiling (62mm = 696 dots),
- rotated: the free length axis, so the element's own box width governs.

An element with its own `angle` rotates within the design canvas and flips which
axis it runs along again — handle that composition rather than special-casing
orientation alone. `render_template` already resolves rotation for extents; reuse
that logic instead of writing a second, divergent copy.

### 3. Truncation must be visible

`detect_overflow(template, media_id, values)` already reports content that will
not print. Truncated wrap content must make it return **True**, so the existing
`overflow` flag on the print and preview responses carries the warning — no new
API surface needed.

Check the recall UI actually surfaces `overflow` to the user
(`frontend/src/pages/template-recall.ts`). If it does not, surface it — a
truncating print that reports nothing on screen is the exact failure mode this
project has spent the day eliminating.

### 4. Editor control

Replace the Wrap checkbox in the contextual control row
(`frontend/src/pages/template-editor.ts`) with a select: **Off / 2 / 3 / 4 / 5
lines**. "Off" sets `labelforge_wrap` false. A number sets it true and
`labelforge_wrap_max_lines` to that number. A template saved with wrap on and no
cap (v0.1.8) should display as unlimited rather than being coerced — add a "No
limit" option for that state if it keeps the control honest.

### 5. Tests

- Cap of 2 on content that needs 4 lines: exactly 2 lines render, and
  `detect_overflow` is True.
- Cap of 2 on content that fits in 2: renders **byte-identically** to wrap-on-
  uncapped. This is the regression bar.
- Cap of 5 on content needing 6: 5 lines, overflow True.
- Rotated template: wrap target follows the free axis, so a value that wraps at
  696 unrotated does **not** wrap prematurely when rotated.
- v0.1.8 compatibility: `labelforge_wrap: true` with no `labelforge_wrap_max_lines`
  still wraps unlimited and renders byte-identically to today.
- Existing suite (61 tests) stays green.

Font fixture pattern: follow `backend/tests/test_render_orientation.py`.

### 6. Docs

- `docs/features/templates.md` — update the wrap section: the cap, that exceeding
  it truncates and flags overflow, and how the target width differs by
  orientation.
- `docs/decisions.md` — newest at top. Record the truncate-with-warning choice
  (the operator chose truncation over shrink-to-fit, with the warning as the
  mitigation) and supersede the "clamp to head width" simplification from the
  v0.1.8 entry.
- `CHANGELOG.md` under `## [Unreleased]`, user-facing.

## Working tree check

`git status --porcelain` first; cross-reference the files this touches and ask
before touching anything already modified. This file is exempt. You are on `dev`.

## Verification

- `ruff check .`, `ruff format --check .`, `mypy backend`, `pytest -q`, and
  `npm run build` in `frontend/`.
- **Use the project's pinned ruff** (`pip install -e ".[dev]"` in a venv →
  0.16.8). The bare `ruff` on PATH is 0.8.4 and reports false formatting failures
  on `backend/tests/`. Three agents have now been caught by this.
- Report before/after line counts and canvas sizes for the four measured cases
  above, plus the rotated case.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. Move it to `prompts/done/` (plain `mv` — untracked) or `prompts/failed/`.
3. **You are a spawned agent: do not commit.** Prepare the tree and report back:
   files changed, a proposed one-line commit message, verification output with
   measurements, observed-vs-reasoned, and deviations. Never `git add -A`, never
   push, never auto-commit.
