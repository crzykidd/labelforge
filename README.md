# labelforge

Self-hosted web app for designing, saving, and printing labels to Brother QL series printers.

**Status**: Released (v0.1.2) — all v1 features are working and the app is packaged as a single Docker image.

**Version:** 0.1.2

## What's New

### v0.1.2 (2026-06-07)

Fixes the published container image. Builds were producing an OCI index with provenance/SBOM
attestation child manifests; the weekly image cleanup deleted those untagged children, leaving
`:latest`/`:v0.1.1` pointing at a missing manifest (`docker pull` → 404). The image is now a
plain single-platform manifest and the cleanup keeps a safety buffer, so pulls work again.

### v0.1.1 (2026-06-06)

Deployment reliability. Startup now logs in detail (version, effective config, data directory,
database created/opened, migrations, "startup complete") and **fails fast with a clear message**
instead of crashing silently — a missing `PRINTER_HOST`/`API_TOKEN` or an unwritable `DATA_DIR`
(the container runs as uid 1000) is now reported as a `CRITICAL` log line with the fix. The
image sets `PYTHONUNBUFFERED=1` and creates/owns `/data` so named-volume deploys work out of the
box. Also rolls in the pending dependency updates (fastapi, pydantic, fabric 7, vite 8,
typescript 6, Docker base `python:3.14-slim`, CI actions). See the permissions notes under
**Running it**.

### v0.1.0 (2026-06-06)

First release. The full v1 feature set is here: quick-print, a Fabric.js canvas
template editor with variable `{placeholder}` fields, template recall with batch/increment
printing, two-color (black + red) printing on DK-2251, print history (reprint, pin, delete,
configurable retention), a hybrid `labels.yml` catalog with friendly names and Brother DK part
numbers, printer-status detection with a media-mismatch override, one-off media override at
recall, a settings UI, and a full Bearer-token HTTP API (every template callable for homelab
integrations). See [`CHANGELOG.md`](CHANGELOG.md) for the complete list.

## What it does

- **Quick-print mode** — type text, pick a font/size/alignment, print (like brother_ql_web)
- **Named templates** — design a label on a freeform canvas (text, QR codes, barcodes,
  images, lines, rectangles) and save it under a friendly name
- **Variable fields** — `{placeholder}` syntax in element text auto-generates a fill-in form
  on recall; numeric fields support increment/batch printing
- **Two-color printing** — black + red on two-color media (DK-2251 / `62red`); red maps to
  black automatically on mono media
- **Print history** — browse, reprint, pin, and delete past prints, with thumbnails and
  configurable retention (keep forever / last N / last N days); pinned prints are never pruned
- **Label catalog** — `labels.yml` merges the printer library's truth with editable UX
  metadata (friendly names, Brother DK part numbers); media the printer can't handle is
  shown disabled
- **Printer status** — auto-detect the loaded roll and warn (or block) on a media mismatch,
  with a print-anyway override
- **Print on different media at recall** — one-off print of a template on another label size
  without mutating the saved template
- **Settings page** — retention policy, default media, and printer-status options, all editable
  in the UI
- **Full HTTP API** — every template is callable via `POST /api/print/{name}` for homelab
  integrations (Home Assistant, etc.); auth is a single Bearer token, or disable app-level
  auth entirely behind a trusted reverse proxy

## Printer setup (required)

The app talks to the printer in **raster** mode over TCP. A factory or
previously-used Brother QL-820NWB often ships configured for standalone
template printing, which will reject raster jobs with a misleading
`wrong roll type` error. Set these on the printer's LCD before first use:

- **Command Mode → Raster.** Menu → (Template/Command settings) → Command
  Mode → Raster. If it is set to `P-touch Template` or `ESC/P`, raster jobs
  fail. This is the single most common cause of prints not appearing.
- **Template Mode → Off.** Menu → Template Settings → Template Mode → Off.
  A saved template size overrides DK roll auto-detection and forces a fixed
  label size, causing `wrong roll type` on a non-matching roll.
- **Unit → mm.** Menu → Settings → Unit → mm. Cosmetic, but keeps the panel
  readout consistent with the catalog.

After changing Command Mode, reseat the DK roll (remove it, close the cover
empty so the printer reports no media, then reload) so media auto-detection
re-runs.

### Troubleshooting `wrong roll type`

If a job is rejected as `wrong roll type` even with the settings above:

- **Worn or sample rolls.** Detection depends on the plastic tabs on the
  roll's spool end-caps pressing micro-switches in the bay. Worn rolls (e.g.
  the bundled SAMPLE roll) can fail to be sensed and get rejected. Test with
  a standard DK roll that has intact end-caps.
- **Media mismatch.** The `label_media` in the request must match the roll
  physically loaded. The printer rejects a job whose declared media does not
  match what it senses.
- The network backend cannot read printer status back, so a failed print may
  still return HTTP 200 with `status: "sent"` — `sent` means *transmitted*,
  not *confirmed printed*. Watch the physical printer.

## Running it

The app ships as a single Docker image (multi-stage build: frontend → static assets served
by FastAPI). Copy `.env.example` to `.env`, fill in the values, and start the stack:

```
cp .env.example .env      # set API_TOKEN and PRINTER_HOST at minimum
docker compose up -d       # uses docker-compose.yml
```

For local development with hot-reload, use `docker-compose.dev.yml`.

### Configuration

All config is environment-driven (see `.env.example` for the full list). The essentials:

| Variable | Default | Purpose |
| --- | --- | --- |
| `API_TOKEN` | _(required)_ | Bearer token for all `/api/*` routes. App refuses to start without it unless `DISABLE_AUTH=true`. |
| `PRINTER_HOST` | _(required)_ | IP/hostname of the Brother QL printer. |
| `PRINTER_MODEL` | `QL-820NWB` | Must match a `brother_ql` model id. Drives label-catalog compatibility. |
| `PRINTER_BACKEND` | `network` | `network` \| `linux_kernel` \| `pyusb`. |
| `DEFAULT_LABEL_MEDIA` | `62` | Pre-selected media in the UI. |
| `DATA_DIR` | `/data` | Where SQLite, `labels.yml`, fonts, and previews live in the container. |
| `DISABLE_AUTH` | `false` | Run with no app-level auth (for a reverse proxy that handles auth). Not SSO; still single-user. |
| `CATALOG_AUTO_MERGE` | `true` | On startup, non-destructively merge new/corrected default catalog entries into the operator's `labels.yml` (a `.bak` is written first). |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`. |

Persistent data lives under `$DATA_DIR`; back it with a named volume or bind mount. The
interactive API docs are at `/docs`.

### Permissions

The container runs as a **non-root user, uid 1000** (`labelforge`). Everything it writes lives
under `$DATA_DIR` (default `/data`), so that path must be writable by uid 1000:

- **Named volume** (e.g. the default `docker-compose.yml`): works out of the box — the image
  creates `/data` owned by uid 1000 and the volume inherits that ownership.
- **Bind mount** (host directory): the host keeps its own ownership, so make the directory
  writable by uid 1000 first: `chown -R 1000:1000 /path/on/host`. Alternatively run the
  container with `--user $(id -u):$(id -g)` and ensure that user owns the directory.

If `$DATA_DIR` isn't writable, startup aborts immediately with a `CRITICAL ... DATA_DIR ... is
NOT writable by uid=1000` log line telling you exactly what to fix. Watch `docker logs` on
first start — the app logs its version, config, and database status as it comes up.

## Design docs

See [`docs/PRD.md`](docs/PRD.md) for scope, then [`docs/features/`](docs/features/) for per-feature designs.

## License

GPL-3.0. Builds on [`matmair/brother_ql-inventree`](https://github.com/matmair/brother_ql-inventree) (GPL-3.0).
