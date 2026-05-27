import { getFonts, getLabels, getSettings, previewQuick, quickPrint, TOKEN_KEY } from '../api'
import type { QuickPrintRequest } from '../types'
import { buildLabelOptionsHtml, firstSupportedId } from '../labels'

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

export function mountQuickPrint(root: HTMLElement): void {
  if (!localStorage.getItem(TOKEN_KEY)) {
    renderTokenGate(root)
  } else {
    renderForm(root)
  }
}

function renderTokenGate(root: HTMLElement): void {
  root.innerHTML = `
    <div class="token-gate">
      <h2>LabelForge</h2>
      <p>Enter your API token to continue.</p>
      <input id="token-input" type="password" placeholder="API token" autocomplete="current-password" />
      <button id="token-save">Save token</button>
    </div>
  `
  const input = root.querySelector<HTMLInputElement>('#token-input')!
  const btn = root.querySelector<HTMLButtonElement>('#token-save')!

  function save(): void {
    const val = input.value.trim()
    if (!val) return
    localStorage.setItem(TOKEN_KEY, val)
    renderForm(root)
  }

  btn.addEventListener('click', save)
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') save() })
}

function renderForm(root: HTMLElement): void {
  root.innerHTML = `
    <div class="quick-print">
      <h2>Quick Print</h2>
      <div id="status-msg" class="status-msg" hidden></div>
      <form id="print-form" autocomplete="off">
        <div>
          <label for="text">Text</label>
          <textarea id="text" rows="4" required></textarea>
        </div>

        <div>
          <label for="font">Font</label>
          <select id="font"><option value="">Loading…</option></select>
        </div>

        <div>
          <label for="font-size">Font size</label>
          <input id="font-size" type="number" min="6" max="200" value="48" />
        </div>

        <div>
          <label for="label-media">Label media</label>
          <select id="label-media"><option value="">Loading…</option></select>
        </div>

        <div>
          <label>Style</label>
          <div class="checkboxes">
            <label><input id="bold" type="checkbox" /> Bold</label>
            <label><input id="italic" type="checkbox" /> Italic</label>
          </div>
        </div>

        <div>
          <label>Alignment</label>
          <div class="radio-group">
            <label><input type="radio" name="alignment" value="left" checked /> Left</label>
            <label><input type="radio" name="alignment" value="center" /> Center</label>
            <label><input type="radio" name="alignment" value="right" /> Right</label>
          </div>
        </div>

        <div>
          <label>Orientation</label>
          <div class="radio-group">
            <label><input type="radio" name="orientation" value="standard" checked /> Standard</label>
            <label><input type="radio" name="orientation" value="rotated" /> Rotated</label>
          </div>
        </div>

        <div class="actions">
          <button type="button" id="btn-preview" disabled>Preview</button>
          <button type="submit" id="btn-print" disabled>Print</button>
        </div>
      </form>
      <div id="preview-area" class="preview-area" hidden>
        <img id="preview-img" alt="Label preview" />
      </div>
    </div>
  `

  const form = root.querySelector<HTMLFormElement>('#print-form')!
  const textarea = root.querySelector<HTMLTextAreaElement>('#text')!
  const fontSelect = root.querySelector<HTMLSelectElement>('#font')!
  const fontSizeInput = root.querySelector<HTMLInputElement>('#font-size')!
  const labelSelect = root.querySelector<HTMLSelectElement>('#label-media')!
  const boldCheck = root.querySelector<HTMLInputElement>('#bold')!
  const italicCheck = root.querySelector<HTMLInputElement>('#italic')!
  const btnPreview = root.querySelector<HTMLButtonElement>('#btn-preview')!
  const btnPrint = root.querySelector<HTMLButtonElement>('#btn-print')!
  const statusMsg = root.querySelector<HTMLDivElement>('#status-msg')!
  const previewArea = root.querySelector<HTMLDivElement>('#preview-area')!
  const previewImg = root.querySelector<HTMLImageElement>('#preview-img')!
  let previewObjectUrl: string | null = null

  function showStatus(msg: string, kind: 'success' | 'error'): void {
    statusMsg.textContent = msg
    statusMsg.className = `status-msg ${kind}`
    statusMsg.hidden = false
  }

  function hideStatus(): void {
    statusMsg.hidden = true
  }

  function updateButtons(): void {
    const empty = textarea.value.trim() === ''
    btnPrint.disabled = empty
    btnPreview.disabled = empty
  }

  function buildRequest(): QuickPrintRequest {
    const alignment = (
      form.querySelector<HTMLInputElement>('input[name="alignment"]:checked')?.value ?? 'left'
    ) as QuickPrintRequest['alignment']
    const orientation = (
      form.querySelector<HTMLInputElement>('input[name="orientation"]:checked')?.value ?? 'standard'
    ) as QuickPrintRequest['orientation']
    return {
      text: textarea.value,
      font: fontSelect.value,
      font_size: parseInt(fontSizeInput.value, 10),
      alignment,
      orientation,
      label_media: labelSelect.value,
      bold: boldCheck.checked,
      italic: italicCheck.checked,
    }
  }

  textarea.addEventListener('input', updateButtons)

  btnPreview.addEventListener('click', async () => {
    btnPreview.disabled = true
    hideStatus()
    try {
      const blob = await previewQuick(buildRequest())
      if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl)
      previewObjectUrl = URL.createObjectURL(blob)
      previewImg.src = previewObjectUrl
      previewArea.hidden = false
    } catch (err) {
      showStatus((err as Error).message, 'error')
    } finally {
      updateButtons()
    }
  })

  // Load fonts, labels, and settings in parallel; settings failure is non-fatal
  Promise.all([
    getFonts(),
    getLabels(),
    getSettings().catch((err: Error) => {
      console.warn('Failed to load settings:', err.message)
      return null as Record<string, unknown> | null
    }),
  ]).then(([fonts, labels, sett]) => {
    // Populate fonts dropdown
    fontSelect.innerHTML = fonts
      .map(f => `<option value="${esc(f.name)}">${esc(f.name)}</option>`)
      .join('')

    labelSelect.innerHTML = buildLabelOptionsHtml(labels)

    // Restore form from settings; last_quick_print takes precedence over per-key defaults
    const lqp = (sett?.last_quick_print ?? null) as QuickPrintRequest | null
    if (lqp) {
      fontSelect.value = lqp.font ?? String(sett?.default_font ?? 'DejaVuSans')
      fontSizeInput.value = String(lqp.font_size ?? sett?.default_font_size ?? 48)
      labelSelect.value = String(lqp.label_media ?? sett?.default_label_media ?? '62')
      boldCheck.checked = lqp.bold ?? false
      italicCheck.checked = lqp.italic ?? false
      const aRadio = form.querySelector<HTMLInputElement>(
        `input[name="alignment"][value="${lqp.alignment ?? 'left'}"]`
      )
      if (aRadio) aRadio.checked = true
      const oRadio = form.querySelector<HTMLInputElement>(
        `input[name="orientation"][value="${lqp.orientation ?? 'standard'}"]`
      )
      if (oRadio) oRadio.checked = true
    } else {
      const defFont = String(sett?.default_font ?? 'DejaVuSans')
      const defSize = String(sett?.default_font_size ?? 48)
      const defMedia = String(sett?.default_label_media ?? '62')
      const defOrientation = String(sett?.default_orientation ?? 'standard')
      fontSelect.value = defFont
      fontSizeInput.value = defSize
      labelSelect.value = defMedia
      const oRadio = form.querySelector<HTMLInputElement>(
        `input[name="orientation"][value="${defOrientation}"]`
      )
      if (oRadio) oRadio.checked = true
    }

    // The chosen default/restored media may be unsupported by the configured
    // printer (its <option> is disabled). Fall back to the first supported id.
    const chosen = labels.find(l => l.id === labelSelect.value)
    if (!chosen || !chosen.supported) {
      const fallback = firstSupportedId(labels)
      if (fallback) labelSelect.value = fallback
    }
  }).catch((err: Error) => {
    showStatus(`Failed to load form data: ${err.message}`, 'error')
  })

  form.addEventListener('submit', async (e) => {
    e.preventDefault()
    btnPrint.disabled = true
    hideStatus()

    try {
      const result = await quickPrint(buildRequest())
      // "sent" = transmitted to printer network backend, not confirmed printed
      showStatus(
        `Sent — job #${result.job_id} (status: ${result.status}). "Sent" means the job was transmitted to the printer; delivery is not confirmed.`,
        'success'
      )
    } catch (err) {
      showStatus((err as Error).message, 'error')
    } finally {
      updateButtons()
    }
  })
}
