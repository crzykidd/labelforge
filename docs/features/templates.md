# Feature: Templates

The core feature. A template is a saved, named label design with a freeform canvas of elements and an auto-derived schema of variable fields.

## User flows

### Create a new template

1. Navigate to `/templates` → list of existing templates
2. Click **New template**
3. Modal: type a friendly name (e.g. `Spool Label`) — the URL slug is auto-derived (`spool-label`)
   and shown as a read-only hint. Pick a label media. The OK button is gated on a valid slug
   (non-empty, matches `^[a-z0-9][a-z0-9-]*$`) and a selected media.
4. Land in editor with a blank canvas sized exactly to that label media at print DPI
5. Add elements from a toolbar (text, QR, barcode, image, line, rect)
6. Position, resize, rotate, layer
7. Edit element content; use `{field_name}` syntax inside text/qr/barcode content to declare a variable
8. Field list updates live in a side panel as placeholders are added/removed
9. Click **Save** → template persisted

### Edit an existing template

1. From `/templates`, click a template
2. Editor opens with elements deserialized from saved JSON
3. Edit, save

### Save As (clone with different label media)

A template's stored media can be permanently changed only via Save As. For a one-off print on
different media, use the recall page's media selector instead (no new template created).

To permanently re-use a design on a different media:

1. Open template
2. Click **Save As**
3. Modal: new name + new label media
4. Saved as new template; original untouched
5. Editor opens on the new copy; user adjusts layout for the new dimensions (no auto-reflow)

### Delete

Soft-delete: `templates.deleted_at` set. Templates with `deleted_at != null` don't show in lists or API. Hard-delete is a manual DB operation; no UI for it in v1.

History rows referencing a deleted template keep their `template_id` and resolve the (now-hidden) name for display. Reprint of a deleted template's history row still works (template data is fetched ignoring `deleted_at`).

### Recall (print from template)

1. From `/templates`, click **Print** on a template
2. **Media selector** — pick which label media to print on (default: the template's stored media).
   Same-width media are listed first (most likely to fit the design). A "Loaded in printer"
   toggle narrows the list to the roll currently mounted (fetches printer status once). This is
   a one-off choice — the stored template media is never mutated.
3. **Mono + red notice** — if the template contains red elements and the chosen media is
   mono (single-color), an inline notice explains that red will print as black. The renderer
   automatically maps red → black; no toggle is needed.
4. Form auto-generated from the template's field schema
5. Required fields validated client-side and server-side
6. **Preview** button → true preview reflecting filled values on the chosen media. The Print
   button is gated until a fresh preview has been taken after any media change.
7. **Overflow warning** — if the chosen media is a die-cut and content extends beyond its
   printable height, an inline warning appears ("Content may be clipped"). Printing still
   proceeds; the user decides from the preview.
8. **Print** button → prints on the chosen media, logs to history with the chosen media.
9. **Batch** toggle → see [`templates - batch`](#batch--increment) below

One-off media overrides are captured in history with the actual printed media. Reprinting a
history row reproduces the original media choice, not the template's stored media.

## Data model

```
templates
  id              integer primary key
  name            text unique         -- slug, used in API URLs
  display_name    text                -- human label, default = name
  label_media     text                -- e.g. "62", "62red", "29x90"
  canvas_json     text                -- serialized Fabric.js scene
  field_schema    text (json)         -- list of {name, type, required, default, increment}
  created_at      timestamp
  updated_at      timestamp
  deleted_at      timestamp nullable
```

`canvas_json` is the Fabric.js `canvas.toJSON()` output, with a custom property added per element for label-specific concerns (e.g. text elements get a `labelforge_raw_content` field that preserves `{placeholders}` even after rendering substitutes them).

`field_schema` is derived on save by walking `canvas_json`, extracting `{placeholder}` matches from text/qr/barcode element content, and merging with any user-edited field properties (type, default).

### Element model (in canvas_json)

Standard Fabric.js objects with extensions:

- All elements: standard `left`, `top`, `width`, `height`, `angle`, `scaleX`, `scaleY`
- Text: `text`, `fontFamily`, `fontSize`, `fontWeight`, `fontStyle`, `textAlign`
  - Extension: `labelforge_raw_content` — original string with `{placeholders}`, used to re-derive fields on edit
- QR code: stored as Fabric `Image` with extension `labelforge_qr_payload` (string with placeholders) and `labelforge_qr_error_correction` (`L`/`M`/`Q`/`H`)
- Barcode: same pattern with `labelforge_barcode_payload` and `labelforge_barcode_symbology`
- Image: standard Fabric image with extension `labelforge_image_id` pointing to an entry in an `images` table
- Line / rect: standard Fabric shapes

QR and barcode elements are rendered as bitmaps in the editor (Fabric Image) but regenerated server-side at print time using the resolved payload string.

## Editor specifics

### Canvas size

The canvas matches the label media at print DPI (300dpi for QL series). A 62×100 die-cut at 300dpi = 696×1109 pixels. The editor displays this scaled to fit the viewport but operates in label pixel coordinates.

For continuous media (62mm endless), the canvas has a fixed width and a user-settable initial length. The length can grow as elements are added beyond the bottom; print length matches the bottommost element's `top + height` plus padding.

### Toolbar

Top: undo, redo, zoom, fit, save, save-as, preview, print

The editor title shows the friendly `display_name` (falls back to the slug when they match).
The current label media is shown as a read-only badge next to the template name so
the user can see what they are editing without opening any menu.

**Save As** opens a modal for entering a new slug name and picking a label media
(pre-filled with the current media). It saves the current canvas first, then calls
`POST /api/templates/{name}/duplicate`. On success, the editor navigates to the new
template. This is the only sanctioned way to retarget a design to different media —
the current template's media is never mutated in the editor.

**Text color** — a Black / Red toggle appears in the toolbar **only when the loaded
label is two-color** (`label.color === 1`, e.g. `62red` / DK-2251). For mono media
the control is hidden and all text is always black. When visible, changing the
control sets the active text element's `fill` property; new text elements default to
the currently-selected color. The server renderer honors the `fill` value and
composites red or black ink onto the print image.

Left: element type palette (text, QR, barcode, image, line, rect)

Right: properties panel for selected element + global panels (fields, label info)

### Field detection

On every canvas change (debounced), parse text/qr/barcode element content for `{name}` matches. Maintain a set of detected field names.

Field schema = previously-known schema + newly-detected names (added with defaults: `type: text, required: true`) - names no longer detected (removed).

User can edit field properties in the right panel (change type, set default, mark increment, mark not-required).

### Save validation

- Name unique (case-insensitive)
- Name slug-valid (`^[a-z0-9][a-z0-9-]*$`)
- Label media exists in catalog
- At least one element on canvas
- No element extends outside the canvas bounds (warn; do not block)

## Batch / increment

Any field with `type: number` can be toggled `increment: true` in the field schema.

In the recall form:
- If any field is incrementable, a **Batch** toggle appears
- Enabling Batch shows: count input, starting value override per increment field
- Print produces `count` labels, with increment fields advancing by 1 each label
- Non-increment fields hold their value across all labels in the batch
- Batch is a single API call (`POST /api/print/{name}/batch`) — see [`api.md`](api.md)

Numeric incrementing:
- Pure number (`47`) → `47, 48, 49, ...`
- Zero-padded (`047`) → `047, 048, 049, ...` (preserve width)
- Suffix-numeric (`spool-047`) → `spool-047, spool-048, ...` (split on trailing digits)

Edge cases:
- Overflow of zero-padded width: when `047` → `048` ... `099` → `100`: width grows. Document as expected behavior.
- Negative or zero count: 400, "Batch count must be >= 1"
- Batch count > 1000: 400, "Batch count exceeds maximum (1000)" — sanity guard

## Template list

The template list shows:
- **Name** — `display_name` (falls back to the slug)
- **Media** — the Brother DK part number with size, e.g. `DK-1209 (62×29mm)` for a die-cut,
  `DK-2251 (62mm) Red` for a two-color continuous roll. If the media id is not in the catalog
  (deleted or custom entry), the raw id is shown in `<code>` as a fallback.
- **Updated** — last-modified timestamp

Renaming `display_name` after creation is not yet supported in the UI (the `TemplateUpdate`
model supports it via the API; a rename modal is left for a future iteration).

## API

See [`api.md`](api.md) for the full API surface. Template endpoints:

- `GET /api/templates` — list (excludes soft-deleted)
- `GET /api/templates/{name}` — full template + field schema
- `POST /api/templates` — create
- `PUT /api/templates/{name}` — update
- `DELETE /api/templates/{name}` — soft-delete
- `POST /api/templates/{name}/duplicate` — Save As (body: new name, new label media)
- `POST /api/print/{name}` — print one
- `POST /api/print/{name}/batch` — print N with increment
- `POST /api/preview/{name}` — render preview without printing

## Out of scope for v1

- Template versioning (edit creates new version, old API calls keep working): deferred — single-user, you'll know when you broke a script
- Template categories / tags: maybe later if the list gets long
- Template sharing / export-import: not a v1 concern
- Conditional elements ("show this text only if {variable} is non-empty"): defer indefinitely
