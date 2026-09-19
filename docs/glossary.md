# Glossary

Defined once here. Used consistently everywhere else.

### Label media

A physical tape or die-cut loaded in the printer. Examples: DK-22205 (62mm continuous), DK-22251 (62mm continuous black+red), DK-11201 (29×90 address label).

In code, identified by the `brother_ql` library's short identifier (`62`, `62red`, `29x90`, ...). Friendly metadata lives in `labels.yml`.

### Label media catalog

The merged set of available label media — library's printable list intersected with `labels.yml` metadata. See [`features/label-catalog.md`](features/label-catalog.md).

### Template

A saved, named label design. Has a *default/home* label media stored with it, but can be printed on a different compatible media at recall time (one-off — the stored media is never mutated). The recall page lets the user pick any supported media; same-width options appear first. Contains an ordered list of elements and an auto-derived field schema. Identified by a slug-like name (`spool`, `file-folder`, `box`).

See also: **Save As** (the way to permanently retarget a design to a new media), **Print-time media override** (the one-off recall path).

### Element

A single visual item on a template. Has a type, a position (x, y), size (width, height), rotation, z-order, and type-specific properties.

Element types in v1:
- `text` — string content, font, size, alignment, bold/italic. May contain `{field}` placeholders.
- `qrcode` — string content (may contain placeholders), error correction level, size
- `barcode` — string content (may contain placeholders), symbology (Code128, EAN-13, etc.)
- `image` — bitmap loaded from the user's uploaded image set
- `line` — two endpoints, stroke width
- `rect` — position + size + stroke + fill

### Field

A `{placeholder}` reference inside any text, qrcode, or barcode element. Auto-detected on template save. Each field has:

- `name` — the placeholder name (`number`, `color`, `weight`)
- `type` — `text` (default), `number`, `date`, `enum`, `list`
- `required` — bool, default true
- `default` — optional default value
- `increment` — marks the field as auto-incrementable in batch print (any `type`, not just `number` — it just advances whatever trailing digits the current value has)
- `enum_values` — fixed, per-template option list; only meaningful when `type` is `enum`

Field schema is derived from element content but can be edited (type, required, default,
increment, enum values) in the template editor's FIELDS panel.

### Field list

A named, ordered list of allowed values for a `type: "list"` field, stored independently of any
template and keyed by field name — every template with a `{room}` field shares the one `room`
field list. Editing it (via the FIELDS panel's **E** drawer, or the `/api/field-lists` API)
changes what every one of those templates offers at recall from then on. Contrast with a
`type: "enum"` field's `enum_values`, which is a one-off list owned by a single template. See
[`features/templates.md`](features/templates.md#value-lists-list-vs-enum).

### Print job

A record of one print action. Captures the template name (or `"quick"` for quick-print), the field values used, the label media at print time, a preview thumbnail, a timestamp, and an optional `pinned` flag (exempts from retention cleanup).

### Quick print

Print path that does not use a saved template. User types text, picks font/size/label media, prints. The action is logged to history but no template is created.

### Template recall

Print path starting from a saved template. UI shows a form auto-generated from the template's field schema; user fills values, sees preview, prints.

### Batch / increment print

Recall path that prints N labels in one operation. One or more numeric fields tagged `increment` advance per label. Backend treats this as a single API call with an array of value sets.

### Field schema

The list of fields a template declares, with types and defaults. Used to:
- Generate the recall form
- Validate API requests against the template
- Decide which fields are increment-capable in batch mode

### True preview

A preview rendered by the same code path that produces the printed bitmap. Pillow renders to an Image at exact printer DPI; that image is shown to the user *and* (on print) sent to `brother_ql` for conversion. What you see is what you get.

### Printer status query

A request to the printer over its TCP protocol asking what media is currently loaded, ink/tape level, and ready state. Supported by the QL-820NWB and other recent network models. Used for auto-detect with override.

### Shared secret / API token

A single string in `.env` (`API_TOKEN=...`) required as `Authorization: Bearer <token>` on all `/api/*` write endpoints. The UI uses the same token internally. No per-user, no expiry, no rotation in v1.
