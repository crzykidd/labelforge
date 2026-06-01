---
name: 2026-05-25-template-recall-ui
status: completed
created: 2026-05-25
completed: 2026-05-25
result: Recall page at /templates/:name/print — auto-generated field form, debounced live preview, single + batch print with client-side increment matching backend advance(); Print button added to templates list; printTemplate/batchPrint API added. Build + typecheck pass. (Side cleanup: untracked compiled src .js artifacts, see ADR 2026-05-25.)
---

# Template Recall UI

Build the frontend "recall" flow: pick a template, fill variable fields, preview, print, and batch print. The backend is done — this is frontend-only work.

## Context

Read these before starting:
- `CLAUDE.md` — project rules, session workflow, stack
- `docs/features/templates.md` — the "Recall (print from template)" section is the spec
- `docs/glossary.md` — vocabulary

The app is a Vite + TypeScript SPA (no React/Vue). Pages are plain functions that receive a root `HTMLElement` and render into it with innerHTML + event listeners. See `frontend/src/pages/templates-list.ts` and `frontend/src/pages/quick-print.ts` as patterns.

## What exists already

**Backend endpoints (all working, all require Bearer auth):**
- `POST /api/print/{name}` — body: `{ "fields": { "key": "value" } }` → prints one label
- `POST /api/print/{name}/batch` — body: `{ "labels": [{ "key": "value" }, ...] }` → prints N labels with per-label field values
- `POST /api/preview/{name}` — body: `{ "fields": { "key": "value" } }` → returns PNG blob

**Frontend API client (`frontend/src/api.ts`):**
- `previewTemplate(name, fields)` — already exists, returns `Promise<Blob>`
- `printTemplate` — DOES NOT EXIST, needs to be added
- `batchPrint` — DOES NOT EXIST, needs to be added
- All other CRUD functions exist (`listTemplates`, `getTemplate`, etc.)

**Types (`frontend/src/types.ts`):**
- `Template` — has `field_schema: FieldSpec[]`
- `FieldSpec` — `{ name, type, required, default, increment, enum_values }`
- `PrintJobResponse` — `{ job_id, status, preview_url }`

**Routing (`frontend/src/router.ts`):**
- `register(path, mountFn)` — exact path match
- `registerPrefix(prefix, mountFn)` — prefix match (first match wins)
- `navigate(path)` — client-side navigation
- Currently registered in `main.ts`:
  - `/` → quick-print
  - `/templates` → templates list
  - `/templates/` prefix → template editor

**Templates list (`frontend/src/pages/templates-list.ts`):**
- Each row has Edit and Delete buttons. Needs a **Print** button added that navigates to the recall page.

## What to build

### 1. Add API client functions

In `frontend/src/api.ts`, add:

```typescript
function printTemplate(name: string, fields: Record<string, string>): Promise<PrintJobResponse> {
  return apiFetch<PrintJobResponse>(`/api/print/${encodeURIComponent(name)}`, {
    method: 'POST',
    body: JSON.stringify({ fields }),
  })
}
```

And a `batchPrint` function that calls `POST /api/print/{name}/batch` with `{ labels: [...] }` and returns `Promise<BatchPrintResponse>`. Add `BatchJobResult` and `BatchPrintResponse` types to `types.ts`:

```typescript
interface BatchJobResult {
  job_id: number;
  status: string;
}

interface BatchPrintResponse {
  batch_id: string;
  jobs: BatchJobResult[];
  succeeded: number;
  failed: number;
}
```

Export both new API functions.

### 2. Create the recall page

New file: `frontend/src/pages/template-recall.ts`

Export `mountTemplateRecall(root: HTMLElement): void`

**Behavior:**

1. Extract template name from URL path (`/templates/:name/print` → name)
2. Fetch the template via `getTemplate(name)`
3. If template has no `field_schema` (no variable fields), show a simple "Preview / Print" UI with no form
4. If template has fields, auto-generate a form:
   - One input per field in `field_schema`
   - Text input for `type: "text"` and `type: "number"` and `type: "date"`
   - `<select>` for `type: "enum"` populated from `enum_values`
   - Pre-fill with `default` value if set
   - Mark required fields (HTML `required` attribute + visual indicator)
   - Client-side validation: all required fields must be non-empty before Print is enabled
5. **Preview button**: collect field values from the form, call `previewTemplate(name, fields)`, display the returned PNG below the form. Preview should update live as fields change (debounced, ~500ms after last keystroke).
6. **Print button**: collect field values, call `printTemplate(name, fields)`, show success/error status message
7. **Batch section**: if ANY field in `field_schema` has `increment: true`:
   - Show a "Batch" toggle/checkbox
   - When enabled, show a "Count" number input (default 1, min 1, max 1000)
   - Show which fields will increment (read-only info)
   - Print button in batch mode calls `batchPrint` — construct the `labels` array by advancing increment fields using the same logic as the backend (`advance()` in `fields.py`): increment trailing digits, preserve zero-padding
   - Show batch result summary (succeeded/failed counts)
8. **Back link**: navigate to `/templates`
9. **Header**: show template display_name, label media

### 3. Update routing

The prefix `/templates/` currently catches all sub-paths for the editor. We need to distinguish:
- `/templates/:name/print` → recall page
- `/templates/:name` → editor

In `frontend/src/main.ts`, register the more-specific prefix first:

```typescript
registerPrefix('/templates/', (root) => {
  const path = window.location.pathname
  if (path.endsWith('/print')) {
    mountTemplateRecall(root)
  } else {
    mountTemplateEditor(root)
  }
})
```

This replaces the current `registerPrefix('/templates/', mountTemplateEditor)` line. Import `mountTemplateRecall` from the new page module.

### 4. Add Print button to templates list

In `frontend/src/pages/templates-list.ts`, add a **Print** button to each template row (alongside Edit and Delete). It should navigate to `/templates/${name}/print`.

### 5. Styling

Use the existing CSS patterns from `frontend/src/style.css`. The recall page should look consistent with the quick-print page. Key elements:
- Form inputs styled like existing inputs
- Preview image displayed at a reasonable size (scale to fit, not full label-pixel resolution)
- Status messages use the existing `.status-msg` pattern
- Batch section visually grouped (fieldset or bordered section)

### 6. Changelog

Add entry under `## [Unreleased]` → `### Added`:

```
- **Template recall UI** — fill variable fields, preview, and print from saved templates at `/templates/{name}/print`; batch printing with auto-increment for numeric fields
```

## Do NOT

- Do not modify any backend code — the backend is complete
- Do not add new npm dependencies
- Do not change the template editor page
- Do not add features beyond what's described here (no history, no settings)
- Do not write JS files — TypeScript only (the `.js` files are build artifacts)

## How to verify

1. Run: `docker compose -f compose.dev.yml up --build -d`
2. Open `http://localhost:8001/templates`
3. Create a template in the editor with text containing `{name}` and `{number}` placeholders, save it
4. Click Print on that template in the list
5. Verify the recall form shows inputs for `name` and `number`
6. Fill values, click Preview — should show server-rendered PNG
7. Click Print — should get success response (will fail to actually print if no printer, that's fine — check for a non-error API response)

## Final step

Update this file's frontmatter: set `status` to `completed` or `failed`, fill in `completed` date, and write a one-line `result` summary.
