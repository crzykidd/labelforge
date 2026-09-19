# labelforge — session start briefing

**Written:** 2026-09-18 · Regenerate this file when it goes stale.

Read `CLAUDE.md` first (it wins over anything here). This file is a status snapshot,
not a handoff prompt — it has no frontmatter and never moves to `prompts/done/`.

---

## Where we are

- **Shipped:** `v0.1.5` (2026-06-24). Tag exists on `main`; GitHub release published.
- **Version source of truth:** `pyproject.toml:7` (bare, no `v` prefix).
- **`CHANGELOG.md` `## [Unreleased]`** holds one entry: the CI format-gate fix below.
  Not enough to justify a release on its own — roll the dependency PRs in first.
- **`dev` is one commit ahead of `main`** (that same fix). Work on `dev`; `main` is PR-only.
- **The repo has been dormant since 2026-06-24** — roughly three months. Everything below
  accumulated while nobody was driving.

v1 is functionally **done**: all eight success criteria in `docs/PRD.md` are implemented
(quick print, canvas editor with `{field}` placeholders, recall + batch/increment, two-color
DK-2251, HTTP API, history with reprint + pin, `labels.yml` friendly names). Post-v1 work has
been incremental polish: QR element (0.1.4), barcode element (0.1.5), version footer and
update check (0.1.3).

---

## Recently fixed — the CI format gate (2026-09-18)

**Resolved on `dev`.** Recorded as an ADR in `docs/decisions.md`; no action needed beyond
knowing why the config looks the way it does.

`ci.yml:53` runs `ruff format --check .`, and `ruff` was pinned only as `ruff>=0.7`. CI
resolved ruff 0.16.x, and ruff ≥0.14 formats Python code blocks **inside Markdown**. Four
files failed — `docs/decisions.md`, `docs/features/label-catalog.md`, and two archived
prompts under `prompts/done/` — so the `python` job failed on every PR regardless of its
contents, blocking all seven dependency PRs and the next release.

Fix: `extend-exclude = ["*.md"]` under `[tool.ruff]`, plus `ruff>=0.16.8,<0.17` on the dev
extra so the gate's tooling can't drift again without a dependabot PR. Verified against a
clean `pip install -e .[dev]`: `ruff check`, `ruff format --check`, `mypy backend` and
`pytest -q` (33 passed) are all green at ruff 0.16.8 / mypy 2.3.1 / pytest 9.1.1.

Note for anyone re-deriving this: excluding only `prompts/**` does **not** work — half the
failing files are under `docs/`. The problem is Markdown generally.

Your local ruff must now be ≥0.16.8; re-run `pip install -e .[dev]` if yours is older.

---

## Open dependabot PRs (7, all targeting `dev`)

| PR | Bump | Opened |
|----|------|--------|
| #41 | github-actions group (checkout, setup-python, setup-node, codeql-action) | 2026-09-01 |
| #39 | pydantic-settings `>=2.6` → `>=2.14.2` | 2026-07-01 |
| #38 | fastapi `>=0.136.3` → `>=0.138.2` | 2026-07-01 |
| #37 | ruff `>=0.7` → `>=0.15.20` | 2026-07-01 |
| #36 | pytest `>=8.3` → `>=9.1.1` | 2026-07-01 |
| #35 | qrcode `>=8.0` → `>=8.2` | 2026-07-01 |
| #34 | vite 8.0.16 → 8.1.2 (frontend, npm minor/patch group) | 2026-07-01 |

Only #41 has a run on record, and it failed on the format gate above rather than on anything
it changed. With that gate fixed these should now be able to go green once rebased onto `dev`.

**#37 (ruff) is superseded** — the pin this repo now carries is narrower than the `>=0.15.20`
it proposes, and 0.15 still has the Markdown behavior. Close it rather than merge it.

A clean `pip install -e .[dev]` already resolves pytest 9.1.1 and mypy 2.3.1 and the suite
passes, so #36 looks safe. Suggested order: rebase the remaining dependabot PRs → merge the
batch → one `chore:` changelog line covering the dependency roll → release prep.

---

## Feature gaps worth knowing about

These are real, in-scope, and not yet built. None is urgent; pick from them when the
maintenance work above is done.

- **Plain image elements are unimplemented end-to-end.** `docs/PRD.md` lists `image` as an
  in-scope element type, but `backend/labelforge/render/template.py:359` raises
  `RenderError("Image elements not yet supported")`, and the editor toolbar
  (`frontend/src/pages/template-editor.ts:61-63`) offers only Add Text / Add QR / Add Barcode.
  Doing this properly needs an asset story first — there is **no upload endpoint**, and the
  route list has nothing under `/api/assets` or similar. Scope that before writing code; it is
  a handoff-prompt-sized job, not an in-session edit.
- **No "Add Line" / "Add Rect" buttons.** The *renderer* handles both
  (`render/template.py:362` and `:378`), so the backend is ready; only the editor toolbar is
  missing. This is the cheapest visible win available and mirrors the QR/barcode pattern that
  ADR 2026-06-24 documents.
- **Template `display_name` cannot be renamed in the UI** — `docs/features/templates.md:182`.
  The `TemplateUpdate` model already supports it over the API; a rename modal was deferred.

Explicitly deferred, do not "helpfully" build: template versioning, template categories/tags
(`docs/features/templates.md:201-202`), and a comment-preserving `labels.yml` writer
(ADR 2026-06-05).

---

## Ground rules that bite most often

Full text is in `CLAUDE.md`; these are the ones a fresh session trips over.

- **Work on `dev`.** `main` is protected — PR only, never a direct push.
- **Commit, don't push.** Propose one commit, list the exact paths, ask `y/n`,
  stage only those paths. Never `git add -A`.
- **Changelog entry for every change**, under `## [Unreleased]`, written as release notes.
- **Handoff prompts:** more than ~2 files or a multi-step change → write
  `prompts/<date>-<slug>.md` from `prompts/TEMPLATE.md` and spawn a subagent on it
  (`model:` — Opus for planning, Sonnet for coding). Don't hand the user a CLI command.
  The prompt file is committed *with* the work in one end commit, after the agent
  `git mv`s it to `prompts/done/`.
- **Record non-obvious decisions** in `docs/decisions.md`, newest at top.
- **Non-negotiables:** GPL-3.0, no SSO, no multi-user, no SaaS, no SSR framework, no swapping
  `brother-ql-inventree` or SQLite without an ADR.
- **Load docs narrowly** — `architecture.md` + `glossary.md` + only the feature doc you need.

---

## Verify the snapshot

```
git fetch --all && git status --porcelain && git log --oneline main..dev && gh pr list --state open
```
