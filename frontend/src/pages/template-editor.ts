import { createTemplate, duplicateTemplate, getFonts, getLabels, getTemplate, previewTemplate, updateTemplate } from '../api'
import { navigate } from '../router'
import type { LabelEntry } from '../types'
import {
  DEFAULT_CONTINUOUS_LENGTH_DOTS,
  addTextElement,
  deleteSelected,
  getCanvasJSON,
  initCanvas,
  isTextType,
  loadCanvasJSON,
} from '../editor/canvas'
import { mountLabelMediaSelect } from '../labels'
import type { LabelMediaSelectHandle } from '../labels'
import type { Canvas } from 'fabric'

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function parsePath(): { name: string; isNew: boolean; newMedia: string; newDisplayName: string } {
  const path = window.location.pathname  // /templates/my-name
  const parts = path.split('/')
  const name = decodeURIComponent(parts[parts.length - 1] ?? '')
  const params = new URLSearchParams(window.location.search)
  const isNew = params.get('new') === '1'
  const newMedia = params.get('media') ?? ''
  const newDisplayName = params.get('display_name') ?? ''
  return { name, isNew, newMedia, newDisplayName }
}

export function mountTemplateEditor(root: HTMLElement): void {
  const { name, isNew, newMedia, newDisplayName } = parsePath()
  // Friendly name shown in the toolbar title; falls back to the slug
  let displayName = newDisplayName || name

  // Widen the app container for the editor
  const appEl = document.getElementById('app')
  appEl?.classList.add('editor-mode')

  root.innerHTML = `
    <div class="editor-shell">
      <div class="editor-toolbar">
        <button id="btn-back">← Back</button>
        <span class="toolbar-sep"></span>
        <span class="editor-title" id="editor-title">${esc(displayName)}</span>${displayName !== name ? `<span class="editor-title-slug" id="editor-title-slug">${esc(name)}</span>` : ''}
        <code class="editor-media-badge" id="editor-media">${esc(isNew ? newMedia : '')}</code>
        <span class="toolbar-sep"></span>
        <button id="btn-add-text" title="Add a text element. Use {fieldname} placeholders (single braces) for variable fields.">Add Text</button>
        <button id="btn-delete">Delete</button>
        <span class="toolbar-sep"></span>
        <select id="font-select" title="Font family" style="max-width:160px">
          <option value="">Loading fonts…</option>
        </select>
        <input id="font-size" type="number" min="6" max="400" value="48" title="Font size" style="width:60px" />
        <span class="toolbar-sep" id="sep-color"></span>
        <select id="text-color" title="Text color">
          <option value="#000000">Black</option>
          <option value="#ff0000">Red</option>
        </select>
        <span class="toolbar-sep"></span>
        <button id="btn-save-as">Save As</button>
        <button id="btn-preview">Preview</button>
        <button id="btn-save" class="btn-primary">Save</button>
      </div>
      <div id="editor-status" class="editor-status" hidden></div>
      <div class="editor-canvas-wrap" id="canvas-wrap">
        <div class="editor-canvas-inner" id="canvas-inner">
          <canvas id="fabric-canvas"></canvas>
        </div>
      </div>
      <div id="preview-area" class="preview-area" hidden style="padding:1rem">
        <img id="preview-img" alt="Server render preview" style="max-width:100%;border:1px solid #ddd" />
      </div>
    </div>
  `

  const btnBack = root.querySelector<HTMLButtonElement>('#btn-back')!
  const btnAddText = root.querySelector<HTMLButtonElement>('#btn-add-text')!
  const btnDelete = root.querySelector<HTMLButtonElement>('#btn-delete')!
  const btnSave = root.querySelector<HTMLButtonElement>('#btn-save')!
  const btnSaveAs = root.querySelector<HTMLButtonElement>('#btn-save-as')!
  const btnPreview = root.querySelector<HTMLButtonElement>('#btn-preview')!
  const fontSelect = root.querySelector<HTMLSelectElement>('#font-select')!
  const fontSizeInput = root.querySelector<HTMLInputElement>('#font-size')!
  const textColorSelect = root.querySelector<HTMLSelectElement>('#text-color')!
  const mediaBadge = root.querySelector<HTMLElement>('#editor-media')!
  const statusEl = root.querySelector<HTMLDivElement>('#editor-status')!
  const canvasWrap = root.querySelector<HTMLDivElement>('#canvas-wrap')!
  const previewArea = root.querySelector<HTMLDivElement>('#preview-area')!
  const previewImg = root.querySelector<HTMLImageElement>('#preview-img')!

  let fabricCanvas: Canvas | null = null
  let labelMedia: string = newMedia
  let labelColorCapable = false
  let existsOnServer = !isNew
  let defaultFont = 'DejaVuSans'
  let previewObjectUrl: string | null = null
  let cachedLabels: LabelEntry[] = []

  function showStatus(msg: string, kind: 'success' | 'error' | ''): void {
    if (!msg) { statusEl.hidden = true; return }
    statusEl.textContent = msg
    statusEl.className = `editor-status ${kind}`
    statusEl.hidden = false
  }

  function getContainerWidth(): number {
    return canvasWrap.clientWidth || 800
  }

  async function initEditor(label: LabelEntry): Promise<void> {
    labelMedia = label.id
    labelColorCapable = label.color === 1
    mediaBadge.textContent = label.id

    const [w, rawH] = label.dots_printable
    // Continuous media report length 0; open at a default working length so the
    // editor canvas isn't zero-height (print length is content-driven server-side).
    const h = rawH > 0 ? rawH : DEFAULT_CONTINUOUS_LENGTH_DOTS
    const canvasEl = root.querySelector<HTMLCanvasElement>('#fabric-canvas')!
    const { canvas } = initCanvas(canvasEl, w, h, getContainerWidth())
    fabricCanvas = canvas

    // Red option enabled only for two-color media; always visible so users know it exists.
    const redOpt = textColorSelect.querySelector<HTMLOptionElement>('option[value="#ff0000"]')!
    redOpt.disabled = !labelColorCapable
    if (!labelColorCapable) redOpt.title = 'Requires a two-color label (e.g. 62red)'

    // Track selection to drive font controls
    canvas.on('selection:created', updateFontControls)
    canvas.on('selection:updated', updateFontControls)
    canvas.on('selection:cleared', () => {})
  }

  function updateFontControls(): void {
    if (!fabricCanvas) return
    type TextProps = { fontFamily?: string; fontSize?: number; fill?: string; type?: string }
    const obj = fabricCanvas.getActiveObject() as unknown as TextProps | null
    if (obj && isTextType(obj.type)) {
      if (obj.fontFamily) fontSelect.value = obj.fontFamily
      if (obj.fontSize) fontSizeInput.value = String(Math.round(obj.fontSize))
      if (obj.fill) {
        const f = (obj.fill as string).toLowerCase()
        const wantRed = (f === '#ff0000' || f === 'red') && labelColorCapable
        textColorSelect.value = wantRed ? '#ff0000' : '#000000'
      }
    }
  }

  fontSelect.addEventListener('change', () => {
    if (!fabricCanvas) return
    const obj = fabricCanvas.getActiveObject()
    if (obj && isTextType(obj.type)) {
      obj.set('fontFamily', fontSelect.value)
      fabricCanvas.renderAll()
    }
  })

  fontSizeInput.addEventListener('change', () => {
    if (!fabricCanvas) return
    const sz = parseInt(fontSizeInput.value, 10)
    if (!isNaN(sz) && sz >= 6) {
      const obj = fabricCanvas.getActiveObject()
      if (obj && isTextType(obj.type)) {
        obj.set('fontSize', sz)
        fabricCanvas.renderAll()
      }
    }
  })

  textColorSelect.addEventListener('change', () => {
    if (!fabricCanvas) return
    const obj = fabricCanvas.getActiveObject()
    if (obj && isTextType(obj.type)) {
      obj.set('fill', textColorSelect.value)
      fabricCanvas.renderAll()
    }
  })

  btnBack.addEventListener('click', () => {
    document.getElementById('app')?.classList.remove('editor-mode')
    navigate('/templates')
  })

  btnAddText.addEventListener('click', () => {
    if (!fabricCanvas) return
    const fill = textColorSelect.value  // Red is disabled on mono media; always safe to read
    addTextElement(fabricCanvas, fontSelect.value || defaultFont, fill)
  })

  btnDelete.addEventListener('click', () => {
    if (!fabricCanvas) return
    deleteSelected(fabricCanvas)
  })

  btnSave.addEventListener('click', () => void doSave())

  btnSaveAs.addEventListener('click', () => void doSaveAs())

  btnPreview.addEventListener('click', () => void doPreview())

  async function doSave(): Promise<void> {
    if (!fabricCanvas) return
    const objs = fabricCanvas.getObjects()
    if (objs.length === 0) {
      showStatus('Add at least one element before saving.', 'error')
      return
    }
    btnSave.disabled = true
    showStatus('', '')
    try {
      const canvasJson = getCanvasJSON(fabricCanvas)
      if (existsOnServer) {
        await updateTemplate(name, { canvas_json: canvasJson, label_media: labelMedia })
      } else {
        await createTemplate({ name, display_name: newDisplayName || undefined, label_media: labelMedia, canvas_json: canvasJson })
        existsOnServer = true
      }
      showStatus('Saved.', 'success')
    } catch (err) {
      showStatus((err as Error).message, 'error')
    } finally {
      btnSave.disabled = false
    }
  }

  async function doSaveAs(): Promise<void> {
    // Save current state first so the clone copies the latest canvas
    await doSave()
    // Only proceed if we're saved on the server
    if (!existsOnServer) return
    showSaveAsModal(name, labelMedia, cachedLabels)
  }

  async function doPreview(): Promise<void> {
    if (!fabricCanvas) return
    btnPreview.disabled = true
    showStatus('', '')
    try {
      // Save first so server has the latest canvas
      const objs = fabricCanvas.getObjects()
      if (objs.length > 0) {
        const canvasJson = getCanvasJSON(fabricCanvas)
        if (existsOnServer) {
          await updateTemplate(name, { canvas_json: canvasJson, label_media: labelMedia })
        } else {
          await createTemplate({ name, display_name: newDisplayName || undefined, label_media: labelMedia, canvas_json: canvasJson })
          existsOnServer = true
        }
      }
      // Build a fields dict: use field name as its own placeholder value for preview
      const fields: Record<string, string> = {}
      const { blob } = await previewTemplate(name, fields)
      if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl)
      previewObjectUrl = URL.createObjectURL(blob)
      previewImg.src = previewObjectUrl
      previewArea.hidden = false
    } catch (err) {
      showStatus((err as Error).message, 'error')
    } finally {
      btnPreview.disabled = false
    }
  }

  // Bootstrap: load label catalog + fonts, then either load existing template or init blank
  Promise.all([getLabels(), getFonts()]).then(async ([labels, fonts]) => {
    cachedLabels = labels

    // Populate font selector
    defaultFont = fonts[0]?.name ?? 'DejaVuSans'
    fontSelect.innerHTML = fonts
      .map(f => `<option value="${esc(f.name)}">${esc(f.name)}</option>`)
      .join('')
    // Try to select DejaVuSans as default
    const dvs = fonts.find(f => f.name.includes('DejaVu') || f.name.includes('DejaVuSans'))
    if (dvs) { fontSelect.value = dvs.name; defaultFont = dvs.name }

    if (isNew) {
      // New template: use newMedia from query params
      const label = labels.find(l => l.id === newMedia)
      if (!label) { showStatus(`Unknown label media: ${newMedia}`, 'error'); return }
      await initEditor(label)
    } else {
      // Load existing template
      try {
        const tmpl = await getTemplate(name)
        labelMedia = tmpl.label_media
        // Update title to show the stored display_name
        displayName = tmpl.display_name || name
        const titleEl = root.querySelector<HTMLElement>('#editor-title')
        if (titleEl) titleEl.textContent = displayName
        const label = labels.find(l => l.id === tmpl.label_media)
        if (!label) { showStatus(`Unknown label media: ${tmpl.label_media}`, 'error'); return }
        await initEditor(label)
        if (fabricCanvas && tmpl.canvas_json && Object.keys(tmpl.canvas_json).length > 0) {
          await loadCanvasJSON(fabricCanvas, tmpl.canvas_json)
        }
      } catch (err) {
        showStatus((err as Error).message, 'error')
      }
    }
  }).catch((err: Error) => {
    showStatus(`Failed to load: ${err.message}`, 'error')
  })
}

function showSaveAsModal(sourceName: string, currentMedia: string, allLabels: LabelEntry[]): void {
  const overlay = document.createElement('div')
  overlay.className = 'modal-overlay'
  overlay.innerHTML = `
    <div class="modal">
      <h3>Save As</h3>
      <div class="modal-status" id="sa-status" hidden></div>
      <label>
        New name (slug)
        <input id="sa-name" type="text" placeholder="my-template-copy" autocomplete="off" />
        <span class="field-error" id="sa-name-error" hidden></span>
      </label>
      <label>Label media</label>
      <div id="sa-media-container"></div>
      <div class="modal-actions">
        <button id="sa-cancel">Cancel</button>
        <button id="sa-ok" class="btn-primary" disabled>Save As</button>
      </div>
    </div>
  `
  document.body.appendChild(overlay)

  const nameInput = overlay.querySelector<HTMLInputElement>('#sa-name')!
  const mediaContainer = overlay.querySelector<HTMLDivElement>('#sa-media-container')!
  const cancelBtn = overlay.querySelector<HTMLButtonElement>('#sa-cancel')!
  const okBtn = overlay.querySelector<HTMLButtonElement>('#sa-ok')!
  const nameError = overlay.querySelector<HTMLSpanElement>('#sa-name-error')!
  const statusEl = overlay.querySelector<HTMLDivElement>('#sa-status')!
  let mediaHandle: LabelMediaSelectHandle | null = null

  const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/

  function validate(): boolean {
    const v = nameInput.value.trim()
    if (!v) { nameError.textContent = 'Name is required'; nameError.hidden = false; return false }
    if (!SLUG_RE.test(v)) { nameError.textContent = 'Use lowercase letters, numbers, hyphens only'; nameError.hidden = false; return false }
    nameError.hidden = true
    return true
  }

  function updateOk(): void {
    okBtn.disabled = !nameInput.value.trim() || !mediaHandle?.getValue()
  }

  nameInput.addEventListener('input', () => { validate(); updateOk() })

  mediaHandle = mountLabelMediaSelect({
    container: mediaContainer,
    labels: allLabels,
    initialValue: currentMedia,
    onChange: () => updateOk(),
  })
  updateOk()

  cancelBtn.addEventListener('click', () => overlay.remove())
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove() })

  okBtn.addEventListener('click', () => {
    if (!validate()) return
    const newName = nameInput.value.trim()
    const newMedia = mediaHandle?.getValue() ?? ''
    okBtn.disabled = true

    duplicateTemplate(sourceName, { name: newName, label_media: newMedia })
      .then(() => {
        overlay.remove()
        navigate(`/templates/${newName}`)
      })
      .catch((err: Error) => {
        statusEl.textContent = err.message
        statusEl.hidden = false
        okBtn.disabled = false
      })
  })

  nameInput.focus()
}
