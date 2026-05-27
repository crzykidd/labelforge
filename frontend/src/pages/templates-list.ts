import { deleteTemplate, listTemplates } from '../api'
import type { Template } from '../types'
import { navigate } from '../router'
import { buildLabelOptionsHtml } from '../labels'

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

  function renderList(templates: Template[]): void {
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
          ${templates.map(t => `
            <tr data-name="${esc(t.name)}">
              <td>${esc(t.display_name || t.name)}</td>
              <td><code>${esc(t.label_media)}</code></td>
              <td>${esc(fmtDate(t.updated_at))}</td>
              <td class="tpl-actions">
                <button class="btn-print" data-name="${esc(t.name)}">Print</button>
                <button class="btn-edit" data-name="${esc(t.name)}">Edit</button>
                <button class="btn-delete" data-name="${esc(t.name)}">Delete</button>
              </td>
            </tr>
          `).join('')}
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
      const templates = await listTemplates()
      renderList(templates)
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
  import('../api').then(({ getLabels }) => {
    const overlay = document.createElement('div')
    overlay.className = 'modal-overlay'
    overlay.innerHTML = `
      <div class="modal">
        <h3>New template</h3>
        <div class="modal-status" hidden></div>
        <label>
          Name (slug)
          <input id="modal-name" type="text" placeholder="my-template" autocomplete="off" />
          <span class="field-error" id="name-error" hidden></span>
        </label>
        <label>
          Label media
          <select id="modal-media"><option value="">Loading…</option></select>
        </label>
        <div class="modal-actions">
          <button id="modal-cancel">Cancel</button>
          <button id="modal-ok" class="btn-primary" disabled>Create</button>
        </div>
      </div>
    `
    document.body.appendChild(overlay)

    const nameInput = overlay.querySelector<HTMLInputElement>('#modal-name')!
    const mediaSelect = overlay.querySelector<HTMLSelectElement>('#modal-media')!
    const cancelBtn = overlay.querySelector<HTMLButtonElement>('#modal-cancel')!
    const okBtn = overlay.querySelector<HTMLButtonElement>('#modal-ok')!
    const nameError = overlay.querySelector<HTMLSpanElement>('#name-error')!

    const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/

    function validate(): boolean {
      const v = nameInput.value.trim()
      if (!v) { nameError.textContent = 'Name is required'; nameError.hidden = false; return false }
      if (!SLUG_RE.test(v)) { nameError.textContent = 'Use lowercase letters, numbers, hyphens only'; nameError.hidden = false; return false }
      nameError.hidden = true
      return true
    }

    function updateOk(): void {
      okBtn.disabled = !nameInput.value.trim() || !mediaSelect.value
    }

    nameInput.addEventListener('input', () => { validate(); updateOk() })
    mediaSelect.addEventListener('change', updateOk)

    getLabels().then(labels => {
      mediaSelect.innerHTML = buildLabelOptionsHtml(labels)
      updateOk()
    })

    cancelBtn.addEventListener('click', () => overlay.remove())
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove() })

    okBtn.addEventListener('click', () => {
      if (!validate()) return
      const name = nameInput.value.trim()
      const media = mediaSelect.value
      overlay.remove()
      // Navigate to editor — template created on first Save
      navigate(`/templates/${name}?new=1&media=${encodeURIComponent(media)}`)
      onCreated()
    })

    nameInput.focus()
  })
}
