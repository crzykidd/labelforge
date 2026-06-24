---
name: 2026-06-22-token-gate-reauth-ux
status: completed
created: 2026-06-22
model: sonnet            # coding task (frontend TS)
completed: 2026-06-22
result: Token gate validates before storing; 401/403 from any fetch path clears token and bounces to gate; Settings escape hatch added
---

# Task: Make a wrong API token recoverable (validate at the gate + re-auth on rejection)

Today the token gate stores whatever you type **without validating it**, and the
client has **no handling for an auth-rejected response**. So if you fat-finger the
API token, the SPA loads but every call fails, and there is no way back to the
token screen — you're stuck (must clear localStorage by hand). Fix it so a bad
token is rejected at entry, any rejected token bounces you back to the gate with a
clear message, and there's always a visible "change token" escape hatch.

## Before you start

- Read `docs/features/api.md` (auth section) and `CLAUDE.md` (working style,
  changelog, check-in rules). This is **frontend-only** — `frontend/src/`.
- Do NOT touch backend auth. Do NOT add multi-user/accounts/SSO. Auth stays a
  single shared token (`docs/decisions.md` ADR 2026-06-02 for `DISABLE_AUTH`).

### Key facts from a code survey (verify before trusting)

**The backend returns 403, not 401, for a wrong token** — this is the crux:
- `backend/labelforge/auth.py` `require_auth`: missing/non-Bearer header →
  **401**; **wrong token → `HTTPException(403, "Invalid API token")`**;
  no-op when `settings.disable_auth` is true.
- `require_auth` is applied at the router level to `labels`, `templates`,
  `history`, `settings`, `print`, `preview`, `fonts`, `admin`. So
  **`GET /api/labels` requires auth** and is a good cheap validation target
  (200 with a good token, 403 with a bad one). `GET /api/health` is the ONLY
  unauthenticated route — it returns 200 regardless, so it CANNOT validate a
  token.
- **Therefore the client must treat BOTH 401 and 403 as auth failures.** A fix
  that only keys on 401 will miss the exact "typed it wrong" case.

**Frontend (`frontend/src/`):**
- `api.ts:3` — `export const TOKEN_KEY = 'labelforge_token'`.
- `api.ts:14-16` — `getToken()` reads localStorage.
- `api.ts:18-35` — `initAuthMode()` / `isAuthRequired()`: probes
  `GET /api/health` for `auth_required`; fails closed to `true`. Called once at
  startup (`main.ts:30-36`) before routing.
- `api.ts:37-66` — central `apiFetch<T>()` attaches `Authorization: Bearer
  ${getToken()}`, inspects `res.ok`, throws `ApiError(detail, status, ...)`
  (`ApiError` at `api.ts:7-12`). Only 409 is special-cased today.
- **Bespoke fetch paths that bypass `apiFetch`** and throw a **plain `Error`
  without status** (they will NOT carry 401/403 unless updated): `previewQuick`
  (`api.ts:83-109`), `previewTemplate` (`api.ts:148-181`), `fetchHistoryPreview`
  (`api.ts:222-243`), `getPrinterStatus` (`api.ts:268-274`). Also a direct token
  read in `editor/fonts.ts:26`.
- `pages/quick-print.ts:14-20` — `mountQuickPrint` is the ONLY place the gate is
  wired: shows the gate iff `isAuthRequired() && !localStorage.getItem(TOKEN_KEY)`,
  else the form. The other routes (`/templates`, `/history`, `/settings`) have
  **no gate** — they just render and fail.
- `pages/quick-print.ts:22-43` — `renderTokenGate` (password input + "Save token")
  and `save()` at `34-39`: non-empty check then **blind** `localStorage.setItem`
  + re-render. No server round-trip.
- No `removeItem(TOKEN_KEY)`, no logout, no 401/403 handling exists anywhere
  (confirmed by search). Nav (`index.html:9-14`) has no token control.
- `router.ts` — SPA router with `navigate()`; fallback route is `/`.

## Working tree check

Run `git status --porcelain` and cross-reference the files this plan touches
(`frontend/src/api.ts`, `frontend/src/pages/quick-print.ts`,
`frontend/src/main.ts`, `frontend/src/router.ts`, `frontend/index.html`,
`frontend/src/pages/settings.ts`, possibly a new small auth module,
`CHANGELOG.md`, `docs/decisions.md`). Note: the repo is on branch `dev` with one
prior commit (the QR/barcode fix) already on it — that's expected; leave it.
If any file you need to edit has unrelated uncommitted changes, list it and ask
before touching. This prompt file is exempt.

## What to do

Implement three things. Keep it DRY — centralize the auth-failure logic so every
call path benefits, including the bespoke fetch helpers.

1. **Validate the token at the gate before storing it.**
   - In `save()`, do an authenticated probe with the *candidate* token (don't
     store first). Add an `api.ts` helper like `validateToken(candidate: string):
     Promise<boolean>` that does `fetch('/api/labels', { headers: { Authorization:
     \`Bearer ${candidate}\` } })` and returns `res.ok` (treat 401/403/network as
     invalid). Only `localStorage.setItem(TOKEN_KEY, candidate)` on success, then
     render the form.
   - On failure show an inline error in the gate ("That token was rejected — check
     it and try again.") and keep the user on the gate. Disable the button while
     the probe is in flight.

2. **Treat 401 AND 403 as an auth failure everywhere → clear token + return to the
   gate with a message.**
   - Add a single `handleAuthFailure()` in `api.ts`: if `isAuthRequired()`,
     `localStorage.removeItem(TOKEN_KEY)`, set a one-shot "rejected" flag (a
     module variable or `sessionStorage`) that `renderTokenGate` reads to show the
     "your token was rejected, re-enter it" message, then route back to the gate
     (`navigate('/')` re-mounts `quick-print`, which now has no token → shows the
     gate). Guard on `isAuthRequired()` so a `DISABLE_AUTH=true` deployment is
     never bounced (a stray 401/403 there must not trap the user on a gate that
     shouldn't exist).
   - Wire it into `apiFetch` (when `res.status === 401 || res.status === 403`) AND
     into the four bespoke fetch helpers + `editor/fonts.ts`. Prefer refactoring
     the bespoke helpers to share a small `assertOk(res)` (or route them through
     `apiFetch`) so the 401/403 check lives in ONE place rather than five. Don't
     leave a fetch path that swallows a 403 silently.
   - Don't double-fire: validation probes in step 1 should NOT trigger
     `handleAuthFailure()` (they expect a possible 403 and handle it locally).

3. **Add a visible "change token" / sign-out escape hatch.**
   - Add a control that clears the token and returns to the gate — e.g. a
     "Sign out / change API token" button in Settings (`pages/settings.ts`), and/or
     a small nav affordance. Only show it when `isAuthRequired()` (pointless under
     `DISABLE_AUTH`). This guarantees recovery even if the user simply wants to
     swap tokens or the auto-bounce ever misses an edge.

## Conventions to honor

- Add a concise, user-facing `CHANGELOG.md` entry under `## [Unreleased]`
  (`### Fixed`). Frontend assets change, so note **"Requires a container image
  rebuild."** at the end, matching the house style of other UI entries.
- Match the existing vanilla-TS style (no framework, no new deps). Reuse
  `showStatus`, the existing gate markup/classes, and the router's `navigate`.
- Comments only for non-obvious *why* (e.g. "403 = wrong token, 401 = missing —
  both mean re-auth"). No giant explainer blocks.
- Type-check and build before finishing:
  `cd frontend && npx tsc --noEmit && npm run build`. There are no frontend unit
  tests; this is the gate that CI enforces.

## When done

1. Update this file's frontmatter: `status`, `completed` (2026-06-22), `result`.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/`.
3. Record the non-obvious decisions in `docs/decisions.md`, newest at top —
   especially **"the client treats 401 and 403 as auth failures because the
   backend returns 403 for a wrong token,"** the validate-before-store choice, and
   the `isAuthRequired()` guard that protects `DISABLE_AUTH` deployments.
4. Prepare ONE commit covering this prompt file, the modified frontend/docs, and
   the prompt move — the prompt is **not** pre-committed, it bundles in here.
   - **You are a spawned agent: do NOT commit.** Prepare the working tree and
     report the exact file list + a proposed one-line message (Conventional-
     Commits `fix:` prefix, no `Co-authored-by:`) back to the orchestrating
     session, which surfaces the `y/n` to the user.
   - Work on `dev` (never `main`), never `git add -A`, never push.
5. Note for the owner: real verification is manual — run the app, enter a wrong
   token (expect rejection at the gate, not a dead UI), enter a correct one, then
   use the "change token" control to confirm you can get back to the gate.
