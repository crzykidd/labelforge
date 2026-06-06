---
name: 2026-06-05-ci-green-for-release
status: completed
created: 2026-06-05
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-06-05
result: CI compose job fixed (docker-compose.yml filenames + hardened loop); CLAUDE.md convention corrected; ruff lint clean (import order, datetime.UTC, all E501 long lines)
---

# Task: Get CI green on `dev` ahead of the first release PR

Two CI jobs are red and block the eventual `dev → main` release PR: the **compose**
validation job and the **python** (ruff) job. Fix both so every required check passes.
These are mechanical lint/config fixes — no runtime behavior changes.

## Before you start

- The compose files are **`docker-compose.yml`** / **`docker-compose.dev.yml`** and
  **stay that way** — `docker-compose.yml` is the standard naming across the owner's dev
  projects. Do **not** rename them. The CI compose job is wrong (it looks for
  `compose.yml`), and `CLAUDE.md` documents the wrong convention; both get corrected to
  match the actual filenames.
- The CI definition is `.github/workflows/ci.yml`. The relevant jobs are `python`
  (runs `ruff check .`, `ruff format --check .`, `mypy backend`, `pytest -q`) and
  `compose` (currently loops over `compose.yml compose.dev.yml` running
  `docker compose config` — wrong filenames, and `bash -e` makes the failing `[ -f ]`
  test the script's last command → exit 1).
- ruff config is in `pyproject.toml`: `line-length = 100`, `select = ["E","F","I","W","B","UP"]`.
- Work on `dev`. This repo adopts `code-checkin-and-pr` — Conventional-Commits prefixes,
  no `Co-authored-by:`, docs ship with code.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files this
plan touches (`.github/workflows/ci.yml`, `CLAUDE.md`, and several files under
`backend/labelforge/`). If any have uncommitted changes, list them and ask before
touching. This handoff file is exempt.

## What to do

### 1. Compose job (point CI at the real filenames + harden the loop)

Keep the files named `docker-compose.yml` / `docker-compose.dev.yml`. Fix everything
else to match that.

- In `.github/workflows/ci.yml`, change the `compose` job's loop to iterate over
  `docker-compose.yml docker-compose.dev.yml`, and harden it so a genuinely-absent file
  is a skip rather than a `bash -e` failure:

  ```yaml
        run: |
          for f in docker-compose.yml docker-compose.dev.yml; do
            if [ -f "$f" ]; then
              docker compose -f "$f" config --quiet && echo "OK $f"
            else
              echo "skip $f (not present)"
            fi
          done
  ```

- Correct `CLAUDE.md` so the documented convention matches reality. In the **Repo
  conventions** section it currently reads: *"Compose stack lives at the repo root as
  `compose.yml`. Dev compose at `compose.dev.yml`."* Change those to `docker-compose.yml`
  and `docker-compose.dev.yml`.
- The compose files themselves are already valid Compose v2 (have `name:` + `services:`,
  no legacy `version:` key) — do **not** rename or restructure them; leave them as-is.

### 2. Python job (ruff)

Reproduce CI locally from the repo root (CI runs ruff against `.`, mypy against `backend`):

- `pip install -e .[dev]` (or use the existing venv).
- `ruff check --fix .` — auto-resolves the import-sort (`I001`) and `datetime.UTC`
  (`UP017`) findings (the "4 fixable" ones), including:
  - `backend/labelforge/main.py` — unsorted import block.
  - `backend/labelforge/routes/print.py` — unsorted import block.
  - `backend/labelforge/templates/store.py:18` — `datetime.now(timezone.utc)` →
    `datetime.now(datetime.UTC)` (adjust the import accordingly).
- Manually fix the remaining `E501` (line-too-long, 100) — ruff won't auto-wrap these:
  - `backend/labelforge/printer/client.py:7` — split the long `# ... .color` comment
    across two comment lines.
  - `backend/labelforge/routes/print.py` and
    `backend/labelforge/routes/template_print.py` — the long
    `from labelforge.printer.client import PrintError, StatusUnavailable, media_compatible, print_image, status_read, to_print_bitmap`
    line: convert to a parenthesized multiline import.
  - `backend/labelforge/routes/template_print.py:72`, `:142`, `:170` — wrap the long
    `media_compatible(status["media_id"], tmpl.label_media)` conditionals and the
    `batch_print(...)` signature. Prefer extracting a local
    (e.g. `media_id = status["media_id"]`) over awkward line continuations.
- The findings list in the failing run is representative, not exhaustive ("Found 15
  errors"). Do **not** hand-fix from this list — make the actual commands pass:
  `ruff check .` reports **zero** errors and `ruff format --check .` passes. Run
  `ruff format .` and review its diff; if it reformats anything, that change is required
  for CI and should be included (keep it scoped to files ruff actually touches).
- Confirm the rest of the python job still passes: `mypy backend` and `pytest -q`.

### 3. Changelog

Add one `chore:`-flavored entry under `## [Unreleased]` in `CHANGELOG.md` (developer/
process-facing, no runtime change) noting the compose CI job fix (correct
`docker-compose.yml` / `docker-compose.dev.yml` filenames + hardened loop), the matching
`CLAUDE.md` convention correction, and the ruff lint/format cleanup.

## Conventions to honor

- LF line endings only (`.gitattributes` enforces). If `git diff --stat` shows the whole
  tree modified, run `git config core.autocrlf input && git checkout -- .`.
- Keep the diff scoped: lint fixes only, no opportunistic refactors beyond what ruff
  requires.
- No runtime/behavior changes — this is purely CI-green plumbing.

## When done

1. Verify locally, then report the one-line result:
   `ruff check . && ruff format --check . && mypy backend && pytest -q` all pass, and the
   compose loop (`for f in docker-compose.yml docker-compose.dev.yml; do docker compose -f "$f" config -q && echo OK $f; done`)
   succeeds.
2. Update this file's frontmatter: set `status`, `completed` (2026-06-05), and `result`.
3. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
4. Record any non-obvious decision (e.g. standardizing on `docker-compose.yml` naming
   across projects) in `docs/decisions.md` if it rises to an ADR; a one-liner is fine if
   it doesn't.
5. Propose ONE commit covering the CI workflow edit, the `CLAUDE.md` convention fix, the
   backend lint fixes, the changelog, and this prompt move. Present the file list and a
   one-line message; ask `commit these as "chore: fix CI compose + ruff lint for release"? (y/n)`.
   On `y`, stage those specific paths (never `git add -A`) and commit on `dev`. Never push.
