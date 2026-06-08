---
name: 2026-06-07-version-badge-and-update-check
status: completed
created: 2026-06-07
model: sonnet            # coding task
completed: 2026-06-07
result: All backend and frontend changes implemented; backend import clean; frontend build passes (tsc + vite). New route backend/labelforge/routes/version.py, setting update_check_enabled added, router registered in main.py, VersionInfo type, getVersionInfo API call, footer in index.html, version.ts module, Updates section in settings.ts, styles in style.css, CHANGELOG entry, feature doc, ADR.
---

# Task: App version footer + GitHub update check + release-notes popup

Add an always-visible app version on every page that links to its GitHub release
notes; when a newer release exists on GitHub, show an "Update available" indicator
next to the version and pop up the new release's notes in a closable box (once per
new version). The GitHub check is backend-proxied + cached and gated by a default-on
Settings toggle.

## Decisions already made (do not re-litigate)

- **Check location: backend proxy.** The backend calls the GitHub API, caches the
  result in-memory with a TTL, and serves it to the frontend at `GET /api/version`.
  The browser never calls GitHub directly.
- **Toggle: `update_check_enabled`, default ON.** A Settings toggle controls whether
  any outbound GitHub call happens. When OFF, `/api/version` returns the current
  version only and makes no network call.
- **Badge placement: fixed footer** (not the nav bar), visible on every page.
- **Repo: `crzykidd/labelforge`** (public).
- **No new Python dependency.** Use the stdlib `urllib.request` for the GitHub call —
  do NOT add `httpx`/`requests` to `pyproject.toml` (httpx is dev-only).

## Before you start

Read these to match conventions:
- `CLAUDE.md` (non-negotiables, repo conventions, changelog + commit rules).
- `docs/architecture.md` and `docs/glossary.md` for endpoint/vocabulary conventions.
- `docs/decisions.md` — newest-at-top ADR format (you will add an entry).
- Existing patterns you must mirror:
  - Backend route: `backend/labelforge/routes/health.py` (an **unauthenticated**
    router — `/api/version` is unauthenticated like `/api/health`, so the footer
    shows even on the token-gate screen).
  - Settings registry + persistence: `backend/labelforge/settings_store.py`
    (`_REGISTRY`, `validate`, `get`, `set`).
  - Router registration: `backend/labelforge/main.py` (the `app.include_router(...)`
    block, all under `/api`).
  - Version source: `backend/labelforge/bootstrap.py` exposes `__version__`
    (already imported in `main.py`). Reuse it; bare version `0.1.2` lives in
    `pyproject.toml`.
  - Frontend API client: `frontend/src/api.ts` (`apiFetch`, exported typed funcs).
  - Frontend types: `frontend/src/types.ts`.
  - Frontend bootstrap: `frontend/src/main.ts`; shared chrome in `frontend/index.html`.
  - localStorage UI-state pattern: `frontend/src/lastLabel.ts` (try/catch wrapper).
  - Settings UI section pattern: `renderPrinterSettings` in
    `frontend/src/pages/settings.ts`.
  - Global styles: `frontend/src/style.css` (match its idiom for the new footer,
    update pill, and modal).

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files
this plan modifies. If any have uncommitted changes, list them and ask before
touching. Surface unrelated dirty files once; don't block. This prompt file is exempt.

## What to do

### Backend

1. **Add the setting.** In `settings_store.py` `_REGISTRY`, add
   `"update_check_enabled": {"default": True, "vtype": bool}`.

2. **New route `backend/labelforge/routes/version.py`** — an `APIRouter()` with **no**
   `require_auth` dependency (mirror `health.py`). One endpoint `GET /version`:
   - Always include the current version from `labelforge.bootstrap.__version__`.
   - Read `update_check_enabled` via `settings_store.get("update_check_enabled")`.
     If False → return current only, no network call:
     `{ "current": <v>, "latest": null, "update_available": false, "release_url": null, "release_name": null, "release_notes": null, "checked": false }`.
   - If True → return the cached GitHub result, refreshing it if older than the TTL.
     Shape: `{ "current", "latest", "update_available", "release_url", "release_name", "release_notes", "checked": true }`.
   - **GitHub fetch** (`https://api.github.com/repos/crzykidd/labelforge/releases/latest`):
     use `urllib.request` with `Accept: application/vnd.github+json` and a
     `User-Agent: labelforge` header, timeout ~3s. Parse `tag_name`, `html_url`,
     `name`, `body`. Strip a leading `v` from `tag_name` to get `latest`.
   - **Cache:** module-level dict holding the parsed result + a timestamp (use
     `time.monotonic()`); TTL ~6 hours. Repeated requests within the TTL must NOT
     re-hit GitHub. A single in-flight refresh is fine; keep it simple.
   - **Never 500 on network/timeout/rate-limit/parse errors.** On failure, serve the
     last good cached value if present; otherwise return `latest: null`,
     `update_available: false`, and log a warning. The footer must degrade gracefully.
   - **Version compare:** small helper that parses dotted numeric semver
     (`MAJOR.MINOR.PATCH`, tolerate missing parts and a `v` prefix) and returns whether
     `latest > current`. If either is unparseable (`"unknown"`), `update_available` is
     false. Put the helper in this module (or a tiny `version_compare` helper) — no new
     dependency.

3. **Register the router** in `main.py`: `app.include_router(version.router, prefix="/api")`
   alongside the others (import it with the rest).

### Frontend

4. **Type** in `types.ts`: add
   ```ts
   export interface VersionInfo {
     current: string
     latest: string | null
     update_available: boolean
     release_url: string | null
     release_name: string | null
     release_notes: string | null
     checked: boolean
   }
   ```

5. **API client** in `api.ts`: add
   `export function getVersionInfo(): Promise<VersionInfo> { return apiFetch<VersionInfo>('/api/version') }`.

6. **Footer chrome** in `index.html`: add `<footer id="app-footer"></footer>` after the
   `#app` div so it's present on every route.

7. **New module `frontend/src/version.ts`** exporting `mountVersionFooter()`:
   - Fetch via `getVersionInfo()`. On any failure, leave the footer empty (silent) —
     do not throw.
   - Render into `#app-footer`:
     - The version as `v{current}` linking to the release-notes page. If
       `release_url` is present and `update_available` is false, link current there;
       otherwise link to the current tag:
       `https://github.com/crzykidd/labelforge/releases/tag/v{current}`. Open in a new
       tab (`target="_blank" rel="noopener"`).
     - If `update_available`, render an "Update available" pill next to the version,
       linking to `release_url` (the latest release). Make it visually distinct.
   - **Release-notes popup:** if `update_available` and the latest version has not been
     dismissed, show a closable modal containing `release_name` (heading) and
     `release_notes`. Dismissal is per-version: store the dismissed `latest` string in
     `localStorage` under key `lf:dismissed-release` (use a try/catch wrapper like
     `lastLabel.ts`). The modal must NOT reappear for that version once dismissed, but
     MUST appear again when a newer version later shows up. Close via an × button, a
     backdrop click, and `Esc`. Also include a link in the modal to the full notes
     (`release_url`).
   - **Security:** `release_notes` is untrusted markdown from GitHub. Do NOT inject it
     as `innerHTML`. Render it as text (e.g. `textContent` into a scrollable
     `<pre>`/`<div class="release-notes-body">`). No markdown library.
   - Call `mountVersionFooter()` once from `main.ts` (after `initAuthMode().finally(...)`
     routing setup — it's independent of routing and should run once at startup, not
     per-route).

8. **Settings UI** in `frontend/src/pages/settings.ts`: add an "Updates" section
   (mirror the printer-settings pattern) with a checkbox bound to
   `update_check_enabled` (default checked when `!== false`) and a Save button that
   calls `putSettings({ update_check_enabled: checkbox.checked })`, with a hint like
   "Check GitHub for new releases". Load the value from the same `getSettings()` call
   already made at the bottom of the file.

9. **Styles** in `style.css`: add rules for `#app-footer`, the version link, the
   "update available" pill, and the release-notes modal (backdrop + box + scrollable
   body + close button). Match the existing visual idiom; keep the footer compact and
   unobtrusive.

### Docs + changelog

10. **`CHANGELOG.md`** — add an entry under `## [Unreleased]` (user-facing, concise),
    e.g. *"Show the app version on every page linking to its GitHub release notes, with
    an update-available indicator and a one-time release-notes popup when a newer
    release is detected (toggle in Settings, on by default)."*

11. **`docs/features/version-update-check.md`** — short feature doc (purpose, the
    `/api/version` contract, the toggle, caching/TTL, dismissal behavior, the
    no-phone-home safeguards). Keep it tight; mirror the style of existing
    `docs/features/*.md`.

12. **`docs/decisions.md`** — new ADR at the very top dating `2026-06-07`. Capture:
    backend-proxied + cached GitHub release check; default-on `update_check_enabled`
    toggle so outbound calls are operator-controllable; stdlib `urllib` (no new dep);
    semver compare; per-version dismissible popup; **why this does not violate the
    non-negotiables** (operator-controllable, can be disabled, read-only public API of
    the project's own repo, no SaaS infrastructure dependency, not an auto-update of the
    label catalog). Note what would cause a revisit.

## Conventions to honor

- LF line endings; match surrounding code style; comments only for non-obvious *why*.
- Backend: keep the endpoint resilient (never 500); cache so repeated hits don't spam
  GitHub. No new runtime dependency.
- Frontend: vanilla TS, no new libs; render untrusted notes as text, not HTML.
- Changelog entry is required; docs ship in the SAME commit as the code.
- Commit prefix `feat:`; no `Co-authored-by:` trailers.

## Verify

- Backend: `python -c "from labelforge.routes import version"` imports clean; with the
  app running, `GET /api/version` returns the current version and (toggle on) a
  `latest`/`update_available`; toggling `update_check_enabled` off makes it skip the
  network call.
- Frontend: `npm run build` (or the project's typecheck/build) passes; footer shows the
  version on every page; popup appears for a newer version and stays dismissed after
  closing.

## When done

1. Update this file's frontmatter: `status`, `completed: 2026-06-07`, one-line `result`.
2. `git mv` this file to `prompts/done/` (success) or `prompts/failed/` (failure);
   create the dir if needed.
3. Record the ADR in `docs/decisions.md` (step 12 above).
4. **You are a spawned agent: do NOT commit.** Prepare the working tree, then report
   the file list + a proposed one-line `feat:` commit message back to the orchestrating
   session for the `y/n`. Never `git add -A`, never push, never auto-commit.
