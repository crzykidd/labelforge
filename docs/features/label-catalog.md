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

1. Reconcile `$DATA_DIR/labels.yml` from the bundled default (see "Upgrade reconciliation" below)
2. Load `$DATA_DIR/labels.yml`
3. Validate against schema (Pydantic model); log warnings for malformed entries, skip them
4. Call `brother_ql.labels` for the printable set
5. Build merged catalog in memory; cache for the process lifetime
6. Log: catalog size, count of yml-only (hidden) entries, count of library-only (fallback) entries

Reload via `POST /api/admin/reload-catalog` (auth-gated). No file watcher — restart or reload is fine.

## Upgrade reconciliation

Each image ships a default catalog at `/app/labels.yml`. On startup labelforge performs a
non-destructive **3-way merge** to deliver new and corrected entries from the bundled default
without overwriting operator customizations.

### State files

| Path | Purpose |
|---|---|
| `/app/labels.yml` | Bundled default — read-only truth for what this release ships |
| `$DATA_DIR/labels.yml` | Operator's live file (what the app reads) |
| `$DATA_DIR/data/labels.default.yml` | Baseline — a copy of the default as of the last sync |

### Startup flows

- **First run** (`$DATA_DIR/labels.yml` absent): default is copied to both the operator file and
  the baseline. No merge needed.
- **No baseline** (existing install upgrading to this feature for the first time): brand-new
  entries (ids in default but not in operator file) are appended; existing entries are never
  touched. Baseline is written. Field-level corrections apply on the next default change.
- **Baseline present, default unchanged** (bytes equal): no-op.
- **Baseline present, default changed**: full 3-way merge runs (see below).

A backup is written to `$DATA_DIR/labels.yml.bak` before any write (single rolling copy).

### 3-way merge rules

Entries are keyed by `id`. For each entry:

- **New entry** (id in default, not in operator): added verbatim at the end.
- **Existing entry** (id in both): for each field in the new default —
  - If `operator_value == baseline_value` (never customized) **and** the default changed it:
    take the new value from the default (e.g. a corrected `brother_part` SKU).
  - If `operator_value != baseline_value` (operator customized it): **keep the operator's value.**
  - Fields the operator added that aren't in the default: kept untouched.
- **Operator-only entry** (id not in default): kept as-is. Custom media the operator added is
  **never deleted**, even if a later default release removed the entry.

Ordering: operator's existing entries in their original order, new default entries appended after.

### Operator controls

- `CATALOG_AUTO_MERGE=false` — disable writes entirely. Startup still detects and logs when an
  updated default is available, but the operator file is never touched.

### Notes

- PyYAML is used for the round-trip. YAML comments and non-standard formatting in the operator
  file are lost when a write occurs (the backup preserves the original). `ruamel.yaml`
  (comment-preserving) was deferred; see ADR 2026-06-05.
- The source for reconciliation is always the bundled image default, **never the internet**.
  This does not violate the "no auto-update from the internet" rule.

## API

- `GET /api/labels` — full merged catalog
- `GET /api/labels/{id}` — single entry
- `POST /api/admin/reload-catalog` — reload from disk (requires API token)

## UI behavior

- Label picker dropdown groups by `category` (`Continuous`, `Die-cut`, `Round`)
- Within a category, entries are sorted by `display_name`
- Color-capable labels show a small red/black indicator
- Media the configured printer can't print (`supported = false`, see "Printer compatibility") stays visible in its group but is rendered as a **disabled, greyed `<option>`** with a `— unavailable` marker and a `title` tooltip carrying the `incompatible_reason`. The browser won't let a user pick a disabled option; selectors also guard programmatic default/restored selections, falling back to the first supported entry.

### Loaded-media filter

Every label-media selector exposes a **Show all / Loaded in printer** mode toggle (implemented as `mountLabelMediaSelect` in `frontend/src/labels.ts`, shared by all selectors). **Show all** (default) lists the complete catalog as described above. **Loaded in printer** calls `GET /api/printer/status` once on first use and narrows options to entries whose `tape_size` matches the loaded roll's `width_mm` and `length_mm` — this naturally groups the mono and two-color variants of a roll (e.g. `62` and `62red` both have `tape_size [62, 0]`) and excludes die-cuts of the same nominal width (`62x29` has `tape_size [62, 29]`).

Edge cases in Loaded mode:
- Printer unreachable (503) → notice "Couldn't reach printer — showing all"; toggle reverts to Show all.
- Printer connected but no media reported → notice "Printer reports no media loaded"; toggle reverts to Show all.
- Loaded media not found in catalog → notice "Loaded media not in catalog — showing all"; full list is shown with the toggle in Loaded position.
- Printer status is fetched once per control mount and cached — the control does not poll.

## Defaults shipped in repo

The repo ships a `labels.yml` covering the common DK-* media that match the QL-820NWB's supported list:

- `12`, `29`, `38`, `50`, `54`, `62` (continuous, mono)
- `62red` (continuous, red+black) — the QL-820NWB headline feature
- `17x54`, `17x87`, `29x90`, `38x90`, `52x29`, `62x29`, `62x100` (common die-cuts)
- `d24` (round)

Other media supported by the library but not in the default yml appear as fallback entries with raw identifiers. Community PRs adding entries are welcome.
