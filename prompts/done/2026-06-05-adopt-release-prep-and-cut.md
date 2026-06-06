---
name: 2026-06-05-adopt-release-prep-and-cut
status: completed
created: 2026-06-05
model: sonnet
completed: 2026-06-05
result: release-prep-and-cut v1.0.0 adopted — slash commands in .claude/commands/, CLAUDE-snippet pasted, build-and-push.yml trigger reconciled to release:published, standards.md + CHANGELOG.md + README.md + ADR updated
---

# Task: Adopt the `release-prep-and-cut` standard in labelforge (@ v1.0.0)

labelforge is about to cut its first release but has **not** adopted the homelab
`release-prep-and-cut` standard that governs how releases are prepped and published. This
task wires it up: copy the two slash-command templates into `.claude/commands/` with
labelforge's values filled in, reconcile the publish trigger, paste the CLAUDE snippet,
register the adoption, and clean up two pre-existing snags. **It does NOT cut a release** —
it only installs the machinery so a later `/release-prep <version>` works.

## Before you start

- **Read the standard, fully**, from the local source-of-truth clone:
  - `~/projects/homelab-configs/standards/release-prep-and-cut/README.md` (the rules)
  - `.../release-prep-and-cut/release-prep.md` and `.../release-cut.md` (the two templates
    you'll copy — each has a placeholder header block at the top)
  - `.../release-prep-and-cut/CLAUDE-snippet.md` (paste-verbatim block)
  - `~/projects/homelab-configs/standards/code-checkin-and-pr/README.md` — it **owns the
    image-publishing matrix that fires on `release: published`**; release-cut composes with
    it. Read its publish-matrix section before touching `build-and-push.yml` (see step 4).
- Read labelforge's `standards.md` (the in-repo registry) and the existing
  `### Code check-in (operational rules)` section in `CLAUDE.md` to match style/placement.
- Map-not-copy: link back to the standard, don't restate its prose.
- Work on `dev`. Conventional-Commits prefixes, no `Co-authored-by:`, docs ship with code.

## Working tree check

Run `git status --porcelain` first. **Sequencing matters:** this depends on two things that
should land before it — (a) the queued `prompts/2026-06-05-enable-mypy-ci.md` work (it sets
the real `<LOCAL_CHECKS>` — mypy must actually pass), and (b) an uncommitted datetime/compose
fix the owner may still be committing. If `CHANGELOG.md`, `pyproject.toml`, or `.github/`
files show unexpected uncommitted changes, **stop and ask** rather than commit over them.

## labelforge placeholder values (use these)

| Placeholder | Value |
|---|---|
| `<VERSION_FILE>` | `pyproject.toml` |
| `<VERSION_LITERAL>` | `version = "<current>"` (the `[project]` version line) |
| `<README_BADGE_PATTERN>` | labelforge's README has **no** version badge today. Add a simple one (e.g. a static shields.io `version-<current>-blue` badge) near the title, OR if you'd rather not introduce a badge, set this to a plain `**Version:** <current>` line. Pick one and be consistent in both templates. |
| `<README_WHATSNEW_SECTION>` | `## What's New` — **create this section** (README has none yet); put it just under the title/intro, above `## What it does`. Also update the `**Status**: Early development. Not yet usable.` line — at first release that claim is no longer true. |
| `<DOCS_TO_SYNC>` | `README.md` (badge/version + What's New entry); `CLAUDE.md` (add a small **Build Status** block: current release target / last shipped release — mirror the standard's example). `docs/PRD.md` has **no** revision-history table — only add version syncing there if you choose to add such a table; otherwise omit. The app already surfaces `App version` in Settings (`docs/features/settings.md:57`) read from `pyproject.toml`, so no code change is needed for the in-app display. |
| `<LOCAL_CHECKS>` | The exact commands CI's `python`/`config`/`compose` jobs run: `ruff check .` · `ruff format --check .` · `mypy backend` · `pytest -q` · the tracked-config YAML/JSON/TOML validation (see the `config` job in `ci.yml`) · `cp .env.example .env` then `docker compose -f docker-compose.yml config --quiet` and `-f docker-compose.dev.yml config --quiet`. Copy them faithfully so prep runs the same gates CI does. |
| `<CHANGELOG_ARCHIVE_DIR>` | `docs/` (archive files `docs/CHANGELOG-<minor>.x.md`) |
| `<MAIN_CI_WORKFLOW>` | `CI` (`.github/workflows/ci.yml`) |
| `<PUBLISH_WORKFLOW>` | `Build and Push` (`.github/workflows/build-and-push.yml`) |
| `<RELEASE_IMAGE_TAGS>` | `:latest`, `:<version>`, `:<major>` — verify against `build-and-push.yml`'s actual `metadata-action` tag rules and correct the list if they differ |

## What to do

1. **Copy the two templates** into `.claude/commands/` (create the dir):
   `release-prep.md` and `release-cut.md`. Replace **every** `<PLACEHOLDER>` using the table
   above. When done, `grep -n '<[A-Z_]\+>' .claude/commands/*.md` must return nothing — no
   unsubstituted placeholders. Keep the source-attribution comment that links back to the
   standard.

2. **Paste `CLAUDE-snippet.md` verbatim** into `CLAUDE.md` as a new
   `## Release process (operational rules)` section (place it near the existing
   `## Code check-in (operational rules)` block — they're siblings). Don't reword it.

3. **Add the Build Status block to `CLAUDE.md`** referenced by `<DOCS_TO_SYNC>` (current
   release target / last shipped release), so `/release-prep` has something to sync.

4. **Reconcile the publish trigger** (the one real design decision — record it as an ADR).
   `build-and-push.yml` currently fires on `push` to `main`/`dev` and on `tags: v*.*.*`.
   The standard's `/release-cut` does `gh release create v<version>`, and both this standard
   and `code-checkin-and-pr` assume the publish matrix fires on **`release: published`**.
   Align it: add a `release: { types: [published] }` trigger that builds the
   `:latest` / `:<version>` / `:<major>` image tags. To avoid a *double* build (creating a
   GitHub release also creates the `v*` tag, which the existing `tags:` trigger would catch),
   **remove the `tags: v*.*.*` trigger** so the release event is the single source of the
   release build; keep the branch-push trigger for `dev`/`main` dev images. Verify the
   `metadata-action` tag rules still emit the three release tags on the `release` event.
   Confirm this matches `code-checkin-and-pr`'s matrix; if that standard mandates a specific
   shape, follow it and note any deviation.

5. **Register the adoption** in `standards.md`: add a new row at the top (newest first),
   `release-prep-and-cut | 1.0.0 | 2026-06-05 | …` with notes covering: templates copied to
   `.claude/commands/`, CLAUDE-snippet pasted, publish trigger reconciled to
   `release: published` (ADR ref), `<VERSION_FILE>` = `pyproject.toml`. Also update the
   `CLAUDE.md` line that points at `standards.md` if its wording needs it.

6. **Cleanup — stray CHANGELOG placeholder.** `CHANGELOG.md` has a leftover
   `## [version] — YYYY-MM-DD` template header (around line 139) sitting below real content.
   Remove it — it's not a real release section and would confuse the prep/archive logic.
   (Leave the real `## [Unreleased]` block untouched.)

7. **Do NOT bump the version or roll the changelog** — that's `/release-prep`'s job, run
   later by the owner. This task only installs the commands and wiring.

## Conventions to honor

- LF endings. The `.claude/commands/*.md` files are agent-facing command specs — keep the
  standard's structure intact; only substitute placeholders and the attribution link.
- Changelog: add a `### Changed` entry under `## [Unreleased]` — labelforge adopts the
  `release-prep-and-cut` standard (`/release-prep` + `/release-cut` slash commands added;
  publish workflow now fires on `release: published`; CLAUDE.md + standards.md updated).
  Developer/process-facing, no runtime change.
- The homelab-configs **registry** (`projects/labelforge/README.md` + `projects/README.md`)
  also needs an adoption row per the standard — but that's a **different repo**
  (`~/projects/homelab-configs`), out of scope for this labelforge commit. Note it in your
  final summary so the owner can do it there.

## When done

1. Verify: `grep` finds no leftover `<PLACEHOLDER>` in `.claude/commands/`; `ruff check . &&
   ruff format --check . && mypy backend && pytest -q` still green; both compose files still
   `config`-validate. Give the one-line "run this to verify".
2. Update this file's frontmatter (`status`, `completed` = 2026-06-05, `result`).
3. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
4. Record the publish-trigger reconciliation (tag-push → `release: published`) as an ADR in
   `docs/decisions.md`.
5. Propose ONE commit covering `.claude/commands/release-prep.md` + `release-cut.md`,
   `CLAUDE.md`, `standards.md`, `README.md`, `.github/workflows/build-and-push.yml`,
   `CHANGELOG.md`, `docs/decisions.md`, and this prompt move. Present the file list and a
   one-line message; ask
   `commit these as "chore: adopt release-prep-and-cut standard (v1.0.0)"? (y/n)`. On `y`,
   stage those specific paths (never `git add -A`) and commit on `dev`. Never push.
6. In your final summary, hand the owner the launch command for a first release once they're
   ready: `/release-prep <version>` (e.g. `/release-prep 0.1.0`), and remind them the
   homelab-configs registry row still needs adding in that repo.
