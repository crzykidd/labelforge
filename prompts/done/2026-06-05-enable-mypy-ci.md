---
name: 2026-06-05-enable-mypy-ci
status: completed
created: 2026-06-05
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-06-05
result: mypy added to dev deps, [tool.mypy] config with pydantic plugin + per-module overrides, 11 type errors fixed (Pillow resampling, client.py no-redef, history.py assert, text.py int cast, printer.py return type)
---

# Task: Make the CI `mypy backend` step real and green

CI runs `mypy backend` (`.github/workflows/ci.yml`, `python` job) but **mypy is not in the
dev dependencies and there is no `[tool.mypy]` config**, so the step fails with
`mypy: command not found` (exit 127) and the code has never actually been type-checked.
Turning it on already paid off once: it caught a live `AttributeError` crash in
`templates/store.py` (since fixed). This task installs mypy, configures it, and fixes the
remaining type errors so the step passes.

## Before you start

- Read `docs/architecture.md`. Load the files listed under "Errors to fix" before editing.
- ruff config and dev extras live in `pyproject.toml`. The dev extra currently has
  `pytest`, `httpx`, `ruff` — **no mypy**.
- Stack is locked: Pillow for rendering, `brother-ql-inventree`, FastAPI, pydantic-settings.
- Work on `dev`. Conventional-Commits prefixes, no `Co-authored-by:`, docs ship with code.
- **Fix root causes, don't just silence mypy.** Reach for `# type: ignore[code]` only where a
  fix isn't appropriate (noted per-item below). Each ignore must be specific (carry the
  error code) and have a one-line reason.

## Working tree check

Run `git status --porcelain` first. This touches `pyproject.toml` and ~7 files under
`backend/labelforge/`. If any show uncommitted changes you didn't expect, list them and ask.

## What to do

### 1. Add mypy + config

- Add `mypy` to `[project.optional-dependencies].dev` in `pyproject.toml`.
- Add a `[tool.mypy]` section: `python_version = "3.12"`, `mypy_path = "backend"`,
  `packages = ["labelforge"]` (or rely on the CI `mypy backend` invocation — keep it
  consistent with how CI calls it). Enable the **pydantic plugin**:
  `plugins = ["pydantic.mypy"]`.
- The third-party libs have no type stubs (≈14 `import-untyped` errors: `brother_ql.*`,
  `qrcode.*`, `barcode.*`, `yaml`, etc.). Handle them with **per-module overrides**, not a
  blanket global ignore, e.g.:
  ```toml
  [[tool.mypy.overrides]]
  module = ["brother_ql.*", "qrcode.*", "barcode.*", "PIL.*"]
  ignore_missing_imports = true
  ```
  For `yaml`, prefer adding `types-PyYAML` to the dev extra (real stubs) over ignoring it.
  Run mypy and add any remaining unstubbed modules to the override list rather than going
  global. Goal: keep type-checking strict on **our** code.

### 2. Fix the real errors (11)

Run `mypy backend` after each cluster to confirm. Current findings:

- **Pillow resampling — `render/template.py:106,173,178,202`** (`attr-defined`:
  `Image.BICUBIC` / `Image.NEAREST`). These top-level constants were removed from the type
  stubs (and are deprecated at runtime since Pillow 9.1). Replace with the modern enum:
  `Image.Resampling.BICUBIC`, `Image.Resampling.NEAREST`. Runtime-equivalent and future-proofs
  the pending Pillow 12 bump.
- **`printer/client.py:215-216`** (`no-redef`: `width_mm`, `length_mm`). Not a logic bug —
  the TCP branch (≈line 184) assigns these and returns early; the HTTP-fallback branch then
  *re-annotates* them (`width_mm: int | None = None`), which mypy reads as a redefinition.
  Drop the type annotation on the fallback assignments (plain `width_mm = None`), or hoist a
  single annotated declaration above both branches. Don't change behavior.
- **`history.py:45-46`** (`arg-type` / `return-value`: `int | None`). `job_id =
  cursor.lastrowid` is typed `int | None`. After an INSERT it's reliably set, so guard it:
  `job_id = cursor.lastrowid; assert job_id is not None` before `_save_preview(job_id, …)` and
  `return job_id`. (Assert is fine here — a None lastrowid would be a genuine DB failure.)
- **`render/text.py:98`** (`return-value`: got `float`, expected `int`). Inspect the
  computation; if the function should return an int (pixel/dot count), wrap the result in
  `int(...)` (or `round(...)` if that's the intent — check surrounding usage). If it can
  legitimately be fractional, widen the annotation instead. Decide from context, note which.
- **`routes/printer.py:27`** (`return-value`: `JSONResponse` vs `dict`). The handler returns
  a `JSONResponse` (for a non-200 path) but is annotated `-> dict`. Widen the return
  annotation to cover both (e.g. `dict[str, Any] | JSONResponse`, or the appropriate FastAPI
  `Response` supertype). Don't strip the JSONResponse — it's intentional (status code).
- **`config.py:33`** (`call-arg`: missing `printer_host` for `Settings`). `Settings()` is
  populated from env by pydantic-settings; `printer_host` is required-from-env with no
  literal default. The `pydantic.mypy` plugin may resolve this once enabled — check first.
  If it doesn't, add a specific `# type: ignore[call-arg]` on that line with a one-line
  reason (BaseSettings fields are populated from the environment at runtime). Do **not** give
  `printer_host` a fake default to placate mypy.

## Conventions to honor

- LF endings. Keep `# type: ignore` rare, specific (with code), and justified.
- Changelog: add a `### Changed` entry under `## [Unreleased]` — CI now type-checks the
  backend with mypy (added to dev deps + `[tool.mypy]` config); notes that enabling it fixed
  a latent Pillow-resampling deprecation and tightened several return types. Developer-facing,
  no runtime behavior change (the `store.py` crash fix is already logged separately).

## When done

1. Verify all green: `ruff check . && ruff format --check . && mypy backend && pytest -q`.
   Give the one-line "run this to verify".
2. Update this file's frontmatter (`status`, `completed` = 2026-06-05, `result`).
3. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
4. Record in `docs/decisions.md` only if a non-obvious call was made (e.g. per-module ignore
   strategy, or any `type: ignore` rationale worth keeping).
5. Propose ONE commit covering `pyproject.toml`, the backend fixes, the changelog, and this
   prompt move. Present the file list and a one-line message; ask
   `commit these as "chore: enable mypy in CI and fix backend type errors"? (y/n)`. On `y`,
   stage those specific paths (never `git add -A`) and commit on `dev`. Never push.
