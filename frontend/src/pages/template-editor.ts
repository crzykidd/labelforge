import { createTemplate, duplicateTemplate, getFonts, getLabels, getTemplate, previewTemplate, updateTemplate } from '../api'
import { navigate } from '../router'
import type { LabelEntry } from '../types'
import {
  DEFAULT_CONTINUOUS_LENGTH_DOTS,
  addBarcodeElement,
  addQrElement,
  addTextElement,
  deleteSelected,
  getCanvasJSON,
  initCanvas,
  isBarcodeType,
  isQrType,
  isTextType,
  loadCanvasJSON,
  makeBarcodePlaceholderDataUrl,
  makeQrPlaceholderDataUrl,
} from '../editor/canvas'
import { loadServerFonts } from '../editor/fonts'
import { mountLabelMediaSelect } from '../labels'
import type { LabelMediaSelectHandle } from '../labels'
import { getLastLabel } from '../lastLabel'
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
        <button id="btn-add-qr" title="Add a QR code element. QR preview is generated on Preview/print (server-side). Use {fieldname} placeholders for variable payloads.">Add QR</button>
        <button id="btn-add-barcode" title="Add a barcode element. Real barcode is generated on Preview/print (server-side). Use {fieldname} placeholders for variable payloads. Note: some symbologies require specific digit counts (e.g. EAN-13 needs 12–13 digits, EAN-8 needs 7–8, UPC-A needs 11–12).">Add Barcode</button>
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
        <span class="toolbar-sep" id="sep-qr" hidden></span>
        <input id="qr-payload" type="text" placeholder="QR payload or {field}" title="QR code payload. Use {fieldname} for variable fields." style="width:200px" hidden />
        <select id="qr-ec" title="Error correction level" hidden>
          <option value="L">EC: L (7%)</option>
          <option value="M" selected>EC: M (15%)</option>
          <option value="Q">EC: Q (25%)</option>
          <option value="H">EC: H (30%)</option>
        </select>
        <span class="toolbar-sep" id="sep-barcode" hidden></span>
        <input id="barcode-payload" type="text" placeholder="Barcode payload or {field}" title="Barcode payload. Use {fieldname} for variable fields. Some symbologies require specific digit counts (e.g. EAN-13 = 12–13 digits). The backend falls back to Code 128 on an invalid symbology." style="width:200px" hidden />
        <select id="barcode-symbology" title="Barcode symbology" hidden>
          <option value="code128" selected>Code 128</option>
          <option value="code39">Code 39</option>
          <option value="ean13">EAN-13</option>
          <option value="ean8">EAN-8</option>
          <option value="upca">UPC-A</option>
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
  const btnAddQr = root.querySelector<HTMLButtonElement>('#btn-add-qr')!
  const btnAddBarcode = root.querySelector<HTMLButtonElement>('#btn-add-barcode')!
  const btnDelete = root.querySelector<HTMLButtonElement>('#btn-delete')!
  const btnSave = root.querySelector<HTMLButtonElement>('#btn-save')!
  const btnSaveAs = root.querySelector<HTMLButtonElement>('#btn-save-as')!
  const btnPreview = root.querySelector<HTMLButtonElement>('#btn-preview')!
  const fontSelect = root.querySelector<HTMLSelectElement>('#font-select')!
  const fontSizeInput = root.querySelector<HTMLInputElement>('#font-size')!
  const textColorSelect = root.querySelector<HTMLSelectElement>('#text-color')!
  const sepQr = root.querySelector<HTMLSpanElement>('#sep-qr')!
  const qrPayloadInput = root.querySelector<HTMLInputElement>('#qr-payload')!
  const qrEcSelect = root.querySelector<HTMLSelectElement>('#qr-ec')!
  const sepBarcode = root.querySelector<HTMLSpanElement>('#sep-barcode')!
  const barcodePayloadInput = root.querySelector<HTMLInputElement>('#barcode-payload')!
  const barcodeSymbologySelect = root.querySelector<HTMLSelectElement>('#barcode-symbology')!
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

  // Text and QR controls are only relevant when those element types are selected.
  // Start hidden; selection events reveal them. QR controls are already hidden via
  // HTML `hidden` attribute; text controls need an explicit JS hide since they were
  // previously always visible.
  fontSelect.style.display = 'none'
  fontSizeInput.style.display = 'none'
  root.querySelector<HTMLElement>('#sep-color')!.hidden = true
  textColorSelect.style.display = 'none'

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

    // Track selection to drive per-type toolbar controls
    canvas.on('selection:created', updateSelectionControls)
    canvas.on('selection:updated', updateSelectionControls)
    canvas.on('selection:cleared', () => {
      showTextControls(false)
      showQrControls(false)
      showBarcodeControls(false)
    })
  }

  function showTextControls(visible: boolean): void {
    fontSelect.style.display = visible ? '' : 'none'
    fontSizeInput.style.display = visible ? '' : 'none'
    const sepColor = root.querySelector<HTMLElement>('#sep-color')!
    sepColor.hidden = !visible
    textColorSelect.style.display = visible ? '' : 'none'
  }

  function showQrControls(visible: boolean): void {
    sepQr.hidden = !visible
    qrPayloadInput.hidden = !visible
    qrEcSelect.hidden = !visible
  }

  function showBarcodeControls(visible: boolean): void {
    sepBarcode.hidden = !visible
    barcodePayloadInput.hidden = !visible
    barcodeSymbologySelect.hidden = !visible
  }

  function updateSelectionControls(): void {
    if (!fabricCanvas) return
    const obj = fabricCanvas.getActiveObject()
    const textSelected = obj ? isTextType(obj.type) : false
    const qrSelected = isQrType(obj)
    const barcodeSelected = isBarcodeType(obj)

    showTextControls(textSelected)
    showQrControls(qrSelected)
    showBarcodeControls(barcodeSelected)

    if (textSelected) {
      updateFontControls(obj)
    }
    if (qrSelected && obj) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const o = obj as any
      qrPayloadInput.value = (o['labelforge_qr_payload'] as string) ?? ''
      qrEcSelect.value = (o['labelforge_qr_error_correction'] as string) ?? 'M'
    }
    if (barcodeSelected && obj) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const o = obj as any
      barcodePayloadInput.value = (o['labelforge_barcode_payload'] as string) ?? ''
      barcodeSymbologySelect.value = (o['labelforge_barcode_symbology'] as string) ?? 'code128'
    }
  }

  function updateFontControls(obj: import('fabric').FabricObject | null | undefined): void {
    if (!obj) return
    type TextProps = { fontFamily?: string; fontSize?: number; fill?: string; type?: string }
    const t = obj as unknown as TextProps
    if (t.fontFamily) fontSelect.value = t.fontFamily
    if (t.fontSize) fontSizeInput.value = String(Math.round(t.fontSize))
    if (t.fill) {
      const f = (t.fill as string).toLowerCase()
      const wantRed = (f === '#ff0000' || f === 'red') && labelColorCapable
      textColorSelect.value = wantRed ? '#ff0000' : '#000000'
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

  qrPayloadInput.addEventListener('change', () => {
    if (!fabricCanvas) return
    const obj = fabricCanvas.getActiveObject()
    if (!isQrType(obj) || !obj) return
    const newPayload = qrPayloadInput.value
    obj.set('labelforge_qr_payload', newPayload)
    // Regenerate placeholder so visible text matches the new payload
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const px = Math.round(((obj as any).width ?? 150) * ((obj as any).scaleX ?? 1))
    const dataUrl = makeQrPlaceholderDataUrl(newPayload, Math.max(50, Math.min(px, 600)))
    // FabricImage.setSrc is async; render after it resolves
    void (obj as import('fabric').FabricImage).setSrc(dataUrl).then(() => {
      fabricCanvas?.renderAll()
    })
  })

  qrEcSelect.addEventListener('change', () => {
    if (!fabricCanvas) return
    const obj = fabricCanvas.getActiveObject()
    if (!isQrType(obj) || !obj) return
    obj.set('labelforge_qr_error_correction', qrEcSelect.value)
    fabricCanvas.renderAll()
  })

  barcodePayloadInput.addEventListener('change', () => {
    if (!fabricCanvas) return
    const obj = fabricCanvas.getActiveObject()
    if (!isBarcodeType(obj) || !obj) return
    const newPayload = barcodePayloadInput.value
    obj.set('labelforge_barcode_payload', newPayload)
    // Regenerate placeholder so visible text matches the new payload
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const o = obj as any
    const w = Math.max(50, Math.min(Math.round((o.width ?? 300) * (o.scaleX ?? 1)), 1200))
    const h = Math.max(20, Math.min(Math.round((o.height ?? 100) * (o.scaleY ?? 1)), 600))
    const dataUrl = makeBarcodePlaceholderDataUrl(newPayload, w, h)
    void (obj as import('fabric').FabricImage).setSrc(dataUrl).then(() => {
      fabricCanvas?.renderAll()
    })
  })

  barcodeSymbologySelect.addEventListener('change', () => {
    if (!fabricCanvas) return
    const obj = fabricCanvas.getActiveObject()
    if (!isBarcodeType(obj) || !obj) return
    obj.set('labelforge_barcode_symbology', barcodeSymbologySelect.value)
    fabricCanvas.renderAll()
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

  btnAddQr.addEventListener('click', () => {
    if (!fabricCanvas) return
    void addQrElement(fabricCanvas)
  })

  btnAddBarcode.addEventListener('click', () => {
    if (!fabricCanvas) return
    void addBarcodeElement(fabricCanvas)
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

  // Bootstrap: load label catalog + fonts, register fonts in browser, then
  // either load existing template or init blank canvas.
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

    // Register server fonts so the canvas uses real typefaces instead of the
    // browser's serif fallback.  loadServerFonts guards double-registration so
    // fonts already loaded app-wide (main.ts) are skipped cheaply.
    await loadServerFonts(fonts)

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
          // Re-render after fonts are guaranteed registered so text elements
          // paint with the correct typeface rather than a serif fallback.
          fabricCanvas?.renderAll()
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
    initialValue: getLastLabel() ?? currentMedia,
    onChange: () => updateOk(),
    remember: true,
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
