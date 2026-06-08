---
name: 2026-06-07-dev-build-version-marker
status: completed
created: 2026-06-07
model: sonnet            # coding task
completed: 2026-06-07
result: Baked BUILD_CHANNEL/GIT_COMMIT into Dockerfile and dev compose; bootstrap reads them; /api/version returns channel/commit/build/is_dev and suppresses update nag on dev; footer uses build label; ADR + changelog + feature doc updated.
---

# Task: Mark dev/unreleased builds in the version display (channel + git SHA)

The app version comes from `pyproject.toml`, which only bumps at release time, so
`dev` builds report the last shipped version (`0.1.2`) and look identical to a
released `0.1.2`. Bake a build channel + git commit into the image so dev builds show
e.g. `v0.1.2-dev+8e32bb1`, and suppress the "update available" nag/popup on dev builds.

This builds on the version footer / update check just added (see
`prompts/done/2026-06-07-version-badge-and-update-check.md`,
`backend/labelforge/routes/version.py`, `frontend/src/version.ts`).

## Decisions already made (do not re-litigate)

- **Mark dev builds with channel + short git SHA**, baked at image build time via
  Docker build args (the container has no `.git`, so runtime detection isn't possible).
  Footer shows `v0.1.2-dev+8e32bb1` for dev; plain `v0.1.2` for release.
- **`/api/version` gains:** `channel`, `commit`, `build` (and an `is_dev` boolean).
  `build` is the full display label WITH the leading `v`.
- **Suppress the update nag on dev:** when the build is a dev build, force
  `update_available=false` and never show the popup (still fine to report `latest`
  informationally).
- **Default channel is `release`.** Only the dev compose file sets `dev`. A plain
  `docker build` / the prod compose / the publish-to-main image stay `release` with no
  extra wiring.

## Before you start

Read:
- `CLAUDE.md` (non-negotiables, conventions, changelog + commit rules).
- The files this task builds on: `backend/labelforge/bootstrap.py` (where `__version__`
  lives), `backend/labelforge/routes/version.py`, `frontend/src/version.ts`,
  `frontend/src/types.ts`.
- Build files: `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`.
- `backend/labelforge/config.py` for the settings idiom (but NOTE: build info is NOT
  operator `.env` config — read it from the OS environment in `bootstrap.py`, see below).
- `docs/decisions.md` (newest-at-top ADR format) and `docs/features/version-update-check.md`
  (you will update both).

## Working tree check

Run `git status --porcelain` and cross-reference the files below. The tree should be
clean after the previous commit (`8e32bb1`). If any file this plan touches has
uncommitted changes, list them and ask before proceeding. This prompt file is exempt.

## What to do

### Build-time wiring

1. **`Dockerfile`** — add two build args and surface them as env vars. To avoid busting
   the layer cache on every commit, place the `ARG`/`ENV` lines **near the very end,
   immediately before `CMD`** (after `USER`/`EXPOSE` is fine):
   ```dockerfile
   ARG BUILD_CHANNEL=release
   ARG GIT_COMMIT=""
   ENV LABELFORGE_CHANNEL=$BUILD_CHANNEL \
       LABELFORGE_COMMIT=$GIT_COMMIT
   ```

2. **`docker-compose.dev.yml`** — under the service `build:`, switch to the long form
   and pass dev args:
   ```yaml
   build:
     context: .
     args:
       BUILD_CHANNEL: dev
       GIT_COMMIT: ${GIT_COMMIT:-}
   ```
   The SHA is best-effort (it goes stale as you commit on a bind-mounted dev container —
   that's acceptable for a dev marker). Document in a short comment that the operator can
   stamp it with:
   `GIT_COMMIT=$(git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml build`.

3. **`docker-compose.yml`** (prod) — leave channel at the default `release`. Optionally
   accept a `GIT_COMMIT` pass-through but keep it minimal; do NOT set `BUILD_CHANNEL`
   here (default `release` is correct). If you switch `build: .` to the long form to add
   the arg, keep `context: .`.

### Backend

4. **`bootstrap.py`** — alongside `__version__`, read the build markers from the OS env
   and expose them (import-safe, no failures):
   - `__channel__ = os.environ.get("LABELFORGE_CHANNEL", "release").strip() or "release"`
   - `__commit__ = os.environ.get("LABELFORGE_COMMIT", "").strip() or None`
   Optionally extend the existing startup log line to include channel/commit.

5. **`routes/version.py`** — import `__channel__`, `__commit__` from bootstrap. Compute:
   - `is_dev = __channel__ != "release"`
   - `build` display label (WITH leading `v`):
     - release → `f"v{current}"`
     - dev → `f"v{current}-dev"` plus `f"+{__commit__}"` when a commit is present
       (e.g. `v0.1.2-dev+8e32bb1`, or `v0.1.2-dev` if no SHA was baked).
   - Add `channel`, `commit`, `build`, `is_dev` to BOTH return branches (toggle-off and
     toggle-on).
   - **Suppress nag on dev:** when `is_dev` is true, force `update_available=False`
     regardless of the semver compare. `latest` may still be reported for info.

### Frontend

6. **`types.ts`** — extend `VersionInfo` with:
   ```ts
   channel: string
   commit: string | null
   build: string
   is_dev: boolean
   ```

7. **`version.ts`** — in `mountVersionFooter`, use `info.build` as the footer link text
   (fallback to `v${info.current}` if `build` is missing). Keep the link *target* as the
   base tag (`https://github.com/crzykidd/labelforge/releases/tag/v${info.current}`) when
   `update_available` is false, since the dev build's base maps to that tag. The pill and
   release-notes popup are already gated on `info.update_available`, which the backend now
   forces false on dev — so no extra frontend gating is needed, but verify that path.

### Docs + changelog

8. **`CHANGELOG.md`** — add a `## [Unreleased]` entry: dev/unreleased builds now show a
   `-dev+<sha>` suffix and don't show the update nag.

9. **`docs/features/version-update-check.md`** — document the new `channel`/`commit`/
   `build`/`is_dev` fields, the build-arg wiring (`BUILD_CHANNEL`, `GIT_COMMIT`), the
   `v0.1.2-dev+<sha>` label, and the dev nag suppression.

10. **`docs/decisions.md`** — new ADR at top (`2026-06-07`): why dev builds are marked
    via build-time channel + SHA (no `.git` in the container → no runtime detection),
    default `release`, and why the update nag is suppressed on dev (dev is typically
    *ahead* of the latest release, so a nag would be misleading). Note what would cause a
    revisit.

## Conventions to honor

- LF line endings; match surrounding style; comments only for non-obvious *why*.
- No new dependencies. Build info via env, not `.env`/pydantic Settings.
- Don't reorder Dockerfile layers in a way that busts the cache earlier than necessary —
  the build-arg ENV goes at the end.
- Changelog required; docs ship in the SAME commit. Commit prefix `feat:`; no
  `Co-authored-by:`.

## Verify

- `python -c "from labelforge.routes import version; from labelforge import bootstrap"`
  imports clean.
- Backend logic check (no Docker needed): with `LABELFORGE_CHANNEL=dev
  LABELFORGE_COMMIT=8e32bb1` set, `GET /api/version` (or a direct call to the build-label
  logic) yields `build == "v0.1.2-dev+8e32bb1"`, `is_dev == true`, and
  `update_available == false` even if a newer `latest` is present. With the channel unset
  it yields `build == "v0.1.2"`, `is_dev == false`.
- Frontend `npm run build` (tsc + vite) passes.

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-07`, one-line `result`).
2. `git mv` this file to `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the ADR (step 10).
4. **You are a spawned agent: do NOT commit.** Prepare the tree and report back the
   per-file summary, final `git status --porcelain`, a proposed one-line `feat:` commit
   message, the explicit paths to stage, and your verify results. Never `git add -A`,
   never push, never auto-commit.
