---
name: 2026-06-07-load-fonts-in-browser
status: completed
created: 2026-06-07
model: sonnet
completed: 2026-06-07
result: Added GET /api/fonts/{name}/file endpoint; loadServerFonts() helper fetches bytes via authenticated fetch and registers FontFace objects; wired into editor bootstrap and main.ts app-wide startup.
---

# Task: Load server fonts into the browser so the editor canvas is WYSIWYG

The template editor's font dropdown lists server fonts (`GET /api/fonts` → name,
family, style), but the actual font files are **never loaded into the browser**.
Fabric.js sets `fontFamily: 'DejaVuSans-Bold'`, the browser has no such font, and
falls back to a serif. Result: the editor canvas shows serif while the server render
/ print uses the real font — the canvas is not WYSIWYG. Fix it by serving the font
bytes and registering each font with the `FontFace` API on load, then re-rendering
the canvas.

Note: Quick Print's preview is a **server-rendered PNG** (`/api/preview/quick`), so it
is already font-correct. Loading fonts app-wide is still desirable for consistency and
costs nothing; do it globally rather than only in the editor.

## Before you start

- Read `docs/features/templates.md` and `docs/features/quick-print.md`.
- Backend font discovery lives in `backend/labelforge/render/fonts.py`
  (`get_fonts()`, `get_font_path(name)`; `FontInfo` has `name`, `path`, `family`,
  `style`). The font endpoint is `backend/labelforge/routes/fonts.py`.
- Frontend: `frontend/src/api.ts` (`getFonts`), `frontend/src/pages/template-editor.ts`
  (bootstrap ~L271 `Promise.all([getLabels(), getFonts()])`), `frontend/src/editor/canvas.ts`.
- Do **not** change the renderer or origin handling here (separate task:
  `2026-06-07-render-honor-origin`). If that prompt is still pending, avoid editing
  `render/template.py`.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files
this plan needs to modify. If any have uncommitted changes, list them and ask before
touching them. Surface unrelated dirty files once as awareness; don't block. This
prompt file is exempt.

## What to do

1. **Backend — serve font bytes.** Add an endpoint to `routes/fonts.py`:
   `GET /api/fonts/{name}/file`. Resolve `name` via `get_font_path(name)` (or look it
   up in `get_fonts()`); 404 if unknown. **Reject path traversal** — only serve a
   path that the font scanner actually returned (compare against known font paths;
   do not join user input onto a directory). Return a `FileResponse`/`Response` with
   the correct media type (`font/ttf` for `.ttf`, `font/otf` for `.otf`) and a long
   `Cache-Control` (fonts are immutable per name). Mirror the auth dependency used by
   the other font/route handlers.

2. **Frontend — register fonts.** Add a helper (e.g. in a new
   `frontend/src/editor/fonts.ts` or alongside `api.ts`):

   ```ts
   export async function loadServerFonts(fonts: FontInfo[]): Promise<void> {
     await Promise.all(fonts.map(async (f) => {
       try {
         const face = new FontFace(f.name, `url(/api/fonts/${encodeURIComponent(f.name)}/file)`)
         await face.load()
         document.fonts.add(face)
       } catch (err) {
         console.warn(`Font failed to load: ${f.name}`, err)
       }
     }))
   }
   ```

   - Register under the **same identifier the canvas uses** for `fontFamily` — that is
     `FontInfo.name` (e.g. `DejaVuSans-Bold`), since `addTextElement`/`fontSelect` set
     `fontFamily` to the font's `name`. The `FontFace` family string must match
     exactly.
   - If the auth token is sent via header (check `api.ts`), the bare `url(...)` in
     `FontFace` cannot attach it. If `/api/fonts/{name}/file` requires auth and the
     app uses header tokens, either (a) fetch the bytes through the existing
     authenticated fetch and build the `FontFace` from the resulting `ArrayBuffer`, or
     (b) confirm fonts are reachable with the cookie/session the browser already sends.
     Pick whichever matches how other `/api/...` GETs for binary (e.g. preview PNGs,
     history previews) are loaded — match that pattern.

3. **Wire it in.** In the editor bootstrap, after `getFonts()` resolves, `await
   loadServerFonts(fonts)`; once fonts are ready, re-render the canvas so existing
   text repaints with the real font (`fabricCanvas?.renderAll()`, and after
   `loadCanvasJSON`). Do the same app-wide entry where convenient (e.g. call it once
   on first load in `main.ts`/router) so Quick Print and the editor share loaded
   fonts. Guard against double-registration (don't re-add a `FontFace` already in
   `document.fonts`).

4. **Verify** the canvas now matches the server render: open the `testt` template
   (62x29). After fixing this, the on-canvas font should be DejaVuSans-Bold
   (sans-serif), matching the Preview. (Positional alignment is the separate origin
   task — don't expect this change to fix the fan-out.)

5. Run frontend build/lint (`npm run build` / typecheck) and backend tests/lint; fix
   issues without bypassing hooks.

## Conventions to honor

- Frontend is vanilla TS + Fabric.js — no frameworks. Match existing module style in
  `frontend/src/editor/` and `frontend/src/api.ts`.
- `CHANGELOG.md`: concise user-facing entry under `## [Unreleased]`, e.g.
  `fix: editor canvas now shows the selected font instead of a serif fallback`.
- Update `docs/features/templates.md` if it claims the canvas is WYSIWYG / describes
  font handling, so docs match. Doc change ships in the **same commit** as the code.
- Commit prefix `fix:`. No `Co-authored-by:` trailers. Work on `dev`. Commit, don't push.

## When done

1. Update this file's frontmatter: `status`, `completed`, `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decision in `docs/decisions.md` (e.g. the chosen
   auth-for-font-bytes approach), if applicable.
4. Propose ONE commit covering the modified files (including this prompt's move).
   Present the file list and a one-line `fix:` message; ask `commit these as
   "<message>"? (y/n)`. On `y`, stage those specific paths and commit on `dev`. Never
   `git add -A`. Never push.
