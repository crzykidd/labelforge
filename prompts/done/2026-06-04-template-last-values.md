---
name: 2026-06-04-template-last-values
status: completed
created: 2026-06-04
model: sonnet
completed: 2026-06-04
result: Added Load previous values button to recall form backed by print history; retention now preserves latest job per template
---

# Task: "Load previous values" on template recall, backed by retained print history

When recalling a template to print, the user wants to optionally reload the field values they
last printed, to make quick changes. We already store every print's `field_values` in the
`print_jobs` history table — so this is a query + a button, plus a prune tweak so the latest
values are never pruned away.

Two parts:
1. A **"Load previous values"** button on the recall form that, if a prior print of this
   template exists, fills the inputs with those values. Form still opens with field defaults
   (current behavior) — loading previous values is an explicit, opt-in action.
2. **Prune always keeps the most recent job per template**, so "previous values" survive
   retention pruning.

## Before you start

- Read `docs/features/history.md` (retention/pruning), `docs/features/templates.md` (recall
  flow), and `docs/features/settings.md` (retention settings). Skim `docs/decisions.md`.
- Data already exists: `print_jobs(template_id, field_values JSON, created_at, pinned, ...)` —
  schema in `backend/labelforge/db.py:5`; writes in `backend/labelforge/history.py:15`
  (`insert_job_with_preview`, stores `field_values` as JSON). "Last values" = the newest
  `print_jobs` row for a `template_id`. **No new table or column is needed.**
- `code-checkin-and-pr`: work on `dev`, Conventional-Commits prefixes, no `Co-authored-by:`,
  docs ship with code, changelog entry required.

## Working tree check

Run `git status --porcelain` first; if any file this plan touches has uncommitted changes, list
them and ask before editing. This prompt file is exempt.

## Key files

- `backend/labelforge/history.py` — add the latest-values query; modify `prune_history` (line ~71)
- `backend/labelforge/routes/templates.py` — add `GET /api/templates/{name}/last-values`
- `backend/labelforge/db.py` — schema reference only (no migration needed)
- `frontend/src/api.ts` — add `getLastValues(name)`
- `frontend/src/pages/template-recall.ts` — render + wire the button (form, `fieldInput`,
  `collectFields`, `updateButtons`, `runPreview`)
- `frontend/src/types.ts` — response type if you add one

## What to do

### Part 1 — Last-values endpoint

1. In `history.py`, add `get_latest_field_values(template_name: str) -> dict | None`: select the
   newest non-null `field_values` for that template —
   `SELECT field_values FROM print_jobs WHERE template_id = ? AND field_values IS NOT NULL
   ORDER BY created_at DESC, id DESC LIMIT 1` — and `json.loads` it (return `None` if no row).
2. In `routes/templates.py`, add `GET /api/templates/{name}/last-values` (auth like the other
   template routes). 404 if the template doesn't exist; otherwise return
   `{"values": <dict> | null, "printed_at": <iso> | null}` (include the row's `created_at` as
   `printed_at` so the UI can label the button, e.g. "Load previous (Jun 3, 2:14 PM)"). Keep it
   simple if surfacing the timestamp adds much code — `{"values": ... }` alone is acceptable.

### Part 2 — Recall UI: "Load previous values" button

1. In `template-recall.ts`, fetch last-values alongside `getTemplate` (parallelize). Keep the
   form opening with field **defaults** as today.
2. Render a **"Load previous values"** button in the form actions (next to Preview/Print), only
   when the template has fields. Disable it (or hide it) when no previous values exist.
3. On click, fill each input/select from the previous values for fields that **still exist** in
   the current `field_schema` (ignore stale keys; leave fields with no stored value at their
   default). Then call `updateButtons()` and, if the preview pane is open, `runPreview()`.
4. Respect existing behavior: required-field validation, batch increment, and live debounced
   preview must keep working after values are loaded.

### Part 3 — Prune keeps the latest job per template

1. In `prune_history` (`history.py`), exclude the newest job of each template from deletion in
   **both** the `last_n` and `last_days` branches. Add to each delete-candidate query:
   `AND id NOT IN (SELECT MAX(id) FROM print_jobs WHERE template_id IS NOT NULL GROUP BY template_id)`.
   (`MAX(id)` = newest per template since id is monotonic; quick-print rows have `template_id`
   NULL and are not protected — that's fine, they have no recall form.)
2. This guarantee is bounded by the number of templates (single-user, small), so it doesn't
   meaningfully undermine "keep last N". Note the behavior in `docs/features/history.md` and
   `docs/features/settings.md` (retention): *the most recent print of each template is always
   kept, to back template recall.* Pinned rows are still always kept.

Acceptance:
- Print a template with values, go to its recall page → "Load previous values" is enabled;
  clicking it fills the last-printed values; Preview/Print still work.
- A template never printed → button disabled/hidden, form shows defaults.
- With retention `last_n = 1`, print template A, then print 5 quick labels → A's last values are
  still loadable (its latest job survived pruning).

## Conventions to honor

- Commits: `feat:` for the endpoint+UI; the prune change can ride in the same commit or a small
  `feat:`/`fix:` of its own — keep docs with the code. Changelog `[Unreleased]` → Added (Load
  previous values) and Changed (retention keeps latest per template). Note the container rebuild
  for the frontend change.
- Match existing vanilla-TS style (`esc()`, plain DOM, `CSS.escape` for selectors) and Python
  style (type hints, parameterized SQL, terse "why" comments).

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the decision in `docs/decisions.md`: template recall pre-fill is derived from print
   history (no new storage), and retention now always preserves the latest job per template.
4. Propose commit(s). Present the file list + one-line message(s); ask
   `commit these as "<message>"? (y/n)`. On `y`, stage those specific paths and commit on `dev`.
   Never `git add -A`. Never push.
