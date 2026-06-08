---
name: 2026-06-07-last-used-label-default
status: completed
created: 2026-06-07
model: sonnet
completed: 2026-06-07
result: Added localStorage-backed last-used label memory to all three choosing pickers (Quick Print, New Template, Save As); build and tsc clean.
---

# Task: Default label pickers to the last-used label

When the user picks a label media in any "choosing" context, remember it and use it
as the default the next time a label picker loads. This makes the app open on the
roll you last worked with instead of a fixed default.

**Product decisions (already made with the owner — do not re-litigate):**
- **Persistence: `localStorage`** — the last-used label persists across browser
  sessions (not just the current tab). Until the user picks a different one.
- **Scope: all three label-*choosing* pickers** — Quick Print, the New Template modal,
  and the Save As modal. Each one (a) defaults to the last-used label and (b) updates
  it when the user changes the selection (selecting counts as "using").
- **Excluded: editing an existing template.** Loading an existing template in the
  editor keeps that template's stored `label_media` and must NOT read or write the
  last-used value. (The editor's only `mountLabelMediaSelect` is the Save As modal,
  which IS in scope; there is no separate existing-template media picker via this
  helper — verified. If you find one, it stays excluded.)

This is a **frontend-only** change. No backend/API changes.

## Before you start

- Read `docs/features/quick-print.md` and `docs/features/templates.md` (label-media /
  defaults sections).
- Key files:
  - `frontend/src/labels.ts` — shared `mountLabelMediaSelect({container, labels,
    initialValue, onChange})`; `getValue`/`setValue` handle. This is where the
    write-on-change hook belongs.
  - `frontend/src/pages/quick-print.ts` — mounts the picker ~L218; `preferMedia` is
    resolved ~L188–216 from `last_quick_print` / settings / `'62'`.
  - `frontend/src/pages/templates-list.ts` — New Template modal mounts the picker into
    `#modal-media-container` (~L172+).
  - `frontend/src/pages/template-editor.ts` — Save As modal mounts the picker ~L368
    with `initialValue: currentMedia`.

## Working tree check

Before making edits, run `git status --porcelain` and cross-reference the files this
plan touches. If any have uncommitted changes, list them and ask before touching.
Surface unrelated dirty files once as awareness; don't block. This prompt file is exempt.

## What to do

1. **New module `frontend/src/lastLabel.ts`** (small, framework-free):

   ```ts
   const LAST_LABEL_KEY = 'lf:last-label'

   export function getLastLabel(): string | null {
     try { return localStorage.getItem(LAST_LABEL_KEY) } catch { return null }
   }

   export function setLastLabel(id: string): void {
     if (!id) return
     try { localStorage.setItem(LAST_LABEL_KEY, id) } catch { /* storage may be unavailable */ }
   }
   ```

2. **Write-on-change in `mountLabelMediaSelect`.** Add an opt-in option, e.g.
   `remember?: boolean` (default `false`). Route every place that currently calls
   `onChange(sel.value)` (the `sel` change listener, both toggle-mode handlers, and
   `setValue`) through a small wrapper that, when `remember` is true, calls
   `setLastLabel(id)` before invoking the caller's `onChange`. Do NOT write on the
   initial `populate()` — only on user-driven changes. Import `setLastLabel` from
   `./lastLabel`.

3. **Default-to-last-used at the three choosing sites.** Resolve `initialValue` as
   `getLastLabel() ?? <existing default>` and pass `remember: true`:
   - **Quick Print** (`quick-print.ts`): make the picker's `initialValue` be
     `getLastLabel() ?? preferMedia` (keep all the existing `last_quick_print` /
     settings logic intact — it stays the fallback). Pass `remember: true`. The picker
     already redirects unsupported ids to the first supported entry, so a stale/
     unsupported stored id is safe.
   - **New Template modal** (`templates-list.ts`): `initialValue: getLastLabel() ?? <whatever
     it currently uses>` (currently likely undefined → first supported). Pass
     `remember: true`.
   - **Save As modal** (`template-editor.ts`, ~L368): `initialValue: getLastLabel() ??
     currentMedia` — last-used wins, source template media is the fallback. Pass
     `remember: true`.

4. Do **not** change the editor's handling of an existing template's stored media, and
   do not add `remember`/`getLastLabel` anywhere outside the three sites above.

5. Build + typecheck the frontend (`npm run build` / tsc) and run the repo's lint;
   fix issues without bypassing hooks. (No backend tests are affected.)

## Conventions to honor

- Vanilla TS + Fabric, no frameworks; match existing module style in `frontend/src/`.
- `CHANGELOG.md`: concise user-facing entry under `## [Unreleased]`, e.g.
  `feat: label pickers default to the last label you used (remembered across sessions)`.
- Update `docs/features/quick-print.md` and/or `docs/features/templates.md` if they
  describe how the label default is chosen, so docs match behavior. Doc change ships in
  the **same commit** as the code.
- Commit prefix `feat:`. No `Co-authored-by:` trailers. Work on `dev`. Commit, don't push.

## When done

1. Update this file's frontmatter: `status`, `completed`, `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Add a short `docs/decisions.md` ADR entry: "Label pickers remember the last-used
   media" — record the two product decisions (localStorage / persist across sessions;
   applies to Quick Print + New Template + Save As; excludes editing an existing
   template).
4. The owner has authorized committing — do NOT ask y/n. Make ONE commit on `dev`
   covering exactly the files you modified (including this prompt's move). Stage
   specific paths (never `git add -A`), `feat:` prefix, no co-author trailer, do not push.
   Report the file list, build result, commit hash + message, and any non-obvious decisions.
