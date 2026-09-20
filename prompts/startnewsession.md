# labelforge — session start briefing

**Written:** 2026-09-19 · Regenerate this file when it goes stale.

Read `CLAUDE.md` first (it wins over anything here). This file is a status snapshot,
not a handoff prompt — it has no frontmatter and never moves to `prompts/done/`.

---

## Where we are

- **Shipped:** `v0.1.9` (2026-09-19). Four releases went out that day: v0.1.6 → v0.1.9.
- **Version source of truth:** `pyproject.toml:7` (bare, no `v` prefix).
- **`dev` and `main` are in sync**, tree clean, `[Unreleased]` empty.
- **No open PRs, no open issues.**
- Local `HEAD` may be on `main` after a release cut. Start with `git checkout dev`.

v1 is functionally complete — all eight `docs/PRD.md` success criteria work. Recent
work has been the template editor, rotation, and variable fields.

---

## What shipped on 2026-09-19

Context for anything that looks unfamiliar:

- **CI had been red on every PR** since ruff 0.14 started formatting Python blocks
  inside Markdown. Fixed by excluding `*.md` from ruff and pinning
  `ruff>=0.16.8,<0.17`. Three months of blocked dependency PRs then merged.
- **Template orientation** (Standard / Rotated 90°) — the editor canvas transposes so
  you design upright; the renderer rotates the finished canvas.
- **Template editor overhaul** — elements panel with click-to-recover for off-canvas
  elements, bounds clamping, grid + snap, keyboard shortcuts, undo/redo, and a
  fixed-height contextual control row so selection no longer shifts the page.
- **Element rotation** snapping to 0/90/180/270 within ~8°, plus a Rotate 90° button.
- **Variable field fitting** — a value longer than its placeholder no longer prints
  clipped; continuous labels grow in both directions.
- **Text wrap** with a line cap (Off / No limit / 2 / 3 / 4 / 5), orientation-aware
  target width, truncation reported rather than silent.
- **FIELDS panel + global value lists** — the first way to edit a template's field
  schema at all. `{room}` marked as a list field resolves options from a shared,
  named list; editing it once changes every template using that field name. This also
  made `increment` settable for the first time.

New modules: `frontend/src/editor/{elements-panel,grid-snap,history,keyboard,fields-panel}.ts`,
`backend/labelforge/field_lists/`.

---

## Open items

### Batch print has no overflow warning

`BatchPrintResponse` (`backend/labelforge/models/__init__.py:133`) has no per-job
overflow field, so a batch of overflowing labels prints with no warning. Single print
and preview both warn correctly. A batch is exactly where silent overflow wastes the
most media. Deliberately deferred from v0.1.9 as a schema change; this is the main
known gap.

### Rotation and fitting: one print confirmed, two not

Rotation/fitting was wrong **three separate times**, and every time only a physical
print revealed it — previews and tests all looked right:

1. Template orientation rotated the wrong way (270° instead of 90°). Fixed in
   `a15fcaf`; direction is now pinned by a test, because 90° and 270° produce
   identical output *sizes* and every dimension assertion passed while the label
   printed upside down.
2. Rotated elements printed clipped — continuous auto-length measured the element's
   *unrotated* height. Fixed in `6e1f1f0`.
3. A field value longer than its placeholder printed clipped with no warning — the
   auto-length measured only each element's *far* edge, so a centre-origin element
   (Fabric's default) grew backwards past the start of the label. Fixed in `5e2ce5e`,
   **confirmed on real media by the operator**.

**Not yet printed:** the wrap line cap (changes rasterisation — highest risk), and
rotated QR/barcode elements, whose pivot point changed in `6e1f1f0`.

When touching any of this, the regression bar is that unrotated / uncapped /
already-fitting output stays **byte-identical**. Nearly every existing template is in
that category.

---

## Known limits — not bugs, don't "fix" them

- **Rotating twice** (template orientation Rotated 90° *plus* an element rotated 90°)
  puts the text back across the fixed 62mm tape. It reports overflow instead of
  printing a blank sliver. Physically cannot fit.
- **A single word wider than the tape** cannot be wrapped — wrap breaks at spaces
  only, never mid-word. `"Bedroom"` at 150pt is 760 dots against a 696-dot label; it
  needs ≤137pt or rotated orientation.

---

## Feature gaps (real, in scope, verified still true)

- **Plain image elements are unimplemented end-to-end.** `docs/PRD.md` lists `image`
  as in scope, but `render/template.py:612` raises
  `RenderError("Image elements not yet supported")`, the editor offers only Add Text /
  Add QR / Add Barcode, and there is **no upload endpoint**. Needs an asset story
  scoped first — handoff-prompt sized.
- **No "Add Line" / "Add Rect" buttons.** The renderer handles both already; only the
  toolbar is missing. Cheapest visible win.
- **Template `display_name` cannot be renamed in the UI** — the API supports it.

Explicitly deferred — do not build: template versioning, template categories/tags, a
comment-preserving `labels.yml` writer.

---

## Ground rules that bite most often

Full text in `CLAUDE.md`; these are the ones a fresh session trips over.

- **Work on `dev`.** `main` is protected — PR only, gated by CI **and CodeQL**.
- **Commit, don't push** (releases excepted). Propose one commit, list exact paths,
  ask `y/n`, stage only those paths. Never `git add -A`. **No `Co-authored-by`
  trailers** — CLAUDE.md forbids them even when the harness suggests otherwise.
- **Changelog entry for every change**, under `## [Unreleased]`, as release notes.
  Do *not* write "Fixed" entries for bugs that only ever existed unreleased — fold
  those into the feature's own entry, or the notes describe churn users never saw.
- **Handoff prompts:** more than ~2 files or multi-step → write
  `prompts/<date>-<slug>.md` from `prompts/TEMPLATE.md` and spawn a subagent on it.
  The prompt file is committed *with* the work in one end commit.
- **Record non-obvious decisions** in `docs/decisions.md`, newest at top.
- **Non-negotiables:** GPL-3.0, no SSO, no multi-user, no SaaS, no SSR framework, no
  swapping `brother-ql-inventree` or SQLite without an ADR.

---

## Four traps that have already cost real time

- **The system `ruff` is 0.8.4; the project pins 0.16.8.** The stale binary reports
  false formatting failures on `backend/tests/`. Always validate with the pinned one
  (`pip install -e ".[dev]"` in a venv). **Three separate agents** reported those
  false failures as "pre-existing".
- **Fabric 7 defaults object origin to `center`**, not `left`/`top`. Any bounds or
  position assertion must be origin-aware, mirroring the backend's `_origin_top_left`.
  This produced three false QA failures in one round, and was itself the root cause of
  the v0.1.8 clipping bug.
- **DOM assertions do not prove a UI works.** A Playwright click on a selector
  succeeds whether or not a human can find or reach the control — one passed while
  Save and Preview were scrolled off-screen. Screenshot the page and *look* at it.
- **`gh run list` takes `-c <sha>`** to filter by commit; `--arg` is not a `gh` flag.

`playwright-core` plus the cached Chromium at `~/.cache/ms-playwright/` drives the app
without installing browsers. Dev servers: backend `uvicorn` on :8001 with
`DISABLE_AUTH=true` and a scratch `DATA_DIR`, frontend Vite on :5174 (**5173 is taken
by another project on this machine**). Vite also needs `allowedHosts` to be reachable
by hostname from another machine.

---

## Verify the snapshot

```
git fetch --all && git status --porcelain && git log --oneline origin/main..dev
gh pr list --state open && gh issue list --state open
```
