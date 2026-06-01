---
name: 2026-05-31-printer-status-spike
status: completed
created: 2026-05-31
model: sonnet
completed: 2026-05-31
result: ESC i S over port 9100 returns empty on QL-820NWB; get_printer() raises NotImplementedError for network; HTTP fallback at /general/status.html works unauthenticated; build prompt at prompts/2026-05-31-printer-status-build.md
---

# Task: Spike — can we read printer status over the `network` backend?

Confirm whether `brother-ql-inventree` (>=1.3) can read the QL-820NWB's status
(loaded media, ready state, errors) over the **network** backend before we commit
the Printer Status feature design. This is the single highest-risk unknown for that
feature, and it shapes the entire print-path design. **This is a spike: prove the
mechanism and write up findings — do not build the feature in this session.**

## Why this is in question

`backend/labelforge/printer/client.py:50-54` states plainly that **the network
backend cannot read back from the printer** — `send()` returns `'sent'` (transmitted,
result unknown), and only USB backends confirm an actual print. But
`docs/features/printer-status.md` assumes the QL-820NWB reports status *over its
network interface*. These two claims are in tension, and production runs
`printer_backend=network` (`config.py:11`). Resolve the contradiction with evidence.

The raw-9100 socket is bidirectional in principle (send the status-request command
`ESC i S` = `1B 69 53`, read the 32-byte reply), so it is *probably* achievable — but
whether the library's `send()` / network backend surfaces that read is unverified, and
the library is **not installed in the planning shell**, so it must be introspected in
the real backend environment (the container or a venv with deps installed).

## Before you start

- Read `docs/features/printer-status.md` (the feature spec — status mapping, error
  codes, API contract) and `docs/features/api.md` (the `GET /api/printer/status`
  200/503 shapes and the `media_mismatch` 409 shape).
- Read `backend/labelforge/printer/client.py` (current print path / send semantics)
  and `backend/labelforge/config.py` (printer host/model/backend).
- Settings keys already exist — `printer_status_check` and
  `printer_status_timeout_ms` are registered in `settings_store.py:27-28`. Do not
  re-add them.
- Standards: this is research, so the main risk is the vexp/grep rule and the
  commit-prefix rule — see `CLAUDE.md`. No feature code lands this session, so the
  changelog entry is for the docs/decision only.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files
this plan touches (the new ADR in `docs/decisions.md`, this prompt, and the build
prompt you'll author). If any have uncommitted changes, list them and ask before
touching. This file is exempt.

## What to do

1. **Introspect the installed library** in an environment where deps are present
   (the container, or `pip install -e .` into a venv). Determine concretely:
   - Does `brother_ql.backends` expose a status-read path for the `network` backend?
     Inspect `brother_ql.backends.helpers`, the network backend module, and any
     `status` module/parser. Note exact import paths and function signatures (mirror
     the verified-imports comment style at the top of `client.py`).
   - Is there a parser that turns the 32-byte status reply into a structure like the
     one in `printer-status.md` (media_type, media_width_mm, media_length_mm, model,
     error_information, status_type)? If yes, name it. If not, scope the thin wrapper
     we'd own.
2. **Test against the real QL-820NWB** (network backend, the configured host). Send a
   status request and capture the raw reply bytes. Confirm you can read back:
   - loaded media type + width/length (→ mappable to a library identifier like `"62"`)
   - ready / error state
   - the tape-color byte (for DK red-capable detection — in v1 scope per the owner).
   If reading back over `network` does **not** work, document exactly how it fails
   (timeout? socket closed? no read API?) and what the fallback is (degrade
   gracefully: skip check, proceed, log — per `printer-status.md` print-path flow).
3. **Write up findings** in an ADR entry in `docs/decisions.md`: can we read status
   over `network` (yes/no/partial), the exact import + call path, the status→library-id
   mapping approach, color-capability detection feasibility, and the graceful-degrade
   behavior when status is unavailable.
4. **Author the build handoff prompt** `prompts/2026-05-31-printer-status-build.md`
   from `prompts/TEMPLATE.md` (`model: sonnet`), encoding the confirmed design. Its
   scope (all four, per owner decision):
   - status-read fn in `printer/client.py` + `GET /api/printer/status` (200/503 per
     `api.md`) + new printer router registered in `main.py` (note: `main.py` currently
     registers no printer router — add `app.include_router(..., prefix="/api")`).
   - pre-print media check in `routes/print.py`: compare loaded vs expected, `409
     media_mismatch` with `override=true` escape hatch, graceful degrade on
     timeout/unsupported (honor `printer_status_check` / `printer_status_timeout_ms`).
   - Settings **Test printer** button (frontend) calling the status endpoint.
   - color-capability detection (DK red) from the tape-color byte.
   Hand the owner the exact run command for it (file-path form, sonnet model).

## Conventions to honor

- Don't `grep`/`glob` the codebase — `run_pipeline` first (vexp rule, `CLAUDE.md`).
- Verify library import paths against the actually-installed version; mirror the
  verified-imports comment block in `client.py`.
- All work on `dev`. Commit, don't push. No `Co-authored-by:` trailers.
- Add a one-line `CHANGELOG.md` entry under `## [Unreleased]` for the decision/ADR
  if anything user-facing is implied; otherwise the ADR alone is fine for a spike.

## When done

1. Update this file's frontmatter: `status`, `completed` (the date), `result` (one line
   — did network status-read work, and where the build prompt lives).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the spike outcome as an ADR in `docs/decisions.md`.
4. Propose ONE commit covering the files modified (ADR, the new build prompt, this
   prompt's move). Present the file list + a one-line `docs:` or `chore:` message and
   ask `commit these as "<message>"? (y/n)`. On `y`, stage those specific paths and
   commit on `dev`. Never `git add -A`. Never push.
