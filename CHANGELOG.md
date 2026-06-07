# Changelog

All notable changes to labelforge are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Project follows semantic versioning once the first release ships.

## [Unreleased]

### Fixed

- fix: render templates at the correct position when elements use centered origins (`originX: 'center'` / `originY: 'center'`); previously such elements were shifted right and down by half their box size, fanning wider elements further than narrow ones.

## [0.1.2] — 2026-06-07

### Fixed

- **Published container image was unpullable (`manifest unknown` / 404)** — the publish
  workflow built with `docker/build-push-action` defaults, which attach provenance/SBOM
  *attestations* and turn each pushed tag into an OCI image index whose per-platform and
  attestation manifests are **untagged**. The weekly "Cleanup Container Images" job deleted
  untagged versions with `min-versions-to-keep: 0`, removing those child manifests and leaving
  every tag (`:latest`, `:v0.1.1`, …) pointing at a missing manifest. The build now pushes a
  plain single-platform manifest (`provenance: false`, `sbom: false`), and the cleanup keeps a
  buffer (`min-versions-to-keep: 5`) with a warning that untagged-deletion is unsafe for
  indexed/attested images. Pulling `:latest` works again after the next publish.

## [0.1.1] — 2026-06-06

### Added

- **Detailed, fail-fast startup logging** — the container now logs its version and Python
  version, the effective (non-secret) configuration, the data directory, whether the database
  was created or opened, any schema migrations applied, and a "startup complete" line. Logging
  is configured before the config is loaded and sent unbuffered to stdout, so a misconfiguration
  is reported clearly instead of crashing silently.
- **Permission preflight on `DATA_DIR`** — startup now write-probes the data directory and, if
  it isn't writable by the container's runtime user (uid 1000), aborts with an actionable
  CRITICAL message (showing the uid/gid and a `chown` hint) instead of a bare `PermissionError`.

### Fixed

- **No more silent crash-on-start** — required-env-var and configuration errors (e.g. a missing
  `PRINTER_HOST` or `API_TOKEN`) previously raised at import time *before* logging was set up,
  so a misconfigured deployment failed with no usable output. Configuration now loads behind
  logging and reports exactly which variable is missing. The Docker image also sets
  `PYTHONUNBUFFERED=1` so logs are never lost to buffering on a fast restart, and creates/owns
  `/data` for the runtime user so named-volume deployments work out of the box. The in-app/API
  version display also now reflects the real package version instead of a hardcoded `0.0.1`.

### Changed

- **Dependency updates** — rolled in the pending Dependabot bumps: backend `fastapi >=0.136.3`,
  `pydantic >=2.13.4`, `python-barcode >=0.16.1`, and dev tools `mypy >=2.1.0` /
  `types-PyYAML >=6.0.12`; frontend `fabric 7.4.0`, `vite 8`, `typescript 6`; the Docker base
  image to `python:3.14-slim`; and CI actions (`docker/metadata-action@v6`,
  `docker/build-push-action@v7`, `github/codeql-action@v4`). Verified locally: backend lint +
  mypy 2.x + tests pass, and the frontend type-checks and builds. A `frontend/src/vite-env.d.ts`
  (`vite/client` reference) was added because TypeScript 6 now requires ambient types for the
  side-effect `import './style.css'`. Fabric 7's serialization was checked to still emit `IText`
  and preserve the `labelforge_raw_content` custom property, so existing saved templates and the
  server renderer are unaffected. No user-facing behaviour change.

## [0.1.0] — 2026-06-06

### Security

- **Log-injection hardening (CWE-117)** — user-influenced values that reach a log line
  (the history `job_id` path parameter and the requested label media on a media-mismatch
  warning) are now passed through a `scrub()` helper that strips CR/LF before interpolation,
  so a crafted value can't forge additional log entries. No behaviour change for legitimate
  input.
- **Code-scanning cleanup** — documented three intentionally-empty exception handlers flagged
  by CodeQL `py/empty-except` (shutdown-task cancellation, best-effort printer-socket close,
  malformed stored-payload fallback); the socket-close handler now logs at debug instead of
  silently swallowing. No behaviour change.
- **No exception detail in the printer-status error response (CWE-209)** — `GET /api/printer/status`
  returned the raw exception text in its 503 body when status was unavailable, which CodeQL
  flagged as information exposure. It now logs the exception server-side and returns a generic
  "Printer status is currently unavailable." message.

### Added

- **Friendly template names** — when creating a template, type a human-readable name (e.g.
  `Spool Label`); the URL slug (`spool-label`) is auto-derived and shown as a live read-only
  hint. The friendly name is stored as `display_name`, shown in the template list and as the
  editor title. Renaming `display_name` after creation is not yet available in the UI. Requires
  a container image rebuild.

- **DK part number in the template list** — the Media column now shows the Brother DK part
  number with dimensions (e.g. `DK-1209 (62×29mm)`) instead of the raw media id. Two-color
  media gets a `Red` suffix (e.g. `DK-2251 (62mm) Red`). If the media id is not in the catalog,
  the raw id is shown as before. Requires a container image rebuild.

- **Print a template on a different label media at recall time (one-off)** — the recall page
  now shows a media selector instead of a read-only badge, defaulting to the template's own
  media (e.g. a two-color template defaults to `62red`). Same-width media appear first
  (most likely to fit the design without adjustment); a "Loaded in printer" toggle narrows
  the list to the roll currently mounted. The stored template media is never mutated. The
  chosen media is logged to history and reproduced faithfully on reprint. The Print button is
  gated until a fresh preview has been taken after any media change. If the chosen media
  doesn't match the roll actually loaded, the printer-status check still blocks with a 409,
  but the recall page now offers a "print anyway" confirmation to override it. Requires a
  container image rebuild.
- **Mono + red notice on recall** — when a template contains red elements and a mono
  (single-color) media is selected, an inline notice explains that red will print in black.
  The renderer already maps red → black automatically; no action is needed.
- **Overflow warning on recall** — when a die-cut media is chosen and the content extends
  past its printable height, an inline warning appears near the preview. Printing still
  proceeds — the user decides from the preview whether to adjust or proceed.

### Changed

- **Docs reconciled with shipped features** — the README's "What it does" was rewritten to
  cover everything now implemented (two-color printing, printer-status/loaded-media detection,
  the label catalog, settings/retention, print-time media override, batch printing, and
  `DISABLE_AUTH`), and gained a "Running it" section with a configuration table. The PRD's
  in-scope list now includes two shipped features it omitted (one-off media override at recall;
  two-color red text in templates), and `architecture.md` was corrected to reference the real
  compose filenames (`docker-compose.yml` / `docker-compose.dev.yml`). Docs-only.

- **Template list actions are now compact icon buttons** — the per-row Print / Edit / Delete
  buttons were full-size text buttons that, together with a verbose timestamp, overflowed the
  card. They're now small icon buttons (with tooltips and accessible labels), the Updated
  column shows a shorter date (no seconds) on a single line, and the table fits within the card
  without widening the layout. Requires a container image rebuild.

- **Adopted `release-prep-and-cut` standard (v1.0.0)** — `/release-prep` and `/release-cut` slash commands added to `.claude/commands/`; publish workflow (`build-and-push.yml`) now fires on `release: published` (tag-push trigger removed); `CLAUDE.md` and `standards.md` updated. Developer/process-facing only — no runtime change.

### Fixed

- **"Run cleanup now" works again** — the Settings → History & Retention "Run cleanup now"
  button returned **Method Not Allowed**: the frontend posted to `/api/admin/prune-history`,
  but that route was never implemented, so the request fell through to the SPA catch-all (a
  GET) and 405'd. The endpoint now exists (auth-gated, like the other admin routes) and
  `prune_history()` returns the number of jobs removed, so the button reports e.g. "Cleanup
  done — 3 job(s) removed." Requires a container image rebuild.

- **Upgrade now delivers new and corrected default catalog entries** (#16) — upgrading the
  container image no longer leaves the operator's `labels.yml` stale. On startup, labelforge
  performs a non-destructive 3-way merge: new entries from the bundled default are added,
  corrected field values (e.g. `brother_part` SKU fixes) are applied to fields the operator
  never customized, and any operator customizations or custom media entries are preserved and
  never deleted. A backup is written to `$DATA_DIR/labels.yml.bak` before any change. Opt out
  with `CATALOG_AUTO_MERGE=false`. Requires a container image rebuild.

### Added

- **`POST /api/admin/reload-catalog`** — re-runs catalog reconciliation and reloads the catalog
  from disk without restarting the container. Returns a JSON summary of entries added/updated
  and whether the operator file was rewritten. Requires API token.

### Changed

- **CI now type-checks the backend with mypy** — `mypy` (≥1.11) and `types-PyYAML` are added to the dev extra; a `[tool.mypy]` section in `pyproject.toml` enables the pydantic plugin and per-module stub overrides for unstubbed third-party libs (`brother_ql`, `qrcode`, `barcode`). Enabling type-checking surfaced a latent Pillow resampling deprecation (`Image.BICUBIC` / `Image.NEAREST` → `Image.Resampling.*`) and tightened several return types. Developer-facing only — no runtime behavior change.

- **CI: compose validation now targets `docker-compose.yml` / `docker-compose.dev.yml`** — the compose job previously looked for `compose.yml` / `compose.dev.yml` (wrong filenames) and used a `bash -e` one-liner that treated a missing file as a failure. The loop is now hardened to skip absent files and only fail on a bad `docker compose config`. It also seeds a throwaway `.env` from the tracked `.env.example` first, since the compose files reference `env_file: .env` (which is gitignored) and `config` would otherwise fail to resolve it. The `CLAUDE.md` convention note is corrected to match the actual filenames. Backend linting (ruff) is also clean: import order fixed in `routes/print.py`, `datetime.UTC` modernisation in `templates/store.py`, and long-line wraps across several `backend/` files.

- **Dependabot now targets `dev`, never `main`, and runs monthly** — all four ecosystems (github-actions, pip, npm, docker) in `.github/dependabot.yml` now set `target-branch: dev`, so dependency-bump PRs open against the working branch and only reach `main` through a managed release PR. Previously they defaulted to `main`, cluttering the release queue with PRs that could never be allowed to auto-merge. The version-update cadence is also relaxed from weekly to monthly to suit a low-maintenance released project (security updates, when enabled, are advisory-driven and unaffected by this schedule). Process-only — no runtime change.

### Added

- **Load previous values on template recall** — the recall form now has a **Load previous values** button (only for templates with variable fields). Clicking it fills the form with the field values from the last time this template was printed, so you can make quick adjustments without re-typing. The button is disabled when the template has no print history. The most recent print job for each template is now also protected from retention pruning, so these values survive cleanup. Requires a container image rebuild.

- **Text-color control always visible in template editor** — the Black / Red color dropdown in the toolbar is now visible for all templates, not just two-color media. On mono media the Red option is present but disabled, with a tooltip explaining it requires a two-color label (e.g. 62red); on two-color media Red is selectable as before. Hovering over the Add Text button now also shows a tooltip noting `{fieldname}` placeholder syntax. Requires a container image rebuild.

### Fixed

- **Continuous templates now extend to fit large text** — previewing or printing a continuous-roll template (e.g. 62mm endless) where the last text element uses a large font no longer cuts off the bottom of that text. Previously the render trusted the editor's browser-measured font height, which is shorter than what Pillow actually draws at the same point size; the canvas was too short and the last line was clipped. The renderer now measures rasterized text height with Pillow before sizing the canvas. Die-cut template rendering is unchanged.

- **Template preview no longer fails when the template has variable fields** — clicking Preview in the editor on a template containing `{fieldname}` placeholders previously returned "Missing required field" because the preview route used the same strict field-validation as the print route. The preview route now fills missing fields with their stored default (if any) or the field name itself as a sample value, so `{type}` renders as the literal text `type`. Passing real field values from the recall UI still works and takes precedence. Requires a container image rebuild.

### Added

- **Save As in template editor** — toolbar now has a **Save As** button that saves the current canvas first, then opens a modal for a new template slug and label media (pre-filled with the current media). Clones the template via `POST /api/templates/{name}/duplicate` and opens the editor on the copy. This is the documented way to re-use a design on different media; the existing template's media is never mutated. The current media is also shown as a read-only badge next to the template name. Requires a container image rebuild.
- **Full two-color (red) text in templates** — templates on two-color media (`62red` / DK-2251) can now use red text in addition to black. A **Black / Red** toggle appears in the editor toolbar only when the loaded label is two-color (hidden for mono media). Selecting an element and changing the toggle updates its Fabric `fill` to `#000000` or `#ff0000`; new text elements inherit the current selection. The server renderer now emits an RGB image for two-color media, compositing each text element's `fill` as the ink color (red → red plane, black → black plane); lines honor `stroke`, rects honor `fill` and `stroke`. The preview PNG for two-color templates now returns a color image rather than thresholded mono, so the preview reflects actual print output. Printing is unchanged (the print path already promoted L→RGB and passed `red=True` for two-color media). Requires a container image rebuild.

### Fixed

- **Template editor canvas aspect on continuous rolls** — opening the editor on a continuous roll (e.g. `62`, `62red`) showed a landscape canvas (696 × 400px for 62mm) because the initial working height was set to 400 dots (~34mm). This made the canvas visually wider than tall, which reads as wrong for a label roll. The default working height is now 1000 dots (~84mm), which gives a portrait display (418 × 600px scaled) for the 62mm roll. Print length is still content-driven server-side. Requires a container image rebuild.

### Known Issues

- QR and barcode template elements render in preview but print as a solid black block (1-bit threshold crushes fine detail). These elements are gated to raise a clear error until fixed. Text, lines, and rectangles print correctly, including in red on two-color media.

### Changed

- **De-adopted the `vexp-context-engine` standard** (now sunset at v3.0.0 — vexp retired homelab-wide). Removed all repo wiring: the `.claude/hooks/vexp-guard.sh` guard hook and `.vexpignore`, the `mcp__vexp__*` permission entries and `PreToolUse` hook in `.claude/settings.json`, the "Context search" operational-rules section in `CLAUDE.md`, and the vexp `.gitignore` block. Coding sessions use normal `grep`/`glob`/`Read` again. Developer/process-facing only — no runtime change.
- **Adopted four crzynet engineering standards**, pinned in a new root `standards.md`: `code-checkin-and-pr @ 1.1.0` (commit messages now use Conventional-Commits prefixes `feat:`/`fix:`/`chore:`/`docs:`; CI gained structured-config and `docker compose config` validation jobs), `handoff-prompt-workflow @ 1.5.0` (completed handoff prompts now archived under `prompts/done/`; `prompts/TEMPLATE.md` added), `repo-sandbox-permissions @ 1.0.0` (repo-wide sandbox in `.claude/settings.json` — auto-approves in-repo work, gates out-of-repo writes and network), and `vexp-context-engine @ 2.1.0` (guard hook now tracked, `.vexpignore` added). Developer/process-facing only — no runtime behavior change.

### Added

- **Optional app-level auth (`DISABLE_AUTH`)** — set `DISABLE_AUTH=true` to run with no Bearer-token auth, for deployments fronted by a reverse proxy (e.g. Traefik) that handles authentication. Default is unchanged and secure: auth on, and the app refuses to start without `API_TOKEN`. When disabled, every `/api/*` route is open, `GET /api/health` reports `auth_required: false`, and the web UI skips its token-entry gate. See ADR 2026-06-02.

### Fixed

- **Continuous-media templates are now editable** — opening the canvas editor on a continuous roll (e.g. `62`, `62red`) produced a zero-height canvas, because continuous media report a printable length of `0` (endless roll) and the editor used that directly. Elements added to it were invisible (and saved at `top=0`), which looked like "Add Text does nothing." Continuous templates now open at a default working length (~34mm); print length is still derived from content server-side, per the templates design doc. Requires a container image rebuild.
- **Template text now renders and prints** — the canvas editor uses Fabric.js v6, which serializes element types as PascalCase class names (`IText`, `Line`, `Image`); the server renderer and field detection still matched the Fabric v5 lowercase/hyphenated names (`i-text`), so every text element was silently skipped — previews and prints of any template came out blank and no variable fields were detected. Both now normalize the type (lowercase, strip hyphen) and handle v5 and v6 serializations. The editor's font family/size controls (which had the same mismatch) again update the selected text. The frontend fix requires a container image rebuild to take effect; the renderer/field-detection fix is backend-only. — printing to a two-color roll (DK-2251, 62mm black/red continuous, id `62red`) was rejected by the printer as "wrong roll: check the print data" because the job declared mono media. The print path now passes `red=True` and an RGB image to the rasterizer for two-color media, so the job declares the correct media type. Black-only text prints fine on these rolls (the red plane is left empty).
- **Pre-print media check no longer blocks same-size color variants** — the printer doesn't reliably report tape color, so the status read can't tell `62` from `62red` (both 62mm continuous) and was wrongly rejecting `62red` prints with a 409. The check now treats rolls of identical physical dimensions as compatible; mismatched sizes (e.g. 62 vs 29) still block.
- **API error messages no longer show `[object Object]`** — the frontend now surfaces the human-readable `message` from structured `409` errors (media mismatch / printer error) instead of stringifying the whole object.

### Known Issues

- QR and barcode template elements render in preview but print as a solid black block (1-bit threshold crushes fine detail). These elements are gated to raise a clear error until fixed. Text, lines, and rectangles print correctly.

### Added

- **Color-limitation note on the label picker** — when "Loaded in printer" matches a roll that has both mono and two-color variants of the same size (e.g. `62` / `62red`), a note above the picker explains that the printer doesn't report tape color, so the right variant must be chosen manually.
- **Printer status controls in Settings** — the Settings → Printer section now has a "Status check enabled" toggle and a status-timeout (ms) field, wired to the `printer_status_check` / `printer_status_timeout_ms` settings. These existed only on the backend before, with no way to change them from the UI.
- **Loaded-media filter on label selectors** — the label-media dropdown on Quick Print and the New Template modal now includes a "Show all / Loaded in printer" toggle; switching to Loaded queries the printer once and narrows options to the roll actually mounted (matching mono and two-color variants by dimension). Falls back to the full list with an inline notice if the printer is unreachable, reports no media, or the loaded roll is not in the catalog.
- **Printer status check** — `GET /api/printer/status` returns loaded media, ready state, and errors; print endpoints (`POST /api/print/quick`, `/api/print/{name}`, `/api/print/{name}/batch`) block on media mismatch with a 409 (pass `?override=true` to proceed); Settings page "Test Printer" button shows live printer state. Status queried over raw TCP (ESC i S) with HTTP fallback to the printer's status page; degrades gracefully if unreachable. Controlled by `printer_status_check` and `printer_status_timeout_ms` settings.
- **Print history page** — browse, reprint, pin, and delete past prints at `/history`; paginated reverse-chronological list with authenticated thumbnail previews, template/quick-print labels, field-value display, and filters (by template name, pinned-only toggle). Reprint creates a new job and refreshes the list; a 409 (template or media gone) surfaces the server's error message. Delete requires confirmation. Pin toggle updates inline without a reload. Retention policy configurable in `/settings` (keep forever / last N / last N days); pinned prints are never pruned; "Run cleanup now" triggers an immediate prune.
- **Print history API** — every print is logged with a preview PNG; browse paginated history at `GET /api/history`, fetch full detail at `GET /api/history/{id}`, serve the preview image at `GET /api/history/{id}/preview.png`, reprint a past job at `POST /api/history/{id}/reprint` (creates a new row linked via `reprint_of`), pin/unpin at `POST /api/history/{id}/pin`, and delete at `DELETE /api/history/{id}`. Retention auto-pruning runs at startup and every 6 hours, honoring the `retention_mode` / `retention_count` / `retention_days` settings. Pinned rows are never pruned.
- **Printer-aware label catalog** — each label now carries a `supported` flag computed at catalog load against the configured printer (`PRINTER_MODEL`). Media the printer physically can't print — wide-format rolls on a non-QL-1xxx printer, two-color rolls on a mono printer — appear in the selectors greyed out, disabled, and marked `— unavailable` with a tooltip explaining why, instead of being silently offered. On the default QL-820NWB the six wide-format rolls (`102`, `103`, `104`, `102x51`, `102x152`, `103x164`) are now disabled; `62red` stays selectable. Compatibility is derived from the `brother_ql` library, not hand-maintained — the `printer_requirements` field in `labels.yml` is deprecated and ignored.
- **Brother DK part numbers in label selectors** — the label-media dropdown (quick-print and the new-template modal) now shows the part number with the name, e.g. `DK-2205: 62mm Continuous (Black)`; entries without a part number show the name alone. Backfilled `brother_part` for 9 more default catalog entries (14 of 15 now carry a part number; `52x29` has no consumer DK roll). Grouping/formatting moved into a shared `frontend/src/labels.ts` helper.
- **Template recall UI** — fill variable fields, preview, and print from saved templates at `/templates/{name}/print`; batch printing with auto-increment for numeric fields
- **Templates editor foundation (text-only slice)** — canvas editor at `/templates/{name}` built on Fabric.js 6.6.1:
  - Templates list page at `/templates`: shows name, label media, last-updated; Edit and Delete (soft-delete) per row; empty state
  - New-template modal: slug-validated name (`^[a-z0-9][a-z0-9-]*$`), label media grouped by form factor (same grouping as quick-print)
  - Editor toolbar: Add Text, Delete selected, font family selector (populated from `/api/fonts`), font size input, Preview, Save, Back
  - Canvas geometry: internal coordinates are label pixels at print DPI (300 dpi); canvas is displayed scale-to-fit the viewport while all saved coordinates remain in label pixels — the coordinate space the server renderer consumes
  - `labelforge_raw_content` custom property: set on every text element at creation and kept in sync on every keystroke; registered via `FabricObject.customProperties` so it survives `canvas.toJSON()` / `loadFromJSON()` round-trips and is available to the server's `detect_fields` and `render_template`
  - Save: calls `POST /api/templates` on first save of a new template, `PUT /api/templates/{name}` on subsequent saves; blocks if canvas is empty
  - Load: `GET /api/templates/{name}` → `canvas.loadFromJSON()` with custom-prop re-attachment
  - Preview button: auto-saves then calls `POST /api/preview/{name}`; shows the server-rendered PNG inline — this is the editor↔server geometry agreement check (text placed in the editor should appear at the same position in the preview PNG)
  - Router extended with prefix-route support (`registerPrefix`) for parameterised paths like `/templates/:name`
- `fabric@6.6.1` added to frontend dependencies
- Project structure and design documentation
- PRD covering quick-print, templates, label catalog, history, HTTP API, printer status, and settings
- Architecture doc locking stack: FastAPI + SQLite + brother-ql-inventree + Vite/TS + Fabric.js
- Glossary defining vocabulary
- ADR log (library choice, license, name, storage, frontend, label catalog model, auth, print-outcome reporting, convert rotation, server-side template rendering, settings source-of-truth, printer status via EWS)
- CLAUDE.md for AI session context
- GPL-3.0 LICENSE
- .gitattributes enforcing LF line endings
- .gitignore for Python + Node + IDE artifacts
- **Slice 2 frontend skeleton** — Vite + TypeScript quick-print SPA: token gate, label/font selectors (grouped by form factor), font size, bold/italic, alignment, orientation, print via `POST /api/print/quick`, localStorage pref persistence; Preview button present but disabled pending backend endpoint
- **Slice 1 backend skeleton** — FastAPI app with lifespan startup (DB init, catalog load, font scan)
- `GET /api/health` — unauthenticated liveness probe
- `GET /api/labels`, `GET /api/labels/{id}` — merged label catalog (library truth + labels.yml metadata)
- `GET /api/fonts` — discovered font list (system fonts + user fonts at `${DATA_DIR}/fonts/`)
- `POST /api/print/quick` — render text with Pillow, print via brother-ql-inventree, log to history
- Bearer-token auth on all `/api/*` routes except `/api/health`; app refuses to start without `API_TOKEN`
- SQLite schema (`print_jobs`, `settings`) created on startup via raw sqlite3
- Default `labels.yml` catalog (15 DK media entries: continuous, die-cut, round)
- Dockerfile (single-stage python:3.12-slim; bundled fonts: dejavu-core, liberation2, noto-core; multi-stage frontend build deferred)
- `compose.yml` (production: Traefik + Dockflare networks) and `compose.dev.yml` (hot-reload via bind-mount + uvicorn --reload, published on host port 8001)
- `.env.example` documenting all env vars
- README: required printer setup (Command Mode → Raster, Template Mode → Off, Unit → mm) and `wrong roll type` troubleshooting

### Changed
- `convert()` called with explicit `rotate="0"` instead of the library default `auto` (see ADR 2026-05-20)

### Fixed
- Dockerfile: copy `README.md` before `pip install -e .` (hatchling validates the readme path; build failed without it)
- `compose.dev.yml`: removed `DATA_DIR=/data/` override that did not match the bind-mount path, breaking startup catalog/DB load
- `.gitignore`: ignore `data-dev/` and the `test-print.json` scratch file
- Print API now reports the true send outcome (`sent` for the network backend) instead of always claiming `printed` (see ADR 2026-05-20)

### Status

- Slice 1 verified end-to-end: a real label printed on the QL-820NWB (DK-1209 die-cut, `62x29`). The render → convert → network-send path is confirmed working. 62mm continuous print remains a media-coverage test pending a continuous roll (capability proven, that specific media not yet physically run).
- Templates engine (slice) built and committed: storage, CRUD, server-side renderer, print/preview/batch. Not yet smoke-tested against a created template end-to-end.
- Printer status: empirically confirmed the network print path (TCP 9100) does not answer status requests; the printer's EWS page (HTTP port 80) does report loaded media and is the chosen status source (opt-in). See ADR 2026-05-20 (c).
- Deferred to later slices: Fabric.js canvas editor, history UI + retention, printer-status feature (EWS scrape), settings UI, two-color (62red) rendering, image elements / image upload.

