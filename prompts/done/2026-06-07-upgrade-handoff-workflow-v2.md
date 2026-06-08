---
name: 2026-06-07-upgrade-handoff-workflow-v2
status: completed
created: 2026-06-07
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-06-07
result: Upgraded handoff-prompt-workflow adoption from v1.5.0 to v2.0.0; TEMPLATE re-synced, canonical snippet pasted, standards.md pin bumped.
---

# Task: Upgrade handoff-prompt-workflow adoption from v1.5.0 → v2.0.0

The `handoff-prompt-workflow` standard bumped to **v2.0.0** in the crzynet
`homelab-configs` repo. labelforge currently pins **1.5.0**. This task performs the
clean swap described in the standard's "Upgrading an existing adopter" section: re-sync
the TEMPLATE, paste the canonical CLAUDE-snippet, and bump the pin. **This is a
config/docs sync only — no app code changes.**

## Before you start

Read the current standard and the two artifacts you'll be syncing. They are on disk in
this WSL host (the adopter happens to have `homelab-configs` checked out locally — use
the local files, do not WebFetch):

- Standard README: `/home/mande/projects/homelab-configs/standards/handoff-prompt-workflow/README.md`
  (read the "Upgrading an existing adopter" section — it's the authority for these steps)
- New snippet: `/home/mande/projects/homelab-configs/standards/handoff-prompt-workflow/CLAUDE-snippet.md`
- New template: `/home/mande/projects/homelab-configs/standards/handoff-prompt-workflow/TEMPLATE.md`

What's new in v2.0.0 (so you understand WHY each edit matters):
- Edit-size threshold is now a **hard rule** (>~2 files → must write a handoff prompt).
- Handoffs are **executed by a spawned subagent by default**, not handed to the user as
  a `claude --model ...` command. The manual launch command is now a fallback only on
  explicit user request.
- A canonical **CLAUDE-snippet must be pasted verbatim** into `CLAUDE.md` (v1.x adopters
  like labelforge only had hand-written prose — that prose is now superseded).
- Commit flow: the prompt is **not** committed up front; it bundles into one end commit.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files this
plan modifies (listed below). If any have uncommitted changes, list them and ask before
touching. Surface unrelated dirty files once as awareness; don't block. This prompt file
itself is exempt.

## What to do

Three standard-owned edits. **Do not touch any existing prompt files** in `prompts/`,
`prompts/done/`, or `docs/decisions.md` history — those are the project ledger, not the
standard's footprint.

### 1. Re-sync `prompts/TEMPLATE.md`

Overwrite `prompts/TEMPLATE.md` with the current TEMPLATE.md from the standard (path
above), verbatim. (The only substantive delta is the "When done" step 4, which now
splits spawned-agent vs. manual-fallback commit behavior — but copy the whole file so
it stays a faithful mirror.)

### 2. Swap the handoff prose in `CLAUDE.md` for the canonical snippet

labelforge's `CLAUDE.md` currently expresses this standard as prose inside the
`## Session workflow` section (around lines 65–91). That section **interleaves**
handoff mechanics with project-specific rules. Separate them cleanly:

a. **Add a new verbatim snippet section.** Paste the full body of the standard's
   `CLAUDE-snippet.md` (the `## Handoff prompts (operational rules)` block, including
   the leading HTML source comment) into `CLAUDE.md` **near the other operational-rules
   sections at the bottom** — place it immediately **before** `## Code check-in
   (operational rules)`. This matches labelforge's existing pattern (code-checkin and
   release standards each have a verbatim "(operational rules)" section there). Paste it
   exactly; do not reword.

b. **Trim the `## Session workflow` section** so it no longer duplicates or contradicts
   the snippet:
   - **Replace old steps 1–4** (Plan first / Decide / Handoff prompts live in / To run a
     handoff prompt) with a short lead-in that keeps the **plan → decide → execute →
     document** framing and **points to the new "Handoff prompts (operational rules)"
     section** for the mechanics. Crucially, the old **step 4** ("hand the user this
     exact command") is **superseded by v2.0.0** (spawn an agent by default) — it must
     not survive as a standalone instruction; the snippet now owns that rule.
   - **Keep the project-specific steps that are NOT owned by this standard**, reworded as
     needed so numbering stays sane:
     - Changelog entry required (old step 5) — **keep**.
     - All dev work on `dev` (old step 6) — **keep**.
     - Commit, don't push (old step 7) — **keep**.
     - Planning prompts for large features (old step 8) — **keep**.
   - Result: `## Session workflow` becomes a brief intro (plan→decide→execute→document +
     "see Handoff prompts (operational rules) below") followed by the four project rules
     above. No loss of the changelog / dev-branch / commit-don't-push / planning-prompt
     guidance.

   Use judgment to keep prose tight and non-duplicative — the snippet is the source of
   truth for handoff mechanics; `CLAUDE.md`'s own section should not restate them.

### 3. Bump the pin in `standards.md`

In the `handoff-prompt-workflow` row of the table in `standards.md`:
- Version `1.5.0` → `2.0.0`
- Adopted date → `2026-06-07`
- Rewrite the Notes cell to reflect v2.0.0: upgraded from 1.5.0; TEMPLATE re-synced;
  canonical CLAUDE-snippet pasted verbatim (replacing the old hand-written handoff prose
  in `## Session workflow`); key v2.0.0 changes = hard edit-size threshold + spawn-agent-
  by-default execution (manual launch command demoted to fallback) + one-end-commit flow.
  Keep the "Origin project for this standard" note.

## Conventions to honor

- **No changelog entry** — this is internal process/docs tooling, not user-facing. (The
  CHANGELOG is for app-visible changes; a standards-pin bump doesn't qualify.)
- LF line endings only.
- Match the existing terse style of `CLAUDE.md` and `standards.md`.
- This project **also adopts `code-checkin-and-pr`**, so its rules apply on top: work on
  the current `dev` branch, Conventional-Commits prefix, **no `Co-authored-by:`
  trailers**, never push.

## When done

1. Update this file's frontmatter: set `status` (completed/failed), `completed`
   (2026-06-07), and `result` (one line).
2. `git mv` this file into `prompts/done/` (on success) or `prompts/failed/` (on
   failure).
3. Record any non-obvious decision in `docs/decisions.md` (newest at top) — e.g. how you
   split the `## Session workflow` section between the snippet and the retained
   project rules, if that call was non-trivial. (A new ADR entry is optional if the
   split was mechanical.)
4. **You are a spawned agent: do NOT commit.** Prepare the working tree, then report
   back to the orchestrating session:
   - the list of files changed (expected: `prompts/TEMPLATE.md`, `CLAUDE.md`,
     `standards.md`, this prompt moved to `prompts/done/`, and `docs/decisions.md` if
     you added an entry),
   - a proposed one-line commit message (suggest:
     `chore: upgrade handoff-prompt-workflow adoption to v2.0.0`),
   - anything you flagged or decided.
   The orchestrating session surfaces the `y/n` commit proposal to the user. Never
   `git add -A`, never push, never auto-commit.

## Registry note (cannot be done from this repo)

The standard's step 6 says the adoption is also registered in
`homelab-configs/projects/labelforge/README.md` and the table in
`projects/README.md`. Those live in the `homelab-configs` repo, not here. **Do not edit
them** — instead, include in your report a one-line note that the registry pin for
`handoff-prompt-workflow` should be bumped to 2.0.0 (2026-06-07) over in
`homelab-configs`, so the user can land it there separately.
