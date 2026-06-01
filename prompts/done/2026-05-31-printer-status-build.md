---
name: 2026-05-31-printer-status-build
status: completed
created: 2026-05-31
model: sonnet
completed: 2026-05-31
result: Added GET /api/printer/status (TCP+HTTP fallback), pre-print media check on all print routes, and Test Printer button in settings UI
---

# Task: Build the Printer Status feature

Implement the Printer Status feature end-to-end as designed in `docs/features/printer-status.md`
and `docs/features/api.md`. The spike in `prompts/done/2026-05-31-printer-status-spike.md`
confirmed the mechanism and resolved the key risk; encode those findings here so this session
doesn't need to re-research.

## Before you start

Read these docs (all needed for this task):
- `docs/features/printer-status.md` — feature spec (API shape, print-path flow, edge cases)
- `docs/features/api.md` — `GET /api/printer/status` 200/503 shapes; `media_mismatch` 409
- `backend/labelforge/printer/client.py` — existing print path; status_read goes here
- `backend/labelforge/config.py` — `printer_host`, `printer_backend`, `printer_model`
- `backend/labelforge/settings_store.py:27-28` — `printer_status_check` and
  `printer_status_timeout_ms` already registered; do NOT add them again
- `docs/decisions.md` — the 2026-05-31 ADR for network status design

Conventions: vexp `run_pipeline` first; `get_skeleton` over `Read`; no grep/glob.
Commit prefix `feat:`; no `Co-authored-by:`; work on `dev`.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files this
plan touches. If any have uncommitted changes, list them and ask before touching. This file
is exempt.

## Spike findings (encode these — do not re-research)

### Import paths verified against brother-ql-inventree 1.3

```
brother_ql.backends.helpers.get_status(printer, receive_only=False, target_status=None)
    — sends b"\x1b\x69\x53" (ESC i S), calls printer.read(), parses via interpret_response()

brother_ql.backends.helpers.backend_factory(backend_identifier)
    — returns {"backend_class": BrotherQLBackendNetwork, "list_available_devices": ...}

brother_ql.reader.interpret_response(data: bytes) -> dict
    — parses 32-byte reply into {model, status_type, status_code, phase_type,
      media_type, media_category, media_width, media_length, tape_color, errors, ...}
    — IMPORTANT: tape_color is only parsed for media_category == "TZe".
      For DK tapes (what QL-820NWB uses), tape_color == "".
      Read data[24] raw for DK color detection.

brother_ql.labels.ALL_LABELS
    — list of Label objects; lbl.tape_size = (width_mm, length_mm); lbl.identifier = "62"
    — lbl.color is Color.BLACK_WHITE (0) or Color.BLACK_RED_WHITE (1)
    — "62" and "62red" both have tape_size=(62, 0); "62x29" has tape_size=(62, 29)
```

### Why get_printer() cannot be used

`brother_ql.backends.helpers.get_printer()` raises `NotImplementedError` for
`backend="network"` (intentional library design). Bypass by directly instantiating
`BrotherQLBackendNetwork`:

```python
be = backend_factory("network")
printer = be["backend_class"](f"tcp://{host}")
```

### Network backend default timeout

`BrotherQLBackendNetwork.read_timeout = 0.01` (10 ms) — too short for a network round-trip.
Override before calling `get_status()`:

```python
printer.read_timeout = timeout_s
printer.s.settimeout(timeout_s)
```

### Live hardware test result

The QL-820NWB at the configured host does **not respond** to ESC i S over port 9100,
regardless of timeout (tested: 10 ms, 500 ms, 2 s, 5 s; raw socket and library path).
The library itself confirms this ("network backend doesn't support readback" in `send()`).
The TCP path is kept as primary anyway because it may work on different printer firmware
or states. Callers must handle empty-byte response gracefully.

### HTTP fallback

`http://{host}/general/status.html` (redirected from `/`) responds without authentication.
Parse `dt`/`dd` pairs:

- `"Device&#32;Status"` dd contains: `"READY"` or error text inside `<span class="moni ...">`.
- `"Media&#32;Status"` dd: `"Not&#32;Empty"` or `"Empty"`.
- `"Media&#32;Type"` dd: `"62mm x 29mm / 2.4\" x 1.1\""` or similar.

Media string format: `r"(\d+)mm\s*x\s*(\d+)mm"` extracts (width, length).
For continuous tapes, the library shows "62mm x 0mm" or just "62mm" — verify and handle
both. HTTP gives no color-capability info; report `color_capable: false` (unknown/safe default).

## What to do

### 1 — `status_read()` in `backend/labelforge/printer/client.py`

Add `StatusUnavailable` exception and `status_read()` after the existing `PrintError` class.

```python
class StatusUnavailable(Exception):
    pass

def status_read(host: str, backend: str, timeout_ms: int = 2000) -> dict:
    """
    Query printer status. Returns a dict:
      {
        "ready": bool,
        "model": str | None,
        "media_id": str | None,      # library identifier, e.g. "62", "62x29", "62red"
        "width_mm": int | None,
        "length_mm": int | None,
        "color_capable": bool,
        "errors": list[str],
        "source": "tcp" | "http",
      }
    Raises StatusUnavailable if both TCP and HTTP paths fail.
    Only the "network" backend is supported; other backends raise StatusUnavailable immediately
    (feature is limited to network-connected printers in v1).
    """
```

**TCP path** (only when `backend == "network"`):
- `backend_factory("network")["backend_class"](f"tcp://{host}")`
- Set `printer.read_timeout` and `printer.s.settimeout` to `timeout_ms / 1000`
- Wrap in `get_status(printer)` — but since `get_status` is defined in helpers.py and
  re-imports `interpret_response`, call it directly; OR manually write/read and call
  `interpret_response(data)` yourself (simpler, avoids the exception-before-assignment
  bug in `get_status` when data is empty)
- If `len(data) < 32`: skip TCP, fall to HTTP
- Parse: `width = data[10]`, `length = data[17]`, `tape_color_raw = data[24]`
- `media_id = _media_id_from_dims(width, length, tape_color_raw)`
- Dispose the backend socket regardless

**HTTP path** (fallback when TCP returns empty):
- `urllib.request.urlopen(f"http://{host}/general/status.html", timeout=timeout_ms/1000)`
- Use `html.parser` or regex to extract dt/dd pairs (no external deps)
- Determine `ready` from Device Status text (READY → True; anything else → False)
- Parse Media Type string for width/length → `_media_id_from_dims(width, length, None)`

**Media ID helper** `_media_id_from_dims(width_mm, length_mm, tape_color_raw)`:
- Search `ALL_LABELS` for `lbl.tape_size == (width_mm, length_mm)`
- Special case continuous 62 mm: if `tape_color_raw is not None`, use raw byte to detect
  two-color media (TODO: verify exact byte for DK-22251; default to "62" until hardware
  confirms the DK red color byte); if `tape_color_raw is None` (HTTP path), return "62"
- Return `None` if no match

**`color_capable`**: derive from `label.color == Color.BLACK_RED_WHITE` once `media_id`
is resolved via `ALL_LABELS`.

Dispose the TCP socket in a `finally` block even if `interpret_response` throws.

### 2 — Printer router: `backend/labelforge/routes/printer.py` (new file)

```python
router = APIRouter(tags=["printer"])

@router.get("/printer/status")
async def get_printer_status():
    """
    Returns printer status (200) or 503 if unreachable/timeout.
    Response matches api.md shape:
      {"ready": bool, "model": str|null, "loaded_media": {...}, "errors": [...]}
    """
```

Map `status_read()` dict to the api.md 200 shape:
```json
{
  "ready": true,
  "model": "QL-820NWB",
  "loaded_media": {
    "id": "62x29",
    "display_name": "62mm × 29mm (Die-cut)",
    "width_mm": 62,
    "length_mm": 29,
    "color_capable": false
  },
  "errors": []
}
```

On `StatusUnavailable`: return 503 `{"error": "status_unavailable", "message": "..."}`.

`display_name` can come from the `labels.yml` catalog if the `media_id` is present there;
fall back to `f"{width_mm}mm × {length_mm}mm"` (or `f"{width_mm}mm Continuous"` for
length=0).

No auth required (read-only, GET).

### 3 — Register the printer router in `backend/labelforge/main.py`

Currently no printer router is registered. Add:

```python
from labelforge.routes.printer import router as printer_router
app.include_router(printer_router, prefix="/api")
```

Check `main.py` to find the pattern used for existing routers (templates, print, history,
settings) and match it exactly.

### 4 — Pre-print media check in `backend/labelforge/routes/print.py`

In both `POST /api/print/quick` and `POST /api/print/{name}`, insert the status check
**after rendering the label image** but **before calling `print_image()`**:

```python
# status check block
settings = get_settings()  # or however settings are loaded in this route
if settings.get("printer_status_check", True):
    timeout_ms = settings.get("printer_status_timeout_ms", 2000)
    try:
        status = status_read(
            host=config.printer_host,
            backend=config.printer_backend,
            timeout_ms=timeout_ms,
        )
        if status["errors"]:
            raise HTTPException(409, {"error": "printer_error", "code": ..., "message": ..., "raw": status})
        if status["media_id"] is not None:
            expected_media = <label_media for this request>
            if not _media_compatible(status["media_id"], expected_media):
                if not request_override:
                    raise HTTPException(409, {
                        "error": "media_mismatch",
                        "expected": expected_media,
                        "loaded": status["media_id"],
                        "override_allowed": true,
                        "message": "..."
                    })
                # else: log warning and proceed
    except StatusUnavailable:
        logger.warning("Printer status unavailable; proceeding without check")
```

`_media_compatible(loaded_id, expected_id)`: two IDs are compatible when the loaded media
can print the expected layout. Key rule from `printer-status.md`:
- `"62"` and `"62red"` are compatible when the template uses only black (treat color
  as a superset); `"62red"` loaded but template is `"62"` → allow.
- `"62"` loaded but template is `"62red"` → block (silent mono output).
- Anything else: exact string match.

`override` parameter: check `?override=true` query param (or request body field —
check how `api.md` specifies it; it says `?override=true` query string).

For `batch` printing: apply the check once per batch, not per label.

### 5 — Settings "Test printer" button (frontend)

In the Settings page (`frontend/src/pages/settings.ts` or wherever settings UI lives):

1. Add a **"Test printer"** button near the printer configuration section.
2. On click: call `GET /api/printer/status` (with `Authorization: Bearer ...` header via
   the existing `apiFetch` or similar helper).
3. Render the result inline below the button:
   - Success (200): show model, loaded media, ready state as a small info block.
   - Error (503): show the error message in a warning chip.
   - Always show the raw source ("tcp" or "http") in small/muted text for debugging.
4. Clear the result when the settings form is saved or when the page unloads.

Use whatever pattern the existing settings page uses for API calls and result display —
do not introduce a new pattern.

### 6 — Color capability detection note

Implement `data[24]` reading for the TCP path as noted above. Add a `# TODO: verify
DK-22251 tape_color_raw byte against hardware` comment where the condition appears. Until
confirmed, the safe default is to return `"62"` (not `"62red"`) for continuous 62 mm
when the byte value is ambiguous.

## Conventions to honor

- `run_pipeline` before any code changes; `get_skeleton` over `Read`.
- No grep/glob while vexp daemon is healthy.
- `feat:` commit prefix; no `Co-authored-by:`.
- All work on `dev`. Commit, don't push.
- Add a `CHANGELOG.md` entry under `## [Unreleased]`.
- Verify imports: mirror the verified-imports comment block at the top of `client.py`
  for any new library calls.
- Do not add `printer_status_check` or `printer_status_timeout_ms` to `settings_store.py`
  — they are already at lines 27-28.

## When done

1. Update this file's frontmatter: `status: completed`, `completed: 2026-05-31`,
   `result: <one line>`.
2. `git mv` this file into `prompts/done/`.
3. Propose ONE commit: `feat: add printer status endpoint, pre-print media check, and Test printer UI`. File list + message → ask `commit these as "<message>"? (y/n)`. On y, stage specific paths only; commit on `dev`; never push.
