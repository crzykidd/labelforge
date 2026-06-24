# Feature: HTTP API

## Goal

Every template is callable from anywhere in the homelab. A Home Assistant automation, a Paperless webhook, a curl from a script, a phone Shortcut — any of these can hit `/api/print/{template}` with JSON values and a label comes out.

## Principles

- **The UI uses the same API as everything else.** No internal-only endpoints. If the UI does it, scripts can do it.
- **OpenAPI is auto-generated** by FastAPI at `/docs`. The spec is the documentation.
- **Pydantic models are the schema.** Validation errors come back as proper 400s with field-level details.

## Auth

**Optional, default-on (see ADR 2026-06-02).** Setting `DISABLE_AUTH=true` runs the app with no app-level auth — every `/api/*` route is open, intended for deployments fronted by a reverse proxy (e.g. Traefik) that authenticates at the edge. With auth disabled, `GET /api/health` returns `"auth_required": false` and the SPA skips its token gate. The rest of this section describes the default (auth enabled) mode.

Single shared secret in `.env` as `API_TOKEN` (required unless `DISABLE_AUTH=true`; the app refuses to start otherwise). The token is sent as `Authorization: Bearer <token>` and enforced by a single FastAPI dependency (`require_auth` in `backend/labelforge/routes/auth.py`) applied at the router level.

**Almost every `/api/*` route requires the token** — all of `templates`, `labels`, `history`, `settings`, `fonts`, `print`, `preview`, and `admin`, on *every* method including `GET`. The only **unauthenticated** routes are:

- `GET /api/health` — liveness + `auth_required` flag
- `GET /api/printer/status` — loaded media / ready state
- `GET /api/version` — version + update-check info
- FastAPI's `/docs`, `/redoc`, `/openapi.json`, and the SPA static files

Auth outcomes:

- **Missing or non-Bearer** `Authorization` header → **401** ("Authorization header required" / "must use Bearer scheme")
- **Wrong token** → **403** ("Invalid API token")
- Valid token → the request proceeds

The web UI stores the token in the browser (localStorage) and attaches it to every request — there is no cookie login page. External access via `labels.crzynet.com` is fronted by a Cloudflare Tunnel (deployment infrastructure); the app itself does not detect Cloudflare or run any extra auth middleware.

See [`decisions.md`](decisions.md) (ADR 2026-06-02) for why this is the v1 model.

## Endpoint surface

### Templates

```
GET    /api/templates                           List templates (no soft-deleted)
GET    /api/templates/{name}                    Get one
POST   /api/templates                           Create
PUT    /api/templates/{name}                    Update
DELETE /api/templates/{name}                    Soft-delete
POST   /api/templates/{name}/duplicate          Save As (new name, new label media)
GET    /api/templates/{name}/last-values        Field values from this template's last print
```

### Printing

```
POST   /api/print/quick                         Quick-print (text + font + size + media)
POST   /api/print/{name}                        Print template with field values
POST   /api/print/{name}/batch                  Batch print with arrays of values
POST   /api/preview/{name}                      Render preview PNG without printing
POST   /api/preview/quick                       Preview a quick-print payload
```

All three print endpoints accept an optional `?override=true` query param to print despite a media-mismatch 409 (see "Override media mismatch" below).

### Label catalog

```
GET    /api/labels                              Merged catalog
GET    /api/labels/{id}                          One label
```

### Admin (token required)

```
POST   /api/admin/reload-catalog                Reload labels.yml from disk
POST   /api/admin/prune-history                 Run history retention pruning now
```

### History

```
GET    /api/history                             List with filters
GET    /api/history/{job_id}                    Detail
GET    /api/history/{job_id}/preview.png        Preview image
POST   /api/history/{job_id}/reprint
POST   /api/history/{job_id}/pin                Body: {pinned: bool}
DELETE /api/history/{job_id}                    Manual delete
```

### Printer

```
GET    /api/printer/status                      Loaded media, ready state, errors (unauthenticated)
```

### Settings

```
GET    /api/settings                            All settings
PUT    /api/settings                            Update (partial OK)
```

### Fonts

```
GET    /api/fonts                               Available fonts from the fonts volume
GET    /api/fonts/{name}/file                   Raw font bytes (browser @font-face registration)
```

### System (unauthenticated)

```
GET    /api/health                              Liveness + auth_required flag
GET    /api/version                             Version + update-check info
```

## Request / response examples

### Print a template

```bash
curl -X POST https://labels.crzynet.com/api/print/spool \
  -H "Authorization: Bearer $LABELFORGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "number": "047",
      "color": "PETG Black",
      "weight": "1kg"
    }
  }'
```

Response (200):
```json
{
  "job_id": 1234,
  "status": "sent",
  "template": "spool",
  "label_media": "62",
  "overflow": false,
  "preview_url": "/api/history/1234/preview.png"
}
```

`status` is the true send outcome — `"sent"` for the network printer backend (the job was handed to the printer over TCP), per ADR 2026-05-20, not `"printed"`. `overflow` is `true` when the rendered content exceeds a die-cut label's printable height (the job is still sent). There is no `printed_at` field.

Errors:
- 400 — validation failure with field details (missing required field, etc.)
- 401 — missing or non-Bearer `Authorization` header
- 403 — wrong API token
- 404 — template doesn't exist
- 409 — printer/media error (media mismatch without override, printer not ready); structured body, see below
- 500 — internal failure

### Batch print

```bash
curl -X POST https://labels.crzynet.com/api/print/spool/batch \
  -H "Authorization: Bearer $LABELFORGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "labels": [
      {"number": "047", "color": "PETG Black", "weight": "1kg"},
      {"number": "048", "color": "PETG Black", "weight": "1kg"},
      {"number": "049", "color": "ABS Red", "weight": "1kg"}
    ]
  }'
```

Response:
```json
{
  "batch_id": "uuid",
  "jobs": [
    {"job_id": 1234, "status": "sent"},
    {"job_id": 1235, "status": "sent"},
    {"job_id": -1, "status": "error: Printer has 29mm continuous loaded, template expects 62mm."}
  ],
  "succeeded": 2,
  "failed": 1
}
```

Partial failure: each job carries its own status. A successful job has the real `job_id` and a status of `"sent"`; a failed job has `job_id: -1` and `status: "error: <message>"`. The endpoint returns **200** as long as at least one job succeeded (mixed success/failure included). If **every** job fails it returns **500**, with the same `BatchPrintResponse` body nested under FastAPI's `detail` key. There is no `207` — it was considered and dropped for v1.

### Quick print

```bash
curl -X POST https://labels.crzynet.com/api/print/quick \
  -H "Authorization: Bearer $LABELFORGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Server Rack 3 - Switch A",
    "font": "DejaVuSans-Bold",
    "font_size": 32,
    "label_media": "62",
    "orientation": "standard"
  }'
```

### Preview without printing

Same body as `print`, hits `/api/preview/{name}` or `/api/preview/quick`. Returns the PNG inline:

```
HTTP/1.1 200 OK
Content-Type: image/png

<png bytes>
```

### Override media mismatch

When auto-detect detects the loaded media differs from what the template expects:

```json
HTTP/1.1 409 Conflict
{
  "detail": {
    "error": "media_mismatch",
    "expected": "62",
    "loaded": "29",
    "override_allowed": true,
    "message": "Printer has 29mm continuous loaded, template expects 62mm. Pass override=true to print anyway."
  }
}
```

Client retries with `?override=true` to print regardless. Note these structured bodies are raised via `HTTPException(detail=...)`, so on the wire they are nested under a top-level `detail` key (as shown), not returned as a bare object.

Two other structured errors follow the same `{"detail": {...}}` envelope:

- **409 printer error** (non-media) — `{"error": "printer_error", "code": ..., "message": ..., "raw": ...}` when the printer rejects the job for a reason other than media mismatch.
- **503 from `GET /api/printer/status`** — `{"error": "status_unavailable", "message": "Printer status is currently unavailable."}` when the printer can't be reached (this one is a plain `JSONResponse`, not wrapped in `detail`).

## Validation

Pydantic models enforce:

- Field types (text/number/date/enum)
- Required fields present
- Defaults applied for missing optional fields
- enum values in the allowed set
- Number fields are actually numbers

Validation errors return 400 with the standard FastAPI error envelope, which includes `loc` (field path) and `msg` per failed field.

## Versioning

No API versioning in v1. If we break an endpoint, scripts that hit it break. Acceptable trade-off for a single-user app where the user is also the script author.

Sticky points:
- Adding fields to a template is backward-compatible **iff** new fields have defaults. The schema endpoint always returns the current schema; old API callers will continue to work as long as they don't send fields that no longer exist.
- Removing a field is breaking. Document loudly if we ever do this and the user happens to have a script.

## OpenAPI

FastAPI generates `/openapi.json` and serves Swagger UI at `/docs` (and ReDoc at `/redoc`). All three are unauthenticated — there is no app-level auth on the docs routes. (External exposure is governed by the Cloudflare Tunnel in front of the deployment, not by app code.)

The spec is the auto-generated reference; this document is the human-facing design/reference and is kept in sync by hand.

## Out of scope for v1

- Rate limiting (single user, no abuse risk)
- Per-token scopes (defer until token table exists)
- Webhooks out of labelforge (events on print)
- WebSocket for live printer status (defer; polling is fine at this scale)
