---
name: 2026-06-23-api-docs-correction
status: completed        # pending | completed | failed
created: 2026-06-23
model: sonnet            # docs correction against a precise audit
completed: 2026-06-23
result: Corrected api.md auth model (401/403, removed fictional cookie/Cloudflare middleware), endpoint surface (dropped /printer/info, added 5 real routes + ?override), and response shapes ("sent" not "printed", overflow, no printed_at, batch 200/500 not 207, {detail} envelope). Executed inline by orchestrator after two spawned agents hit transient API 500s.
---

# Task: Correct `docs/features/api.md` to match the implemented API

`docs/features/api.md` has drifted from the actual FastAPI implementation: the
auth model is described wrong, a documented endpoint doesn't exist, several real
endpoints are missing, response shapes don't match, and a "TBD" was resolved in
code but not in the doc. Bring the doc in line with reality. **This is a
docs-only task** — do not change API behavior. If a discrepancy looks like a
genuine API bug worth a *code* change (not mere doc drift), FLAG it for the owner
in your report rather than changing behavior.

## Before you start

- Read `docs/features/api.md` in full, and `CLAUDE.md` (docs source-of-truth
  rules, changelog, check-in). The doc is the design/reference for the API — we
  keep it accurate; we do NOT auto-generate it.
- **Verify every claim below against the actual code** (cite `file:line`). The
  list comes from an audit and is reliable, but confirm before writing — the doc
  must end up correct even if an audit line slipped.
- The auth dependency is `require_auth` in **`backend/labelforge/routes/auth.py`**
  (lines 6-20). Routers are registered with `prefix="/api"` in
  `backend/labelforge/main.py` (~139-150).

## The discrepancies to fix (audit findings — verify, then correct)

### A. Auth model (the biggest error) — api.md §Auth, ~lines 14-25, 219-223

1. **False claim (line ~23):** "GET endpoints (templates list, label catalog,
   history read) are unauthenticated on the LAN." Reality: `require_auth` is
   applied at the **router level** to `labels`, `templates`, `history`,
   `settings`, `fonts`, `admin`, `print`, `preview`, `template_print` — so **every
   GET on those requires the token** (verify: `labels.py:7`, `templates.py:15`,
   `history.py:21`, `settings.py:8`, `fonts.py:10`, `admin.py:12`).
2. **The only unauthenticated routes** are `GET /api/health`,
   `GET /api/printer/status`, `GET /api/version`, plus FastAPI's
   `/docs` / `/redoc` / `/openapi.json` and the SPA fallback. Document this
   accurately (verify: `health.py`, `printer.py:13`, `version.py:14` carry no
   `require_auth`).
3. **401 vs 403 (lines ~120, 122 and the Auth section):** a **missing or
   non-Bearer** Authorization header → **401**; a **wrong token → 403**
   ("Invalid API token"). The doc currently only says "401 — missing/invalid
   token" and never mentions 403. Fix every error list and the Auth prose
   (verify: `routes/auth.py:15,17` → 401; `:20` → 403; no-op when
   `settings.disable_auth`).
4. **Remove the fictional mechanism:** lines ~21, 23 describe a same-origin
   cookie login page and a Cloudflare-header-detecting `require_token`
   middleware. **Neither exists.** Auth is a single FastAPI `Header`-based Bearer
   dependency. Cloudflare Tunnel is deployment infrastructure (keep that framing
   if useful per `docs/PRD.md`), but do not describe app code that isn't there.
   Cross-check `docs/decisions.md` ADR 2026-06-02 (`DISABLE_AUTH`) and keep the
   doc consistent with it.

### B. Endpoint surface — api.md §Endpoint surface, ~lines 27-87

5. **Documented but does NOT exist:** `GET /api/printer/info` (line ~73). Remove
   it (only `GET /api/printer/status` exists in `printer.py`). If you think an
   info endpoint is worth having, flag it — don't invent the doc for absent code.
6. **Implemented but undocumented — add these** (verify each):
   - `GET /api/health` — liveness + `auth_required` flag (unauth) (`health.py:8`)
   - `GET /api/version` — version + update check (unauth) (`version.py:113`)
   - `GET /api/printer/status` — note it's **unauthenticated** (`printer.py:16`)
   - `POST /api/admin/prune-history` — run retention now (`admin.py:47`)
   - `GET /api/fonts/{name}/file` — raw font bytes (`fonts.py:23`)
   - `GET /api/templates/{name}/last-values` — last printed field values
     (`templates.py:83`)
   - Confirm `POST /api/templates/{name}/duplicate` is already documented
     (line ~37) — it is; leave it.
7. **`?override=true`** query param is real on `/print/quick`, `/print/{name}`,
   `/print/{name}/batch` (`print.py:27`, `template_print.py:81,201`) but isn't in
   the endpoint surface. Note it where those endpoints are listed.

### C. Response shapes & examples

8. **Print template response (api.md ~106-116):** the handler returns a plain
   dict (no `response_model`) of `{job_id, status, template, label_media,
   preview_url, overflow}` (verify `template_print.py:159-166`). Corrections:
   - `status` is the **send outcome — `"sent"` for the network backend, not
     `"printed"`** (intentional per ADR 2026-05-20 — report true outcome). Fix
     here and everywhere the doc shows `"printed"`.
   - **`printed_at` is NOT returned** — remove it from the example.
   - **`overflow` (bool) IS returned** — add it.
9. **Quick-print response** is `PrintJobResponse` = `{job_id, status,
   preview_url}` only (verify `models/__init__.py`). The doc shows no quick-print
   response example today; if you add one, match this shape (and `"sent"`).
10. **Batch (api.md ~140-154):** the **`207` was never implemented** — the TBD
    must be resolved in the doc: mixed results return **200**; all-failed returns
    **500** (verify `template_print.py:294-302`). Also document the failed-job
    shape (`job_id: -1`, `status: "error: <msg>"`, `template_print.py:288,291`)
    and that the all-failed 500 nests the `BatchPrintResponse` under FastAPI's
    `detail` key.
11. **Error envelopes:** the 409 media-mismatch / 400 bodies are raised via
    `HTTPException(detail={...})`, so the wire shape is `{"detail": {...}}`, not
    the bare object the examples show (lines ~186-194). Either wrap the examples
    in `{"detail": ...}` or add a clear note. Also document the other real error
    responses: the `409 {error:"printer_error", code, message, raw}`
    (`print.py:58-66`) and the `503 {error:"status_unavailable"}` from
    `GET /api/printer/status` (`printer.py:28-34`). The documented
    `media_mismatch` body matches the code otherwise — keep it.

### D. OpenAPI (api.md ~219-223)

12. `/docs`, `/redoc`, `/openapi.json` ARE served and unauthenticated (no global
    auth dependency; verify `main.py` `FastAPI(...)` doesn't override the urls).
    Keep this, but correct the "require the token via Cloudflare" half to match
    the real (no app-level docs auth) behavior — Cloudflare is infra, not app
    code.

## Working tree check

Run `git status --porcelain`. Branch is `dev` with three prior commits on it
(`421caee`, `b76218b`, `d179c5f`) — expected, leave them; tree should be clean.
You'll touch `docs/features/api.md`, `CHANGELOG.md`, and maybe
`docs/decisions.md`. If anything has unrelated uncommitted changes, list it and
ask. This prompt file is exempt.

## Conventions to honor

- Keep api.md's existing structure and tone; correct content in place rather than
  rewriting wholesale. Keep curl examples runnable and consistent with the fixes
  (e.g. any example showing a response `status` must say `"sent"`).
- Add a `CHANGELOG.md` entry under `## [Unreleased]` → `### Changed` (docs-only,
  user/developer-facing, e.g. "Corrected the HTTP API reference (auth model,
  401-vs-403, response shapes, missing/removed endpoints)."). **No "requires a
  container image rebuild"** — docs don't ship in the image.
- Record any non-obvious doc decision in `docs/decisions.md` only if it's a real
  decision (e.g. "documented the actual 403 behavior rather than changing the
  code to 401"); routine doc fixes don't need an ADR.
- Do NOT change any backend code. If you find what looks like a genuine API bug
  (not doc drift), list it in your report under "Flagged for owner."

## When done

1. Update this file's frontmatter (`status`, `completed` 2026-06-23, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/`.
   The command sandbox is disabled — you CAN run `git mv` directly.
3. Prepare ONE commit (this prompt file + the doc changes + the prompt move). The
   prompt is **not** pre-committed — it bundles in.
   - **You are a spawned agent: do NOT commit.** Prepare the tree and report back
     the exact file list + a proposed one-line message (Conventional-Commits
     `docs:` prefix, no `Co-authored-by:`). The orchestrator surfaces the y/n.
   - Work on `dev`, never `main`, never `git add -A`, never push.
4. In your report include: a concise list of every correction you made (so the
   orchestrator can spot-check against the audit), and a separate "Flagged for
   owner" section for anything you think is a code bug rather than doc drift
   (e.g. the missing `printed_at`, or whether `/api/printer/info` should exist).
