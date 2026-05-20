# Changelog

All notable changes to labelforge are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Project follows semantic versioning once the first release ships.

## [Unreleased]

### Added
- Project structure and design documentation
- PRD covering quick-print, templates, label catalog, history, HTTP API, printer status, and settings
- Architecture doc locking stack: FastAPI + SQLite + brother-ql-inventree + Vite/TS + Fabric.js
- Glossary defining vocabulary
- ADR log with 6 decisions recorded (library choice, license, name, storage, frontend, label catalog model, auth)
- CLAUDE.md for AI session context
- GPL-3.0 LICENSE
- .gitattributes enforcing LF line endings
- .gitignore for Python + Node + IDE artifacts

### Status
- No code yet. Design phase complete. Next: backend skeleton + first end-to-end print path (slice 1).

---

Format for future entries:

## [version] — YYYY-MM-DD

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security