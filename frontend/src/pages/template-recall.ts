import { batchPrint, getLastValues, getTemplate, previewTemplate, printTemplate } from '../api'
import type { FieldSpec, Template, TemplateLastValues } from '../types'
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

export function mountTemplateRecall(root: HTMLElement): void {
  const name = nameFromPath()
  root.innerHTML = `<div class="template-recall"><p>Loading…</p></div>`

  Promise.all([
    getTemplate(name),
    getLastValues(name).catch(() => ({ values: null, printed_at: null } satisfies TemplateLastValues)),
  ])
    .then(([tpl, lastVals]) => renderRecall(root, tpl, lastVals))
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

function renderRecall(root: HTMLElement, tpl: Template, lastVals: TemplateLastValues): void {
  const fields = tpl.field_schema ?? []
  const hasFields = fields.length > 0
  const incrementFields = fields.filter(f => f.increment)
  const canBatch = incrementFields.length > 0

  root.innerHTML = `
    <div class="template-recall">
      <a href="#" class="back-link" id="back-link">← Templates</a>
      <h2>${esc(tpl.display_name || tpl.name)}</h2>
      <p class="recall-meta">Media: <code>${esc(tpl.label_media)}</code></p>
      <div id="status-msg" class="status-msg" hidden></div>

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
          <button type="submit" id="btn-print">Print</button>
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

  let previewObjectUrl: string | null = null
  let debounceTimer: number | undefined

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
    btnPrint.disabled = missingRequired()
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
    previewTemplate(tpl.name, collectFields())
      .then(blob => {
        if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl)
        previewObjectUrl = URL.createObjectURL(blob)
        previewImg.src = previewObjectUrl
        previewArea.hidden = false
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
    btnPrint.disabled = true
    hideStatus()
    try {
      if (batchEnable?.checked) {
        const labels = buildBatchLabels()
        const result = await batchPrint(tpl.name, labels)
        const kind = result.failed > 0 ? 'error' : 'success'
        showStatus(
          `Batch ${result.batch_id}: ${result.succeeded} sent, ${result.failed} failed (${labels.length} requested). "Sent" means transmitted to the printer; delivery is not confirmed.`,
          kind,
        )
      } else {
        const result = await printTemplate(tpl.name, collectFields())
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
