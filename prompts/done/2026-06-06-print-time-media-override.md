---
name: 2026-06-06-print-time-media-override
status: completed
created: 2026-06-06
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-06-06
result: Print-time media override: recall page media selector, mono+red notice, overflow warning, reprint binds to history row media; 8 new backend tests; all green.
---

# Task: Print a template on a different label media at print time

Let the user choose a **different label media when printing a template** (one-off, the
template's stored media is never mutated). Covers the real case: a design saved on `62red`
(62mm two-color continuous) that the user also wants to print on `62x29` (DK-1209, 62mm
die-cut). When the chosen media is mono and the template uses red, red prints as black —
surface that. When the chosen media is smaller and content overflows, warn but allow.
Changing the media forces a fresh preview so the user can see whether it fits.

This **overturns a documented design rule** — the glossary currently says *"a template
belongs to exactly one label media (a 62mm Spool template cannot be printed on a 29×90
die-cut)."* Updating that rule + an ADR is part of this task.

## Before you start

- Read `docs/features/templates.md` (recall/print + "Save As" sections), `docs/glossary.md`
  (Template / Label media entries — the rule you're changing), `docs/features/label-catalog.md`,
  and `docs/decisions.md` (newest ADRs).
- Load these implementation anchors:
  - `backend/labelforge/render/template.py` — `render_template(template, values)` reads
    `template.label_media`. Note `_canvas_color_to_l` already maps **any non-white color
    (incl. red) → 0 (black)**, so mono rendering of a red template already prints red as
    black. No renderer recolor work is needed for "print in black."
  - `backend/labelforge/routes/template_print.py` — `print_template` / `preview_template`
    (+ batch); uses `tmpl.label_media` for render, the `media_compatible` status check, and
    history logging.
  - `backend/labelforge/routes/history.py` — `_reprint_template` (see the reprint fix below).
  - `backend/labelforge/models/__init__.py` — `PrintRequest` (`fields`), `BatchPrintRequest`.
  - `frontend/src/labels.ts` — **reusable** label-media selector with the "Show all / Loaded
    in printer" toggle and `matchesLoadedMedia()`. **Reuse it** on recall; do not build a new
    one.
  - `frontend/src/pages/template-recall.ts` — the recall page (read-only `Media:` badge at
    ~line 68; preview wiring `runPreview`/debounce ~line 167+).
- One-off only (per owner): the choice applies to this print/preview; the stored template is
  untouched. History captures the actual media, and reprint reproduces it (below) — that's
  the "recall from history" path. Do **not** add a "save this media to the template" affordance
  (Save As already covers persistent retargeting).
- Ships **before** the 0.1.0 release — `/release-prep` waits for this. Work on `dev`.

## Working tree check

`git status --porcelain` first. This touches `render/template.py`, `routes/template_print.py`,
`routes/history.py`, `models/__init__.py`, `frontend/src/pages/template-recall.ts`,
`frontend/src/labels.ts` (and maybe `api.ts`/`types.ts`), plus docs. If any show unexpected
uncommitted changes, list them and ask.

## What to do — backend

1. **Models**: add `label_media: str | None = None` to `PrintRequest` and
   `BatchPrintRequest`. `None` = use the template's stored media (unchanged behavior).

2. **Renderer**: give `render_template` an effective-media override. Recommended signature:
   `render_template(template, values, *, media_override: str | None = None)`. Internally
   resolve `effective_media = media_override or template.label_media` and `get_label(...)`
   on that. Everything downstream (canvas width, continuous-vs-die-cut, `two_color`) keys off
   the resolved label, **not** `template.label_media`. Keep the default-None path byte-for-byte
   equivalent to today.

3. **Print / preview / batch routes** (`template_print.py`): when `body.label_media` is set:
   - Validate it's a real, **supported** catalog entry (`get_label` non-None and
     `.supported`); 400 otherwise.
   - Render with `media_override=body.label_media`.
   - Run the existing printer `media_compatible` status check against the **chosen** media,
     not `tmpl.label_media` (same 409 + `override=true` escape hatch as today).
   - Log history with the chosen media as `label_media` (so the row reflects what was printed).
   - The print JSON response already returns `label_media` — make sure it returns the chosen one.

4. **Overflow detection (warn, never block)**: for a **die-cut** effective media, detect when
   rendered content extends beyond the label's printable height (compare the content's
   bottommost extent to `label.dots_printable[1]`). Surface it without blocking:
   - `preview_template` returns an image `Response` — add a response header
     `X-Label-Overflow: true` when content overflows (the recall UI reads it).
   - `print_template` (JSON) — add `"overflow": true/false` to the response body.
   Continuous media never overflows (length is content-driven). Do not raise; printing still
   proceeds — the user decides from the preview.

5. **Reprint honors historical media** (`history.py` `_reprint_template`): it currently renders
   with `tmpl.label_media`. Change it to render on the **row's** media:
   `render_template(tmpl, field_values, media_override=row["label_media"])`, and keep the
   existing "label media no longer in catalog" guard pointed at `row["label_media"]`. This is
   what makes a one-off media print reproducible from history (the owner's "recall in history"
   path). Mono+red reprints naturally re-derive red→black via the renderer.

## What to do — frontend (recall page)

6. **Media selector** replacing the read-only badge: render the reusable selector from
   `labels.ts`, defaulting to the template's media. Address the owner's "the full list is
   overwhelming" concern:
   - **Group/sort same-width-as-template first** (compare `tape_size[0]`), e.g. an optgroup
     "Same width (62mm)" above an "Other media" group, so the relevant rows are at the top.
   - Keep the existing **"Loaded in printer"** toggle (queries `GET /api/printer/status` once,
     narrows to the mounted roll via `matchesLoadedMedia`) — this is the fastest path to "what's
     actually in the printer right now."
   - Only list `supported` media.

7. **Force preview on media change**: when the selected media changes, immediately run the
   preview and reveal the preview area. Gate the **Print** button so it can't fire on a media
   the user hasn't previewed since changing it (e.g. mark preview stale on change; require a
   fresh preview first). Pass `label_media` in the preview/print/batch API calls.

8. **Mono + red notice**: if the selected media is mono (`color === 0`) and the template
   contains any red element (scan `canvas_json` objects for a red `fill`/`stroke` —
   `#ff0000`/`#f00`/`red`/`rgb(255,0,0)`; a small helper mirroring the backend's red set is
   fine), show an inline notice: *"This label is black-only — red elements will print in
   black."* The forced preview already shows this (renderer maps red→black on mono). No toggle
   needed; proceeding is printing in black.

9. **Overflow warning**: when preview returns `X-Label-Overflow: true`, show an inline
   *"Content may be clipped — it's taller than this label"* warning near the preview. Still
   allow Print.

10. **Batch parity**: pass the chosen `label_media` through the batch path too, so increment
    prints honor the override.

## Conventions to honor

- LF endings. Match existing recall-page style; reuse `labels.ts` rather than duplicating
  selector logic. Comments only for non-obvious *why*.
- **Docs (ship with the code):**
  - `docs/glossary.md` — revise the Template entry: a template has a *default/home* media but
    can be printed on another compatible media at print time (one-off); the stored media is
    unchanged. Fix the "cannot be printed on a 29×90 die-cut" line.
  - `docs/features/templates.md` — document the recall media selector, the mono+red notice,
    the overflow warning, and that one-off media is captured in history + reproduced on reprint.
- **Changelog**: `### Added` under `## [Unreleased]` — print a template on a different label
  media at recall time (one-off); same-width media surfaced first + "Loaded in printer" filter;
  mono+red prints in black with a notice; smaller media warns about clipping but still prints;
  the choice is logged to history and honored on reprint. Note the container-rebuild requirement.

## When done

1. Verify green: `ruff check . && ruff format --check . && mypy backend && pytest -q`; add a
   backend test for the override (render on a non-stored media; reprint uses `row.label_media`;
   overflow flag on a die-cut). Build the frontend (`npm run build`) so the recall changes
   compile. Manually confirm: pick `62x29` on a `62red` template → forced preview + clip
   warning; pick a mono `62` → red-as-black notice. Give the one-line "run this to verify".
2. Update this file's frontmatter (`status`, `completed` = 2026-06-06, `result`).
3. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
4. **ADR in `docs/decisions.md`**: print-time media override — one-off (non-persistent),
   warn-but-allow on die-cut overflow, red→black automatic on mono (no toggle), reprint binds
   to the historical media. Record that this supersedes the glossary "one template = one media"
   rule, and why (same physical width makes a design portable across length/geometry; the user
   physically swaps rolls and the pre-print media check + override already guard mismatches).
5. Propose ONE commit covering backend, frontend, docs, changelog, ADR, tests, and this prompt
   move. Present the file list and a one-line message; ask
   `commit these as "feat: print a template on a different label media at print time"? (y/n)`.
   On `y`, stage those specific paths (never `git add -A`) and commit on `dev`. Never push.
