---
name: 2026-06-05-catalog-reconcile-on-upgrade
status: completed
created: 2026-06-05
model: sonnet
completed: 2026-06-05
result: >-
  3-way merge at startup (reconcile.py + 13 tests), CATALOG_AUTO_MERGE config toggle,
  POST /api/admin/reload-catalog route, ADR + changelog + doc update; closes #16
---

# Task: Reconcile the shipped `labels.yml` into the operator's copy on upgrade (issue #16)

Closes GitHub issue **#16** ("labels.yml doesn't refresh when upgrading"). Today the
bundled default catalog is copied into `$DATA_DIR/labels.yml` **only on first run**
(`backend/labelforge/main.py:39-44`, `if not yml_path.exists()`). After that, upgrades
never deliver new media or corrected metadata (e.g. fixed `brother_part` SKUs) to an
existing install. We will add a **non-destructive 3-way merge** at startup that updates
the operator's file without clobbering their customizations.

## Before you start

- Read `docs/features/label-catalog.md` (the two-source model: library = physical truth,
  `labels.yml` = UX metadata keyed by `id`), `docs/architecture.md`, and
  `docs/decisions.md`. Load `backend/labelforge/main.py` and
  `backend/labelforge/catalog/loader.py` — the loader already anticipates this work (see
  the `POST /api/admin/reload-catalog` comment near line 49).
- **Source is the bundled image default at `/app/labels.yml`, NOT the internet.** CLAUDE.md
  says "Don't auto-update the label catalog from the internet" — this feature reads only
  the default shipped inside the image, so it does not violate that rule. Call this out in
  the ADR so the distinction is on record.
- Stack is locked: **PyYAML** for the catalog (no `ruamel.yaml` — that would be a stack
  change needing its own ADR). Accept that a PyYAML round-trip drops comments/formatting
  from the operator's file; mitigate with a mandatory backup-before-write (see below).
- Single-user homelab app — no migrations framework, no multi-user concerns.
- Work on `dev`. Conventional-Commits prefixes, no `Co-authored-by:`, docs ship with code.

## Working tree check

Run `git status --porcelain` first. This plan touches `backend/labelforge/main.py`, adds
`backend/labelforge/catalog/reconcile.py` (+ tests), and may add a route + a config field.
A separate CI-fix session may be in flight touching `backend/labelforge/main.py` (import
sort), `.github/workflows/ci.yml`, `CLAUDE.md`, and other `backend/labelforge/` lint fixes
— if `main.py` (or anything you need) shows uncommitted changes, **stop and ask** rather
than risk a conflicting edit. Also note: there's an untracked junk file
`backend/labelforge/routes/template_print.py.tmp.*` — leave it alone (not yours to commit).

## Design (follow this)

### State

- `default_path = /app/labels.yml` — the image's bundled default (read-only truth for "what
  the current release ships").
- `yml_path = $DATA_DIR/labels.yml` — the operator's live file (what `load_catalog` reads).
- `baseline_path = $DATA_DIR/data/labels.default.yml` — **new**: a copy of the bundled
  default as it was the *last time we synced*. This is both the change-detector and the
  "old default" leg of the 3-way merge. Store it under `$DATA_DIR/data/` (alongside
  `app.db`), not at the data-dir root, so it isn't mistaken for an operator file.

### Startup flow (replaces the `if not yml_path.exists()` block in `main.py`)

1. **First run** (`yml_path` missing): copy `default_path` → `yml_path` **and** copy
   `default_path` → `baseline_path`. Done (no merge needed).
2. **No baseline yet but operator file exists** (existing install upgrading *to* this
   feature): we cannot know which fields the operator customized, so do the safe thing —
   **add brand-new entries only** (ids in default but not in the operator file), never
   touch existing entries — then write `baseline_path = copy of default_path`. Log clearly
   that field-level corrections will apply on the *next* default change, not this one.
3. **Baseline exists**: if `default_path` bytes == `baseline_path` bytes → nothing changed,
   no-op. Otherwise run the 3-way merge (below), back up the operator file, write the
   merged result to `yml_path`, then overwrite `baseline_path` with `default_path`.
4. Backup-before-write: before overwriting `yml_path`, copy it to
   `$DATA_DIR/labels.yml.bak` (single rolling backup is fine). Log the path.
5. Wrap the whole reconcile in try/except and log-but-continue on failure — a botched merge
   must never stop the app from starting. On failure, leave the operator file untouched and
   load whatever is currently on disk.

### Merge algorithm — put it in a pure, testable function

Add `backend/labelforge/catalog/reconcile.py` with a **pure** function operating on parsed
data (no file IO), e.g.:

```python
def merge_catalog(operator: dict, old_default: dict, new_default: dict) -> tuple[dict, list[str]]:
    """3-way merge of labels.yml documents keyed by entry id.
    Returns (merged_document, change_log_lines). Operator always wins on conflict."""
```

Rules (entries are `{"labels": [ {id, display_name, ...}, ... ]}`, keyed by `id`):

- **New entry** (id in `new_default`, not in `operator`): add it verbatim. Log `added <id>`.
- **Existing entry** (id in both): copy the operator entry, then for each field present in
  `new_default[id]`:
  - `old = old_default[id].get(field)`, `op = operator[id].get(field)`, `new = new_default[id][field]`.
  - If `op == old` (operator never customized this field relative to baseline) **and**
    `new != op`: take `new`. Log `updated <id>.<field>`.
  - Else (operator customized it, i.e. `op != old`): **keep the operator's value.**
  - Fields the operator added that aren't in the default: keep them untouched.
- **Operator-only entry** (id in `operator`, not in `new_default`): keep as-is. This covers
  custom media the operator added. **Never delete it** — even if it was a default entry that
  a later release removed. Log nothing or `kept custom <id>` at debug.
- Ordering: preserve the operator's existing entry order; append brand-new entries after,
  in `new_default` order. Round-trip with `yaml.safe_dump(..., sort_keys=False, allow_unicode=True)`.

The file-IO wrapper (also in `reconcile.py`) does the hash/bytes compare, backup, dump, and
baseline update, and returns a summary for logging and the reload endpoint.

### Config toggle (operator stays in control)

Add `catalog_auto_merge: bool = True` to `Settings` in `backend/labelforge/config.py`
(env `CATALOG_AUTO_MERGE`). When `False`, skip the write entirely but still **detect and
log** that an updated default is available (and update nothing). Default on; the backup +
operator-wins rules make on-by-default safe.

### Secondary (build only if the core above is clean): reload without restart

Add `POST /api/admin/reload-catalog` (auth-gated, mirror the `Depends(require_auth)` pattern
in `routes/settings.py`; a new `routes/admin.py` is fine — register it in `main.py`). It
re-runs the reconcile + `load_catalog(yml_path)` and returns a JSON summary (counts of
added/updated entries, whether a write happened). Remove the now-satisfied "A future POST
/api/admin/reload-catalog" comment in `loader.py`. If this turns out non-trivial, leave the
comment and note it as deferred in the ADR — do not let it block the core feature.

## Tests (required — merge correctness is the whole point)

Create `backend/tests/test_reconcile.py` (mirror wherever existing pytest tests live; if
there's no `backend/tests/` yet, create it). Cover at minimum:

- default unchanged → no-op, operator file byte-identical.
- new entry in default → added to operator output.
- operator-customized field (op != baseline) → preserved even when default changed it.
- uncustomized field (op == baseline) with changed default → updated to new value
  (this is the `brother_part` SKU-correction case — assert it explicitly).
- operator-only custom entry → preserved.
- default removed an entry → still preserved in operator output (no deletion).
- no-baseline transition → add-new-only, existing entries untouched, baseline then written.

## Conventions to honor

- LF endings only. Comments only for non-obvious *why*. Keep `merge_catalog` pure so the
  tests don't touch the filesystem.
- Changelog: add an entry under `## [Unreleased]` → `### Fixed` (it fixes #16), user-facing:
  upgrades now deliver new/corrected default catalog entries without overwriting operator
  customizations; a `labels.yml.bak` backup is written before any change; opt out with
  `CATALOG_AUTO_MERGE=false`. Mention the container rebuild requirement.
- Update `docs/features/label-catalog.md` with a short "Upgrade reconciliation" section
  describing the 3-way merge, the `$DATA_DIR/data/labels.default.yml` baseline, the `.bak`
  backup, operator-wins semantics, and the no-deletion rule.

## When done

1. Verify: `ruff check . && ruff format --check . && mypy backend && pytest -q` all green
   (the new tests included). Give the one-line "run this to verify".
2. Update this file's frontmatter (`status`, `completed` = 2026-06-05, `result`).
3. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
4. Add an ADR to `docs/decisions.md`: the 3-way-merge-with-baseline approach, why
   operator-wins + never-delete, the PyYAML comment-loss tradeoff (and ruamel deferred), and
   the "bundled default, not internet" distinction vs the no-auto-update rule.
5. Propose ONE commit covering `main.py`, the new `reconcile.py` + tests, the config field,
   the optional route, the changelog, the doc, the ADR, and this prompt move. Present the
   file list and a one-line message; ask
   `commit these as "fix: reconcile default labels.yml into operator copy on upgrade (#16)"? (y/n)`.
   On `y`, stage those specific paths (never `git add -A`) and commit on `dev`. Never push.
   Leave the issue open for the owner to close after verifying on a real upgrade.
