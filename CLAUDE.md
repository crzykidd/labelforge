# CLAUDE.md

Context for AI coding sessions in this repo. Read this before doing anything.

## What this is

`labelforge` — self-hosted web app for printing labels to Brother QL series printers, with saved templates, variable fields, an HTTP API for homelab integrations, and a freeform canvas editor.

Owner: crzykidd. Personal homelab project, public open source. Single-user app — no multi-user features.

## Build Status

- **Last shipped:** v0.1.0 (first release)
- **Target for next release:** TBD

## Standards

This project implements shared engineering standards from the crzynet `homelab-configs` repo. **Read [`standards.md`](standards.md) at the repo root on session start** whenever the work could touch branching, commits, PRs, handoff prompts, or the sandbox — it pins which standards and versions this repo conforms to. The hard per-session operational rules from those standards are pasted verbatim at the end of this file (Code check-in; Release process).

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
- **No SSO** (Authentik, Authelia, etc.). Auth is a single shared secret from `.env`. Do not propose SSO under any circumstances. App-level auth can be disabled with `DISABLE_AUTH=true` (default-off, for deployments fronted by a reverse proxy that handles auth — see ADR 2026-06-02); that is *not* SSO and does not relax this rule. Still no multi-user / accounts.
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
3. **Handoff prompts live in `prompts/`** (checked into git), per the `handoff-prompt-workflow` standard pinned in [`standards.md`](standards.md). The top-level `prompts/` dir is the **live queue** — pending work only. Start new prompts from `prompts/TEMPLATE.md`. Frontmatter:
   ```yaml
   ---
   name: YYYY-MM-DD-short-description
   status: pending          # pending | completed | failed
   created: YYYY-MM-DD
   model:                   # opus = research/planning, sonnet = coding
   completed:               # filled when done
   result:                  # one-line summary of outcome
   ---
   ```
   Before making edits, run `git status --porcelain` and cross-reference the files the plan touches; if any overlap with uncommitted work, list them and ask before touching. The **last instruction** in every handoff prompt: update its own frontmatter (status / completed / result), then `git mv` it into `prompts/done/` (success) or `prompts/failed/` (failure) — created lazily on first use. Record non-obvious decisions (approach changed, alternative rejected, workaround needed) in `docs/decisions.md` as an ADR entry.
4. **To run a handoff prompt** — the moment you create one, hand the user this exact command (file-path form, never inlined `cat`):
   ```
   claude --model <model> "Read prompts/<file>.md and execute it as your task."
   ```
   `<model>` matches the prompt's `model:` field (opus = research/planning, sonnet = coding; omit to use the default). Run from the repo root so the relative path resolves.
5. **Changelog entry required.** Every change — feature, fix, refactor — gets a short entry in `CHANGELOG.md` under `## [Unreleased]`. Write it for release notes (concise, user-facing language).
6. **All dev work on `dev`** unless explicitly told otherwise.
7. **Commit, don't push.** Sessions commit their work with a descriptive message. The owner pushes.
8. **Planning prompts for large features.** The owner will ask for a planning session prompt when scoping a new feature block. That prompt gets handed to a fresh session to execute.

## Repo conventions

- Line endings: LF only. `.gitattributes` enforces this. If `git diff --stat` shows all files modified, run `git config core.autocrlf input && git checkout -- .`
- Branches: `main` is protected — the ONLY way in is a pull request, gated by CodeQL and other checks; never push to `main` directly. `dev` is the working branch (solo work commits straight to `dev`). Use `feature/<name>` branches when more than one person is working; merge those to `dev`, then PR `dev` → `main` for a release.
- Commits: imperative present tense with a Conventional-Commits prefix — `feat:` (user-facing feature), `fix:` (bug fix), `chore:` (config/tooling/deps), `docs:` (docs only). E.g. `feat: add template recall endpoint`. No co-author tags. See the **Code check-in (operational rules)** section below for the full rule set.
- Compose stack lives at the repo root as `docker-compose.yml`. Dev compose at `docker-compose.dev.yml`.

## Things to never do

- Don't add features outside the PRD without asking
- Don't add multi-user, RBAC, or SSO
- Don't replace SQLite with Postgres without an ADR
- Don't replace the canvas editor with a non-canvas approach
- Don't auto-update the label catalog from the internet
- Don't suggest hosted/SaaS replacements for any component
- Don't write giant explainer comments in code — code should be readable; comments only for non-obvious *why*
- Don't generate `package.json` / `pyproject.toml` / `Dockerfile` until the relevant slice has been scoped

<!--
Source: standards/code-checkin-and-pr @ v1.1.0 (crzynet/homelab-configs).
Paste the section below verbatim into the adopting project's CLAUDE.md.
The full standard (publishing matrix, retention, CI check definitions) lives at:
https://gitea.crzynet.com/crzynet/homelab-configs/src/branch/main/standards/code-checkin-and-pr/README.md
-->

## Code check-in (operational rules)

This project adopts the `code-checkin-and-pr` standard. The full why-and-how lives at
the source above; the rules below are the per-session do/don'ts a coding agent must
honor by default:

- **Never push directly to `main`.** `main` is protected. All changes land via a pull
  request from `dev` → `main`, and only when every required check is green.
- **Day-to-day work happens on `dev`** (or a short-lived branch off `dev`). Push to
  `dev` freely.
- **Commit message prefixes are required** — Conventional-Commits style:
  - `feat:` — new user-facing feature
  - `fix:` — bug fix
  - `chore:` — config, tooling, dependencies, maintenance
  - `docs:` — documentation-only changes
- **Do not add `Co-authored-by:` trailers** unless the user explicitly asks.
- **Doc updates ship in the same commit as the code they describe** — never as a
  follow-up commit.
- **Never bypass hooks** (no `--no-verify`, `--no-gpg-sign`, etc.) unless the user
  explicitly asks. If a hook fails, fix the underlying issue.
- **Stable releases are tagged from `main` only.** Don't tag from `dev`.

If you're unsure whether an action would violate one of the above, stop and ask before
acting.

<!--
Source: standards/release-prep-and-cut @ v1.0.0 (crzynet/homelab-configs).
Paste the section below verbatim into the adopting project's CLAUDE.md.
The full standard (two-phase prep/cut workflow, archive trigger, validation
steps, adoption checklist) lives at:
https://gitea.crzynet.com/crzynet/homelab-configs/src/branch/main/standards/release-prep-and-cut/README.md
-->

## Release process (operational rules)

This project adopts the `release-prep-and-cut` standard. The full why-and-how
lives at the source above; the rules below are the per-session do/don'ts a
coding agent must honor by default:

- **The version is stored BARE in the source-of-truth file** — no `v` prefix
  anywhere in code. The `v` prefix is added in exactly one place: the git tag
  and matching GitHub release name. Don't add it to README badges, CHANGELOG
  headers, in-code image tags, or anywhere else.
- **`CHANGELOG.md` is the single source of truth for release notes.** The PR
  description (set by `/release-prep`) and the GitHub release body (set by
  `/release-cut`) reuse the **same section verbatim**. Never author release
  notes twice.
- **One commit per release prep.** Version bump + changelog roll + every doc
  sync ship in a single `chore(release): prepare v<version>` commit. No
  `Co-authored-by:` trailers.
- **Never re-tag.** If `v<version>` already exists as a local tag, a remote
  tag, or a GitHub release, STOP. Never delete-and-recreate; never `--force`.
  Pick the next version instead.
- **`/release-cut` only after the PR has merged and CI is green.** The
  publish-to-`main` workflow must have already pushed `:latest` images to the
  registry before `/release-cut` runs. If you cannot confirm both — STOP and
  tell the user to wait.
- **The release tag is the only thing the cut command writes to `main`.** Both
  the prep commit and any follow-up docs commit land on `dev` and reach `main`
  only via PR. Never push directly to `main` as part of a release.

If you're unsure whether an action would violate one of the above, stop and
ask before acting.
