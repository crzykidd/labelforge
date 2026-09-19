import { ApiError, createFieldList, getFieldList, updateFieldList } from '../api'
import type { FieldSpec } from '../types'

export interface FieldsPanelHandle {
  /** Replace the panel's schema — called after load and after every Save
   * (the server response is the source of truth for detected fields). */
  setSchema(schema: FieldSpec[]): void
  getSchema(): FieldSpec[]
}

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

const TYPE_OPTIONS: Array<{ value: FieldSpec['type']; label: string }> = [
  { value: 'text', label: 'Text' },
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'list', label: 'List (global)' },
  { value: 'enum', label: 'Enum (this template)' },
]

/**
 * FIELDS panel — lists every field currently in the template's schema (one
 * per detected `{placeholder}`) and lets the user set type / required /
 * default / increment. A `type: "list"` field gets an **E** button that opens
 * a drawer over the canvas to edit the *global* value list of the same name
 * (shared by every template using that field name); `type: "enum"` gets an
 * inline comma-separated values input scoped to this template only.
 *
 * This panel does not detect placeholders itself — `detect_fields` on the
 * backend is the source of truth, so the schema shown here only changes on
 * load and after each Save, from the server's response.
 */
export function mountFieldsPanel(
  container: HTMLElement,
  onChange: (schema: FieldSpec[]) => void,
): FieldsPanelHandle {
  let schema: FieldSpec[] = []

  function findField(name: string): FieldSpec | undefined {
    return schema.find(f => f.name === name)
  }

  function render(): void {
    if (schema.length === 0) {
      container.innerHTML = '<div class="fields-panel-empty">No variable fields yet. Add a {placeholder} to a text, QR, or barcode element.</div>'
      return
    }
    container.innerHTML = schema.map(f => `
      <div class="field-row" data-name="${esc(f.name)}">
        <div class="field-row-name">{${esc(f.name)}}</div>
        <div class="field-row-controls">
          <label class="field-row-item">
            <span>Type</span>
            <select class="field-type-select" data-field="${esc(f.name)}">
              ${TYPE_OPTIONS.map(o => `<option value="${o.value}"${o.value === f.type ? ' selected' : ''}>${o.label}</option>`).join('')}
            </select>
          </label>
          ${f.type === 'list' ? `<button type="button" class="field-list-edit-btn" data-field="${esc(f.name)}" title="Edit the global '${esc(f.name)}' list — shared by every template that uses this field name">E</button>` : ''}
        </div>
        ${f.type === 'enum' ? `
          <label class="field-row-item field-row-item-wide">
            <span>Values (comma-separated)</span>
            <input type="text" class="field-enum-input" data-field="${esc(f.name)}" value="${esc((f.enum_values ?? []).join(', '))}" placeholder="e.g. Red, Blue, Green" />
          </label>
        ` : ''}
        <div class="field-row-controls">
          <label class="field-row-item">
            <span>Default</span>
            <input type="text" class="field-default-input" data-field="${esc(f.name)}" value="${esc(f.default ?? '')}" />
          </label>
          <label class="field-row-checkbox">
            <input type="checkbox" class="field-required-cb" data-field="${esc(f.name)}" ${f.required ? 'checked' : ''} /> Required
          </label>
          <label class="field-row-checkbox" title="Auto-advance this field's trailing number by 1 per label in a batch print">
            <input type="checkbox" class="field-increment-cb" data-field="${esc(f.name)}" ${f.increment ? 'checked' : ''} /> Increment
          </label>
        </div>
      </div>
    `).join('')
  }

  container.addEventListener('change', (e) => {
    const target = e.target as HTMLElement
    const name = target.dataset.field
    if (!name) return
    const field = findField(name)
    if (!field) return

    if (target.classList.contains('field-type-select')) {
      field.type = (target as HTMLSelectElement).value as FieldSpec['type']
      render()  // toggles the E button / enum-values input visibility
    } else if (target.classList.contains('field-default-input')) {
      const v = (target as HTMLInputElement).value
      field.default = v === '' ? null : v
    } else if (target.classList.contains('field-required-cb')) {
      field.required = (target as HTMLInputElement).checked
    } else if (target.classList.contains('field-increment-cb')) {
      field.increment = (target as HTMLInputElement).checked
    } else if (target.classList.contains('field-enum-input')) {
      const v = (target as HTMLInputElement).value
      field.enum_values = v.split(',').map(s => s.trim()).filter(s => s.length > 0)
    } else {
      return
    }
    onChange(schema)
  })

  container.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('.field-list-edit-btn')
    if (!btn) return
    const name = btn.dataset.field
    if (name) openListDrawer(name)
  })

  return {
    setSchema(next: FieldSpec[]) {
      schema = next
      render()
    },
    getSchema() {
      return schema
    },
  }
}

function openListDrawer(fieldName: string): void {
  const overlay = document.createElement('div')
  overlay.className = 'field-list-drawer-overlay'
  overlay.innerHTML = `
    <div class="field-list-drawer">
      <h3>Edit list: {${esc(fieldName)}}</h3>
      <p class="field-list-drawer-warning">
        This list is <strong>global</strong> — it's shared by every template that uses a field
        named <code>${esc(fieldName)}</code>. Saving changes here changes what all of them offer.
      </p>
      <div class="field-list-drawer-status" id="fld-status" hidden></div>
      <div class="field-list-drawer-values" id="fld-values">Loading…</div>
      <div class="field-list-drawer-add">
        <input type="text" id="fld-new-value" placeholder="Add a value" autocomplete="off" />
        <button type="button" id="fld-add-btn">+ Add</button>
      </div>
      <div class="modal-actions">
        <button type="button" id="fld-cancel">Cancel</button>
        <button type="button" id="fld-save" class="btn-primary">Save list</button>
      </div>
    </div>
  `
  document.body.appendChild(overlay)

  const valuesEl = overlay.querySelector<HTMLDivElement>('#fld-values')!
  const newValueInput = overlay.querySelector<HTMLInputElement>('#fld-new-value')!
  const addBtn = overlay.querySelector<HTMLButtonElement>('#fld-add-btn')!
  const cancelBtn = overlay.querySelector<HTMLButtonElement>('#fld-cancel')!
  const saveBtn = overlay.querySelector<HTMLButtonElement>('#fld-save')!
  const statusEl = overlay.querySelector<HTMLDivElement>('#fld-status')!

  let values: string[] = []
  let existedOnServer = false

  function showStatus(msg: string): void {
    statusEl.textContent = msg
    statusEl.hidden = !msg
  }

  function renderValues(): void {
    if (values.length === 0) {
      valuesEl.innerHTML = '<div class="field-list-drawer-empty">No values yet — add one below.</div>'
      return
    }
    valuesEl.innerHTML = values.map((v, i) => `
      <div class="field-list-drawer-row" data-index="${i}">
        <span class="field-list-drawer-value">${esc(v)}</span>
        <span class="field-list-drawer-row-actions">
          <button type="button" class="fld-move-up" data-index="${i}" ${i === 0 ? 'disabled' : ''} title="Move up">↑</button>
          <button type="button" class="fld-move-down" data-index="${i}" ${i === values.length - 1 ? 'disabled' : ''} title="Move down">↓</button>
          <button type="button" class="fld-remove" data-index="${i}" title="Remove">×</button>
        </span>
      </div>
    `).join('')
  }

  valuesEl.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    const btn = target.closest<HTMLButtonElement>('button')
    if (!btn) return
    const idx = Number(btn.dataset.index)
    if (btn.classList.contains('fld-remove')) {
      values.splice(idx, 1)
    } else if (btn.classList.contains('fld-move-up') && idx > 0) {
      ;[values[idx - 1], values[idx]] = [values[idx], values[idx - 1]]
    } else if (btn.classList.contains('fld-move-down') && idx < values.length - 1) {
      ;[values[idx + 1], values[idx]] = [values[idx], values[idx + 1]]
    } else {
      return
    }
    renderValues()
  })

  function addValue(): void {
    const v = newValueInput.value.trim()
    if (!v) return
    if (values.includes(v)) {
      showStatus(`"${v}" is already in the list.`)
      return
    }
    values.push(v)
    newValueInput.value = ''
    showStatus('')
    renderValues()
  }

  addBtn.addEventListener('click', addValue)
  newValueInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addValue()
    }
  })

  function close(): void {
    overlay.remove()
  }

  cancelBtn.addEventListener('click', close)
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close() })

  saveBtn.addEventListener('click', () => {
    saveBtn.disabled = true
    showStatus('')
    const save = existedOnServer
      ? updateFieldList(fieldName, values)
      : createFieldList(fieldName, values)
    save
      .then(() => close())
      .catch((err: Error) => {
        showStatus(err.message)
        saveBtn.disabled = false
      })
  })

  getFieldList(fieldName)
    .then((fl) => {
      existedOnServer = true
      values = [...fl.values]
      renderValues()
    })
    .catch((err) => {
      if (err instanceof ApiError && err.status === 404) {
        // No global list named this yet — the drawer creates one on Save.
        existedOnServer = false
        values = []
        renderValues()
      } else {
        valuesEl.innerHTML = ''
        showStatus((err as Error).message)
      }
    })

  newValueInput.focus()
}
