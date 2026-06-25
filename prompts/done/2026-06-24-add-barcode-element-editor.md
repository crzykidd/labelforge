---
name: 2026-06-24-add-barcode-element-editor
status: completed
created: 2026-06-24
model: sonnet            # coding task (frontend TS)
completed: 2026-06-24
result: Added Add Barcode button + barcode controls (payload + symbology dropdown) to template editor; registered barcode custom props fixing the latent serialization bug; mirrored QR pattern exactly; tsc and build both pass.
---

# Task: Add an "Add Barcode" button to the template editor

The server already renders barcode elements (`_render_barcode_element`) and
detects `{field}` placeholders in barcode payloads, but the editor has **no way
to create a barcode** and — critically — the barcode custom props aren't even
registered for serialization, so a barcode can't round-trip at all today. Add an
"Add Barcode" button plus payload + symbology controls, mirroring the QR feature
shipped in commit `d179c5f`. This completes the QR/barcode pair in the PRD's
canvas element palette.

## Before you start

- Read `docs/features/templates.md` (element model) and `CLAUDE.md`. **Frontend-only.**
- **This is a direct mirror of the existing QR implementation.** Study the QR code
  first and copy its shape for barcode — same patterns, same file locations. Do not
  invent a new approach.
- **No new runtime dependency.** `frontend/package.json` has only `fabric@7.4.0`;
  the placeholder is client-drawn, the real barcode is rendered server-side. Do NOT
  add a JS barcode library.

### Backend is already done (verify, don't change)

- `backend/labelforge/render/template.py:350-358` — dispatches an `image` element
  with `labelforge_barcode_payload` to `_render_barcode_element(payload, symbology,
  box_w, box_h)`; reads `labelforge_barcode_symbology` (default `"code128"`).
- `_render_barcode_element` (`template.py:206-223`) uses `python-barcode`; unknown
  symbology falls back to `code128`; it resizes (stretches) the barcode to
  `box_w × box_h`, so the element's box dimensions set the printed size directly.
- `templates/fields.py:22-23` already extracts `{field}` placeholders from
  `labelforge_barcode_payload`, so variable-field barcodes work automatically.
- Backend tests already cover barcode render (`backend/tests/test_render_qr_barcode.py`).
  Do NOT modify the backend.

### The QR implementation to mirror (exact anchors)

`frontend/src/editor/canvas.ts`:
- `CUSTOM_PROPS` (line 3) — the serialization allow-list; currently
  `labelforge_raw_content`, `labelforge_qr_payload`, `labelforge_qr_error_correction`,
  registered into `FabricObject.customProperties` by the loop at line ~20.
- `isQrType(obj)` (line 39) — checks `obj['labelforge_qr_payload'] !== undefined`
  (QR/barcode both serialize as Fabric `Image`, so you distinguish by the custom prop).
- `makeQrPlaceholderDataUrl(payload, px)` (line 53) — draws a client-side placeholder
  PNG on an offscreen `<canvas>`.
- `addQrElement(canvas, payload, errorCorrection)` (line 163) — builds the placeholder
  `FabricImage`, stamps the custom props, adds + selects.
- `refreshQrPlaceholder(obj)` (line 202) + its call in `loadCanvasJSON` (line ~239)
  — regenerates the placeholder on load so `canvas_json` needn't store the bitmap.

`frontend/src/pages/template-editor.ts`:
- Toolbar buttons: `#btn-add-text` (line 58), `#btn-add-qr` (line 59).
- QR controls: `#qr-payload` input (line 72), `#qr-ec` select (line 73); refs at
  lines 107-108; change handlers at 247-267; Add-QR handler at 282-285.
- `updateSelectionControls()` (line 184) — currently shows the text controls for text
  and the QR group for QR (`isQrType`); `updateFontControls` (line 204); selection
  events wired at 162-164. **You must extend this to a three-way: text / QR / barcode.**

## Working tree check

Run `git status --porcelain`. Check out `dev` and make sure it's current
(`git checkout dev && git pull origin dev`) — v0.1.4 has shipped, so `dev` should be
clean and even with origin. Files you'll touch: `frontend/src/editor/canvas.ts`,
`frontend/src/pages/template-editor.ts`, maybe `frontend/src/style.css`,
`CHANGELOG.md`, `docs/decisions.md`. If any has unrelated uncommitted changes, list
it and ask. This prompt file is exempt.

## What to do (mirror QR for barcode)

1. **Register the barcode props** in `canvas.ts` `CUSTOM_PROPS`:
   `labelforge_barcode_payload` and `labelforge_barcode_symbology`. (Without this,
   barcodes silently lose their props on save — the current latent bug.)
2. **`isBarcodeType(obj)`** in `canvas.ts` — mirror `isQrType`, checking
   `labelforge_barcode_payload`.
3. **`makeBarcodePlaceholderDataUrl(payload, w, h)`** — like the QR placeholder but
   **rectangular** (barcodes are wide, not square): a bordered box with a few vertical
   bars to evoke a barcode, a "BARCODE" label, and the truncated payload text. Takes
   width AND height (not a single square `px`).
4. **`addBarcodeElement(canvas, payload, symbology)`** — mirror `addQrElement`, but:
   - default `payload = "12345678"`, default `symbology = "code128"`
   - default box is a **landscape rectangle** (e.g. ~300×100 label px), not square
   - stamp `labelforge_barcode_payload` + `labelforge_barcode_symbology`
5. **`refreshBarcodePlaceholder(obj)`** + call it from `loadCanvasJSON` for objects
   carrying `labelforge_barcode_payload` (alongside the existing text and QR branches).
   Regenerate at the element's current `width*scaleX × height*scaleY`.
6. **Toolbar (`template-editor.ts`)**: add an `#btn-add-barcode` button next to
   `#btn-add-qr`, and a barcode control group — a `#barcode-payload` text input and a
   `#barcode-symbology` `<select>`. Offer a sensible symbology set: **Code 128**
   (default), Code 39, EAN-13, EAN-8, UPC-A. Add a `title`/hint that some symbologies
   require specific digit counts (e.g. EAN-13 = 12–13 digits) and that the real
   barcode is generated on Preview/print; the backend falls back to Code 128 on a bad
   symbology.
7. **Wire it up**: Add-Barcode click handler (`void addBarcodeElement(fabricCanvas)`);
   payload `change` handler (update prop + regenerate placeholder); symbology `change`
   handler (update prop — mirror the QR EC handler, which doesn't regenerate).
8. **Extend `updateSelectionControls`** to a three-way switch: show the text controls
   when a text element is selected, the QR group for QR, the barcode group for barcode,
   and hide the others. Pre-fill the barcode inputs from the selected object's props.
   Make sure `selection:cleared` hides the barcode group too.

## Conventions to honor

- `CHANGELOG.md` entry under `## [Unreleased]` → `### Added`, ending with
  **"Requires a container image rebuild."** (frontend asset change).
- Record the decision in `docs/decisions.md` (newest at top): barcode mirrors QR
  (Fabric Image + custom props + client placeholder + server-side real render);
  symbology default `code128`; **and note this also fixes the latent bug where barcode
  props were missing from `CUSTOM_PROPS`.**
- Match the QR code's vanilla-TS style exactly. No framework, no deps.
- Comments only for non-obvious *why*.
- **Type-check and build before finishing** (sandbox is disabled, run these and paste
  results): `cd frontend && npx tsc --noEmit && npm run build`. No frontend unit tests
  exist; this is the CI gate. Do not report "done" unless both pass.

## When done

1. Update this file's frontmatter (`status`, `completed` 2026-06-24, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/`.
3. Record the decision in `docs/decisions.md`.
4. Prepare ONE commit (prompt file + code/docs + prompt move). The prompt is **not**
   pre-committed — it bundles in.
   - **You are a spawned agent: do NOT commit.** Prepare the tree and report back the
     exact file list + a proposed one-line `feat:` message. The orchestrator surfaces
     the y/n.
   - Work on `dev`, never `main`, never `git add -A`, never push.
5. Report the manual test path: open a template → **Add Barcode** → set a payload (try
   a `{field}` too) → Save → **Preview** (a real barcode should render server-side) →
   resize the box to change the printed size → switch symbology and Preview again.
   Note any symbology whose default payload (`12345678`) is invalid (e.g. EAN-13).
