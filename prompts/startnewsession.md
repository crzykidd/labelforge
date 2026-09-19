# labelforge — session start briefing

**Written:** 2026-09-19 · Regenerate this file when it goes stale.

Read `CLAUDE.md` first (it wins over anything here). This file is a status snapshot,
not a handoff prompt — it has no frontmatter and never moves to `prompts/done/`.

---

## Where we are

- **Shipped:** `v0.1.7` (2026-09-19). `v0.1.6` shipped the same day.
- **Version source of truth:** `pyproject.toml:7` (bare, no `v` prefix).
- **`[Unreleased]` holds an unreleased fix** — oversized field values on continuous
  labels, plus the per-element text-wrap option. Not yet printed on real media.
- **No open PRs.** One open issue (#42) that is actually already fixed — see below.
- Local `HEAD` may be on `main` after a release cut. Start with `git checkout dev`.

v1 is functionally complete — all eight `docs/PRD.md` success criteria work. Recent
work has been the template editor and rotation.

---

## What shipped on 2026-09-19 (v0.1.6 + v0.1.7)

A large day. Context for anything that looks unfamiliar in the editor:

- **CI was red on every PR** and had been since ruff 0.14. `ruff format --check` began
  formatting Python blocks inside Markdown, so `docs/` and `prompts/done/` failed the
  gate and blocked all seven dependency PRs. Fixed by excluding `*.md` from ruff and
  pinning `ruff>=0.16.8,<0.17`.
- **Three months of dependency updates** merged (FastAPI 0.141.1, pydantic-settings
  2.15.0, qrcode 8.2, pytest 9.1.1, Vite 8.3.0, GitHub Actions v7/v4).
- **Template orientation** — Standard / Rotated 90°, stored per template. The editor
  canvas transposes so you design upright; the renderer rotates the finished canvas.
- **Template editor overhaul** — elements panel (lists every object, flags off-canvas
  ones, click the red badge to recover just that one), bounds clamping with a backstop,
  grid + snap, keyboard shortcuts, undo/redo, and a fixed-height contextual control row
  so selecting an element no longer shifts the page.
- **Element rotation** — snaps to 0/90/180/270 within ~8°, free elsewhere, plus a
  "Rotate 90°" button. The renderer now accounts for rotation when sizing continuous
  labels and detecting overflow.

New frontend modules: `frontend/src/editor/{elements-panel,grid-snap,history,keyboard}.ts`.

---

## Open items

### Issue #42 is fixed but still open

`gh issue view 42` — the drag-clamp leak. It **was fixed** in v0.1.6 (`3906373`) and
verified in a real browser. The commit referenced it as "(#42)" rather than a
`Fixes #42` keyword, so GitHub never auto-closed it. Close it, or confirm first with
`gh issue view 42`.

### Rotation and text fitting are unverified on physical media

Rotation/fitting has now been wrong **three times**, and every time only a real print
revealed it:

1. Template orientation rotated the wrong way (270° instead of 90°) — the label read
   upside down. Fixed in `a15fcaf`; direction is now pinned by
   `test_rotated_direction_design_top_lands_on_label_left`. The dimension tests could
   not catch it, because 90° and 270° produce identical output sizes.
2. Rotated elements printed clipped, because the continuous auto-length measured the
   element's *unrotated* height. Fixed in `6e1f1f0`.

3. A field value longer than its placeholder printed clipped with no warning. The
   continuous auto-length measured only each element's *far* edge, so a centre-origin
   element (Fabric's default) grew backwards past the start of the label and was cut.
   The label got longer, just not in the direction that saved the text. Fixed on `dev`,
   unreleased.

**Still unconfirmed on paper:** the `6e1f1f0` fix also changed the rotation pivot for
`left`/`top`-origin elements — which is QR codes and barcodes — from the sub-image
centre to the Fabric origin. That is verified against Fabric's source and runtime but
has never been printed. If a rotated QR or barcode lands in the wrong place, start
there.

When touching rotation, the regression bar is that `angle == 0` output stays
**byte-identical** — nearly every existing template is unrotated.

---

## Feature gaps (real, in scope, not urgent)

Verified still true as of this writing:

- **Plain image elements are unimplemented end-to-end.** `docs/PRD.md` lists `image` as
  in scope, but `backend/labelforge/render/template.py:433` raises
  `RenderError("Image elements not yet supported")`, the editor has only Add Text / Add
  QR / Add Barcode, and there is **no upload endpoint at all**. Needs an asset story
  scoped first — handoff-prompt sized, not an in-session edit.
- **No "Add Line" / "Add Rect" buttons.** The renderer already handles both; only the
  toolbar is missing. Cheapest visible win, and the QR/barcode pattern shows how.
- **Template `display_name` cannot be renamed in the UI** —
  `docs/features/templates.md:298`. The API supports it; a rename modal was deferred.

Explicitly deferred — do not "helpfully" build: template versioning, template
categories/tags, a comment-preserving `labels.yml` writer.

---

## Ground rules that bite most often

Full text in `CLAUDE.md`; these are the ones a fresh session trips over.

- **Work on `dev`.** `main` is protected — PR only, never a direct push.
- **Commit, don't push** (releases excepted). Propose one commit, list exact paths, ask
  `y/n`, stage only those paths. Never `git add -A`. **No `Co-authored-by` trailers** —
  CLAUDE.md forbids them even when the harness suggests otherwise.
- **Changelog entry for every change**, under `## [Unreleased]`, as release notes. Do
  not write "Fixed" entries for bugs that only ever existed unreleased — fold those into
  the feature's own entry, or the notes describe churn users never saw.
- **Handoff prompts:** more than ~2 files or multi-step → write
  `prompts/<date>-<slug>.md` from `prompts/TEMPLATE.md` and spawn a subagent on it.
  The prompt file is committed *with* the work in one end commit.
- **Record non-obvious decisions** in `docs/decisions.md`, newest at top.
- **Non-negotiables:** GPL-3.0, no SSO, no multi-user, no SaaS, no SSR framework, no
  swapping `brother-ql-inventree` or SQLite without an ADR.

---

## Two traps that have already cost real time

- **The system `ruff` on this machine is 0.8.4; the project pins 0.16.8.** The stale
  binary reports false formatting failures on `backend/tests/`. Always validate with the
  pinned one (`pip install -e ".[dev]"` in a venv). Two separate agents reported those
  false failures as "pre-existing".
- **Fabric 7 defaults object origin to `center`, not `left`/`top`.** Any bounds or
  position assertion must be origin-aware, mirroring the backend's `_origin_top_left`.
  A whole round of browser QA produced three false failures from assuming top-left.

And one method note worth keeping: **DOM assertions do not prove a UI works.** A
Playwright click on a selector succeeds whether or not a human can find the control, and
passed while Save/Preview were scrolled off-screen. Screenshot the page and look at it.

---

## Verify the snapshot

```
git fetch --all && git status --porcelain && git log --oneline origin/main..dev
gh pr list --state open && gh issue list --state open
```
