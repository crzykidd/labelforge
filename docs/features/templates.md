# Feature: Templates

The core feature. A template is a saved, named label design with a freeform canvas of elements and an auto-derived schema of variable fields.

## User flows

### Create a new template

1. Navigate to `/templates` → list of existing templates
2. Click **New template**
3. Modal: type a friendly name (e.g. `Spool Label`) — the URL slug is auto-derived (`spool-label`)
   and shown as a read-only hint. Pick a label media (defaults to the last-used media, shared
   with Quick Print and Save As). The OK button is gated on a valid slug
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
3. Modal: new name + new label media (defaults to the last-used media; falls back to the source template's media if none stored)
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
7. **Overflow warning** — if content extends beyond the printable area, an inline warning
   appears ("Content may be clipped"). This checks the *resolved* field values, not the
   stored placeholders, so a value longer than the placeholder it was designed around (e.g.
   `{name}` filled with a long name) is caught even though the template looked fine in the
   editor. Die-cut media is checked on both axes; continuous media only on the print-head
   width (a single line wider than the tape) — continuous length itself never overflows,
   since the label just prints longer (see Rotation → auto-length, below). Printing still
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
  orientation     text                -- "standard" (default) or "rotated"
  created_at      timestamp
  updated_at      timestamp
  deleted_at      timestamp nullable
```

`canvas_json` is the Fabric.js `canvas.toJSON()` output, with a custom property added per element for label-specific concerns (e.g. text elements get a `labelforge_raw_content` field that preserves `{placeholders}` even after rendering substitutes them).

`field_schema` is derived on save by walking `canvas_json`, extracting `{placeholder}` matches from text/qr/barcode element content, and merging with any user-edited field properties (type, default).

### Element model (in canvas_json)

Standard Fabric.js objects with extensions:

- All elements: standard `left`, `top`, `width`, `height`, `angle`, `scaleX`, `scaleY`. The renderer also honors `originX`/`originY` (defaulting to `left`/`top` when absent), so `left`/`top` are interpreted exactly as Fabric does: as coordinates relative to the element's declared origin, not necessarily its top-left corner.
- Text: `text`, `fontFamily`, `fontSize`, `fontWeight`, `fontStyle`, `textAlign`
  - Extension: `labelforge_raw_content` — original string with `{placeholders}`, used to re-derive fields on edit
  - Extension: `labelforge_wrap` (boolean, default `false`/absent) — word-wrap at spaces to fit the element's box width; see Wrap, below
  - Extension: `labelforge_wrap_max_lines` (integer, default `0` = no limit) — caps wrapped output at this many lines, truncating and flagging overflow beyond it; see Wrap, below
- QR code: stored as Fabric `Image` with extension `labelforge_qr_payload` (string with placeholders) and `labelforge_qr_error_correction` (`L`/`M`/`Q`/`H`)
- Barcode: same pattern with `labelforge_barcode_payload` and `labelforge_barcode_symbology`
- Image: standard Fabric image with extension `labelforge_image_id` pointing to an entry in an `images` table
- Line / rect: standard Fabric shapes

QR and barcode elements are rendered as bitmaps in the editor (Fabric Image) but regenerated server-side at print time using the resolved payload string.

## Editor specifics

### Canvas size

The canvas matches the label media at print DPI (300dpi for QL series). A 62×100 die-cut at 300dpi = 696×1109 pixels. The editor displays this scaled to fit the viewport but operates in label pixel coordinates.

For continuous media (62mm endless), the canvas has a fixed width and a user-settable initial length. The length can grow as elements are added beyond the bottom; print length matches the bottommost element's extent plus padding — for a rotated element (see Rotation, below) that's the *rotated* bounding box, not the unrotated `top + height`, so a rotated element that's now taller than the label grows the print length to fit it instead of clipping it.

### Orientation

Every template stores an `orientation`: `standard` (default) or `rotated`. This mirrors Quick
Print's rotation concept (`orientation` on `QuickPrintRequest`), but templates store it per
template rather than reading Settings' `default_orientation` — a template's orientation is a
property of the design, not a global default, and the two are otherwise unrelated.

When `rotated`, the editor canvas is **transposed**: its width is the label's length axis and its
height is the fixed print-head width, so you design and type upright, in normal reading
orientation. The rendered/printed output — what Preview shows and what actually prints — is that
canvas rotated a quarter turn, i.e. sideways relative to how it was authored. Continuous media's
auto-length still works under rotation; it just grows along the transposed axis (the design's
width instead of its height).

Toggling orientation on an existing template **never moves or resizes elements** — `left`/`top`
coordinates are preserved exactly, even though the canvas they sit on changes shape. There is no
auto-reflow: a one-time status message says the layout will likely need adjusting. This is
deliberate — a design that's visibly wrong after toggling is easier to fix than one silently
rearranged to some guessed-at "correct" layout.

### Elements panel, bounds, grid/snap, keyboard, undo

The canvas has no scrollbars past its own edges, so an element dragged off it is
otherwise invisible and unselectable — and not merely a display nuisance: it
still renders server-side at its off-canvas position, and on continuous media a
stray element inflates the auto-derived print length. The following exist to
make that unrecoverable state impossible to reach, and recoverable when it's
already happened (e.g. a template edited before this existed).

**Elements panel** — a list beside the canvas (right of it at normal widths;
wraps below the canvas on narrow windows so the canvas is never squeezed) shows
every object on the canvas regardless of position: its type (Text / QR /
Barcode / Line / Rect / Image) and a short content snippet. Clicking a row
selects that object. Rows for an object currently outside the canvas bounds are
flagged. The list re-renders on every add/remove/modify and on text edits.

An off-canvas row's flag is itself a button (**"off canvas"**, not just a
label) — clicking it clamps that one element back inside and selects it,
without touching any other element. The panel header additionally shows a
**"Bring all on-canvas"** button, but only while at least one element actually
is off canvas; it clamps every out-of-bounds object at once and selects the
first one it moved. Both exist because the per-row fix reads as the obvious
action right where a user notices the problem, while the bulk button is faster
once several elements need it — see docs/decisions.md for why the bulk button
lives here instead of the main toolbar.

The status line also shows a one-line hint ("N elements are off the
label — …") the moment the off-canvas count changes away from zero, naming
both recovery paths; it clears itself once nothing is off canvas, without
clobbering an unrelated Save/Preview message.

**Clamping** — dragging or resizing an element keeps its bounding box inside
the canvas; you cannot drag or grow an element out of bounds. A backstop clamp
also runs on `object:modified` and `mouse:up`, so the position actually
committed at the end of a drag is always back-checked against the bounds
regardless of what happened mid-drag. This only prevents new breakage. To
repair a template that already has an off-canvas element (e.g. one created
before this existed, or edited via raw API calls), use the elements panel's
recovery controls described above.

Bounds checks and clamping compare against the label's pixel dimensions (the
same axis-swap `orientation` applies to the design canvas), not the on-screen
display size — the two differ whenever the canvas is zoomed to fit the
viewport.

**Grid and snap** — the **Grid** toggle (remembered per browser) overlays a
10-label-pixel grid, drawn as a CSS background on the canvas element itself,
never as objects on the canvas — anything added to the canvas serializes into
`canvas_json` and would print. Independent of the grid toggle, dragging an
element always snaps to the canvas edges and to the horizontal/vertical
centerlines (with a brief guide line) within a few pixels; enabling the grid
additionally snaps to its lines. Resizing snaps the edge being dragged the same
way.

**Keyboard** — with an element selected: arrow keys nudge it 1 label pixel,
Shift+arrow nudges 10, Delete/Backspace removes it, Escape deselects.
Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z redoes (also available as toolbar buttons).
None of this fires while inline-editing a text element's content, or while a
toolbar input/select has focus — otherwise typing would move or delete the
element being edited.

**Rotation** — every element (text, QR, barcode) has a standard Fabric rotate
handle. Rotating within about 8° of 0/90/180/270 snaps exactly to that angle;
outside that window rotation is free. This uses Fabric's built-in
`snapAngle`/`snapThreshold` object properties, not custom event math. A brief
"N°" readout appears near the element while rotating, and a **"Rotate 90°"**
button in the contextual row (visible whenever an element is selected) turns
the current selection by 90° per click, mod 360, for discoverability without
needing to grab the handle. Per-element rotation (the `angle` property) is
independent of the template's `orientation` (below) — rotating one element
does not affect the label's orientation, and vice versa.

The server renderer accounts for `angle` when computing extent: continuous
auto-length uses the element's *rotated* bounding box (so rotated text isn't
clipped and doesn't sit under a large blank gap), and die-cut overflow
detection (`detect_overflow`) checks the rotated footprint too. The renderer
also rotates an element about its Fabric origin point, matching the editor —
see docs/decisions.md for why that isn't always the element's own centre.

On continuous media the auto-length calculation tracks both the nearest and
farthest edge of every element, not just the farthest: a centre-anchored
element (Fabric's default) whose printed value is wider than the design it was
sized around grows the label backwards past the start as well as forwards, and
the label grows to cover all of it rather than silently losing the part that
grew backwards.

**Don't combine template `orientation: rotated` with a 90° `angle` on the same
element.** To print text longer than the tape width, use *one* of: the
template's own `Rotated 90°` orientation (design upright, the whole label
prints sideways), or rotate the individual element 90° on a `standard`
template. Doing both together drives that element's long axis onto the fixed
print-head-width axis instead of the free length axis — content that can't be
made to fit by growing the label, flagged by the overflow warning rather than
silently clipped. See docs/decisions.md.

**Undo/redo** — a 50-entry snapshot stack. A snapshot is taken after every
add/remove/modify, and once per text-editing session (debounced, not per
keystroke). Restoring a snapshot goes through the same load path used to open a
saved template, so QR/barcode placeholder bitmaps and the text raw-content sync
are regenerated exactly as on initial load — not a bare Fabric deserialize,
which would silently lose both.

### Wrap

Every text element has an opt-in **Wrap** control in the contextual control row: a select
with **Off / No limit / 2 / 3 / 4 / 5 lines** (default Off — existing templates are
unaffected). When enabled, the *resolved* text (after field substitution) is word-wrapped at
spaces to fit the element's own box width (`width × scaleX`). "No limit" wraps to as many
lines as needed (the v0.1.8 behavior — a template saved before the cap existed, with
`labelforge_wrap: true` and no `labelforge_wrap_max_lines`, keeps rendering exactly as it
did, byte-for-byte). Choosing 2–5 sets `labelforge_wrap_max_lines`: each line is still
greedily filled first (as much text as fits before breaking), and once the content needs
more lines than the cap, the remainder is **truncated** — not shrunk to fit — and the print
and preview responses' existing `overflow` flag is set, surfacing the same warning the
recall page already shows for any other kind of overflow. Truncation is a deliberate
operator choice over auto-shrinking text to fit: it keeps font size predictable and pairs a
visible warning with the one case it can't avoid. See docs/decisions.md.

The wrap target width is orientation-aware: text runs along whichever axis the element's
local width actually maps onto once its own `angle` composes with the template's
`orientation`. On a **standard** (unrotated) template with an axis-aligned element, that's
still the print-head width — a hard, physical ceiling, exactly as before. On a **rotated**
template, the design canvas is transposed and text normally runs along the free (tape)
length axis instead, which is effectively unbounded — clamping to the print-head width there
wrapped far too early. The element's own `angle` can flip this again (a 90°-rotated element
inside a rotated template lands back on the head-width axis) — the renderer composes both
rotations rather than special-casing orientation alone.

Wrapping only ever breaks at a space; it never hyphenates or splits a word mid-character. A
single word wider than the target width is left on its own line, overflowing — the overflow
warning (above) catches this case too, since wrap can't fix it. A value that already fits on
one line, or within its line cap, renders identically whether Wrap is on or off.

Wrap is a per-element choice, not automatic, because auto-wrapping every text element would
silently change the layout of templates that currently rely on a fixed one-line box (e.g. a
tight label under a barcode) — the operator opts in per element instead.

### Toolbar

Top: undo, redo, zoom, fit, save, save-as, preview, print

The editor title shows the friendly `display_name` (falls back to the slug when they match).
The current label media is shown as a read-only badge next to the template name so
the user can see what they are editing without opening any menu.

The main toolbar never wraps to a second row (it scrolls horizontally instead
at narrow widths) — selecting an element used to reflow the toolbar and shift
the canvas down; it can no longer do either. Per-selection controls (font,
text color, QR/barcode payload, the rotate button) live in a separate,
fixed-height row below the main toolbar, always present, whose *contents*
swap by selection type. When nothing is selected it shows a short hint instead
of collapsing. **Bring all on-canvas** is not in either toolbar row — it's in
the elements panel header, described above.

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
