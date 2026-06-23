---
name: 2026-06-22-add-qr-element-editor
status: completed
created: 2026-06-22
model: sonnet            # coding task (frontend TS)
completed: 2026-06-22
result: Added "Add QR" toolbar button and QR property controls; QR element serializes as Fabric Image with labelforge_qr_payload/labelforge_qr_error_correction custom props; placeholder bitmap generated client-side; real QR rendered server-side on Preview/print; tsc + build pass.
---

# Task: Add an "Add QR Code" button to the template editor

The server-side renderer now prints QR codes correctly (commit 421caee), but the
editor has **no way to create a QR element** — the toolbar only has "Add Text"
(`addTextElement`). So QR templates can only be built by hand-POSTing canvas JSON.
Add an "Add QR Code" button plus the controls to edit a selected QR element's
payload and error-correction level, so QR templates can be authored and tested
entirely in the UI. **QR only this pass — not barcode** (barcode shares the same
mechanism and is a trivial follow-up, but the owner asked for QR).

## Before you start

- Read `docs/features/templates.md` (element model, ~lines 89-101) and `CLAUDE.md`
  (working style, changelog, check-in rules). This is **frontend-only**.
- QR/barcode are in PRD scope (templates: text, QR, barcode, image, line, rect) —
  this fills a planned slice, not new scope. Don't add multi-user/SSO/etc.
- **No new runtime dependency.** `frontend/package.json` has only `fabric@7.4.0`
  and no client-side QR library. Do NOT add one (see the in-editor visual decision
  below). If you think a real client-side QR bitmap is worth a dependency, STOP and
  raise it — don't add it unilaterally.

### The JSON contract (what the backend already expects)

The server dispatches an element by `norm_type == "image"` AND which custom prop
is present (`backend/labelforge/render/template.py:335-357`). The exact shape is
pinned in `backend/tests/test_render_qr_barcode.py:43-57`:

```json
{ "type": "Image", "left": 20, "top": 20, "width": 100, "height": 100,
  "scaleX": 1, "scaleY": 1, "angle": 0, "originX": "left", "originY": "top",
  "labelforge_qr_payload": "https://example.com",
  "labelforge_qr_error_correction": "M" }
```

- The element MUST serialize with `type` normalizing to `"image"` (a Fabric
  `Image` serializes as `"Image"` → backend lowercases it — good). A Fabric `Rect`
  would serialize as `"Rect"` and the backend would render it as a black box, NOT a
  QR — so the in-editor object MUST be a Fabric `Image`, not a Rect/Group.
- Backend QR size comes from `width*scaleX` × `height*scaleY`; error correction is
  `L/M/Q/H` (default `M`, `_QR_CORRECTION` map). QR is square — default to a square
  box.
- Payload may contain `{field}` placeholders; `detect_fields`
  (`backend/labelforge/templates/fields.py:19-22`) already extracts them, so a QR
  with payload `{url}` automatically becomes a variable field. No frontend work
  needed for that beyond storing the raw payload — but verify a `{placeholder}`
  payload still saves and previews (preview fills sample values).

### Editor structure (from a survey — verify before trusting)

- `frontend/src/editor/canvas.ts`
  - `CUSTOM_PROPS = ['labelforge_raw_content']` (line 3) and the global
    registration `FabricObject.customProperties.push('labelforge_raw_content')`
    (lines 15-16) — this is what makes a custom prop survive `toJSON()`/
    `loadFromJSON()`. **Add `labelforge_qr_payload` + `labelforge_qr_error_correction`
    here** (extend `CUSTOM_PROPS` and push them; the code currently pushes the
    literal rather than spreading the array — unify it: push every entry of
    `CUSTOM_PROPS`).
  - `addTextElement` (lines 56-79) — the pattern to mirror: compute a virtual
    (unzoomed) position from the viewport transform, construct the Fabric object,
    `.set(...)` the custom props, `add` + `setActiveObject` + `renderAll`.
  - `getCanvasJSON` = `canvas.toJSON()` (89-92); `loadCanvasJSON` (94-109) restores
    custom props automatically and re-attaches the text `changed` listener.
  - `isTextType` (23-26) — copy this to make an `isQrType(obj)` that checks the
    active object carries `labelforge_qr_payload` (QR serializes as Image, so you
    must distinguish by the prop, exactly as the backend does).
- `frontend/src/pages/template-editor.ts`
  - Toolbar HTML literal (lines 47-82); "Add Text" button at line 55, wired at
    192-196. Add the "Add QR Code" button next to it and a sibling handler.
  - Property controls live **inline in the toolbar** (font select / size / color,
    lines 58-66, handlers 157-185), each guarded on `isTextType`. Add a QR control
    group (payload `<input>` + error-correction `<select>` L/M/Q/H) following the
    same pattern, guarded on `isQrType`.
  - `updateFontControls` (142-155) + selection events (`selection:created/updated/
    cleared`, 136-139) drive per-selection toolbar state. Extend this so the QR
    group shows when a QR element is selected and the text group shows for text;
    give `selection:cleared` real reset behavior.

## In-editor visual decision (prescribed — do this, don't redesign)

There is no client QR library and we're not adding one. The in-editor
representation of a QR element is a **client-generated placeholder bitmap** set as
the Fabric `Image`'s source — a small square PNG drawn on an offscreen
`<canvas>`: a bordered box with a "QR" label and the (truncated) payload text
underneath, so the user can see it's a QR placeholder and where it sits. The
**authoritative QR is rendered server-side** and shown on Preview — make this
obvious (e.g. the button/element tooltip: "QR preview is generated on Preview/
print").

Requirements for the placeholder:
- Built via `new Image()` / Fabric `FabricImage.fromURL(dataUrl, ...)` (or
  `fromObject`) so the element's serialized `type` is `"Image"`.
- Carries `labelforge_qr_payload` (default `"https://example.com"`) and
  `labelforge_qr_error_correction` (default `"M"`) as custom props.
- Default to a square box (~150 label px); keep it resizable.
- **Round-trips:** after Save then reload, the element reappears as the same
  placeholder with its payload/EC intact. Since the placeholder bitmap is derived
  from the payload, regenerate the placeholder `src` on load for objects carrying
  `labelforge_qr_payload` (in `loadCanvasJSON`, alongside the existing text-listener
  re-attach) rather than relying on a stored data URL — keep `canvas_json` lean.
- Editing the payload in the toolbar updates the stored prop AND regenerates the
  placeholder so the visible text matches.

If any of this proves infeasible with Fabric 7's API (e.g. async image construction
ordering), solve it without adding a dependency and note the workaround in
decisions; don't silently switch to a Rect (it breaks the backend contract).

## Working tree check

Run `git status --porcelain`. The branch is `dev`, with two prior commits already
on it (`421caee` QR/barcode renderer, `b76218b` token-gate) — that's expected,
leave them; the tree should be clean. Files you'll touch:
`frontend/src/editor/canvas.ts`, `frontend/src/pages/template-editor.ts`, maybe
`frontend/src/style.css`, `CHANGELOG.md`, `docs/decisions.md`, possibly
`docs/features/templates.md`. If any has unrelated uncommitted changes, list it and
ask before touching. This prompt file is exempt.

## What to do

1. Register the two QR custom props in `canvas.ts` (and unify the
   `CUSTOM_PROPS`/`customProperties` push).
2. Add `addQrElement(canvas)` to `canvas.ts` mirroring `addTextElement`: creates
   the placeholder Fabric `Image` with the custom props and default payload/EC,
   adds + selects it.
3. Add a placeholder-bitmap generator (payload → square data URL) used by
   `addQrElement`, the load path, and the payload-edit handler.
4. Regenerate the placeholder on load in `loadCanvasJSON` for QR elements.
5. Add the "Add QR Code" toolbar button + handler in `template-editor.ts`.
6. Add the QR property group (payload input + EC select) with `isQrType`-guarded
   change handlers; show/hide it (and the text group) via the selection events.
7. Add an `isQrType` helper in `canvas.ts`.

## Conventions to honor

- Add a user-facing `CHANGELOG.md` entry under `## [Unreleased]` → `### Added`,
  ending with **"Requires a container image rebuild."** (frontend assets change).
- Record the non-obvious decision (placeholder-bitmap-not-client-QR-lib; regenerate
  on load; distinguish QR by custom prop since it serializes as Image) in
  `docs/decisions.md`, newest at top. If `docs/features/templates.md`'s
  "rendered as bitmaps in the editor" wording needs a small clarification that the
  editor shows a placeholder authored client-side, update it in the same commit.
- Match the existing vanilla-TS / toolbar-inline style. No framework, new deps.
- Comments only for non-obvious *why*.
- **Type-check and build before finishing:** `cd frontend && npx tsc --noEmit &&
  npm run build`. No frontend unit tests exist; this is the CI gate. The command
  sandbox is disabled, so you CAN run these — paste the results.

## When done

1. Update this file's frontmatter (`status`, `completed` 2026-06-22, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/`.
3. Record decisions in `docs/decisions.md` (see above).
4. Prepare ONE commit (this prompt file + the code/docs + the prompt move). The
   prompt is **not** pre-committed — it bundles in.
   - **You are a spawned agent: do NOT commit.** Prepare the tree and report back
     the exact file list + a proposed one-line message (Conventional-Commits
     `feat:` prefix, no `Co-authored-by:`). The orchestrator surfaces the y/n.
   - Work on `dev`, never `main`, never `git add -A`, never push.
5. Report for the owner: the manual test path — open a template in the editor,
   click "Add QR Code", set a payload, Save, then Preview (the real QR should
   appear in the server-rendered preview), and a quick note that resizing the
   placeholder box changes the printed QR size.
