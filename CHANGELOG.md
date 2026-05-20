# Changelog

All notable changes to labelforge are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Project follows semantic versioning once the first release ships.

## [Unreleased]

### Added
- Project structure and design documentation
- PRD covering quick-print, templates, label catalog, history, HTTP API, printer status, and settings
- Architecture doc locking stack: FastAPI + SQLite + brother-ql-inventree + Vite/TS + Fabric.js
- Glossary defining vocabulary
- ADR log (library choice, license, name, storage, frontend, label catalog model, auth, print-outcome reporting, convert rotation)
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
- Slice 1 verified end-to-end: a real label printed on the QL-820NWB (DK-1209 die-cut, `62x29`). The render → convert → network-send path is confirmed working. Deferred to later slices: templates, canvas editor, history UI, printer-status query, settings UI, batch/increment, frontend.

---

Format for future entries:

## [version] — YYYY-MM-DD

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security