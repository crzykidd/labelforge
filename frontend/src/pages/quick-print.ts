import { getFonts, getLabels, quickPrint, TOKEN_KEY } from '../api'
import type { LabelEntry, QuickPrintRequest } from '../types'

// localStorage is the v1 stand-in for saved settings; replace when GET/PUT /api/settings exists
const PREF = {
  font: 'labelforge_font',
  font_size: 'labelforge_font_size',
  label_media: 'labelforge_label_media',
  alignment: 'labelforge_alignment',
  orientation: 'labelforge_orientation',
}

const FORM_FACTOR_LABEL: Record<number, string> = {
  1: 'Die-cut',
  2: 'Continuous',
  3: 'Round',
  4: 'P-touch Continuous',
}

// Render order for form-factor groups
const FF_ORDER = [2, 1, 3, 4]

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
          <button type="button" id="btn-preview" disabled title="Preview endpoint not yet implemented">Preview</button>
          <button type="submit" id="btn-print" disabled>Print</button>
        </div>
      </form>
    </div>
  `

  const form = root.querySelector<HTMLFormElement>('#print-form')!
  const textarea = root.querySelector<HTMLTextAreaElement>('#text')!
  const fontSelect = root.querySelector<HTMLSelectElement>('#font')!
  const fontSizeInput = root.querySelector<HTMLInputElement>('#font-size')!
  const labelSelect = root.querySelector<HTMLSelectElement>('#label-media')!
  const boldCheck = root.querySelector<HTMLInputElement>('#bold')!
  const italicCheck = root.querySelector<HTMLInputElement>('#italic')!
  const btnPrint = root.querySelector<HTMLButtonElement>('#btn-print')!
  const statusMsg = root.querySelector<HTMLDivElement>('#status-msg')!

  function showStatus(msg: string, kind: 'success' | 'error'): void {
    statusMsg.textContent = msg
    statusMsg.className = `status-msg ${kind}`
    statusMsg.hidden = false
  }

  function hideStatus(): void {
    statusMsg.hidden = true
  }

  function updatePrintButton(): void {
    btnPrint.disabled = textarea.value.trim() === ''
  }

  textarea.addEventListener('input', updatePrintButton)

  Promise.all([getFonts(), getLabels()]).then(([fonts, labels]) => {
    // Populate fonts
    fontSelect.innerHTML = fonts
      .map(f => `<option value="${esc(f.name)}">${esc(f.name)}</option>`)
      .join('')
    const savedFont = localStorage.getItem(PREF.font)
    if (savedFont) fontSelect.value = savedFont

    // Group labels by form_factor, sort within groups by display_name
    const groups = new Map<number, LabelEntry[]>()
    for (const label of labels) {
      const ff = label.form_factor
      if (!groups.has(ff)) groups.set(ff, [])
      groups.get(ff)!.push(label)
    }
    for (const entries of groups.values()) {
      entries.sort((a, b) => a.display_name.localeCompare(b.display_name))
    }

    // Render known order first, then any remaining form_factor values
    const allKeys = [...new Set([...FF_ORDER, ...groups.keys()])]
    labelSelect.innerHTML = allKeys
      .filter(k => groups.has(k))
      .map(k => {
        const groupLabel = FORM_FACTOR_LABEL[k] ?? 'Other'
        const opts = groups
          .get(k)!
          .map(l => `<option value="${esc(l.id)}">${esc(l.display_name)}</option>`)
          .join('')
        return `<optgroup label="${esc(groupLabel)}">${opts}</optgroup>`
      })
      .join('')

    const savedLabel = localStorage.getItem(PREF.label_media)
    if (savedLabel) labelSelect.value = savedLabel

    // Restore remaining prefs
    const savedSize = localStorage.getItem(PREF.font_size)
    if (savedSize) fontSizeInput.value = savedSize

    const savedAlignment = localStorage.getItem(PREF.alignment)
    if (savedAlignment) {
      const radio = form.querySelector<HTMLInputElement>(
        `input[name="alignment"][value="${savedAlignment}"]`
      )
      if (radio) radio.checked = true
    }

    const savedOrientation = localStorage.getItem(PREF.orientation)
    if (savedOrientation) {
      const radio = form.querySelector<HTMLInputElement>(
        `input[name="orientation"][value="${savedOrientation}"]`
      )
      if (radio) radio.checked = true
    }
  }).catch((err: Error) => {
    showStatus(`Failed to load form data: ${err.message}`, 'error')
  })

  form.addEventListener('submit', async (e) => {
    e.preventDefault()
    btnPrint.disabled = true
    hideStatus()

    const alignment = (
      form.querySelector<HTMLInputElement>('input[name="alignment"]:checked')?.value ?? 'left'
    ) as QuickPrintRequest['alignment']

    const orientation = (
      form.querySelector<HTMLInputElement>('input[name="orientation"]:checked')?.value ?? 'standard'
    ) as QuickPrintRequest['orientation']

    const req: QuickPrintRequest = {
      text: textarea.value,
      font: fontSelect.value,
      font_size: parseInt(fontSizeInput.value, 10),
      alignment,
      orientation,
      label_media: labelSelect.value,
      bold: boldCheck.checked,
      italic: italicCheck.checked,
    }

    localStorage.setItem(PREF.font, req.font)
    localStorage.setItem(PREF.font_size, String(req.font_size))
    localStorage.setItem(PREF.label_media, req.label_media)
    localStorage.setItem(PREF.alignment, req.alignment)
    localStorage.setItem(PREF.orientation, req.orientation)

    try {
      const result = await quickPrint(req)
      // "sent" = transmitted to printer network backend, not confirmed printed
      showStatus(
        `Sent — job #${result.job_id} (status: ${result.status}). "Sent" means the job was transmitted to the printer; delivery is not confirmed.`,
        'success'
      )
    } catch (err) {
      showStatus((err as Error).message, 'error')
    } finally {
      updatePrintButton()
    }
  })
}
