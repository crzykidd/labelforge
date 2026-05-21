# Decisions

Architecture Decision Records, newest at the top. Each entry: what we decided, why, what we considered, and what would cause us to revisit.

---

## 2026-05-20 (d) — App stays deployment-generic; branch model is PR-gated main + dev working branch

**Decision (deployment)**: labelforge's repo and docs describe the app generically — a single Docker container serving HTTP on 8000, with persistent data under `$DATA_DIR` (default `/data`). No specific host paths, hostnames, registries, orchestrators, or reverse-proxy wiring appear in the app or its public docs. `compose.yml` ships a standalone example using a named volume; operators substitute their own bind mount / proxy / tunnel.

**Decision (branches)**: `main` is protected and reachable only via pull request, gated by CodeQL and other checks — never a direct push. `dev` is the working branch; solo work commits directly to `dev`. `feature/<name>` branches are used when more than one person is involved, merged to `dev`, and `dev` is PR'd to `main` for a release.

**Why**: The project is public open source. Baking the owner's homelab (host paths like `/var/docker/labelforge`, hostnames like `labels.crzynet.com`, Dockflare/Traefik labels, Gitea registry, the orchestrator) into the app's defaults and docs made it non-portable and misled readers — a stranger cloning the repo got the author's filesystem as a default and a deploy story they can't use. The deployment specifics are the operator's concern, not the app's. Separately, the documented branch model (`main` deployable, feature branches as default) did not match reality (PR-gated `main`, `dev` as the normal working branch), which repeatedly caused confusion; the docs now match the actual workflow.

**Consequence**: `config.py` defaults `DATA_DIR=/data`; `compose.yml` uses a named volume and carries no proxy/network specifics; CLAUDE.md and architecture.md describe paths as `$DATA_DIR`-relative and deployment as bring-your-own-proxy. The owner's actual homelab deployment (named orchestrator, host paths, tunnel) lives outside this repo. Any future doc or default that reintroduces a specific host/hostname/registry/orchestrator into the app should be rejected and pointed at this ADR.

**Would revisit if**: the project ships an official first-party deployment (e.g. a published image + opinionated compose) — at which point an *example* registry/image name may belong in docs, still framed as one option, not a baked-in default.

---

## 2026-05-20 (c) — Printer status comes from the EWS status page (opt-in), not the print path or vendor SDKs

**Decision**: Live printer status (loaded media type, device-ready state) is read by fetching and parsing the printer's embedded web server (EWS) status page over HTTP — `http://<printer-host>/general/status.html` on the QL-820NWB — **as an opt-in feature, disabled by default**. The raster print path (TCP 9100) and the Brother b-PAC / Mobile SDKs are NOT used for status.

**Why**: Three channels were evaluated against the locked stack (Python/FastAPI, Linux container, networked printer):

- **TCP 9100 (raster/print path)** — send-only. A probe issuing the status-information request opcode (`ESC i S`) then reading returned empty against an idle, ready printer. No status here. (Confirmed empirically.)
- **Brother b-PAC SDK / Mobile SDK** — these do expose status (e.g. `getLabelInfoStatus` returning a label-ID enum), but b-PAC is a Windows COM component and the Mobile SDK is iOS/Android. Neither runs in a Linux container. Off-stack — rejected. (The enum reports the same sensed-media fact the EWS page already gives us, so nothing is lost.)
- **EWS over HTTP (port 80)** — the printer serves a status page reporting `Device Status` (e.g. READY), `Media Type` (e.g. "62mm x 29mm"), `Media Status`, and `Emulation`. The Status page is readable with an unauthenticated GET. Verified directly against the device. **Chosen.**

**Scope of this decision**: read-only, unauthenticated status scrape, opt-in.

- Default **off**. A setting (`printer_status_check`) enables it; when off, labelforge assumes nothing about loaded media and relies solely on the user-selected `label_media`.
- Status is **advisory, never a gate**. A status read never blocks or fails a print. If the fetch fails, times out, or the page can't be parsed, status is reported as "unknown" and printing proceeds normally.

**Consequence — the page is firmware-controlled, so version-track the parser**: The status page is HTML emitted by printer firmware and can change shape across firmware versions. Therefore the parser targets a known page layout and records which layout/firmware it was written against (a parser-version constant); parsing must fail soft (unrecognized layout → status "unknown" + logged warning, never an exception reaching the print flow); treat the scrape as best-effort telemetry, not a contract.

**Deferred open decision — authenticated EWS access (NOT decided here)**: Logging into the EWS with the admin password exposes firmware version and the ability to change raster/printer settings via authenticated POSTs (which carry a CSRF token). This is materially different from read-only status — it means storing the printer admin credential and performing writes against device config. That needs its own decision (security posture, where the password lives, whether write access is in scope for a single-user homelab tool). Flagged as a future fork; deliberately out of scope here.

**Would revisit if**: the EWS page format proves too unstable across firmware to parse reliably, or a feature need pulls the authenticated-EWS decision onto the table.

---

## 2026-05-20 (b) — Settings: DB rows are source of truth, env is bootstrap default

**Decision**: User-adjustable preferences live in the SQLite `settings` table and are the source of truth at runtime. Code holds the default for each setting. Environment variables are NOT the runtime source for these preferences — with one bridge: the `default_label_media` setting falls back to the env value (`config.settings.default_label_media`) when no DB row exists. All other settings fall back to their code-defined defaults.

**Why**: `config.py` already reads `default_label_media` from env, and `features/settings.md` lists the same key as a DB-backed setting — an overlap that needed resolving. The settings doc's model is "defaults in code, DB stores overrides," which fits a UI that lets the user change preferences at runtime (env changes require a container restart; DB changes don't). Making the DB authoritative means the Settings UI is the single place a preference is owned. The one env bridge (`default_label_media`) preserves the existing env-based bootstrap so a fresh install with no DB rows still honors a deployer's configured default.

**Considered**:

- **Env always wins** — rejected. A runtime Settings UI that can't actually change a setting without a container restart is a confusing UI; env is for deploy-time bootstrap, not live preferences.
- **Ignore env entirely, code defaults only** — rejected. Throws away the existing `default_label_media` env bootstrap that deployers may already rely on.
- **DB authoritative, env bridges `default_label_media` only** — chosen. DB owns runtime prefs; the existing env bootstrap is preserved for the one key that already had it.

**Consequence**: The settings store reads DB-first, then default; for `default_label_media` the default is the env value rather than a hardcoded literal. `features/settings.md` should note this precedence so the env/DB relationship is documented where settings are specified.

**Would revisit if**: more settings need a deploy-time env bootstrap (then generalize the bridge into a per-key "env default" mechanism rather than special-casing one key).

---

## 2026-05-20 — Templates render server-side from element data, not from a browser-exported image

**Decision**: A template stores its design as structured element data (the canvas scene plus per-element `labelforge_*` content with `{placeholders}`). At print/preview time the **server** resolves placeholder values into element content and rasterizes the scene to a Pillow bitmap. The rendered bitmap is the source of truth for both preview and print. The browser is never in the print path.

**Why**: The API contract is "a client passes *values* for a named template and the server prints that template with those values" (`POST /api/print/{name}` with `{fields: {...}}`). The client sends values, not an image. Any client — a script, a webhook, a phone shortcut, a home-automation call, or the app's own UI — must get the same result with no browser involved. Therefore the server must hold the design and render it itself. This is also what `architecture.md` already assumes (Pillow is the rendering source of truth) and what `features/templates.md` implies (QR/barcode regenerated server-side from the resolved payload).

**Considered**:
- **Browser exports a PNG, server prints that bitmap** — rejected. Breaks the core API contract: a headless client has no browser, so it could not render a template at all. Only the UI could ever print. This defeats the reason the API exists.
- **Headless browser on the server (Playwright/Puppeteer renders Fabric)** — rejected for v1. Faithful to the editor, but drags a full browser + Node runtime into the `python:3.12-slim` runtime image, inflating image size and ops weight against the single-small-container design. Disproportionate for a single-user homelab tool.
- **Server re-renders from element data with Pillow** — chosen. Browser-free, keeps the runtime image lean, and makes the API work for every client by construction. QR via `qrcode[pil]`, barcodes via `python-barcode`, text/line/rect/image via Pillow.

**Consequence / known cost**: There are now two renderers of the same scene — the Fabric.js editor (authoring, in-browser) and the server-side Pillow renderer (preview + print). They must agree on geometry: coordinate origin, the 300dpi label scale, font metrics, and element transforms (`angle`, `scaleX`, `scaleY`). Divergence shows up as "preview/print doesn't match the editor." Mitigations: the editor operates in label-pixel coordinates at print DPI (per `features/templates.md`), and `POST /api/preview/{name}` returns the *server*-rendered bitmap so the user always previews the real output, not the editor's own canvas. The server renderer is the authority; the editor is an approximation of it.

**Would revisit if**: editor/server geometry drift becomes a recurring source of bugs that coordinate-matching can't tame, at which point a headless-browser renderer (accepting the image-size cost) returns to the table.

---

## 2026-05-20 — Print API reports `sent`, not `printed`, on the network backend

**Decision**: `POST /api/print/*` returns the print outcome verbatim from the brother_ql backend. For the network (TCP) backend this is `sent`, meaning the raster was transmitted but the result is unconfirmed. Only backends that can read printer status back (USB) return `printed`. The API never claims `printed` for a network send.

**Why**: The brother_ql network backend writes raster bytes and returns immediately — the QL-820NWB does not support status read-back over TCP, so the library cannot know whether a label actually printed. Reporting `printed` would be a lie that misleads API consumers (e.g. Home Assistant) into trusting a success that may not have happened. `sent` accurately means "transmitted, outcome unknown."

**Considered**:
- Always report `printed` on a successful send (rejected — false positive; hides real failures like a rejected roll)
- Add a follow-up status query after sending (rejected for v1 — the network backend doesn't reliably answer status requests; revisit with printer-status feature)

**Would revisit if**: the printer-status feature lands and we can poll for completion, or we add a USB backend path that confirms prints.

---

## 2026-05-20 — brother_ql `convert()` called with explicit `rotate="0"`

**Decision**: `printer/client.py` passes `rotate="0"` to `brother_ql.conversion.convert()` rather than relying on the library default of `rotate="auto"`. The renderer (`render/text.py`) produces images already in the correct orientation for the print head.

**Why**: `auto` rotation can flip a wide continuous image into a geometry that misrepresents the label width. Keeping `rotate="0"` makes the rendered image's pixel width (e.g. 696px for 62mm) the print-head width directly, matching what the renderer intends. Verified that for the current render path both produce identical rasters, but explicit-zero removes ambiguity if the renderer's output dimensions change.

**Would revisit if**: a future render path produces images in the feed-direction orientation, at which point rotation handling moves into the renderer or this flag changes accordingly.

---

## 2026-05-19 — Use `brother-ql-inventree` as the printer library

**Decision**: Take `brother-ql-inventree` (PyPI) as the printer protocol library. Pin as a normal dependency, do not fork.

**Considered**:
- `pklaus/brother_ql` (upstream): last release 2020, effectively abandoned
- `luxardolabs/brother_ql`: modern Python 3.13+ rewrite, but narrower printer scope (QL-810W to QL-1060N), unverified on QL-820NWB
- `matmair/brother_ql-inventree`: actively maintained, used in production by the InvenTree project, added explicit printer status query CLI, broader model support
- Forking: rejected — pre-emptive forks are a maintenance tax; fork only when upstream blocks us

**Why**: Production usage in InvenTree validates it for batch printing. Status query support unlocks the auto-detect feature day one. Model support includes the QL-820NWB explicitly.

**Would revisit if**: maintenance stops, a critical bug for QL-820NWB goes unfixed for >90 days, or a fork with materially better API ergonomics emerges with comparable test coverage.

---

## 2026-05-19 — License: GPL-3.0

**Decision**: Project license is GPL-3.0.

**Why**: The printer library is GPL-3.0. Linking (Python import) requires our distribution to be GPL-compatible. MIT/Apache/BSD are not options.

**Considered**: AGPL-3.0 — closes the SaaS-modification loophole. Rejected for v1 as overkill for a homelab tool; we can tighten later if it ever becomes relevant.

**Would revisit if**: someone forks and runs a modified hosted version, and we want to require those modifications to be public. Unlikely.

---

## 2026-05-19 — Name: `labelforge`

**Decision**: Project name is `labelforge`. Container, repo, hostname all match.

**Considered**: `qlforge`, `fast-ql`, `qlprint`, `labelbench`, `printpress`, `stickershop`.

**Why**: Generic enough to survive adding non-Brother printer support later. Reads correctly without prior knowledge. No trademark concerns. `fast-ql` was rejected because it reads as "fast SQL" to anyone not in the printer ecosystem.

**Would revisit if**: someone trademarks `labelforge` and serves a takedown notice. Unlikely.

---

## 2026-05-19 — Storage: SQLite, not Postgres

**Decision**: SQLite for templates, history, settings, API tokens. File-based, single user, no separate service.

**Why**: Single-container, single-user app. No concurrency requirements. SQLite is one file — trivial backup, no ops overhead. Postgres adds a service for zero benefit at this scale.

**Would revisit if**: multi-user becomes a requirement (it won't — see PRD out-of-scope) or write contention becomes measurable (it won't for one user).

---

## 2026-05-19 — Frontend: vanilla TS + Vite, no React

**Decision**: Frontend is plain TypeScript with Vite as the build tool. Fabric.js for the canvas. No component framework.

**Considered**: React (familiar, but build complexity and bundle size cost), Svelte (smaller bundle but less universally known), HTMX-only (rejected — the canvas editor is fundamentally client-side state).

**Why**: The UI is a small number of pages. The hard part is the canvas editor, which is Fabric.js — independent of any framework. A framework adds tax for no benefit at this surface area.

**Would revisit if**: the page count grows large enough that vanilla TS becomes painful (unlikely — see PRD scope), or we hire a contributor who only knows React.

---

## 2026-05-19 — Label catalog: library truth + yml UX layer (hybrid)

**Decision**: Library `brother_ql.info.labels()` is the authoritative list of printable media. `labels.yml` provides friendly names, descriptions, categories, and other UX metadata. The user-facing catalog is the intersection.

**Considered**:
- Library-only (no yml): rejected — raw library identifiers (`62`, `62red`, `29x90`) are not user-friendly and don't expose color capability or DK part numbers
- yml-only (parallel printability list): rejected — physically impossible to print on media the library doesn't support
- yml-driven with library validation: rejected — same problem, plus update friction

**Why**: Library knows what can be printed. Humans need names and context. Decoupling lets the catalog grow via PRs from anyone with a label roll, without touching print logic. Library updates Just Work.

**Would revisit if**: the library list gains rich enough metadata to make `labels.yml` redundant. Unlikely.

---

## 2026-05-19 — Auth: shared secret in env, no SSO, no token table for v1

**Decision**: A single `API_TOKEN` in `.env` protects all `/api/*` write endpoints. UI uses the same token internally. No per-user, no rotation, no SSO.

**Considered**:
- LAN-only no auth (rejected — we want Home Assistant to call this from anywhere)
- Token table in DB with UI for issuing/revoking (deferred — overkill for v1)
- SSO via Authentik/Authelia (rejected — explicitly out of scope per the session prompt)

**Would revisit if**: we want per-integration revocation (e.g. revoke the Home Assistant token without breaking the Paperless one). At that point: add a `tokens` table, keep the env token as a bootstrap admin.
