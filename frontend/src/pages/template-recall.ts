import { batchPrint, getLabels, getLastValues, getTemplate, previewTemplate, printTemplate } from '../api'
import type { FieldSpec, LabelEntry, Template, TemplateLastValues } from '../types'
import { mountLabelMediaSelect } from '../labels'
import { navigate } from '../router'

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/** Mirror of the backend `advance()` in templates/fields.py — increment trailing digits, preserve zero-padding. */
function advance(value: string): string {
  const m = /^(.*?)(\d+)$/.exec(value)
  if (!m) return value
  const prefix = m[1]
  const digits = m[2]
  const next = parseInt(digits, 10) + 1
  const nextStr = digits.startsWith('0') ? String(next).padStart(digits.length, '0') : String(next)
  return prefix + nextStr
}

/** Extract the template name from `/templates/:name/print`. */
function nameFromPath(): string {
  const parts = window.location.pathname.split('/').filter(Boolean)
  // ['templates', ':name', 'print']
  return decodeURIComponent(parts[1] ?? '')
}

/** True when any canvas object uses a red fill or stroke color. */
function templateHasRed(tpl: Template): boolean {
  const redValues = new Set(['#ff0000', '#f00', 'red', 'rgb(255,0,0)'])
  const objects = (tpl.canvas_json?.objects ?? []) as Array<Record<string, unknown>>
  for (const obj of objects) {
    const fill = (obj.fill as string | undefined)?.toLowerCase().trim() ?? ''
    const stroke = (obj.stroke as string | undefined)?.toLowerCase().trim() ?? ''
    if (redValues.has(fill) || redValues.has(stroke)) return true
  }
  return false
}

/** Group labels: same-width-as-template first, then all others. */
function partitionByWidth(labels: LabelEntry[], templateWidthMm: number): { sameWidth: LabelEntry[]; other: LabelEntry[] } {
  const sameWidth: LabelEntry[] = []
  const other: LabelEntry[] = []
  for (const l of labels) {
    if (l.tape_size[0] === templateWidthMm) {
      sameWidth.push(l)
    } else {
      other.push(l)
    }
  }
  return { sameWidth, other }
}

/** Build optgroup HTML for the grouped recall media selector.
 *
 * Same-width media appear first (most likely to fit without clipping).
 * Within each group, only supported media are selectable.
 */
function buildRecallOptionsHtml(sameWidth: LabelEntry[], other: LabelEntry[], widthMm: number): string {
  function renderOpt(l: LabelEntry): string {
    const text = l.brother_part ? `${l.brother_part}: ${l.display_name}` : l.display_name
    if (l.supported) {
      return `<option value="${esc(l.id)}">${esc(text)}</option>`
    }
    const reason = l.incompatible_reason ?? 'Not supported by the configured printer'
    return `<option value="${esc(l.id)}" disabled title="${esc(reason)}">${esc(text)} — unavailable</option>`
  }
  const sw = sameWidth.map(renderOpt).join('')
  const ot = other.map(renderOpt).join('')
  const swLabel = `Same width (${widthMm}mm)`
  return (sw ? `<optgroup label="${esc(swLabel)}">${sw}</optgroup>` : '') +
         (ot ? `<optgroup label="Other media">${ot}</optgroup>` : '')
}

export function mountTemplateRecall(root: HTMLElement): void {
  const name = nameFromPath()
  root.innerHTML = `<div class="template-recall"><p>Loading…</p></div>`

  Promise.all([
    getTemplate(name),
    getLastValues(name).catch(() => ({ values: null, printed_at: null } satisfies TemplateLastValues)),
    getLabels(),
  ])
    .then(([tpl, lastVals, allLabels]) => renderRecall(root, tpl, lastVals, allLabels))
    .catch((err: Error) => {
      root.innerHTML = `
        <div class="template-recall">
          <a href="#" class="back-link" id="back-link">← Templates</a>
          <div class="status-msg error">${esc(err.message)}</div>
        </div>
      `
      root.querySelector('#back-link')!.addEventListener('click', e => {
        e.preventDefault()
        navigate('/templates')
      })
    })
}

function renderRecall(root: HTMLElement, tpl: Template, lastVals: TemplateLastValues, allLabels: LabelEntry[]): void {
  const fields = tpl.field_schema ?? []
  const hasFields = fields.length > 0
  const incrementFields = fields.filter(f => f.increment)
  const canBatch = incrementFields.length > 0
  const hasRed = templateHasRed(tpl)

  // Only supported media in the selector
  const supportedLabels = allLabels.filter(l => l.supported)

  // Find template's label width for grouping
  const tplLabel = allLabels.find(l => l.id === tpl.label_media)
  const tplWidthMm = tplLabel?.tape_size[0] ?? 0

  root.innerHTML = `
    <div class="template-recall">
      <a href="#" class="back-link" id="back-link">← Templates</a>
      <h2>${esc(tpl.display_name || tpl.name)}</h2>
      <div id="status-msg" class="status-msg" hidden></div>

      <div class="recall-media-selector">
        <p class="recall-meta">Print media (default: <code>${esc(tpl.label_media)}</code>):</p>
        <div id="media-selector-container"></div>
        <p id="mono-red-notice" class="recall-notice info" hidden>This label is black-only — red elements will print in black.</p>
        <p id="overflow-notice" class="recall-notice warn" hidden>Content may be clipped — it's taller than this label.</p>
      </div>

      <form id="recall-form" autocomplete="off">
        ${hasFields ? fields.map(fieldInput).join('') : '<p class="recall-meta">This template has no variable fields.</p>'}

        ${canBatch ? `
          <fieldset class="batch-box">
            <legend>Batch</legend>
            <label class="batch-toggle">
              <input type="checkbox" id="batch-enable" /> Print multiple labels
            </label>
            <div id="batch-opts" hidden>
              <label for="batch-count">Count</label>
              <input type="number" id="batch-count" min="1" max="1000" value="1" />
              <p class="recall-meta">Auto-increments per label: ${incrementFields.map(f => `<code>${esc(f.name)}</code>`).join(', ')}</p>
            </div>
          </fieldset>
        ` : ''}

        <div class="actions">
          ${hasFields ? `<button type="button" id="btn-load-prev"${lastVals.values ? '' : ' disabled'}>Load previous values${lastVals.printed_at ? ` (${fmtDate(lastVals.printed_at)})` : ''}</button>` : ''}
          <button type="button" id="btn-preview">Preview</button>
          <button type="submit" id="btn-print" disabled>Print</button>
        </div>
      </form>

      <div id="preview-area" class="preview-area" hidden>
        <img id="preview-img" alt="Label preview" />
      </div>
    </div>
  `

  const form = root.querySelector<HTMLFormElement>('#recall-form')!
  const btnPreview = root.querySelector<HTMLButtonElement>('#btn-preview')!
  const btnPrint = root.querySelector<HTMLButtonElement>('#btn-print')!
  const btnLoadPrev = root.querySelector<HTMLButtonElement>('#btn-load-prev')
  const statusMsg = root.querySelector<HTMLDivElement>('#status-msg')!
  const previewArea = root.querySelector<HTMLDivElement>('#preview-area')!
  const previewImg = root.querySelector<HTMLImageElement>('#preview-img')!
  const batchEnable = root.querySelector<HTMLInputElement>('#batch-enable')
  const batchOpts = root.querySelector<HTMLDivElement>('#batch-opts')
  const batchCount = root.querySelector<HTMLInputElement>('#batch-count')
  const monoRedNotice = root.querySelector<HTMLParagraphElement>('#mono-red-notice')!
  const overflowNotice = root.querySelector<HTMLParagraphElement>('#overflow-notice')!
  const mediaSelectorContainer = root.querySelector<HTMLDivElement>('#media-selector-container')!

  let previewObjectUrl: string | null = null
  let debounceTimer: number | undefined
  // True when the selected media has changed since the last preview was run.
  // Print is blocked until a fresh preview confirms the user has seen the output.
  let previewStale = false

  root.querySelector('#back-link')!.addEventListener('click', e => {
    e.preventDefault()
    navigate('/templates')
  })

  function showStatus(msg: string, kind: 'success' | 'error'): void {
    statusMsg.textContent = msg
    statusMsg.className = `status-msg ${kind}`
    statusMsg.hidden = false
  }

  function hideStatus(): void {
    statusMsg.hidden = true
  }

  function collectFields(): Record<string, string> {
    const values: Record<string, string> = {}
    for (const f of fields) {
      const el = form.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${CSS.escape(f.name)}"]`)
      values[f.name] = el?.value ?? ''
    }
    return values
  }

  function missingRequired(): boolean {
    return fields.some(f => f.required && collectFields()[f.name].trim() === '')
  }

  function updateButtons(): void {
    // Print requires: all required fields filled AND a fresh preview after any media change.
    btnPrint.disabled = missingRequired() || previewStale
  }

  // Wire the reusable label-media selector with same-width-first grouping.
  // We build the HTML directly rather than using buildLabelOptionsHtml so we can
  // inject custom optgroups. The toggle (Show all / Loaded in printer) comes from
  // mountLabelMediaSelect, but the option content is replaced after mount via the
  // handle — simpler to just override innerHTML of the inner <select> element.
  //
  // Chosen approach: mount with all supported labels (provides the toggle machinery),
  // then immediately replace option content with our grouped version.
  const mediaHandle = mountLabelMediaSelect({
    container: mediaSelectorContainer,
    labels: supportedLabels,
    initialValue: tpl.label_media,
    onChange: (id: string) => {
      onMediaChange(id)
    },
  })

  // Replace the option content with same-width-first grouping, preserving current value.
  const innerSelect = mediaSelectorContainer.querySelector<HTMLSelectElement>('.media-filter-select')!
  function repopulateGrouped(list: LabelEntry[]): void {
    const { sameWidth: sw, other: ot } = partitionByWidth(list, tplWidthMm)
    innerSelect.innerHTML = buildRecallOptionsHtml(sw, ot, tplWidthMm)
    // Restore the current value if still available; otherwise fall to first supported
    if (mediaHandle.getValue() && innerSelect.querySelector(`option[value="${CSS.escape(mediaHandle.getValue())}"]`)) {
      innerSelect.value = mediaHandle.getValue()
    } else {
      const first = innerSelect.querySelector<HTMLOptionElement>('option:not([disabled])')
      if (first) innerSelect.value = first.value
    }
  }
  repopulateGrouped(supportedLabels)

  // Patch the "Show all" toggle to also rebuild with grouping.
  // We can't override mountLabelMediaSelect internals, so we intercept via the
  // select's change event (which fires after mountLabelMediaSelect updates it).
  // The simplest robust approach: re-run grouping whenever the mode toggle fires.
  const toggleBtns = mediaSelectorContainer.querySelectorAll<HTMLButtonElement>('.media-filter-btn')
  toggleBtns.forEach(btn => {
    // Add a second listener that runs after the one mounted by mountLabelMediaSelect.
    btn.addEventListener('click', () => {
      // Allow mountLabelMediaSelect's listener to run first (same tick), then regroup.
      window.setTimeout(() => {
        // Collect whichever labels are now visible (all or filtered) from the current options.
        const visibleIds = new Set(
          Array.from(innerSelect.options).map(o => o.value)
        )
        const visibleLabels = supportedLabels.filter(l => visibleIds.has(l.id))
        repopulateGrouped(visibleLabels)
      }, 0)
    })
  })

  function getCurrentMedia(): string {
    return innerSelect.value || tpl.label_media
  }

  function onMediaChange(id: string): void {
    // Update mono+red notice
    const label = supportedLabels.find(l => l.id === id)
    const isMono = label ? label.color === 0 : true
    monoRedNotice.hidden = !(hasRed && isMono)

    // Mark preview as stale — force user to preview before printing.
    previewStale = true
    overflowNotice.hidden = true
    updateButtons()

    // Immediately trigger preview so the user sees the new layout.
    window.clearTimeout(debounceTimer)
    debounceTimer = window.setTimeout(() => runPreview(), 0)
  }

  // Initialize notice state for the template's default media
  const initialLabel = supportedLabels.find(l => l.id === tpl.label_media)
  if (initialLabel && hasRed && initialLabel.color === 0) {
    monoRedNotice.hidden = false
  }

  function buildBatchLabels(): Record<string, string>[] {
    const count = Math.max(1, Math.min(1000, parseInt(batchCount?.value ?? '1', 10) || 1))
    const base = collectFields()
    const labels: Record<string, string>[] = []
    let current = { ...base }
    for (let i = 0; i < count; i++) {
      labels.push({ ...current })
      const next = { ...current }
      for (const f of incrementFields) {
        next[f.name] = advance(next[f.name])
      }
      current = next
    }
    return labels
  }

  function runPreview(): void {
    if (missingRequired()) return
    btnPreview.disabled = true
    hideStatus()
    const chosenMedia = getCurrentMedia()
    // Only pass label_media override when it differs from the template's stored media.
    const mediaOverride = chosenMedia !== tpl.label_media ? chosenMedia : undefined
    previewTemplate(tpl.name, collectFields(), mediaOverride)
      .then(({ blob, overflow }) => {
        if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl)
        previewObjectUrl = URL.createObjectURL(blob)
        previewImg.src = previewObjectUrl
        previewArea.hidden = false
        overflowNotice.hidden = !overflow
        // Preview is fresh — allow printing.
        previewStale = false
        updateButtons()
      })
      .catch((err: Error) => showStatus(err.message, 'error'))
      .finally(() => { btnPreview.disabled = false })
  }

  // Live preview, debounced ~500ms after the last keystroke.
  form.addEventListener('input', () => {
    updateButtons()
    window.clearTimeout(debounceTimer)
    debounceTimer = window.setTimeout(() => {
      if (!previewArea.hidden) runPreview()
    }, 500)
  })

  if (batchEnable && batchOpts) {
    batchEnable.addEventListener('change', () => {
      batchOpts.hidden = !batchEnable.checked
    })
  }

  btnPreview.addEventListener('click', runPreview)

  btnLoadPrev?.addEventListener('click', () => {
    const vals = lastVals.values
    if (!vals) return
    for (const f of fields) {
      if (!(f.name in vals)) continue
      const el = form.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${CSS.escape(f.name)}"]`)
      if (el) el.value = vals[f.name]
    }
    updateButtons()
    if (!previewArea.hidden) runPreview()
  })

  form.addEventListener('submit', async (e) => {
    e.preventDefault()
    if (missingRequired()) {
      showStatus('Fill all required fields before printing.', 'error')
      return
    }
    if (previewStale) {
      showStatus('Preview the label with the selected media before printing.', 'error')
      return
    }
    btnPrint.disabled = true
    hideStatus()
    const chosenMedia = getCurrentMedia()
    const mediaOverride = chosenMedia !== tpl.label_media ? chosenMedia : undefined
    try {
      if (batchEnable?.checked) {
        const batchLabels = buildBatchLabels()
        const result = await batchPrint(tpl.name, batchLabels, mediaOverride)
        const kind = result.failed > 0 ? 'error' : 'success'
        showStatus(
          `Batch ${result.batch_id}: ${result.succeeded} sent, ${result.failed} failed (${batchLabels.length} requested). "Sent" means transmitted to the printer; delivery is not confirmed.`,
          kind,
        )
      } else {
        const result = await printTemplate(tpl.name, collectFields(), mediaOverride)
        showStatus(
          `Sent — job #${result.job_id} (status: ${result.status}). "Sent" means the job was transmitted to the printer; delivery is not confirmed.`,
          'success',
        )
      }
    } catch (err) {
      showStatus((err as Error).message, 'error')
    } finally {
      updateButtons()
    }
  })

  updateButtons()
}

function fieldInput(f: FieldSpec): string {
  const id = `field-${f.name}`
  const req = f.required ? 'required' : ''
  const star = f.required ? ' <span class="req-star">*</span>' : ''
  const def = f.default ?? ''
  let control: string
  if (f.type === 'enum') {
    const opts = (f.enum_values ?? [])
      .map(v => `<option value="${esc(v)}"${v === def ? ' selected' : ''}>${esc(v)}</option>`)
      .join('')
    const placeholder = f.required ? '' : '<option value=""></option>'
    control = `<select id="${esc(id)}" name="${esc(f.name)}" ${req}>${placeholder}${opts}</select>`
  } else {
    // text / number / date all use a plain text input (per spec) — avoids native
    // date-picker silently rejecting non-ISO default values.
    control = `<input id="${esc(id)}" name="${esc(f.name)}" type="text" value="${esc(def)}" ${req} />`
  }
  return `
    <div class="recall-field">
      <label for="${esc(id)}">${esc(f.name)}${star} <span class="field-type">${esc(f.type)}</span></label>
      ${control}
    </div>
  `
}
