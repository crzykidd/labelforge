# Feature: Label Catalog

## Goal

Present the user with a friendly, well-organized list of label media to pick from, while remaining authoritative about what can actually be printed.

## Model

Two sources, merged at runtime:

1. **Library (truth)**: `brother_ql.info.labels()` returns the set of identifiers the library can print on, with raw dimensions and type (continuous / die-cut / round). This is the source of truth for *what can be printed*.

2. **`labels.yml` (UX)**: A user-editable YAML file shipped in the repo and mounted as a volume. Provides friendly names, descriptions, categories, Brother DK part numbers, color capability, and other metadata. Each entry maps to a library identifier.

### Merge rule

The user-facing catalog is the intersection of identifiers:

- In **both** library and yml → full entry: library dimensions + yml metadata
- In library, **not** in yml → fallback entry: library dimensions + raw identifier as display name
- In yml, **not** in library → **hidden**. (Log a warning at startup so the user knows their yml has stale entries.)

This means: the user can never pick a label that won't print. The yml can have outdated entries without breaking the app.

## `labels.yml` schema

```yaml
# Each entry maps to a brother_ql library identifier.
# Required: id, display_name
# Everything else is optional.

labels:
  - id: "62"
    display_name: "62mm Continuous (Black)"
    brother_part: "DK-22205"
    description: "General-purpose paper tape, black on white."
    category: continuous
    color_capable: false
    common_use:
      - "address labels"
      - "file folders"
      - "spool labels"

  - id: "62red"
    display_name: "62mm Continuous (Black + Red)"
    brother_part: "DK-22251"
    description: "Two-color paper tape. Requires QL-800 series printer."
    category: continuous
    color_capable: true
    printer_requirements:
      - "QL-800"
      - "QL-810W"
      - "QL-820NWB"

  - id: "29x90"
    display_name: "29mm × 90mm Address Label"
    brother_part: "DK-11201"
    description: "Standard address label, die-cut."
    category: die-cut
    color_capable: false
    common_use:
      - "address"
      - "file folder"
      - "spool"

  - id: "62x100"
    display_name: "62mm × 100mm Shipping Label"
    brother_part: "DK-11202"
    description: "Larger die-cut, good for shipping or product labels."
    category: die-cut
    color_capable: false

  - id: "d24"
    display_name: "24mm Round"
    brother_part: "DK-11218"
    description: "Round die-cut, 24mm diameter."
    category: round
    color_capable: false
```

### Field reference

| Field | Required | Description |
|---|---|---|
| `id` | yes | Library identifier (`62`, `62red`, `29x90`, ...) |
| `display_name` | yes | Human-readable name shown in dropdowns |
| `brother_part` | no | Brother DK part number (display only) |
| `description` | no | Long description, shown on hover or in selector |
| `category` | no | `continuous` / `die-cut` / `round` — drives grouping in the picker |
| `color_capable` | no | bool — drives a UI hint when red elements are used |
| `printer_requirements` | no | list of QL models that support this media — drives a warning if a different printer is configured |
| `common_use` | no | list of tags, used to surface "Recommended for X" hints in the template-create flow |
| `preview_image` | no | filename relative to `/var/docker/labelforge/label-previews/` |

Unknown fields in `labels.yml` are ignored (forward-compatible).

## Loading

At startup:

1. Load `labels.yml` from `/var/docker/labelforge/labels.yml`
2. If missing, copy the default shipped at `/app/labels.yml` (image asset) to the volume on first run
3. Validate against schema (Pydantic model); log warnings for malformed entries, skip them
4. Call `brother_ql.labels` for the printable set
5. Build merged catalog in memory; cache for the process lifetime
6. Log: catalog size, count of yml-only (hidden) entries, count of library-only (fallback) entries

Reload on `SIGHUP` or via an admin endpoint (`POST /api/admin/reload-catalog`). No file watcher in v1 — restart or reload is fine.

## API

- `GET /api/labels` — full merged catalog
- `GET /api/labels/{id}` — single entry
- `POST /api/admin/reload-catalog` — reload from disk (requires API token)

## UI behavior

- Label picker dropdown groups by `category` (`Continuous`, `Die-cut`, `Round`)
- Within a category, entries are sorted by `display_name`
- Color-capable labels show a small red/black indicator
- When the configured printer doesn't match `printer_requirements`, the entry is shown but disabled with a tooltip

## Defaults shipped in repo

The repo ships a `labels.yml` covering the common DK-* media that match the QL-820NWB's supported list:

- `12`, `29`, `38`, `50`, `54`, `62` (continuous, mono)
- `62red` (continuous, red+black) — the QL-820NWB headline feature
- `17x54`, `17x87`, `29x90`, `38x90`, `52x29`, `62x29`, `62x100` (common die-cuts)
- `d24` (round)

Other media supported by the library but not in the default yml appear as fallback entries with raw identifiers. Community PRs adding entries are welcome.
