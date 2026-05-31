# Changelog

All notable changes to labelforge are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Project follows semantic versioning once the first release ships.

## [Unreleased]

### Changed

- **Adopted four crzynet engineering standards**, pinned in a new root `standards.md`: `code-checkin-and-pr @ 1.1.0` (commit messages now use Conventional-Commits prefixes `feat:`/`fix:`/`chore:`/`docs:`; CI gained structured-config and `docker compose config` validation jobs), `handoff-prompt-workflow @ 1.5.0` (completed handoff prompts now archived under `prompts/done/`; `prompts/TEMPLATE.md` added), `repo-sandbox-permissions @ 1.0.0` (repo-wide sandbox in `.claude/settings.json` — auto-approves in-repo work, gates out-of-repo writes and network), and `vexp-context-engine @ 2.1.0` (guard hook now tracked, `.vexpignore` added). Developer/process-facing only — no runtime behavior change.

### Known Issues

- QR and barcode template elements render in preview but print as a solid black block (1-bit threshold crushes fine detail). These elements are gated to raise a clear error until fixed. Text, lines, and rectangles print correctly.

### Added

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

---

Format for future entries:

## [version] — YYYY-MM-DD

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security