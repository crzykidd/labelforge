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
| `printer_requirements` | no | **Deprecated and ignored.** Printer compatibility is now library-derived (see below), not declared per-entry. Remove it from entries; it has no effect. |
| `common_use` | no | list of tags, used to surface "Recommended for X" hints in the template-create flow |
| `preview_image` | no | filename relative to `/var/docker/labelforge/label-previews/` |

Unknown fields in `labels.yml` are ignored (forward-compatible).

## Printer compatibility

Whether a given media can actually be printed depends on the **configured printer** (`PRINTER_MODEL`, default `QL-820NWB`), not on `labels.yml`. Compatibility is therefore **derived from the `brother_ql` library**, the same source of truth as the printable list — never hand-maintained. (This is why the old `printer_requirements` yml field is deprecated: a hand-kept printer list drifts from the library and can't know two-color capability.)

Each catalog entry gets two extra library-derived fields plus the computed result:

| Field | Source | Meaning |
|---|---|---|
| `restricted_to_models` | `brother_ql` `Label.restricted_to_models` | Models this media is restricted to. Empty = works on all models. Populated only for the six wide-format rolls, all restricted to the QL-1xxx series. |
| `color` | `brother_ql` `Label.color` | `1` = two-color media (e.g. `62red`), `0` = mono. |
| `supported` | computed | Whether the configured printer can print this media. |
| `incompatible_reason` | computed | Human-readable reason shown as a tooltip when `supported` is false. |

The rule, computed once at catalog load against the configured printer's `Model` (looked up by `identifier` in `brother_ql.models.ALL_MODELS`, whose `two_color: bool` flags the QL-800 series):

```python
supported = (not label.restricted_to_models or printer_model in label.restricted_to_models) \
            and (label.color == 0 or model.two_color)
```

- Restricted to other models → `incompatible_reason = "Requires a wide-format printer (QL-1100 series)"`.
- Two-color media on a mono printer → `incompatible_reason = "Requires a two-color printer (QL-800 series)"`.
- If `PRINTER_MODEL` is not found in the library, a warning is logged and **all** media are treated as supported (don't wrongly disable everything).

On the default `QL-820NWB`: the six wide rolls (`102`, `103`, `104`, `102x51`, `102x152`, `103x164`) → `supported = false`; everything else including `62red` → `supported = true`.

> Computed at load because `PRINTER_MODEL` is fixed in config. A future `POST /api/admin/reload-catalog` recomputes it. `brother_ql`'s `Label.works_with_model()` is **not** used — it's broken in the pinned fork (raises `NameError` on restricted labels and ignores two-color). See `docs/decisions.md`.

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
- Media the configured printer can't print (`supported = false`, see "Printer compatibility") stays visible in its group but is rendered as a **disabled, greyed `<option>`** with a `— unavailable` marker and a `title` tooltip carrying the `incompatible_reason`. The browser won't let a user pick a disabled option; selectors also guard programmatic default/restored selections, falling back to the first supported entry.

## Defaults shipped in repo

The repo ships a `labels.yml` covering the common DK-* media that match the QL-820NWB's supported list:

- `12`, `29`, `38`, `50`, `54`, `62` (continuous, mono)
- `62red` (continuous, red+black) — the QL-820NWB headline feature
- `17x54`, `17x87`, `29x90`, `38x90`, `52x29`, `62x29`, `62x100` (common die-cuts)
- `d24` (round)

Other media supported by the library but not in the default yml appear as fallback entries with raw identifiers. Community PRs adding entries are welcome.
