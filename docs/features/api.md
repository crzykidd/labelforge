# Feature: HTTP API

## Goal

Every template is callable from anywhere in the homelab. A Home Assistant automation, a Paperless webhook, a curl from a script, a phone Shortcut — any of these can hit `/api/print/{template}` with JSON values and a label comes out.

## Principles

- **The UI uses the same API as everything else.** No internal-only endpoints. If the UI does it, scripts can do it.
- **OpenAPI is auto-generated** by FastAPI at `/docs`. The spec is the documentation.
- **Pydantic models are the schema.** Validation errors come back as proper 400s with field-level details.

## Auth

Single shared secret in `.env` as `API_TOKEN`. Required as `Authorization: Bearer <token>` on:

- All `POST`, `PUT`, `DELETE` endpoints
- `GET /api/admin/*`
- The UI obtains the token from a same-origin cookie set by an unauthenticated login page (LAN access only)

`GET` endpoints (templates list, label catalog, history read) are unauthenticated on the LAN. For external access via `labels.crzynet.com`, all endpoints require the token — enforced by Cloudflare Tunnel access policy plus an app-level `require_token` middleware when the request comes through Cloudflare (detected by header).

See [`decisions.md`](decisions.md) for why this is the v1 model.

## Endpoint surface

### Templates

```
GET    /api/templates                           List templates (no soft-deleted)
GET    /api/templates/{name}                    Get one
POST   /api/templates                           Create
PUT    /api/templates/{name}                    Update
DELETE /api/templates/{name}                    Soft-delete
POST   /api/templates/{name}/duplicate          Save As (new name, new label media)
```

### Printing

```
POST   /api/print/quick                         Quick-print (text + font + size + media)
POST   /api/print/{name}                        Print template with field values
POST   /api/print/{name}/batch                  Batch print with arrays of values
POST   /api/preview/{name}                      Render preview PNG without printing
POST   /api/preview/quick                       Preview a quick-print payload
```

### Label catalog

```
GET    /api/labels                              Merged catalog
GET    /api/labels/{id}                         One label
POST   /api/admin/reload-catalog                Reload labels.yml from disk
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
GET    /api/printer/status                      Loaded media, ready state, errors
GET    /api/printer/info                        Model, firmware (if available)
```

### Settings

```
GET    /api/settings                            All settings
PUT    /api/settings                            Update (partial OK)
```

### Fonts

```
GET    /api/fonts                               Available fonts from the fonts volume
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
  "status": "printed",
  "template": "spool",
  "label_media": "62",
  "preview_url": "/api/history/1234/preview.png",
  "printed_at": "2026-05-19T14:23:11Z"
}
```

Errors:
- 400 — validation failure with field details
- 401 — missing/invalid token
- 404 — template doesn't exist
- 409 — printer error (media mismatch without override, out of paper, etc.) with details
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
    {"job_id": 1234, "status": "printed"},
    {"job_id": 1235, "status": "printed"},
    {"job_id": 1236, "status": "printed"}
  ],
  "succeeded": 3,
  "failed": 0
}
```

Partial failure: each job has its own status. The batch endpoint returns 200 if at least one succeeded, 207 if mixed, 500 if all failed. (TBD — confirm during implementation; 207 may not be worth the complexity for v1.)

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
  "error": "media_mismatch",
  "expected": "62",
  "loaded": "29",
  "override_allowed": true,
  "message": "Printer has 29mm continuous loaded, template expects 62mm. Pass override=true to print anyway."
}
```

Client retries with `?override=true` to print regardless.

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

FastAPI generates `/openapi.json` and serves Swagger UI at `/docs`. Both unauthenticated on the LAN, both require the token via Cloudflare.

The spec is the documentation. We do not maintain a separate API doc.

## Out of scope for v1

- Rate limiting (single user, no abuse risk)
- Per-token scopes (defer until token table exists)
- Webhooks out of labelforge (events on print)
- WebSocket for live printer status (defer; polling is fine at this scale)
