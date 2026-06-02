import { createTemplate, getFonts, getLabels, getTemplate, previewTemplate, updateTemplate } from '../api'
import { navigate } from '../router'
import type { LabelEntry } from '../types'
import {
  addTextElement,
  deleteSelected,
  getCanvasJSON,
  initCanvas,
  isTextType,
  loadCanvasJSON,
} from '../editor/canvas'
import type { Canvas } from 'fabric'

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function parsePath(): { name: string; isNew: boolean; newMedia: string } {
  const path = window.location.pathname  // /templates/my-name
  const parts = path.split('/')
  const name = decodeURIComponent(parts[parts.length - 1] ?? '')
  const params = new URLSearchParams(window.location.search)
  const isNew = params.get('new') === '1'
  const newMedia = params.get('media') ?? ''
  return { name, isNew, newMedia }
}

export function mountTemplateEditor(root: HTMLElement): void {
  const { name, isNew, newMedia } = parsePath()

  // Widen the app container for the editor
  const appEl = document.getElementById('app')
  appEl?.classList.add('editor-mode')

  root.innerHTML = `
    <div class="editor-shell">
      <div class="editor-toolbar">
        <button id="btn-back">← Back</button>
        <span class="toolbar-sep"></span>
        <span class="editor-title" id="editor-title">${esc(name)}</span>
        <span class="toolbar-sep"></span>
        <button id="btn-add-text">Add Text</button>
        <button id="btn-delete">Delete</button>
        <span class="toolbar-sep"></span>
        <select id="font-select" title="Font family" style="max-width:160px">
          <option value="">Loading fonts…</option>
        </select>
        <input id="font-size" type="number" min="6" max="400" value="48" title="Font size" style="width:60px" />
        <span class="toolbar-sep"></span>
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
  const btnPreview = root.querySelector<HTMLButtonElement>('#btn-preview')!
  const fontSelect = root.querySelector<HTMLSelectElement>('#font-select')!
  const fontSizeInput = root.querySelector<HTMLInputElement>('#font-size')!
  const statusEl = root.querySelector<HTMLDivElement>('#editor-status')!
  const canvasWrap = root.querySelector<HTMLDivElement>('#canvas-wrap')!
  const previewArea = root.querySelector<HTMLDivElement>('#preview-area')!
  const previewImg = root.querySelector<HTMLImageElement>('#preview-img')!

  let fabricCanvas: Canvas | null = null
  let labelMedia: string = newMedia
  let existsOnServer = !isNew
  let defaultFont = 'DejaVuSans'
  let previewObjectUrl: string | null = null

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
    const [w, h] = label.dots_printable
    const canvasEl = root.querySelector<HTMLCanvasElement>('#fabric-canvas')!
    const { canvas } = initCanvas(canvasEl, w, h, getContainerWidth())
    fabricCanvas = canvas

    // Track selection to drive font controls
    canvas.on('selection:created', updateFontControls)
    canvas.on('selection:updated', updateFontControls)
    canvas.on('selection:cleared', () => {})
  }

  function updateFontControls(): void {
    if (!fabricCanvas) return
    type TextProps = { fontFamily?: string; fontSize?: number; type?: string }
    const obj = fabricCanvas.getActiveObject() as unknown as TextProps | null
    if (obj && isTextType(obj.type)) {
      if (obj.fontFamily) fontSelect.value = obj.fontFamily
      if (obj.fontSize) fontSizeInput.value = String(Math.round(obj.fontSize))
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

  btnBack.addEventListener('click', () => {
    document.getElementById('app')?.classList.remove('editor-mode')
    navigate('/templates')
  })

  btnAddText.addEventListener('click', () => {
    if (!fabricCanvas) return
    addTextElement(fabricCanvas, fontSelect.value || defaultFont)
  })

  btnDelete.addEventListener('click', () => {
    if (!fabricCanvas) return
    deleteSelected(fabricCanvas)
  })

  btnSave.addEventListener('click', () => void doSave())

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
        await createTemplate({ name, label_media: labelMedia, canvas_json: canvasJson })
        existsOnServer = true
      }
      showStatus('Saved.', 'success')
    } catch (err) {
      showStatus((err as Error).message, 'error')
    } finally {
      btnSave.disabled = false
    }
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
          await createTemplate({ name, label_media: labelMedia, canvas_json: canvasJson })
          existsOnServer = true
        }
      }
      // Build a fields dict: use field name as its own placeholder value for preview
      const fields: Record<string, string> = {}
      const blob = await previewTemplate(name, fields)
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
