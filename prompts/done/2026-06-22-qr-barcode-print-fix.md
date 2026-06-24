---
name: 2026-06-22-qr-barcode-print-fix
status: completed
created: 2026-06-22
model: sonnet            # coding task
completed: 2026-06-22
result: Wired QR and barcode render helpers into the image dispatch; field substitution, integer-multiple NEAREST upscale, hard-threshold insurance; 6 new tests pass.
---

# Task: Make QR and barcode template elements print correctly

QR and barcode elements currently render in preview but print as a solid black
block (the 1-bit threshold crushes anti-aliased detail), so they are hard-gated
to raise a `RenderError` at print/preview time. Re-enable them by wiring the
already-written, threshold-safe render helpers into the element dispatch and
proving (with tests) that the rasterized output survives the print threshold.
This closes the last v1 PRD gap (success criterion #2 — a Spool template with a
QR code).

## Before you start

- Read `docs/features/templates.md` (element model + extensions, lines ~89-101)
  and `CLAUDE.md` (working style, changelog, check-in rules).
- This is a backend-only fix to the server-side renderer and its tests. No
  frontend change is needed — the editor already stores QR/barcode as Fabric
  `Image` objects with the extension keys below.
- Honor the locked stack: `qrcode[pil]` for QR, `python-barcode` for barcodes,
  Pillow for rasterization. Do not add dependencies.

### What's already there (from a code survey — verify before trusting)

- `backend/labelforge/render/template.py`
  - `_render_qr_element(payload, correction, box_w, box_h)` (~lines 173-198) —
    `qrcode.QRCode(error_correction=ec, border=1, box_size=1)`, then an
    **integer-multiple NEAREST upscale** to avoid grey edges. Carries a
    `# TODO: re-enable when QR/barcode 1-bit print bug is fixed`.
  - `_render_barcode_element(payload, symbology, box_w, box_h)` (~lines 202-222)
    — `python-barcode` + `ImageWriter()`, `write_text=False`, then forces pure
    B/W via `.point(lambda x: 0 if x < 128 else 255)` and NEAREST resize.
  - **Both helpers exist but are never called.** The `image` branch
    (~lines 334-346) raises `RenderError("QR elements are not yet supported…")`
    / `"Barcode elements are not yet supported…"` before reaching them.
  - `_QR_CORRECTION` map (~lines 22-27) translates `L/M/Q/H`.
- Extension keys: `labelforge_qr_payload` + `labelforge_qr_error_correction`
  (`L/M/Q/H`); `labelforge_barcode_payload` + `labelforge_barcode_symbology`.
  Confirmed in `templates/fields.py` `detect_fields` (~lines 11-27) and
  `docs/features/templates.md`.
- Threshold path (not `convert("1")`): `backend/labelforge/printer/client.py`
  — `PRINT_THRESHOLD = 70` (percent), `_PRINT_CUTOFF = 179`, and
  `to_print_bitmap(image)` (`im.convert("L").point(lambda x: 0 if x <= 179 else
  255)`, no dither). `print_image(...)` calls
  `convert(..., threshold=PRINT_THRESHOLD, red=red)`. Any L pixel ≤ 179 prints
  black — this is what crushes anti-aliased edges.
- Preview vs print: previews of mono templates already go through
  `to_print_bitmap` (`routes/template_print.py` `preview_template`), so once the
  helpers emit pure 0/255 pixels, **preview and print agree**.
- Only renderer test today: `backend/tests/test_render_origin.py` (text origin
  only). No QR/barcode/threshold coverage.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the
files this plan touches (`backend/labelforge/render/template.py`,
`backend/tests/`, `CHANGELOG.md`, maybe `docs/features/templates.md`). If any
have uncommitted changes, list them and ask before touching them. Surface
unrelated dirty files once as awareness; don't block. This prompt file is
exempt.

## What to do

1. **Resolve the payload's variable fields.** QR/barcode payloads can contain
   `{placeholder}` tokens (`detect_fields` already extracts them). Before
   rasterizing, substitute resolved field values into the payload using the same
   field-resolution the text branch uses — so `{number}` in a QR payload prints
   the actual value, and preview uses the same sample/default fill the text
   branch does. Confirm how the text branch resolves fields and reuse it; do not
   fork a second substitution path.

2. **Replace the gate with real dispatch** in the `image` branch of
   `render_template` (~lines 334-346):
   - If `labelforge_qr_payload` is present → resolve payload, read
     `labelforge_qr_error_correction` (default `M` if missing/invalid), compute
     the element's box size in label pixels from the Fabric object
     (`width * scaleX`, `height * scaleY`, rounded), call `_render_qr_element`,
     and paste at the element's position honoring its origin (match how the
     existing text/rect branches compute top-left from originX/originY).
   - If `labelforge_barcode_payload` is present → same, with
     `labelforge_barcode_symbology` (helper already falls back to `code128`).
   - Plain images (no QR/barcode payload) → keep raising "Image elements not yet
     supported" (image upload is a separate, out-of-scope feature here).
   - Watch the arg-name/key mismatch the survey flagged: the helper params are
     `correction` / `symbology`; the stored keys are
     `labelforge_qr_error_correction` / `labelforge_barcode_symbology`. Wire them
     through explicitly.

3. **Two-color media.** On an `RGB` canvas, QR/barcode ink is black — paste the
   mono glyph into the black plane (red plane untouched), consistent with how the
   black text path composites. Don't emit grey.

4. **Verify no grey survives the threshold.** The whole point: the pasted
   QR/barcode region must be pure 0/255 *before* `to_print_bitmap` /
   `convert(threshold=70)`. If the NEAREST-upscale path can still leave
   anti-aliased edges when the box size isn't an integer multiple of the symbol
   size, fix it so the final pasted pixels are strictly black or white (e.g.
   render at native module size, integer-upscale to the largest multiple that
   fits the box, and pad rather than smooth-resize). A `.point()` hard-threshold
   on the element bitmap before paste is acceptable insurance.

5. **Tests** (`backend/tests/`, pytest, match existing style):
   - A QR element renders non-blank and, after `to_print_bitmap`, contains **both
     black and white** pixels (asserting it is NOT a solid block) and the white
     fraction is in a sane range (finder patterns + quiet zone present).
   - Same for a barcode element (alternating bars → both colors survive).
   - A QR payload with a `{placeholder}` resolves the field value before
     rasterizing.
   - These should not require the printer or a network. Gate on the qrcode /
     python-barcode imports if needed, but they're already project deps so they
     should import.

6. **Remove the stale TODOs** on the helpers once they're wired and tested.

7. **Manual verification line.** End with a one-liner the owner can run, e.g.
   `cd backend && python -m pytest tests/ -q`, plus a note that a real-printer
   smoke test on the QL-820NWB (a template with a QR code) is the final
   confirmation, since the threshold bug only manifested on hardware.

## Conventions to honor

- Add a concise, user-facing `CHANGELOG.md` entry under `## [Unreleased]`
  (Fixed). Mention it requires a container image rebuild only if a frontend asset
  changes — this is backend-only, so it likely does NOT.
- Update the **Known Issues** note: the QR/barcode "prints as a solid black
  block" caveat should be removed/updated once fixed (it appears in the changelog
  history; only update the live/unreleased framing, don't rewrite shipped release
  sections).
- If `docs/features/templates.md` describes QR/barcode as gated/not-yet-printing,
  reconcile it. Docs ship in the **same commit** as the code.
- Comments only for non-obvious *why* (e.g. why integer NEAREST upscale). No
  giant explainer blocks.
- One logical change. Keep the diff focused on the renderer + tests + docs.

## When done

1. Update this file's frontmatter: set `status` (completed/failed), `completed`
   (2026-06-22 or the actual date), and `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/`
   (failure). Create the subdir if needed.
3. Record any non-obvious decisions (e.g. the upscale/threshold strategy, the
   schema-key wiring) in `docs/decisions.md`, newest at top.
4. Prepare ONE commit covering this prompt file, the modified source/tests/docs,
   and the prompt move — the prompt is **not** pre-committed, it bundles in here.
   - **You are a spawned agent: do NOT commit.** Prepare the working tree, then
     report the file list + a proposed one-line message (Conventional-Commits
     `fix:` prefix, no `Co-authored-by:`) back to the orchestrating session,
     which surfaces the `y/n` to the user.
   - Work on `dev` per the project's `code-checkin-and-pr` rules; never `main`,
     never `git add -A`, never push.
