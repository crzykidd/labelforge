---
name: 2026-06-07-readme-whats-new-tiered-format
status: completed
created: 2026-06-07
model: sonnet            # docs/process edits, clear spec
completed: 2026-06-07
result: Reformatted v0.1.1 and v0.1.2 README entries to compact tiered format; updated release-prep Step 4 with tiered instructions and anchor-slug rule; added CHANGELOG entry and ADR.
---

# Task: Tiered README "What's New" format + make it the release standard

Adopt a two-tier "What's New" format in `README.md` and bake it into the release
process so every future release follows it:

- **Feature releases (`vX.Y.0`, i.e. PATCH == 0)** — keep a larger overview entry,
  exactly like the current `### v0.1.0` entry.
- **Patch releases (`vX.Y.Z`, PATCH > 0)** — compact entry: the version heading with a
  "What's New" link to that release's `CHANGELOG.md` section, then a one-line
  description below.

Reformat the existing `v0.1.1` and `v0.1.2` entries to the compact form now, and update
`.claude/commands/release-prep.md` so the convention is standard going forward.

## Decisions already made (do not re-litigate)

- **Chosen format = "link next to version"** (link on the heading line):
  ```
  ### v0.1.2 (2026-06-07) — [What's New](CHANGELOG.md#012--2026-06-07)
  Fixes the published container image so `docker pull` works again.
  ```
- Feature (`.0`) releases keep the full overview; do NOT compact `v0.1.0`.
- The link label is exactly `What's New`; target is the changelog anchor for that
  version's section.

## Before you start

Read:
- `README.md` — the current `## What's New` section (entries for v0.1.2, v0.1.1, v0.1.0).
- `CHANGELOG.md` — the `## [0.1.2] — 2026-06-07` and `## [0.1.1] — 2026-06-06` sections
  (source for the one-liners and the anchor targets).
- `.claude/commands/release-prep.md` — Step 4 "Sync the README" (item 2 is what you'll
  amend).
- `CLAUDE.md` "Release process (operational rules)" — do NOT edit it (it's a
  verbatim-from-standard section); just be aware of it.
- `docs/decisions.md` — newest-at-top ADR format (you'll add an entry).

## Working tree check

Run `git status --porcelain`; the tree should be clean (last commit `11b7f50`). If any
file this plan touches is dirty, list it and ask before proceeding. This prompt file is
exempt.

## What to do

### 1. Reformat `README.md` "What's New"

Replace the current multi-paragraph `### v0.1.2` and `### v0.1.1` entries with compact
entries in the chosen format. Leave `### v0.1.0` (the overview) unchanged.

Target result (verify the anchors — see note below):

```
### v0.1.2 (2026-06-07) — [What's New](CHANGELOG.md#012--2026-06-07)
Fixes the published container image so `docker pull` of `:latest` works again.

### v0.1.1 (2026-06-06) — [What's New](CHANGELOG.md#011--2026-06-06)
Deployment reliability: fail-fast startup logging, correct `DATA_DIR` permissions, and rolled-in dependency updates.
```

Tighten the one-liners if you can do so more accurately from the changelog, but keep
them to a single line each and in the existing voice.

**Anchor note:** GitHub heading slugs lowercase the text, drop characters that aren't
alphanumeric / space / hyphen (so `[`, `]`, `.`, and the em-dash `—` are removed), then
replace each remaining space with a hyphen. For `## [0.1.2] — 2026-06-07` that yields
`#012--2026-06-07` (the two spaces around the removed em-dash become `--`); for
`## [0.1.1] — 2026-06-06`, `#011--2026-06-06`. Use those. If you have any doubt the
double-hyphen is right, fall back to linking the whole file (`CHANGELOG.md`) rather than
shipping a broken fragment — but prefer the anchored link.

Do not touch the rest of README (status line, `**Version:** 0.1.2`, the body sections).

### 2. Encode the standard in `.claude/commands/release-prep.md`

Rewrite Step 4 item 2 (the "Add a `### v$ARGUMENTS (<today>)` entry…" instruction) so it
prescribes the tiered format:

- If the release is a **feature release** (PATCH == 0, i.e. a new minor/major): add a
  full **overview** entry (a short paragraph covering the headline features), matching
  the voice of the `v0.1.0` entry.
- If the release is a **patch release** (PATCH > 0): add a **compact** entry in the
  form `### v$ARGUMENTS (<today>) — [What's New](CHANGELOG.md#<anchor>)` followed by a
  one-line description on the next line. Document the anchor-slug rule (lowercase, drop
  non-alphanumeric/space/hyphen incl. `.` `[` `]` `—`, spaces → hyphens) with the
  `#012--2026-06-07` worked example so future runs compute it correctly.

Keep the rest of the command file intact. Match its existing wording/voice.

### 3. Changelog + ADR

- **`CHANGELOG.md`** `## [Unreleased]`: add a `### Changed` (or `### Docs`-style, match
  existing categories — use `Changed`) entry, e.g. *"README 'What's New' now uses a
  tiered format — feature releases keep a full overview, patch releases get a one-line
  summary linking to the changelog; `/release-prep` updated to match."*
- **`docs/decisions.md`**: new ADR at the top (`2026-06-07`) recording the tiered
  "What's New" convention, why (keep the README scannable — full overview for feature
  releases, one-liner + changelog link for patches), where it's enforced
  (`.claude/commands/release-prep.md` Step 4), and what would cause a revisit.

## Conventions to honor

- LF line endings; match the surrounding doc voice; no scope creep beyond the files
  listed (README.md, `.claude/commands/release-prep.md`, CHANGELOG.md, docs/decisions.md,
  this prompt).
- Changelog entry required; docs ship in the SAME commit. Commit prefix `docs:`; no
  `Co-authored-by:`.

## Verify

- `README.md` renders: two compact entries (v0.1.2, v0.1.1) + the unchanged v0.1.0
  overview; the two changelog links use the computed anchors.
- `git diff README.md` shows only the v0.1.1 / v0.1.2 entries changed.
- `.claude/commands/release-prep.md` Step 4 now describes the tiered format with the
  anchor rule.

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-07`, one-line `result`).
2. `git mv` this file to `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the ADR (step 3).
4. **You are a spawned agent: do NOT commit.** Prepare the tree and report back: a
   per-file summary, the final `git status --porcelain`, a proposed one-line `docs:`
   commit message, the explicit paths to stage, and your verify notes (including the
   exact anchor strings you used). Never `git add -A`, never push, never auto-commit.
