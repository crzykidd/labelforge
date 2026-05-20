# labelforge — PRD

## Purpose

A self-hosted web app for printing labels to Brother QL series label printers, with saved templates, variable fields, and an HTTP API. Replaces `brother_ql_web` and its forks, which lack any template persistence.

## Users

Single user (the operator). Family members may print via the same URL but there is no per-user state. No authentication beyond a shared API token (UI is unauthenticated on the LAN; the API requires the token).

## What it replaces

- `brother_ql_web` (no templates, no persistence)
- `bql-label-printer` (templates are HTML files on disk, no UI editor)
- Brother P-touch Editor (Windows/Mac only, not self-hosted)

## Hardware target

Brother **QL-820NWB** (the owner's printer). The app must work with any printer supported by the `brother-ql-inventree` library, but development and testing is on the QL-820NWB. Two-color (red + black) printing on DK-22251 must work.

## Deployment target

Single Docker container, deployed on `docker10` via Dockhand. External access via Cloudflare Tunnel at `labels.crzynet.com`. Internal access at `labels.home.arpa`.

## Scope

### In scope

- Quick-print mode (text + font + size + label media — like brother_ql_web, kept)
- Named templates with a freeform canvas layout (text, QR, barcode, image, line, rect)
- Variable fields auto-detected from `{placeholder}` syntax in element content
- Template recall: form auto-generated from field schema, fill, preview, print
- Increment / batch printing for numeric fields
- Print history with reprint, pinning, and configurable retention
- HTTP API: every template callable via `POST /api/print/{name}` with JSON field values
- Label media catalog combining library truth + user-editable UX metadata (`labels.yml`)
- Server-side true preview before printing (renders the exact bitmap)
- Printer status query with override (auto-detect loaded media, warn on mismatch)

### Out of scope (forever, or at least very long term)

- Multi-user, accounts, RBAC, SSO
- Cloud sync, mobile app, hosted SaaS version
- Brother P-touch Editor (`.lbx`) file import
- Network printer auto-discovery
- Multi-printer support per deployment (one printer per instance)
- Theming / branding customization
- Internationalization (English UI only for v1)

## Feature designs

Each feature has its own document. Open only the ones relevant to the current task:

- [`features/quick-print.md`](features/quick-print.md) — type, pick font, print
- [`features/templates.md`](features/templates.md) — template data model, editor, recall flow
- [`features/label-catalog.md`](features/label-catalog.md) — `labels.yml` + library hybrid
- [`features/history.md`](features/history.md) — print log, retention, pinning
- [`features/api.md`](features/api.md) — HTTP API surface, auth, integration patterns
- [`features/printer-status.md`](features/printer-status.md) — auto-detect with override
- [`features/settings.md`](features/settings.md) — user-configurable settings (retention, defaults)

## Cross-cutting concerns

- **Architecture & stack**: [`architecture.md`](architecture.md)
- **Vocabulary**: [`glossary.md`](glossary.md)
- **Past decisions**: [`decisions.md`](decisions.md) — read before contradicting

## Success criteria for v1

The owner can:

1. Open the UI on the LAN and print arbitrary text on a 62mm continuous label.
2. Design a "Spool" template with fixed text + variable fields + a QR code, save it.
3. Recall the Spool template, fill fields, preview, and print.
4. Print a batch of 10 incrementing spool labels in one operation.
5. POST JSON to `/api/print/spool` from Home Assistant and have a label come out.
6. See the last 50 prints in history, click one, reprint it.
7. Pin a frequently-used print so retention cleanup never removes it.
8. Edit `labels.yml` to add a friendly name for a new label media without touching code.

If all eight work end-to-end, v1 is done.
