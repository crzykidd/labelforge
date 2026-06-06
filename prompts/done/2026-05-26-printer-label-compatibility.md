---
name: 2026-05-26-printer-label-compatibility
status: completed
created: 2026-05-26
completed: 2026-05-26
result: Catalog now computes a library-derived `supported` flag per label against the configured printer; selectors disable+grey unsupported media with a tooltip; `printer_requirements` removed. Verified against the installed library (QL-820NWB disables the 6 wide rolls, keeps 62red; QL-700 disables 62red; QL-1100 enables wide). ADR added.
---

# Task: derive label↔printer compatibility from the library and disable incompatible media in the pickers

Read `CLAUDE.md` first. Load `docs/features/label-catalog.md`, `docs/architecture.md`, `docs/glossary.md`, and `docs/features/settings.md`. Work on `dev`, commit don't push, no co-author tags.

## Goal

The label catalog currently lists every label the `brother_ql` library knows about, regardless of whether the configured printer can print it. On the configured QL-820NWB the picker shows 6 wide-format media it physically cannot print. Make the catalog **printer-aware**: each label gets a `supported` flag computed against the configured printer, and the selectors show unsupported media **disabled + greyed with a tooltip** (this is already specified in `docs/features/label-catalog.md` under "UI behavior").

## Decisions already made (do not relitigate)

- **Compatibility is library-derived**, not hand-maintained in `labels.yml`. This is consistent with the ADR "Label catalog: library truth + yml UX layer." Do NOT add a `compatible_printers`/printer array to `labels.yml`.
- **The `printer_requirements` yml field is deprecated** and replaced by this. Remove it (see below).
- Picker behavior for incompatible media: **disable + tooltip** (keep it visible in its group, do not hide).
- **Do NOT use `Label.works_with_model()`** — it is broken in the pinned library (`brother-ql-inventree>=1.3`): it raises `NameError: name 'models' is not defined` (`brother_ql/labels.py:67`) for any restricted label, and it ignores two-color capability (returns `True` for `62red` on a mono `QL-700`). Compute compatibility from primitive fields instead.

## The compatibility rule (verified against the installed library)

```python
supported = (not label.restricted_to_models or printer_model in label.restricted_to_models) \
            and (label.color == 0 or model.two_color)
```

Verified library facts (`brother_ql` from `brother-ql-inventree>=1.3`):

- `Label.restricted_to_models: list[str]` — empty = works on all models. Populated only for these 6 wide-format labels, all restricted to the QL-1xxx series (`QL-1050`, `QL-1060N`, `QL-1100`, `QL-1110NWB`, `QL-1115NWB`):
  `102`, `103` (→ only `QL-1100`/`QL-1110NWB`), `104`, `102x51`, `102x152`, `103x164` (→ only `QL-1100`/`QL-1110NWB`).
- `Label.color: int` — `1` for two-color (`62red`), `0` for mono.
- `Model.two_color: bool` — from `brother_ql.models.ALL_MODELS`. `True` for the 800-series (`QL-800`, `QL-810W`, `QL-820NWB`); `False` otherwise.

**Expected result for the default `printer_model="QL-820NWB"`:** the 6 wide labels above → `supported=False`; everything else (incl. `62red`) → `supported=True`.

## Current state / where things live

- `backend/labelforge/config.py:9` — `printer_model: str = "QL-820NWB"` (from `.env`). Already exists; the catalog must use it.
- `backend/labelforge/catalog/loader.py` — `load_catalog()` iterates `ALL_LABELS` and builds `LabelEntry` per id. This is where to read `restricted_to_models` + `color` and compute `supported`. Loaded once at startup; `printer_model` is fixed in config, so compute at load time. (A future `POST /api/admin/reload-catalog` should recompute — fine to leave a note.)
- `backend/labelforge/models/__init__.py` — `LabelEntry` Pydantic model. Currently has `printer_requirements: list[str]` (to be removed).
- `frontend/src/types.ts` — `LabelEntry` TS interface (mirror the model).
- `frontend/src/labels.ts` — `buildLabelOptionsHtml(labels)` is the SINGLE place that renders `<option>` markup; both selectors use it. Add the disabled/tooltip rendering here.
- Selectors that call the helper: `frontend/src/pages/quick-print.ts` and `frontend/src/pages/templates-list.ts` (new-template modal). The template editor has no media selector.

## Implementation

### Backend
1. In `loader.py`, build a model lookup once: `from brother_ql.models import ALL_MODELS`; find the `Model` whose `identifier == config.settings.printer_model`.
   - **If the configured model is not found** in `ALL_MODELS`: log a warning and treat **all** labels as supported (don't wrongly disable everything). Capture `two_color = found_model.two_color if found else None`, and when `None` skip the color check.
2. For each library label, read `restricted_to_models` (coerce to `list[str]`) and `color` (int). Compute `supported` per the rule above.
3. Compute `incompatible_reason: str | None` for unsupported entries:
   - restricted and printer not in it → `"Requires a wide-format printer (QL-1100 series)"`.
   - two-color label on a mono printer → `"Requires a two-color printer (QL-800 series)"`.
4. Add to `LabelEntry`: `restricted_to_models: list[str] = []`, `color: int = 0`, `supported: bool = True`, `incompatible_reason: str | None = None`. **Remove** `printer_requirements`.

### Frontend
5. `types.ts`: mirror the model — add `restricted_to_models`, `color`, `supported`, `incompatible_reason`; remove `printer_requirements`.
6. `labels.ts`: in `buildLabelOptionsHtml`, render unsupported entries as `<option ... disabled title="${esc(incompatible_reason)}">`. Keep them in their form-factor group. Consider a trailing marker (e.g. ` — unavailable`) in the option text for clarity.
7. Default-selection guard: in `quick-print.ts` and `templates-list.ts`, when applying the default/restored `label_media`, if that id is unsupported fall back to the first supported entry. (A small `firstSupportedId(labels)` helper in `labels.ts` is reasonable.) Browsers won't let a user pick a `disabled` option, but a programmatic `.value` set can still land on one — guard it.

### Data / docs
8. `labels.yml`: remove the now-dead `printer_requirements:` block from the `62red` entry.
9. `docs/features/label-catalog.md`: replace the `printer_requirements` row/explanation with the library-derived model (`restricted_to_models` + `color`/`two_color` vs configured `printer_model`); note `printer_requirements` is deprecated/ignored.
10. `CHANGELOG.md` `## [Unreleased]`: concise user-facing entry.
11. `docs/decisions.md`: add an ADR (newest at top) — library-derived compatibility computed at catalog load against the configured printer; `works_with_model()` rejected as buggy (cite the `NameError` and the ignored two-color); `printer_requirements` deprecated. Consider noting the upstream bug could be reported to `inventree/brother_ql`.

## Verification

- Backend: load the catalog with `printer_model="QL-820NWB"` and assert `102`/`102x51`/`103x164` → `supported=False`, `62`/`62red`/`62x100` → `supported=True`; with `printer_model="QL-700"` assert `62red` → `supported=False`; with `printer_model="QL-1100"` assert `102` → `supported=True`. (A quick pytest or a throwaway script is fine.)
- Frontend: `cd frontend && npx tsc --noEmit && npm run build` must pass.
- Visual: `npm run dev` → quick-print and "New template" → the 6 wide media are greyed with a tooltip; `62red` is selectable.

## Last steps (required)

- Commit to `dev` with a descriptive message (imperative, no co-author tag).
- Update THIS file's frontmatter: set `status` (`completed`/`failed`), `completed:` date, and a one-line `result:`.
- If any non-obvious decision/workaround came up beyond what's above, add it to `docs/decisions.md` as an ADR.
