# Decisions

Architecture Decision Records, newest at the top. Each entry: what we decided, why, what we considered, and what would cause us to revisit.

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
