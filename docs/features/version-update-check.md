# Feature: Version Footer & Update Check

## Purpose

Show the running app version on every page, link it to the GitHub release notes, and surface a
non-intrusive "Update available" indicator plus a one-time release-notes popup when a newer
release is detected on GitHub.

## Footer

`<footer id="app-footer">` is present in `index.html` and therefore visible on every route.
`mountVersionFooter()` (called once from `main.ts` at startup) fetches `/api/version` and
renders a small version badge into the footer. On any network failure, the footer stays empty —
never throws or blocks app startup.

- Version link: `v{current}` linking to the current tag's release page, opening in a new tab.
- If `update_available`, an "Update available" pill appears next to the version, linking to the
  latest release page.

## Release-notes popup

When `update_available` is true and the user has not already dismissed this version, a closable
modal appears showing the new release name and notes. Dismissal is stored in `localStorage`
under `lf:dismissed-release`; the modal does not reappear for that version. It will reappear
when a newer version is later detected. Close via the × button, backdrop click, or Esc.

`release_notes` content is treated as untrusted text — always rendered via `textContent` into a
`<pre>` element, never injected as `innerHTML`.

## Dev/unreleased build markers

When an image is built from `docker-compose.dev.yml` (or with `--build-arg BUILD_CHANNEL=dev`),
the version footer shows a `-dev+<sha>` suffix — for example `v0.1.2-dev+8e32bb1`. This makes
dev and release builds visually distinct at a glance.

- **`channel`** — `"release"` (default) or `"dev"`. Set via Docker build arg `BUILD_CHANNEL`.
- **`commit`** — short git SHA baked in at image build time via `GIT_COMMIT` build arg (or `null`
  when not stamped). The container has no `.git`, so this is the only way to surface the SHA.
- **`build`** — the full display label with leading `v`:
  - release → `v0.1.2`
  - dev, no SHA → `v0.1.2-dev`
  - dev, with SHA → `v0.1.2-dev+8e32bb1`
- **`is_dev`** — `true` when `channel != "release"`.

**Stamping a dev build with the current commit:**
```sh
GIT_COMMIT=$(git rev-parse --short HEAD) docker compose -f docker-compose.dev.yml build
```

The SHA is best-effort: it goes stale as you commit on a bind-mounted dev container. That is
acceptable — it is a dev marker, not a safety mechanism.

**Update nag suppression on dev:** when `is_dev` is true, the backend forces
`update_available=false` regardless of the semver comparison. Dev builds are typically ahead of
the latest release, so a nag would be misleading. `latest` is still reported for informational
purposes.

## `/api/version` contract

Unauthenticated endpoint (no `require_auth` dependency — mirrors `/api/health` so the footer is
visible even before a user logs in).

**Response when `update_check_enabled` is `false`:**
```json
{
  "current": "0.1.2",
  "latest": null,
  "update_available": false,
  "release_url": null,
  "release_name": null,
  "release_notes": null,
  "checked": false,
  "channel": "release",
  "commit": null,
  "build": "v0.1.2",
  "is_dev": false
}
```

**Response when `update_check_enabled` is `true`:**
```json
{
  "current": "0.1.2",
  "latest": "0.2.0",
  "update_available": true,
  "release_url": "https://github.com/crzykidd/labelforge/releases/tag/v0.2.0",
  "release_name": "v0.2.0",
  "release_notes": "...",
  "checked": true,
  "channel": "release",
  "commit": null,
  "build": "v0.1.2",
  "is_dev": false
}
```

**Response for a dev build (`BUILD_CHANNEL=dev`, `GIT_COMMIT=8e32bb1`):**
```json
{
  "current": "0.1.2",
  "latest": "0.1.2",
  "update_available": false,
  "release_url": "https://github.com/crzykidd/labelforge/releases/tag/v0.1.2",
  "release_name": "v0.1.2",
  "release_notes": "...",
  "checked": true,
  "channel": "dev",
  "commit": "8e32bb1",
  "build": "v0.1.2-dev+8e32bb1",
  "is_dev": true
}
```

If already on the latest version, `update_available` is `false` and `latest` equals `current`.

## `update_check_enabled` toggle

- Default: `true`.
- Stored in the `settings` table (key `update_check_enabled`, type `bool`).
- Exposed in Settings → Updates section with a checkbox and a Save button.
- When `false`, `/api/version` returns the current version only and makes no outbound call.

## Caching & TTL

- The backend caches the parsed GitHub API response in memory with a 6-hour TTL
  (`time.monotonic()`-based). Repeated page loads within the TTL do not contact GitHub.
- On any network error, timeout, or parse failure: the last good cached value is served if
  present; otherwise `latest: null`, `update_available: false` is returned. The endpoint
  never returns a 500.

## No-phone-home safeguards

- The check is backend-proxied; the browser never contacts GitHub directly.
- `update_check_enabled` (default on) gives the operator a single toggle to disable all
  outbound calls.
- The endpoint calls the public REST API of the project's own public repo — read-only,
  no credentials, no SaaS dependency.
- This is unrelated to the label catalog: no auto-update of catalog data occurs.
