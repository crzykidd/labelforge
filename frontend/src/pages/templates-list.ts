import { deleteTemplate, getLabels, listTemplates } from '../api'
import type { LabelEntry, Template } from '../types'
import { navigate } from '../router'
import { mountLabelMediaSelect, type LabelMediaSelectHandle } from '../labels'
import { getLastLabel } from '../lastLabel'

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

// Inline line icons (no icon-font dependency). 16px, inherit currentColor.
const ICON_PRINT = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>`
const ICON_EDIT = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>`
const ICON_DELETE = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`

function fmtDate(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    // Compact: drop seconds so the column stays on one line (e.g. "6/6/2026, 8:51 AM").
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'numeric', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
    })
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
              <td class="tpl-updated">${esc(fmtDate(t.updated_at))}</td>
              <td class="tpl-actions">
                <button class="icon-btn btn-print" data-name="${esc(t.name)}" title="Print" aria-label="Print ${esc(t.display_name || t.name)}">${ICON_PRINT}</button>
                <button class="icon-btn btn-edit" data-name="${esc(t.name)}" title="Edit" aria-label="Edit ${esc(t.display_name || t.name)}">${ICON_EDIT}</button>
                <button class="icon-btn btn-delete" data-name="${esc(t.name)}" title="Delete" aria-label="Delete ${esc(t.display_name || t.name)}">${ICON_DELETE}</button>
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
      initialValue: getLastLabel() ?? undefined,
      onChange: () => updateOk(),
      remember: true,
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
