# Decisions

Architecture Decision Records, newest at the top. Each entry: what we decided, why, what we considered, and what would cause us to revisit.

---

## 2026-06-07 — Font bytes served via authenticated fetch, not bare CSS url()

**Decision**: `loadServerFonts()` fetches font bytes through an authenticated `fetch()` call (attaching the `Authorization: Bearer` header) and constructs the `FontFace` from the resulting `ArrayBuffer`, rather than passing a bare `url(/api/fonts/{name}/file)` string to the `FontFace` constructor.

**Why**: The API uses a per-request Bearer token in the `Authorization` header. A bare CSS `url(...)` inside `FontFace` is loaded by the browser's font engine, which cannot attach custom request headers — the request would arrive unauthenticated and be rejected with 401/403 unless `DISABLE_AUTH=true`. Fetching bytes through the same authenticated `fetch()` pattern already used for preview PNGs (`previewQuick`, `fetchHistoryPreview`) is the correct approach and requires no special-casing of the font endpoint.

**Considered**:
- Make `GET /api/fonts/{name}/file` public (no auth required) — rejected. Font names reveal which fonts are installed (data disclosure), and diverging auth on a single route class adds maintenance confusion. When `DISABLE_AUTH=true` the bearer header is sent but ignored, so the ArrayBuffer path works in both modes.
- Use a short-lived signed URL or a cookie-based session — rejected as over-engineering for a single-user homelab app with no session mechanism.

**Would revisit if**: A cookie-based auth mechanism is added, in which case `FontFace` with a bare URL would work and the ArrayBuffer fetch could be simplified.

---

## 2026-06-07 — Server renderer honors Fabric `originX`/`originY`

**Decision**: The server renderer (`render/template.py`) now translates each element's stored `left`/`top` from origin-relative coordinates to the true top-left corner before pasting. A small helper `_origin_top_left(obj, left, top, box_w, box_h)` handles the shift: `center` origin subtracts half the box dimension; `right`/`bottom` subtracts the full dimension; `left`/`top` (the Fabric defaults) are a no-op. The translation is applied at all three sites that consume `left`/`top`: the main draw loop, the continuous-canvas `bottommost` accumulation, and `detect_overflow`.

**Why**: Fabric stores `left`/`top` relative to `originX`/`originY`. The `testt` template's three text objects all carry `originX: 'center', originY: 'center'`, so the raw coordinates are the element's center point, not its top-left corner. The old renderer treated them as top-left, placing each element's left edge at its intended center — shifting it right (and down) by half its box. Wider elements fanned out further than narrow ones, making the label appear misaligned ("everything fans out / not left-aligned" bug).

**Fix is server-only and origin-agnostic**: no stored templates are mutated, no frontend changes are needed. Templates that already use the `left`/`top` default (the common case) are unaffected — the helper is a no-op. Templates saved with any origin combination will render correctly going forward.

**Considered**:
- Normalize stored templates on load (convert center-origin coordinates to left/top) — rejected; mutating stored data on read is fragile and breaks the invariant that `canvas_json` always matches what Fabric serialized.
- Fix in the frontend only (set `originX`/`originY` to `left`/`top` on save) — rejected; would not correct existing templates already in the database, and the server should be the authority on rendering anyway (per 2026-05-20 ADR).

**Would revisit if**: Fabric changes its coordinate serialization format in a future major version such that `left`/`top` are always expressed relative to the top-left corner regardless of declared origin.

---

## 2026-06-06 — Print-time media override: one-off, warn-but-allow, red→black automatic, reprint binds to history

**Decision**: A template can be printed on any supported media at recall time without mutating
the stored template. The behavior:

- **One-off, non-persistent**: the media choice applies to the current print/preview only.
  `template.label_media` is never modified. Save As remains the way to permanently retarget
  a design.
- **Overflow on die-cut: warn but allow**: when the chosen media is a die-cut and content
  extends beyond its printable height (`label.dots_printable[1]`), the preview response
  returns `X-Label-Overflow: true` (header) and the print response includes `"overflow": true`
  in the JSON body. The recall UI shows an inline warning. Printing is never blocked.
- **Red → black on mono: automatic, no toggle**: the renderer's existing `_canvas_color_to_l`
  already maps any non-white color (including red) to 0 (black). Choosing a mono media for
  a two-color template requires no additional renderer work — the preview will show the result.
  An inline notice in the recall UI informs the user.
- **Reprint binds to the historical media**: `_reprint_template` now renders with
  `media_override=row["label_media"]` (the row's actual print media) rather than
  `tmpl.label_media`. This makes one-off overrides reproducible from history.

**Supersedes**: the glossary rule "a template belongs to exactly one label media (a 62mm Spool
template cannot be printed on a 29×90 die-cut)" — see `docs/glossary.md`. The spirit of the
rule (Save As for persistent retargeting; editor media is immutable) is preserved. What changes
is the recall path: a one-off override is now supported.

**Why**: The same physical design (e.g. a spool label) fits on rolls of the same width but
different geometries (continuous vs die-cut, different die-cut lengths). The user physically
swaps rolls and the pre-print media compatibility check already guards mismatches. Blocking
the print when geometry is close (same width, different length) is friction with no safety
benefit — the preview shows the result before ink touches paper.

**Why same-width-first grouping**: When the list of all media is shown unsorted, the user must
scan to find the relevant alternatives. Same-width media share the design's coordinate system
width and are the most natural substitutes. Surfacing them first addresses the "overwhelming
list" concern without removing any option.

**Considered**:
- Block cross-width prints entirely — rejected; a 62mm design on 62x29 is the exact motivating
  case (user has a die-cut roll loaded, wants the label to auto-crop). The warn path is safer.
- A "save this media to the template" affordance — rejected; Save As already covers persistent
  retargeting, and adding a second save path creates confusion about which one is canonical.
- Recolor toggle for red→black (explicit opt-in) — rejected; the preview already shows the
  result, and an automatic mapping is simpler. A notice informs the user.
- Keep history logging the template's stored media — rejected; the historical row would then
  be wrong (it logged a 62red print when a 62 roll was used), and reprint would reproduce
  the wrong media.

**Would revisit if**: a future override needs to be persistent without a full Save As (e.g.
"set this media as the new default for the template") — at that point a dedicated endpoint
or UI affordance would be appropriate.

---

## 2026-06-05 — Release publish trigger: `release: published` replaces tag-push for production builds

**Decision**: Removed the `tags: v*.*.*` trigger from `build-and-push.yml`. `release: published` is now the sole trigger for production image builds. The `push: branches: [main, dev]` trigger is retained for rolling dev/latest builds.

**Why**: `gh release create v<version>` (run by `/release-cut`) both creates the GitHub release AND pushes the git tag. With both `tags: v*.*.*` and `release: published` active, a single `/release-cut` invocation would fire the build workflow twice on the same commit — wasting CI minutes and risking a race between two concurrent builds pushing identical `:latest` image layers. Removing the tag-push trigger makes `release: published` the single, deterministic gate for release builds. This aligns with the `code-checkin-and-pr` standard's publishing matrix and is required by the `release-prep-and-cut` standard's `/release-cut` step 6 (verifies the build triggered by the `release` event specifically).

**Image tags on release**: The `metadata-action`'s `type=semver,prefix=v` rules produce `:v<version>`, `:v<major>.<minor>`, `:v<major>` (with a `v` prefix on image tags, matching the existing tag convention). `:latest` is also produced by `type=raw,value=latest,enable=startsWith(github.ref, 'refs/tags/v')`. This implements the `code-checkin-and-pr` matrix (`:latest`, `:<semver>`, `:<major>`) with an added `v` prefix from the existing config.

**Context**: Part of adopting `release-prep-and-cut @ 1.0.0`.

**Considered**:
- Keep `tags: v*.*.*` only, remove `release: published` — rejected; the `release-prep-and-cut` standard requires `/release-cut` to verify a build triggered by the `release` event.
- Keep both triggers and deduplicate in the workflow — rejected; fragile and over-engineered for a solo project.

**Would revisit if**: Docker image tag conventions change (e.g. dropping the `v` prefix from image tags); or if the release workflow needs pre-release staging triggered by draft releases.

---

## 2026-06-05 — Catalog reconciliation: 3-way merge with baseline, operator-wins, never-delete

**Decision**: On startup, labelforge performs a non-destructive 3-way merge of the bundled
`/app/labels.yml` into the operator's `$DATA_DIR/labels.yml`. A baseline copy
(`$DATA_DIR/data/labels.default.yml`) records the default as of the last sync. Merge logic:
if a field's operator value equals the baseline value (never customized), a changed default
value is applied; if the operator changed it, the operator wins. Entries the operator added or
that a later default removed are never deleted. A rolling backup (`$DATA_DIR/labels.yml.bak`)
is written before any write. The feature is opt-out via `CATALOG_AUTO_MERGE=false`. Closes #16.

**Source of truth for reconciliation is the bundled image default, NOT the internet.** This is
intentionally distinct from "don't auto-update the catalog from the internet" (`CLAUDE.md`):
reconcile reads only the default shipped inside the image; no network access occurs.

**PyYAML is used for the round-trip** (not `ruamel.yaml`). PyYAML drops YAML comments and
non-standard formatting from the operator file on write. Mitigation: the backup preserves the
original. This is an accepted trade-off; the operator file is user-editable but not expected to
carry extensive comments.

**Why operator-wins + never-delete**: The operator may have customized `brother_part`, tweaked
`display_name`, or added custom media entries that have no default counterpart. Silently
overwriting these would break their setup. "Never delete" covers the case where an operator
has a physical roll for an entry a future default drops — their printer still works.

**Why the baseline (3-source model, not 2)**: Without a baseline, distinguishing "operator
customized this field" from "operator left it at the old default value" is impossible when the
default changes. The baseline is the missing anchor that makes intent deterministic.

**Considered**:
- `ruamel.yaml` for comment-preserving round-trips — deferred. `ruamel.yaml` is not in the
  locked stack (PyYAML is); adding it would need its own ADR. The backup mitigates the loss.
- Simple overwrite on upgrade — rejected; clobbers operator customizations, the root cause of #16.
- Operator-file-wins on every field, no merge — rejected; defeats the purpose (SKU corrections
  and new entries would never arrive).
- Delete entries removed from the default — rejected; custom media the operator added would
  silently vanish.

**Would revisit if**: comment-preserving round-trips become a strong operator ask (add
`ruamel.yaml` with an ADR); or the locked stack adds a structured YAML library with better
semantics.

---

## 2026-06-04 — Template recall pre-fill uses print history; retention preserves latest job per template

**Decision**: The "Load previous values" button on the recall form reads `field_values` from the newest `print_jobs` row for that template. No new table or column was needed — `field_values` was already stored at print time. `GET /api/templates/{name}/last-values` returns `{values, printed_at}`.

Retention pruning (`prune_history`) now always exempts the highest `id` per `template_id` from deletion in both `last_n` and `last_days` modes (quick-print rows have `template_id = NULL` and are not protected). This is bounded by template count (single-user, small) and does not meaningfully undermine the configured N.

**Why**: The data was already there; the feature is a query and a button. Protecting the latest job per template avoids a surprising edge case where `last_n = 1` + a burst of quick prints silently erases recall pre-fill.

**Would revisit if**: A dedicated "last values" column is needed (e.g. to survive template deletion); at that point a migration to copy the latest values would be appropriate.

---

## 2026-06-04 — Continuous label length measured from Pillow-rasterized text, not Fabric metrics

**Decision**: For continuous-roll templates, `render_template` computes canvas height from PIL-measured text extents, not from Fabric's serialized `height`. Text elements are pre-rendered to PIL sub-images before the canvas is created; the sub-image's `.height` (measured with `multiline_textbbox`) drives `bottommost` for the continuous canvas sizing. Non-text elements (line, rect) still use `height * scaleY` from Fabric — those are reliable.

`_render_text_element` also sizes its sub-image from the same PIL measurement (not `box_h` from Fabric), so text is never clipped inside its own element box regardless of media type. The draw origin is shifted by `-bbox[1]` to cancel any positive ascender gap, keeping the ink flush with the top of the sub-image without affecting the paste position (which is still taken from Fabric's `top`).

**Why**: Fabric measures text with the browser's font engine; PIL measures with FreeType directly. The two disagree — PIL renders taller at the same `fontSize`, with the gap widening as font size grows. For continuous media, trusting Fabric's `height` produced a canvas too short to contain the last line. The root cause was the two-renderer divergence described in the 2026-05-20 server-side rendering ADR: "Divergence shows up as 'preview/print doesn't match the editor.'" This fix makes the server renderer authoritative for its own geometry.

**Considered**:
- Correct only the canvas height, leave sub-image sized by Fabric `box_h` — rejected; text still clips inside its element box for die-cut media.
- Add a per-element measurement pass separate from the render pass — rejected; pre-rendering text elements once and reusing the sub-image is cleaner and avoids double font loads.

**Would revisit if**: Fabric's font metrics are made to match PIL (e.g. by using the same font rendering engine server-side), at which point the browser measurement could be trusted for canvas sizing again.

---

## 2026-06-03 — Two-color template rendering (supersedes "later slice" note)

**Decision**: `render_template` now supports two-color (black + red) media. When `label.color == 1` (e.g. `62red` / DK-2251) the renderer returns a mode-`RGB` image instead of mode-`L`: black pixels are `(0,0,0)`, red pixels are `(255,0,0)`, paper is `(255,255,255)`. The print path in `printer/client.py` already promoted `L→RGB` and passed `red=True` for two-color media (2026-05-31 ADR) — it consumes the RGB image correctly without change. Text color comes from the Fabric element's `fill` property (`#000000` / `#ff0000`); lines use `stroke`; rects use `fill`/`stroke`. The template-preview PNG also returns RGB (color-accurate) instead of the threshold-crushed mono.

The "Two-color (62red) rendering is a later slice; always renders mono" docstring note is superseded by this implementation.

**Why**: Two-color DK rolls are a first-class media in the catalog and the most useful differentiated feature of those rolls. The print path infrastructure was already in place; only the renderer and frontend controls were missing. QR/barcode elements remain mono (raised as `RenderError`) — a separate fix is needed for those.

**Considered**:
- Separate `render_template_color()` function — rejected; branching on `label.color` inside the existing function keeps the call-site unchanged.
- Always return RGB — rejected; doubles memory for mono jobs and changes the mono threshold behavior.

**Would revisit if**: QR/barcode color rendering is implemented (extend the two-color path to those element types).

---

## 2026-06-03 — Template media retargeting: Save As only; live media switch is not in scope

**Decision**: A template is locked to its label media. The editor toolbar exposes a **Save As** button that clones the template to a new name and optionally a new media via `POST /api/templates/{name}/duplicate`. No dropdown or control that mutates the open template's `label_media` exists in the editor. The current media is shown as a read-only badge next to the template name.

**Why**: Mutating a template's media in the editor would silently invalidate all saved element positions (they're in print-DPI pixel coordinates sized for the original media). Save As makes the user explicitly create a new template and adjust the layout, preventing silent corruption. This matches the design in `docs/features/templates.md` ("A template is locked to its label media").

**Considered**:
- A live media-switch dropdown in the editor that rescales element positions — rejected; position rescaling is lossy (different aspect ratios, different DPIs across form factors) and the complexity is not justified for a single-user homelab tool.
- Auto-redirect to a new template on media change (same as Save As, just triggered differently) — rejected; the explicit Save As click makes the copy intent clear and avoids accidental renames.

**Would revisit if**: a "reflow to new media" feature is scoped in a PRD change with explicit rescaling rules.

---

## 2026-06-02 — De-adopt vexp-context-engine (sunset)

**Decision**: Removed the `vexp-context-engine` standard from this repo, following its v3.0.0 sunset (vexp retired homelab-wide — it didn't pay for its host-provisioning + guard-hook + per-session-rule tax). De-wired the repo per the v3.0.0 removal guide: deleted the guard hook + `.vexpignore`, the `mcp__vexp__*` allow entries and `PreToolUse` block in `.claude/settings.json`, the "Context search" section in `CLAUDE.md`, the vexp `.gitignore` block, and the on-disk `.vexp/` / auto-generated `.claude/CLAUDE.md`. `standards.md` row flipped to sunset.

**Why**: The upstream standard is deprecated and instructs existing adopters to remove it. Coding agents return to normal `grep`/`glob`/`Read`.

**Considered**: Keep vexp running locally despite the sunset (rejected — it's unmaintained, and the guard hook actively fights the agent's normal tools).

**Would revisit if**: a maintained graph-RAG context engine is re-introduced homelab-wide.

**Note**: Host-level teardown (uninstalling the vexp daemon/CLI on this WSL box) belongs to the `ansible` repo, not this app repo.

---

## 2026-06-02 — App-level auth is optional (`DISABLE_AUTH`), default-on; proxy can own auth

**Decision**: App-level Bearer auth becomes opt-out via a `DISABLE_AUTH` env flag. Default is unchanged and secure: auth on, and the app refuses to start without `API_TOKEN`. When `DISABLE_AUTH=true`, the `require_auth` dependency short-circuits (every `/api/*` route is open) and `GET /api/health` reports `auth_required: false` so the SPA skips its token gate. The intended deployment for the disabled mode is behind a reverse proxy (Traefik forward-auth / basic-auth) that authenticates instead.

This amends **2026-05-19 — Auth** (the env token stays the default mechanism; it's now skippable, not removed). Multi-user accounts were considered and rejected again — single-user remains a hard non-goal.

**Why**: Owner runs this behind Traefik and prefers to authenticate at the edge rather than maintain a second secret in the app. Per-app token auth is friction when the proxy already gates the route.

**Considered**:
- User accounts / login (rejected — multi-user is a hard non-goal; `CLAUDE.md`).
- Rip auth out entirely (rejected — not reversible without a revert; an unconfigured instance would be silently open). The flag keeps default-secure behavior and is a one-line env change.
- Silently treat an empty `API_TOKEN` as "no auth" (rejected — too easy to ship an accidentally-open instance; disabling auth must be explicit).

**Would revisit if**: we later want per-integration tokens (see 2026-05-19) or the proxy-auth assumption stops holding (e.g. exposing the app directly).

---

## 2026-05-31 — Two-color DK rolls: print with `red=True`; tape color is not detectable from status

**Decision**:
- `print_image()` passes `red=True` and an RGB image to `brother_ql.convert()` whenever the selected media is a two-color label (e.g. `62red` / DK-2251), even for black-only content. Without it the job declares mono media and the printer rejects it on the LCD as "Wrong roll: check the print data".
- The pre-print `media_compatible()` check treats rolls of identical physical dimensions (`tape_size`) as compatible rather than blocking on a guessed color. Differing sizes (e.g. 62 vs 29) still block.

**Why**: The QL-800/810W/820NWB status protocol does **not** report tape/media color. Verified against Brother's official *Raster Command Reference QL-800/810W/820NWB*: the 32-byte `ESC i S` response carries media width (byte 10), media type = continuous/die-cut (byte 11), and media length (byte 17) only; bytes 12–14, 16, 23 and **24–31 are reserved/fixed `00h`**. The strings "tape color", "text color", "media color" do not appear in the document. The printer enforces the correct DK roll at print time by sensing the physical roll, but never surfaces color in status. So `62` and `62red` (both 62mm continuous, `tape_size (62, 0)`) are indistinguishable from a status read — the earlier plan to read `data[24]` for color (see the ESC i S ADR below) is not viable; that byte is always `00h`. Brother's own P-touch Editor doesn't auto-detect DK color either: the user manually picks the roll and a BK-RD vs Monochrome mode, and selecting Monochrome on a DK-2251 produces the same printer-side "wrong roll type" error ([Brother FAQ a_id/142492](https://help.brother-usa.com/app/answers/detail/a_id/142492/)). (Color *is* auto-detected on P-touch label makers, but only because TZe tape cassettes are physically keyed — DK rolls have no such keying.)

**Considered**: (a) read `data[24]` for color — rejected, reserved `00h` per spec; (b) scrape the printer's `status.html` — rejected, it doesn't show color either; (c) key off the DK part number — we don't pass DK numbers to the library and can't read the loaded roll's part number.

**Consequence**: The user picks `62` vs `62red` manually; the status panel labels a 62mm continuous roll generically. The "Loaded in printer" filter offers both same-size variants. A `red=True` job prints black-only fine (red plane left empty).

**Would revisit if**: a future firmware/model exposes media color in the status response, or the library gains reliable DK color reading.

---

## 2026-05-31 — Printer status over network: ESC i S unreliable; implement raw-TCP + HTTP fallback

**Decision**: The Printer Status feature will use a two-path `status_read()` function in `printer/client.py`:

1. **Primary — raw TCP ESC i S**: Directly instantiate `BrotherQLBackendNetwork(f"tcp://{host}")` (bypassing `get_printer()`, which raises `NotImplementedError` for the network backend), override `read_timeout` from the default 10 ms to the configured `printer_status_timeout_ms` value, then call `get_status()`. Parse the 32-byte response via `brother_ql.reader.interpret_response()`. For DK tape color detection, read `data[24]` directly (the library only parses `tape_color` for TZe-category tapes, not DK).

2. **Fallback — HTTP scrape**: If the TCP path returns empty bytes, fetch `http://{host}/general/status.html` (unauthenticated) and parse `dt`/`dd` pairs for "Device Status" (→ ready bool) and "Media Type" (→ string like `"62mm x 29mm"` → regex-extract width/length → look up in `ALL_LABELS`).

3. **Graceful degrade**: If both paths fail, raise `StatusUnavailable`; callers log and proceed (per `printer-status.md` print-path spec).

Media ID mapping for both paths: search `brother_ql.labels.ALL_LABELS` where `lbl.tape_size == (width_mm, length_mm)`. For continuous 62 mm (length = 0), mono `"62"` and color `"62red"` share the same `tape_size` — disambiguate via `data[24]` on the TCP path; report `color_capable: false` (unknown) on the HTTP path. The exact DK-22251 tape-color byte value needs hardware verification when a two-color roll is loaded.

**Why**: A spike against the QL-820NWB (2026-05-31) showed:
- `get_printer()` raises `NotImplementedError` for `backend="network"` (intentional library design; comment: "Not implemented due to lack of an available test device").
- `send()` explicitly skips readback for the network backend: "The network backend doesn't support readback."
- The library's CLI `discover` command skips `get_status()` for the network backend.
- Live hardware test: TCP port 9100 connects, but ESC i S returns empty bytes regardless of timeout (10 ms, 500 ms, 2 s, 5 s all tested). Full raster init sequence (200 null bytes + ESC @ + ESC i a 01 + ESC i S) also returns empty.
- The HTTP interface at `/general/status.html` responded without authentication and returned "READY" + "62mm x 29mm".

`get_status()` is technically callable via direct backend instantiation (the function sends ESC i S and reads; it does not filter on the backend type), so the TCP path is kept as primary in case it works on different firmware versions or printer states. The 10 ms default `read_timeout` is the likely cause of spurious failures if the printer ever does respond.

**Considered**:
- HTTP-only: simpler, but abandons ESC i S even on printers/firmware where it works; provides no color-capability information.
- Pure TCP with no HTTP fallback: leaves us with 503 on every status call against the current hardware.
- Patching `get_printer()` via a fork: rejected — no fork policy without an ADR; bypass by direct instantiation is sufficient.

**Would revisit if**: A firmware update makes ESC i S respond on the QL-820NWB (at which point the HTTP fallback can be dropped); or we test on a USB backend where `get_printer()` and `get_status()` work as intended.

---

## 2026-05-31 — History UI: authed image loading via fetch+objectURL

**Decision**: `/api/history/{id}/preview.png` requires a bearer token, so `<img src="...">` bare URLs 401. The history page fetches previews via `fetch()` with the `Authorization` header, creates an object URL via `URL.createObjectURL(blob)`, and sets that as `img.src`. Object URLs are revoked on page remount and on filter/pagination resets via a generation counter that skips stale async completions.

**Why**: Matches the existing pattern used by `previewQuick` and `previewTemplate` in `api.ts`. Keeps the token out of query strings (which appear in server logs and browser history).

**Considered**: Embedding tokens in query strings (`?token=...`) — rejected (leaks credential). Server-side session cookies — out of scope (auth is a single bearer token).

**Revisit if**: The session adopts cookie-based auth, at which point `<img src>` works without a fetch wrapper.

---

## 2026-05-31 — History UI: "Load more" pagination over prev/next

**Decision**: The `/history` page uses a "Load more" button (appending to the list) rather than prev/next page navigation.

**Why**: Simpler DOM management; no need to track current page number or re-render the full list on page change. Works well with the "most recent first" order where users typically care about the top of the list.

**Revisit if**: The history list grows large enough that scrolling becomes painful, at which point a fixed-size window with prev/next would be preferable.

---

## 2026-05-31 — Print history: preview stored as file on disk, not inline BLOB

**Decision**: Preview images for print history are stored as PNG files under `${DATA_DIR}/label-previews/{job_id}.png`. The `print_jobs.preview_path` column stores the filename (e.g. `"42.png"`); the history preview route resolves the full path at request time. Previews are written after INSERT (job_id is needed for the filename), so rows exist briefly with `preview_path = NULL`. If preview write fails, the row is kept with `preview_path = NULL` and the preview route returns 404 for that job.

**Why the schema already chose this**: The live `print_jobs` schema already had a `preview_path TEXT NULL` column — not a `preview_png BLOB` column. `history.md` specified a BLOB; the live schema diverged (likely because the data-path contract already reserves `label-previews/` and keeping SQLite small is a long-standing goal). Aligning the implementation with the live schema avoids a destructive migration.

**Why files over BLOBs in general**: Keeps the SQLite file small at scale; HTTP serving (FileResponse) is simpler for binary content; preview files can be examined or deleted directly without touching the DB. For a homelab with retention pruning the footprint is bounded.

**Consequence**: `docs/features/history.md` data model updated to reflect `preview_path` (file ref) rather than `preview_png` (BLOB). A missing or deleted preview file returns 404 from the preview route; the frontend should render a placeholder rather than erroring.

**History frontend deferred**: The `/history` page and retention-settings UI are Slice B — not built in this slice.

**Revisit if**: preview files become inconvenient to manage (backup, migration) compared to keeping everything in one SQLite file — at that point a BLOB column is a viable alternative.

---

## 2026-05-31 — Adopt four homelab-configs standards; flip commits to Conventional-Commits prefixes

**Decision**: Adopt `code-checkin-and-pr @ v1.1.0`, upgrade `handoff-prompt-workflow` to `v1.5.0`, adopt `repo-sandbox-permissions @ v1.0.0` (repo-wide), and formalize `vexp-context-engine @ v2.1.0`. All four are pinned in the new root `standards.md`. As part of `code-checkin-and-pr`, commit messages now **require** Conventional-Commits prefixes (`feat:` / `fix:` / `chore:` / `docs:`).

**Why**: The standards' adoption was incomplete and undocumented — only `handoff-prompt-workflow @ 1.0.0` was in the registry, `standards.md` didn't exist, and vexp was wired with drift (guard hook untracked, stale custom snippet). `standards.md` + verbatim CLAUDE-snippets make conformance auditable in-repo.

**The reversal**: `CLAUDE.md` previously said *"No conventional-commits prefixes."* This directly contradicted `code-checkin-and-pr`, which mandates them. We chose to flip the convention (adopt prefixes) rather than record a permanent deviation, so the standard is implemented cleanly. The "No co-author tags" rule is unchanged — it matches the standard.

**Considered**: (a) Keep no-prefix commits and document a partial-adoption deviation in `standards.md` Notes — rejected; a deviation on the standard's most visible rule undercuts the point of adopting it. (b) Add an Alembic migration system to satisfy CI check #3 — rejected as out of scope; the app uses raw SQLite, so the migration check is marked **N/A** in `standards.md`.

**Revisit if**: the project gains a migration system (wire CI check #3 then), or the GPU offload for vexp's local LLM is provisioned on this host (update the `vexp-context-engine` Notes row from CPU-only).

## 2026-05-26 — Printer↔label compatibility is library-derived, computed at catalog load; `printer_requirements` deprecated

**Decision**: A label's printability on the configured printer is computed at catalog load from primitive `brother_ql` fields, not declared in `labels.yml`. Each catalog entry gains `restricted_to_models` (`Label.restricted_to_models`), `color` (`Label.color`), a computed `supported: bool`, and `incompatible_reason: str | None`. The rule:

```python
supported = (not label.restricted_to_models or printer_model in label.restricted_to_models) \
            and (label.color == 0 or model.two_color)
```

`model` is the entry in `brother_ql.models.ALL_MODELS` whose `identifier == PRINTER_MODEL`; `two_color` flags the QL-800 series. If the configured model isn't found, a warning is logged and all media are treated as supported. Selectors render unsupported media as disabled+greyed `<option>`s with a tooltip and guard programmatic default selection. The `printer_requirements` yml field is **deprecated and ignored** (removed from the model, the default yml, and the loader).

**Why**: The catalog already follows "library is truth, yml is the UX layer" (see the 2026-05-19 label-catalog ADR). A hand-maintained `printer_requirements` list violated that — it drifts from the library and can't express two-color capability, which lives on the printer model, not the media. Deriving compatibility from the library keeps a single source of truth and means new media/printer support from a library bump Just Works. On the configured QL-820NWB this correctly disables the six wide-format rolls the printer physically can't feed while keeping `62red` available.

**Why not `Label.works_with_model()`**: The obvious library helper is unusable in the pinned `brother-ql-inventree>=1.3`. Verified against the installed library:
- It raises `NameError: name 'models' is not defined` for **any** restricted label (`brother_ql/labels.py:67`) — e.g. `labels['102'].works_with_model('QL-820NWB')` throws.
- It ignores two-color capability — `labels['62red'].works_with_model('QL-700')` returns `True` even though a mono QL-700 can't print two-color media.

So the helper is both crash-prone and wrong. Computing from `restricted_to_models` + `color` vs `model.two_color` sidesteps both bugs. This is an upstream bug worth reporting to `inventree/brother_ql`; until fixed (and the fix reaches our pin) we do not call `works_with_model()`.

**Considered**:
- Keep `printer_requirements` in yml — rejected; contradicts the library-truth ADR and can't know two-color.
- Use `Label.works_with_model()` — rejected; crashes on restricted labels and ignores color (above).
- Hide unsupported media entirely — rejected; the spec calls for disable+tooltip so the user understands *why* a roll they own isn't offered.
- Recompute per request — unnecessary; `PRINTER_MODEL` is fixed in config, so compute once at load. A future `POST /api/admin/reload-catalog` recomputes.

**Would revisit if**: a future printer becomes runtime-configurable (then compatibility must recompute on change, not just at load), or upstream fixes `works_with_model()` and the fix reaches our pin (then prefer the library helper over the open-coded rule).

---

## 2026-05-26 — Label selectors show `brother_part: display_name`; `52x29` intentionally has no part number

**Decision**: Label-media `<select>` options render as `{brother_part}: {display_name}` (e.g. `DK-2205: 62mm Continuous (Black)`) when the catalog entry has a `brother_part`, and as the display name alone when it doesn't. The grouping/formatting lives in one shared helper (`frontend/src/labels.ts::buildLabelOptionsHtml`) used by every label selector. The default `labels.yml` was backfilled so 14 of 15 entries carry a `brother_part`; `52x29` is deliberately left without one.

**Why**: The part number is how the owner actually identifies a roll to load, so it belongs in front of the human name in every place a label is chosen. Brother's QL-820NWB consumables list confirmed the part numbers; `52x29` is a `brother_ql`-printable size with **no consumer DK roll**, so there is nothing to map — the empty `brother_part` is correct, not an oversight. The format degrades cleanly (no dangling `: `). Centralizing in one helper keeps quick-print and the new-template modal from drifting and makes a future third selector consistent for free.

**Considered**:
- Suffix form `display_name (DK-…)` — rejected; the part number is the lookup key, so it reads better leading.
- Backfill a guessed part for `52x29` — rejected; no such product exists, a fake number would mislead.
- Edit the two duplicated option blocks in place — rejected in favor of the shared helper (the grouping logic was already duplicated verbatim).

**Would revisit if**: Brother ships a DK roll at 52×29 mm (add its `brother_part`), or a selector needs richer option markup than a flat string (the helper returns an HTML string today).

---

## 2026-05-25 — Compiled `.js` is not tracked; `.ts` is the only source in `frontend/src`

**Decision**: `frontend/src` tracks TypeScript only. The `.js` files `tsc` emits next to each `.ts` are build artifacts: `tsconfig.json` sets `noEmit: true` (so `tsc` in the `build` script is typecheck-only), `.gitignore` ignores `frontend/src/**/*.js`, and the 9 previously-committed `src/**/*.js` were untracked.

**Why**: The repo had a compiled `.js` committed beside every `.ts`. Nothing consumed them — Vite compiles the `.ts` directly (esbuild in dev, Rollup in prod) and the Docker image builds from source — so they were stale dead weight that doubled every source diff and risked misleading anyone reading the tree. Committing build output beside source is an anti-pattern for an app with a build step.

**Considered**:
- Keep committing the `.js` in sync with source — rejected; perpetuates the smell for zero runtime benefit.
- Untrack only, leave `tsc` emitting — rejected; artifacts would silently reappear on the next local build and risk being re-added.
- Untrack + `noEmit` + ignore — chosen; removes the artifacts and the mechanism that created them.

**Would revisit if**: the project ever ships hand-authored `.js` in `src` (it shouldn't) or moves to a build that legitimately emits into `src`.

---

## 2026-05-20 (e) — Preview must apply the same 1-bit threshold as print

**Decision**: The preview endpoints return the exact 1-bit (black/white) image the printer will rasterize, produced by the same threshold/dither step as the print path — not the pre-threshold greyscale render. There is a single shared definition of "the bitmap that prints," used by both preview and print.

**Why**: A QR element previewed as a crisp code but printed as a solid black block. Cause: the printer's `convert()` thresholds the greyscale render to 1-bit (~70% default, no dither), which crushed the QR's anti-aliased fine modules; preview returned the pre-threshold greyscale, so it looked fine while the print did not. The rendering ADR's promise that "preview is the exact bitmap that prints" only holds if preview applies the same final threshold. Fine detail (QR, barcode, thin lines, small text) is where preview-vs-print divergence shows up — and it showed up on a physical label, the most expensive place to find it.

**Consequence**: QR/barcode elements are rendered as pure black/white scaled by integer factors so thresholding cannot crush them. Threshold/dither settings are explicit and centralized so preview and print provably agree. This refines (does not contradict) the server-side rendering ADR.

**Would revisit if**: a future need for greyscale/dithered output (e.g. photo-ish images on a label) requires preview to represent dithering, at which point the shared step must reproduce the dither, not just the threshold.

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
