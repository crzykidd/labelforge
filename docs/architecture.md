# Architecture

## Stack

### Backend

- **Python 3.12+**
- **FastAPI** — API + UI server, OpenAPI generated at `/docs`
- **Pydantic v2** — schema validation shared between the form UI and the JSON API
- **SQLite** via `sqlite3` stdlib or `SQLModel` (decide in the slice that introduces persistence)
- **brother-ql-inventree** (PyPI) — printer protocol; do not switch without an ADR
- **Pillow** — server-side label rasterization, the source of truth for previews
- **qrcode[pil]** — QR code generation
- **python-barcode** — 1D barcode generation (Code 128, EAN, etc.)
- **PyYAML** — read `labels.yml`

### Frontend

- **Vite** + **TypeScript**, vanilla (no React/Vue/Svelte)
- **Fabric.js** for the canvas editor
- Built to static assets at `frontend/dist/`, served by FastAPI as static files in the container

### Storage

- **SQLite** at `$DATA_DIR/data/app.db` — templates, history, settings (auth is a single shared secret from the environment, not stored here)
- **`labels.yml`** at `$DATA_DIR/labels.yml` — user-editable label catalog metadata
- **Fonts** at `$DATA_DIR/fonts/` — `.ttf` / `.otf` files, drop-in
- **Label preview images** (optional) at `$DATA_DIR/label-previews/` — referenced from `labels.yml`

$DATA_DIR defaults to `/data` inside the container; back it with a named volume or bind mount as you prefer.

### Why these choices

- **FastAPI over Flask**: API is a first-class deliverable (every template is callable). FastAPI gives OpenAPI for free, Pydantic gives shared validation between UI form and API endpoint. Flask would mean bolting these on.
- **SQLite over Postgres**: single user, single container, no concurrency. SQLite is one file, trivially backed up, zero ops cost. Postgres adds a service for no benefit.
- **Vanilla TS over React**: the UI surface is small (a handful of pages) and the canvas editor is the hard part — Fabric.js doesn't need React. Avoiding the React build complexity tax.
- **Fabric.js over Konva/raw canvas**: Fabric has out-of-the-box selection, transform handles, group operations, serialization to/from JSON. Konva is similar; Fabric won on documentation quality.
- **`brother-ql-inventree` over alternatives**: actively maintained, used in production by InvenTree, supports printer status queries, includes the QL-820NWB. See [`decisions.md`](decisions.md).

## Repo layout

```
labelforge/
├── README.md
├── LICENSE                       # GPL-3.0
├── CLAUDE.md
├── .gitignore
├── .gitattributes
├── docker-compose.yml            # single-service stack; bring your own proxy
├── docker-compose.dev.yml        # local dev: bind mounts, no Traefik labels
├── Dockerfile                    # multi-stage: frontend build → python runtime
├── pyproject.toml                # backend deps + tool config
├── docs/
│   ├── PRD.md
│   ├── architecture.md
│   ├── glossary.md
│   ├── decisions.md
│   └── features/
│       └── ...
├── backend/
│   ├── labelforge/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app entry
│   │   ├── config.py             # settings from env
│   │   ├── db.py                 # sqlite connection + migrations
│   │   ├── models/               # Pydantic models
│   │   ├── routes/               # FastAPI routers grouped by feature
│   │   ├── render/               # Pillow rendering pipeline
│   │   ├── printer/              # brother_ql wrapper, status queries
│   │   └── catalog/              # labels.yml loader + library merge
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── pages/
│       ├── components/
│       └── editor/               # Fabric.js wrapper
└── labels.yml                    # default catalog shipped in repo
```

## Container layout

Single image, multi-stage build:

1. **Stage 1 (frontend)**: `node:lts-alpine` — `npm ci` + `npm run build` → produces `frontend/dist/`
2. **Stage 2 (runtime)**: `python:3.12-slim` — installs backend deps, copies backend source + `frontend/dist/` from stage 1, starts uvicorn

Runtime user is non-root. Container exposes port `8000`.

## Data flow

### Print path (UI or API)

```
client → POST /api/print/{template}
      → validate field values against template schema (Pydantic)
      → load template + label media metadata
      → render to Pillow Image at exact printer DPI
      → (optional) query printer status, compare loaded vs expected media
      → convert image to printer raster via brother_ql
      → send to printer over TCP
      → write print job row to SQLite (template, values, timestamp, preview thumb)
      → return job_id + preview_url
```

### Preview path

Same pipeline up to the Pillow Image step — that image is returned as PNG instead of being sent to the printer. Preview is the *exact* bitmap that would print.

### Label catalog load

At startup and on `labels.yml` change (file watcher or restart):

```
brother_ql.info.labels()  →  set of printable identifiers (truth)
labels.yml                →  metadata per identifier (UX layer)
merge: only identifiers in the intersection are user-facing.
       identifiers in library but not yml: shown with raw identifier.
       identifiers in yml but not library: hidden.
```

## Deployment

- Single Docker image built from the included `Dockerfile` (multi-stage: frontend build → python runtime). No build step at deploy time once the image is built.
- Runs as one container serving plain HTTP on port `8000`. Put it behind whatever reverse proxy or tunnel you use; proxy wiring is deployment-specific and intentionally not baked into the app.
- Persistent data lives under `$DATA_DIR` (default `/data`); back it with a named volume or a host bind mount. See `docker-compose.yml` for a standalone example and `docker-compose.dev.yml` for local hot-reload dev.
- Env-driven config: printer host/port, API token, default label media, data dir, log level. See `.env.example`.

## Out of scope for v1

- Reverse-proxy hardening (proxy choice is left to the operator)
- Database migrations beyond initial schema creation (manually managed for v1)
- Health-check endpoint beyond what Traefik needs
- Prometheus metrics endpoint (can add later if useful)
