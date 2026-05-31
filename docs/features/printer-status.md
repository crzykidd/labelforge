# Feature: Printer Status

## Goal

When the user prints, verify the printer has the expected media loaded. If not, surface a clear warning with an override option rather than producing a misprint.

## Hardware context

The QL-820NWB (the development hardware) supports a status protocol over its network interface. When asked, it reports:

- Currently loaded media type and dimensions (mapped to library identifiers)
- Ready state (idle / printing / error)
- Error codes (cover open, no media, jam, etc.)

The `brother-ql-inventree` library exposes this via a `status` command and a corresponding API. Not all QL models support this equally; the network-connected models do, USB is iffier.

## When status is queried

Three points:

1. **Before printing** — print path queries status, compares loaded media to expected, blocks or warns
2. **Settings page "Test printer" button** — explicit user-initiated check
3. **Periodic background poll (optional, off by default)** — for a dashboard tile showing current state

For v1: implement #1 and #2. Defer #3 unless trivial.

## Print-path flow

```
print request received
  → render label image
  → if status_check_enabled (setting, default true):
       query printer status (timeout 2s)
       if loaded_media == expected_media: proceed
       if loaded_media != expected_media:
         if request.override == true: proceed (log warning)
         else: 409 media_mismatch (see api.md)
       if status query timed out / unsupported:
         log warning, proceed (degrade gracefully)
  → convert image via brother_ql
  → send to printer
  → return success or printer error
```

## Settings

- `printer_status_check`: bool (default true)
  - When false, skip the pre-print check entirely. Useful if the printer model doesn't support status reliably or if checks are causing latency.

- `printer_status_timeout_ms`: int (default 2000)
  - How long to wait for a status response before giving up

These live in the general settings table; see [`settings.md`](settings.md).

## Status mapping

The library returns raw bytes from the printer's status protocol. The library's `status` module parses these into a structure roughly like:

```python
{
  "media_type": "continuous_length_tape",
  "media_width_mm": 62,
  "media_length_mm": 0,             # 0 = continuous
  "model": "QL-820NWB",
  "error_information": [],
  "status_type": "phase_change",
  ...
}
```

We need a mapping function: `(media_type, media_width_mm, media_length_mm) → library_identifier` (e.g. `"62"` or `"62x100"`). This logic exists in the library or close to it; if not, it's a thin wrapper we own.

Color capability of the loaded media (whether it's DK-22251 red-capable or DK-22205 mono): the printer reports tape type and the library should distinguish. If it doesn't expose this directly, we read the raw status bytes — there's a specific tape-color byte.

## Error reporting

Printer errors (no paper, cover open, jam) come back as 409 from the API:

```json
{
  "error": "printer_error",
  "code": "no_media",
  "message": "Printer reports no media loaded. Insert a label roll and try again.",
  "raw": { ...status response... }
}
```

Map the library's error codes to friendly messages. Include `raw` for debugging.

## API

```
GET /api/printer/status
```

Response (200):
```json
{
  "ready": true,
  "model": "QL-820NWB",
  "loaded_media": {
    "id": "62",
    "display_name": "62mm Continuous (Black)",
    "width_mm": 62,
    "length_mm": 0,
    "color_capable": false
  },
  "errors": []
}
```

If status query fails or times out:
```json
HTTP/1.1 503 Service Unavailable
{
  "error": "status_unavailable",
  "message": "Printer did not respond within 2000ms"
}
```

## UI

- Settings page has a **Test printer** button that calls `GET /api/printer/status` and renders the result inline
- Print form shows the currently-loaded media as a chip near the print button, polled lazily on form open (not every keystroke)
- A media mismatch in the print response shows a modal: "Printer has X loaded, template expects Y. [Cancel] [Print anyway]"
- Label-media selectors include a **Loaded in printer** filter mode (see [label-catalog.md](label-catalog.md#loaded-media-filter)) that queries this endpoint to narrow the dropdown to the mounted roll's matching catalog entries.

## Edge cases

- Printer powered off or unreachable → `503` from status endpoint; print attempts return `503` with "printer unreachable"
- Status query returns garbage / unparseable → log raw bytes, return `503` "status response malformed"
- Two-color media loaded but template uses no red → still match (62red is a superset of 62 for layout purposes; we just won't use the red channel). Decision: treat 62 and 62red as compatible at print time when the template uses only black; warn but allow. Same in reverse: template specifies red but mono loaded → block (we'd silently produce mono).
- Printer reports a media we don't recognize → fall back to "unknown media: <raw>"; block print with override
