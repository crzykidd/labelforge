import { deleteTemplate, getLabels, listTemplates } from '../api'
import type { LabelEntry, Template } from '../types'
import { navigate } from '../router'
import { mountLabelMediaSelect, type LabelMediaSelectHandle } from '../labels'

function slugify(s: string): string {
  return s.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

function formatMediaLabel(label: LabelEntry): string {
  const part = label.brother_part || label.display_name || label.id
  const [w, h] = label.tape_size
  const size = h > 0 ? `(${w}×${h}mm)` : `(${w}mm)`
  const red = label.color === 1 ? ' Red' : ''
  return `${part} ${size}${red}`
}

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function fmtDate(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export function mountTemplatesList(root: HTMLElement): void {
  root.innerHTML = `
    <div class="templates-list">
      <div class="templates-list-header">
        <h2>Templates</h2>
        <button id="btn-new-template">New template</button>
      </div>
      <div id="tpl-status" class="status-msg" hidden></div>
      <div id="tpl-body"></div>
    </div>
  `

  const btnNew = root.querySelector<HTMLButtonElement>('#btn-new-template')!
  const statusEl = root.querySelector<HTMLDivElement>('#tpl-status')!
  const bodyEl = root.querySelector<HTMLDivElement>('#tpl-body')!

  function showStatus(msg: string, kind: 'success' | 'error'): void {
    statusEl.textContent = msg
    statusEl.className = `status-msg ${kind}`
    statusEl.hidden = false
  }

  function renderList(templates: Template[], labelMap: Map<string, LabelEntry>): void {
    if (templates.length === 0) {
      bodyEl.innerHTML = `<p class="empty-state">No templates yet. Create one.</p>`
      return
    }
    bodyEl.innerHTML = `
      <table class="tpl-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Media</th>
            <th>Updated</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${templates.map(t => {
            const label = labelMap.get(t.label_media)
            const mediaCellHtml = label
              ? esc(formatMediaLabel(label))
              : `<code>${esc(t.label_media)}</code>`
            return `
            <tr data-name="${esc(t.name)}">
              <td>${esc(t.display_name || t.name)}</td>
              <td>${mediaCellHtml}</td>
              <td>${esc(fmtDate(t.updated_at))}</td>
              <td class="tpl-actions">
                <button class="btn-print" data-name="${esc(t.name)}">Print</button>
                <button class="btn-edit" data-name="${esc(t.name)}">Edit</button>
                <button class="btn-delete" data-name="${esc(t.name)}">Delete</button>
              </td>
            </tr>
          `}).join('')}
        </tbody>
      </table>
    `

    bodyEl.querySelectorAll<HTMLButtonElement>('.btn-print').forEach(btn => {
      btn.addEventListener('click', () => navigate(`/templates/${btn.dataset.name!}/print`))
    })

    bodyEl.querySelectorAll<HTMLButtonElement>('.btn-edit').forEach(btn => {
      btn.addEventListener('click', () => navigate(`/templates/${btn.dataset.name!}`))
    })

    bodyEl.querySelectorAll<HTMLButtonElement>('.btn-delete').forEach(btn => {
      btn.addEventListener('click', async () => {
        const name = btn.dataset.name!
        if (!confirm(`Delete template "${name}"? This cannot be undone.`)) return
        btn.disabled = true
        try {
          await deleteTemplate(name)
          await load()
        } catch (err) {
          showStatus((err as Error).message, 'error')
          btn.disabled = false
        }
      })
    })
  }

  async function load(): Promise<void> {
    bodyEl.innerHTML = `<p>Loading…</p>`
    statusEl.hidden = true
    try {
      const [templates, labels] = await Promise.all([listTemplates(), getLabels()])
      const labelMap = new Map(labels.map(l => [l.id, l]))
      renderList(templates, labelMap)
    } catch (err) {
      showStatus((err as Error).message, 'error')
      bodyEl.innerHTML = ''
    }
  }

  btnNew.addEventListener('click', () => {
    showNewTemplateModal(() => load())
  })

  void load()
}

function showNewTemplateModal(onCreated: () => void): void {
  const overlay = document.createElement('div')
  overlay.className = 'modal-overlay'
  overlay.innerHTML = `
    <div class="modal">
      <h3>New template</h3>
      <div class="modal-status" hidden></div>
      <label>
        Name
        <input id="modal-name" type="text" placeholder="Spool Label" autocomplete="off" />
        <span class="slug-hint" id="slug-hint" hidden></span>
        <span class="field-error" id="name-error" hidden></span>
      </label>
      <label>Label media</label>
      <div id="modal-media-container"></div>
      <div class="modal-actions">
        <button id="modal-cancel">Cancel</button>
        <button id="modal-ok" class="btn-primary" disabled>Create</button>
      </div>
    </div>
  `
  document.body.appendChild(overlay)

  const nameInput = overlay.querySelector<HTMLInputElement>('#modal-name')!
  const slugHint = overlay.querySelector<HTMLSpanElement>('#slug-hint')!
  const mediaContainer = overlay.querySelector<HTMLDivElement>('#modal-media-container')!
  const cancelBtn = overlay.querySelector<HTMLButtonElement>('#modal-cancel')!
  const okBtn = overlay.querySelector<HTMLButtonElement>('#modal-ok')!
  const nameError = overlay.querySelector<HTMLSpanElement>('#name-error')!
  let mediaHandle: LabelMediaSelectHandle | null = null

  const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/

  function validate(): boolean {
    const friendly = nameInput.value.trim()
    if (!friendly) {
      nameError.textContent = 'Name is required'
      nameError.hidden = false
      slugHint.hidden = true
      return false
    }
    const slug = slugify(friendly)
    if (!slug || !SLUG_RE.test(slug)) {
      nameError.textContent = 'Name must contain at least one letter or number'
      nameError.hidden = false
      slugHint.hidden = true
      return false
    }
    nameError.hidden = true
    slugHint.textContent = `URL: ${slug}`
    slugHint.hidden = false
    return true
  }

  function updateOk(): void {
    const friendly = nameInput.value.trim()
    const slug = slugify(friendly)
    okBtn.disabled = !slug || !SLUG_RE.test(slug) || !mediaHandle?.getValue()
  }

  nameInput.addEventListener('input', () => { validate(); updateOk() })

  getLabels().then(labels => {
    mediaHandle = mountLabelMediaSelect({
      container: mediaContainer,
      labels,
      onChange: () => updateOk(),
    })
    updateOk()
  })

  cancelBtn.addEventListener('click', () => overlay.remove())
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove() })

  okBtn.addEventListener('click', () => {
    if (!validate()) return
    const friendly = nameInput.value.trim()
    const slug = slugify(friendly)
    const media = mediaHandle?.getValue() ?? ''
    overlay.remove()
    // Navigate to editor — template created on first Save
    // Pass display_name so the editor can include it in the create call
    navigate(`/templates/${slug}?new=1&media=${encodeURIComponent(media)}&display_name=${encodeURIComponent(friendly)}`)
    onCreated()
  })

  nameInput.focus()
}
