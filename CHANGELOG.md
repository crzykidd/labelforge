# Changelog

All notable changes to labelforge are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Project follows semantic versioning once the first release ships.

## [Unreleased]

### Known Issues

- QR and barcode template elements render in preview but print as a solid black block (1-bit threshold crushes fine detail). These elements are gated to raise a clear error until fixed. Text, lines, and rectangles print correctly.

### Added

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