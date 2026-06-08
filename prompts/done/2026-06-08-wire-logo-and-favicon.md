---
name: 2026-06-08-wire-logo-and-favicon
status: completed
created: 2026-06-08
model: sonnet            # frontend coding, clear spec
completed: 2026-06-08
result: Added favicon <link> and nav-brand <a><img> to index.html; CSS for #nav-brand in style.css; CHANGELOG entry; build verified — both PNGs hashed under /assets/ in dist.
---

# Task: Wire in the app logo (nav brand) + favicon

Add the LabelForge logo to the nav bar (as a home link) and set the browser
favicon, using the transparent PNG assets already placed in
`frontend/src/assets/`. Frontend-only; no backend change.

## Context already done (do NOT regenerate)

- The assets exist and are final — do not resize or modify them:
  - `frontend/src/assets/logo.png` — 256×256, transparent, 44 KB
  - `frontend/src/assets/favicon.png` — 48×48, transparent, 3.3 KB
- **Why src/assets and not public/:** the FastAPI server only serves the Vite
  `/assets` mount (`backend/labelforge/main.py:155-159`); any other path falls
  through to the SPA catch-all that returns `index.html`
  (`main.py:161-167`). So assets MUST be referenced in a way Vite bundles into
  `dist/assets/` (hashed) — a bare `public/` file at the dist root would be
  shadowed by the catch-all and never load. Confirm your references end up under
  `/assets/` in the build (see Verify).

## Before you start

Read:
- `frontend/index.html` — the `<head>` (no favicon link yet) and the static
  `<nav id="nav">` with four `<a data-route="...">` links.
- `frontend/src/router.ts` — how `data-route` links are wired for client-side
  navigation (the brand link must use the same mechanism so clicking it routes
  to `/` without a full reload).
- `frontend/src/style.css` — the `#nav` rules (around line 140): `#nav` is
  `display:flex; gap:1.25rem; max-width:520px; margin:0 auto 1rem;` and `#nav a`
  styling. Match the existing visual idiom.
- `CLAUDE.md` repo conventions; memory note: frontend changes need a docker
  rebuild + hard refresh to show (dev compose hot-reloads backend only).

## Working tree check

Run `git status --porcelain`. Expect the two untracked PNGs under
`frontend/src/assets/` (leave them as-is — they're the prepared assets) and an
otherwise clean tree on `dev`. If anything you plan to edit is already dirty,
list it and ask before proceeding. This prompt file is exempt.

## What to do

1. **Favicon** — in `frontend/index.html` `<head>`, add:
   ```html
   <link rel="icon" type="image/png" href="./src/assets/favicon.png" />
   ```
   Use a **relative** `./src/assets/...` path (not `/src/...`) so Vite rewrites
   it to the hashed `/assets/…` URL on build. (The existing `<title>` stays.)

2. **Nav brand logo** — add the logo as the FIRST child of `<nav id="nav">`, as a
   home link that routes to `/` via the existing router mechanism, e.g.:
   ```html
   <a href="/" data-route="/" id="nav-brand" aria-label="LabelForge home">
     <img src="./src/assets/logo.png" alt="LabelForge" />
   </a>
   ```
   Again use the relative `./src/assets/logo.png` so Vite bundles it. Make sure
   the existing four nav links are unchanged and the brand uses `data-route="/"`
   so `router.ts` handles the click (verify against how router.ts binds
   `data-route`).

3. **CSS** — in `frontend/src/style.css`, style the brand so it sits cleanly at
   the left of the nav:
   - `#nav` should vertically center its items (add `align-items: center;` if not
     present).
   - `#nav-brand img { height: 28px; width: auto; display: block; }`
   - `#nav-brand` should have no bottom-border/underline treatment from the
     `#nav a` rules (it's an icon, not a text tab) — reset as needed so it
     doesn't show the text-link border on hover/active.
   - Keep the nav compact; don't break the centered `max-width: 520px` layout.
     If the logo makes it feel cramped, a small right gap before the text links
     is fine.

## Conventions to honor

- LF line endings; vanilla TS; no new dependencies; match surrounding style.
- `CHANGELOG.md`: add an entry under `## [Unreleased]` (`### Added`), e.g.
  *"App logo now appears in the nav (links home) and as the browser favicon."*
- Docs ship in the same commit. Commit prefix `feat:`; no `Co-authored-by:`.
- No ADR needed (cosmetic UI).

## Verify

- `npm run build` (from `frontend/`) passes (tsc + vite).
- In the build output, confirm BOTH images are emitted under `dist/assets/`
  (hashed names) and that `dist/index.html` references them via `/assets/…`
  URLs for the favicon `<link>` and the nav `<img>` (grep the built
  `dist/index.html`). This proves they'll be served by the FastAPI `/assets`
  mount rather than swallowed by the SPA catch-all.
- Optionally note the dev path works too (`./src/assets/...` resolves under the
  Vite dev server).

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-08`, one-line
   `result`).
2. `git mv` this file to `prompts/done/` (success) or `prompts/failed/`.
3. **You are a spawned agent: do NOT commit.** Prepare the tree and report back:
   a per-file summary, the final `git status --porcelain`, the proposed one-line
   `feat:` commit message, the explicit paths to stage (including the two PNG
   assets and the moved prompt), and your verify output (the grep of built
   `dist/index.html` showing the `/assets/…` references). Never `git add -A`,
   never push, never auto-commit.
