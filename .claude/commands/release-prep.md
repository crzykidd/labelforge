---
description: Prepare a release — bump version, roll changelog, sync docs, validate, commit, push to dev, open PR
argument-hint: <version>   (e.g. 0.3.6)
---

<!--
Template from standards/release-prep-and-cut @ v1.0.0
(crzynet/homelab-configs/standards/release-prep-and-cut/README.md).
labelforge values: VERSION_FILE=pyproject.toml, CHANGELOG_ARCHIVE_DIR=docs/
-->

# Release Prep

You are preparing release **v$ARGUMENTS**. This command does ONLY the prep + PR
steps. It does **not** merge and does **not** create the GitHub release — the
human merges, and `/release-cut` (run after `main` CI is green) creates the
release.

## Execution rules

- Work on the `dev` branch. Never push directly to `main`.
- Do NOT add `Co-authored-by` lines to the commit.
- Do NOT create the GitHub release or tag in this command.
- If any validation step fails, STOP and report — do not commit broken state.
- Make exactly ONE commit covering version + changelog + all doc updates.
- `$ARGUMENTS` is the target version. It SHOULD be bare semver, no `v` prefix
  (e.g. `0.3.6`). If a leading `v` was typed (`v0.3.6`), strip it silently and
  proceed with the bare number. After stripping, if the value is empty or does
  not match `MAJOR.MINOR.PATCH` exactly (three integers, dot-separated, no
  pre-release/build suffix), STOP and ask for a valid version.
- Reminder on the `v` convention: the version is stored and used BARE
  everywhere (`pyproject.toml`, changelog header, README badge, in-code image
  tags). The `v` prefix is added in exactly one place — the git tag / GitHub
  release — and that happens in `/release-cut`, not here.

## Step 0 — Preflight

1. Confirm the current branch is `dev`. If not, STOP and report.
2. Confirm the working tree is clean (`git status --porcelain` empty). If
   there are uncommitted changes, STOP and show them — the user must decide.
3. Read the current version from `pyproject.toml`. Parse both the current
   version and `$ARGUMENTS` into `(MAJOR, MINOR, PATCH)` integer triples for
   comparison.

### 0a — Hard stops (never proceed past these)

- **Not newer.** If `$ARGUMENTS` is not strictly greater than the current
  version (compared as integer triples, not string compare), STOP and report.
  This blocks re-running an already-shipped version, going backward, or a typo
  that lands on an old number. Equal-to-current also stops.
- **Tag already exists.** Run `git fetch --tags` then check both
  `git tag -l "v$ARGUMENTS"` and `gh release view "v$ARGUMENTS"`. If either
  exists, STOP and report — the release already exists and must not be
  clobbered.

### 0b — Bump-tier classification (warn + confirm)

Classify the jump from current → target. Only a clean single-patch bump
proceeds silently; everything else pauses for explicit confirmation.

- **Patch bump** = MAJOR and MINOR unchanged, PATCH increased.
  - If PATCH increased by exactly 1 (e.g. `0.3.3` → `0.3.4`): proceed, no
    prompt.
  - If PATCH skipped ahead (e.g. `0.3.3` → `0.3.7`): WARN that N patch
    versions were skipped, show the expected next patch (current with
    PATCH+1), and require explicit confirmation before proceeding.

- **Minor bump** = MINOR increased (MAJOR unchanged), e.g. `0.3.3` → `0.4.0`.
  ALWAYS warn and require confirmation, even for the clean `.0` case. Message:
  this is a **new minor release**, which is infrequent — confirm it's
  intended. Note that a new minor also fires the changelog archive trigger
  (Step 3). If the target is a minor bump but PATCH is not `0` (e.g.
  `0.3.3` → `0.4.2`), additionally flag that new minors normally start at
  `.0`.

- **Major bump** = MAJOR increased, e.g. `0.3.3` → `1.0.0`. ALWAYS warn with
  strong language and require explicit confirmation: this is a **major
  release**, the rarest and most consequential bump, and it produces a new
  `:<major>` image tag. If MINOR or PATCH is not `0` (e.g. `1.2.0`),
  additionally flag that major releases normally start at `X.0.0`.

When warning, always show the three "expected next" successors from the
current version so the user can see what they may have meant:
next patch (`MAJOR.MINOR.PATCH+1`), next minor (`MAJOR.MINOR+1.0`),
next major (`MAJOR+1.0.0`).

Do not proceed on any warned tier without a clear affirmative ("yes",
"confirmed", etc.) in the chat. If the user declines, STOP.

### 0c — Remaining setup

4. Determine whether this is a **new minor** (MINOR differs from current) or
   a **patch within the current minor**. This decides whether the archive
   trigger fires (Step 3). (A major bump is also "new minor" for archive
   purposes — the previous minor series gets archived regardless.)
5. Capture today's date as `YYYY-MM-DD` for the changelog header.

## Step 1 — Bump the version

Update `pyproject.toml` so the literal `version = "<current>"` reflects
`$ARGUMENTS`. This is the single source of truth — CI and the in-app version
display both read from it. Do not touch helper functions or surrounding code.

## Step 2 — Roll the changelog

In `CHANGELOG.md`:

1. Change the `## [Unreleased]` header to `## [$ARGUMENTS] — <today>`.
2. Insert a fresh empty `## [Unreleased]` block (matching whatever HTML-comment
   skeleton the file already uses) directly above the new version header.
3. Leave the rolled section's entries exactly as written by the dev work — do
   not rewrite them, but DO sanity-check that every entry is user-facing prose
   and sits under a correct category heading (Added / Changed / Fixed /
   Security / Deprecated / Removed). Fix obvious miscategorisation only.
4. If the `[Unreleased]` section is empty (no entries to ship), STOP and
   report — there is nothing to release.

## Step 3 — Per-minor archive trigger (NEW MINOR ONLY)

Only if Step 0 determined this is the **first release of a new minor** (e.g.
cutting `0.4.0` while the active file holds `0.3.x`):

1. Move the entire previous minor series (all `0.3.x` blocks, in this example)
   out of `CHANGELOG.md` into a new `docs/CHANGELOG-<prev-minor>.x.md` (e.g.
   `docs/CHANGELOG-0.3.x.md`), newest-first within that file, matching the
   format of any existing archive file.
2. Prepend a link to the new archive in the "Archived releases" index at the
   bottom of `CHANGELOG.md`.
3. Confirm the active `CHANGELOG.md` now holds only `[Unreleased]` plus the
   new current minor series (just the `$ARGUMENTS` block at this point).

For a **patch release** (e.g. `0.3.6`), do NOT archive anything — skip this
step entirely.

## Step 4 — Sync the README

In `README.md`:

1. Update the version badge: in `**Version:** <current>`, replace the current
   version with `$ARGUMENTS` (e.g. `**Version:** 0.0.1` → `**Version:** $ARGUMENTS`).
2. Add a `### v$ARGUMENTS (<today>)` entry at the top of the `## What's New`
   section, summarising this release in user-facing language drawn from the
   changelog entries you just rolled. Keep it consistent with the voice of the
   existing entries.
3. Update any top-of-file new-in banner / one-line status blurb to reference
   `$ARGUMENTS` if it currently names a specific version.

## Step 5 — Sync long-form docs

For each of these docs:

- **`README.md`**: version line and `## What's New` entry — handled in Step 4.
- **`CLAUDE.md`**: update the **Build Status** block — set "Last shipped:
  v$ARGUMENTS" and update "Target for next release" as appropriate.

Do not invent new sections — only adjust version-referencing content that
already exists.

## Step 6 — Validate locally BEFORE committing

Run the same checks CI will run, so a red PR is caught now. Run each in order.
If ANY check fails, STOP, report exactly what failed, and do not commit.

1. `ruff check .`
2. `ruff format --check .`
3. `mypy backend`
4. `pytest -q`
5. Config validation (`config` job from `ci.yml` — validate all tracked YAML/JSON/TOML):
   ```bash
   python - <<'PY'
   import json, pathlib, subprocess, sys, tomllib
   import yaml
   files = subprocess.check_output(
       ["git", "ls-files", "*.yml", "*.yaml", "*.json", "*.toml"],
       text=True).split()
   errors = []
   for f in files:
       p, data = pathlib.Path(f), pathlib.Path(f).read_bytes()
       try:
           if p.suffix in (".yml", ".yaml"):
               list(yaml.safe_load_all(data))
           elif p.suffix == ".json":
               json.loads(data)
           elif p.suffix == ".toml":
               tomllib.loads(data.decode())
       except Exception as e:
           errors.append(f"{f}: {e}")
   for e in errors:
       print(f"::error::{e}")
   if errors:
       sys.exit(1)
   print(f"OK: {len(files)} config files parse cleanly")
   PY
   ```
6. `[ -f .env ] || cp .env.example .env`
7. `docker compose -f docker-compose.yml config --quiet`
8. `docker compose -f docker-compose.dev.yml config --quiet`

Also grep for version-string drift: confirm no stale `<old-version>`
references remain in `README.md`, `pyproject.toml`, or `CLAUDE.md`.
Report any other occurrences you find rather than blindly editing.

## Step 7 — Commit

Stage everything and make ONE commit. Use a conventional-commit subject and a
body that lists what changed. Template:

```
chore(release): prepare v$ARGUMENTS

- pyproject.toml bumped to $ARGUMENTS
- CHANGELOG: rolled [Unreleased] → [$ARGUMENTS] — <today>
- README: version badge + What's New entry
- CLAUDE.md: Build Status block updated
<- archive line ONLY if a new-minor archive was performed>
```

No `Co-authored-by` lines.

## Step 8 — Push and open the PR

1. `git push origin dev`.
2. Open a PR `dev` → `main` with `gh pr create`:
   - Title: `Release v$ARGUMENTS`
   - Body: this release's CHANGELOG section (the `[$ARGUMENTS]` block you just
     rolled), so the PR description is the release notes. This is the same
     text `/release-cut` will use as the GitHub release body — single source
     of truth.
3. Capture the PR URL.

## Step 9 — Report and STOP

Print a short summary:

- The PR URL.
- Confirmation that local validation passed.
- The exact next steps for the human, verbatim:
  1. Review the PR on GitHub and wait for CI to go green.
  2. Merge the PR into `main`.
  3. Wait for the push-to-`main` build to publish `:latest` to the registry.
  4. Run `/release-cut $ARGUMENTS` to tag and publish the GitHub release.

Do NOT proceed past this point. Do not merge. Do not tag.
