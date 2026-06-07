# Feature: Quick Print

## Goal

Type some text, pick a font, pick a label media, print. The brother_ql_web mode, kept as a first-class feature for one-off labels that don't deserve a saved template.

## User flow

1. User lands on `/` (default page is quick-print)
2. Single text area — multiline allowed
3. Font dropdown (sourced from fonts directory)
4. Font size (number input or slider)
5. Label media dropdown (sourced from catalog — see [`label-catalog.md`](label-catalog.md))
6. Bold / italic toggles
7. Alignment: left / center / right
8. Orientation: standard / rotated 90°
9. **Preview** button → renders true preview inline
10. **Print** button → prints and logs to history

Last-used values for font, size, alignment, and orientation are persisted in the `settings` table (single-row, keyed by setting name) and restored on next visit. Label media is additionally remembered in `localStorage` (`lf:last-label`) and shared with the New Template and Save As pickers so the most-recently-used roll is the default everywhere.

## Data model

Quick prints are **not** templates. They produce a `print_jobs` row with:

- `template_id = null`
- `quick_print_payload` = JSON snapshot of {text, font, size, alignment, orientation, label_media}

This lets history show quick prints alongside template prints and supports reprint.

## API

`POST /api/print/quick` — see [`api.md`](api.md). The UI calls this endpoint; there is no UI-only shortcut.

Request body:
```json
{
  "text": "Hello world",
  "font": "DejaVuSans-Bold",
  "font_size": 48,
  "alignment": "center",
  "orientation": "standard",
  "label_media": "62",
  "bold": false,
  "italic": false
}
```

Response: same shape as template print (`job_id`, `preview_url`, `status`).

## Rendering rules

- Text wraps to label width automatically
- For continuous media, the rendered length is `text height + padding`, no fixed length
- For die-cut media, text scales to fit; if text doesn't fit at requested size, return a `400` with a clear message (do not silently shrink)
- Multi-line text respects the alignment setting per line

## "Save as template" affordance

Quick-print page has a `Save as template` button. Captures current quick-print state, prompts for a template name, opens the template editor pre-populated with a single text element matching the quick-print content. From there, the user can add placeholders, QR codes, etc.

## Out of scope (defer to templates)

- Multiple text blocks
- QR codes (you want a template for that)
- Variables / placeholders
- Saving the quick-print itself (use "Save as template")

## Edge cases

- Empty text → 400, "Text is required"
- Text too long for die-cut → 400, "Text exceeds label dimensions at requested font size"
- Selected font not found → 400, "Font {name} not available"
- Selected label media not in catalog → 400, "Unknown label media: {id}"
