# CLAUDE.md

Context for AI coding sessions in this repo. Read this before doing anything.

## What this is

`labelforge` — self-hosted web app for printing labels to Brother QL series printers, with saved templates, variable fields, an HTTP API for homelab integrations, and a freeform canvas editor.

Owner: crzykidd. Personal homelab project, public open source. Single-user app — no multi-user features.

## Source of truth

The design is in `docs/`. Do not invent features not described there. If a request expands scope, push back and ask whether the PRD should change first.

- `docs/PRD.md` — purpose, users, scope, non-goals
- `docs/architecture.md` — stack, deployment, repo layout
- `docs/glossary.md` — vocabulary (template, element, field, media...)
- `docs/decisions.md` — ADR log; consult before contradicting a past decision
- `docs/features/*.md` — per-feature designs; load only the ones the current task touches

When working on a task, load the relevant feature doc(s) plus `architecture.md` and `glossary.md`. Do not load the whole `docs/` tree by default.

## Stack (locked)

- **Backend**: Python 3.12+, FastAPI, Pydantic v2, SQLite (file-based, single user)
- **Printer**: `brother-ql-inventree` from PyPI (`matmair/brother_ql-inventree` fork) — do not switch without an ADR
- **Rendering**: Pillow for server-side label rasterization; `qrcode[pil]` for QR; `python-barcode` for barcodes
- **Config**: PyYAML for the label catalog
- **Frontend**: Vite + TypeScript, vanilla (no React/Vue/Svelte), Fabric.js for the canvas
- **Deployment**: single Docker container, multi-stage build (frontend → static assets → served by FastAPI)
- **Container image**: built from the included `Dockerfile`; publish to whatever registry you use.

## Non-negotiables

- **License is GPL-3.0.** Cannot be relaxed (the printer library is GPL-3.0).
- **No SSO** (Authentik, Authelia, etc.). Auth is a single shared secret from `.env`. Do not propose SSO under any circumstances.
- **No SaaS dependencies.** Self-hosted only. No cloud functions, no hosted databases, no third-party APIs that aren't user-controllable.
- **No Next.js, no SSR frameworks.** Frontend is a static SPA served from the FastAPI container.
- **No alternative printer libraries** without an ADR. We picked `brother-ql-inventree` after evaluation.
- **Data path**: the app reads/writes everything under `$DATA_DIR` (default `/data` in the container): SQLite at `$DATA_DIR/data/app.db`, label catalog at `$DATA_DIR/labels.yml`, fonts at `$DATA_DIR/fonts/`, optional preview images at `$DATA_DIR/label-previews/`. How that path is backed (named volume, bind mount) is the operator's choice.

## Working style

From the session prompt that owns this project:

- Direct, decisive — commit to a position, adjust if corrected
- Short answers with concrete commands beat long explanations
- One file at a time unless they're tightly coupled
- Show file paths before code
- After each task, give a one-line "run this to verify" and stop
- If you find yourself making more than one assumption to keep going, **stop and ask**
- Use artifacts for code files to save; inline for snippets to read once
- Don't write a 50-line README before there's code
- Don't propose features not in the PRD

## Session workflow

Every task follows: **plan → decide → execute → document**.

1. **Plan first.** Before writing code, outline what will change and why. For small fixes the plan can be verbal in-session. For larger features, produce a handoff prompt (see below).
2. **Decide: current session or handoff.** If the plan is scoped and the current session has context, do it here. If it's a large feature slice or a fresh context would be cleaner, write a handoff prompt for a new session.
3. **Handoff prompts live in `prompts/`.** Checked into git. Format:
   ```
   prompts/YYYY-MM-DD-short-description.md
   ```
   Frontmatter:
   ```yaml
   ---
   name: YYYY-MM-DD-short-description
   status: pending          # pending | completed | failed
   created: YYYY-MM-DD
   completed:               # filled when done
   result:                  # one-line summary of outcome
   ---
   ```
   The **last instruction** in every handoff prompt must be: update this file's frontmatter — set status, completed date, and result summary.
4. **To run a handoff prompt:** `claude -- "$(cat prompts/file.md)"` (interactive session with file as opening prompt)
5. **Changelog entry required.** Every change — feature, fix, refactor — gets a short entry in `CHANGELOG.md` under `## [Unreleased]`. Write it for release notes (concise, user-facing language).
6. **All dev work on `dev`** unless explicitly told otherwise.
7. **Commit, don't push.** Sessions commit their work with a descriptive message. The owner pushes.
8. **Planning prompts for large features.** The owner will ask for a planning session prompt when scoping a new feature block. That prompt gets handed to a fresh session to execute.

## Repo conventions

- Line endings: LF only. `.gitattributes` enforces this. If `git diff --stat` shows all files modified, run `git config core.autocrlf input && git checkout -- .`
- Branches: `main` is protected — the ONLY way in is a pull request, gated by CodeQL and other checks; never push to `main` directly. `dev` is the working branch (solo work commits straight to `dev`). Use `feature/<name>` branches when more than one person is working; merge those to `dev`, then PR `dev` → `main` for a release.
- Commits: imperative present tense ("Add template recall endpoint" not "Added"). No conventional-commits prefixes. No co-author tags.
- Compose stack lives at the repo root as `compose.yml`. Dev compose at `compose.dev.yml`.

## Things to never do

- Don't add features outside the PRD without asking
- Don't add multi-user, RBAC, or SSO
- Don't replace SQLite with Postgres without an ADR
- Don't replace the canvas editor with a non-canvas approach
- Don't auto-update the label catalog from the internet
- Don't suggest hosted/SaaS replacements for any component
- Don't write giant explainer comments in code — code should be readable; comments only for non-obvious *why*
- Don't generate `package.json` / `pyproject.toml` / `Dockerfile` until the relevant slice has been scoped
