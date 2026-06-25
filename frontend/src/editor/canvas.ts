import { Canvas, FabricImage, FabricObject, IText } from 'fabric'

export const CUSTOM_PROPS = [
  'labelforge_raw_content',
  'labelforge_qr_payload',
  'labelforge_qr_error_correction',
  'labelforge_barcode_payload',
  'labelforge_barcode_symbology',
] as const

// Continuous media report a printable length of 0 (endless roll). The editor
// still needs a finite working canvas, so continuous templates open at this
// initial length (≈84mm at 300dpi). Print length is derived from content
// server-side, so this is only the starting editing area.
// 1000 dots keeps the initial canvas portrait for the 62mm roll (696px wide):
// scale = min(1, 600/1000=0.6) → 418×600 display, not the landscape 696×400
// that 400 dots produced.
// See docs/features/templates.md.
export const DEFAULT_CONTINUOUS_LENGTH_DOTS = 1000

// Register all custom props so canvas.toJSON() includes them on every object automatically.
for (const prop of CUSTOM_PROPS) {
  FabricObject.customProperties.push(prop)
}

/**
 * True for any Fabric text object. Fabric v6 reports `type` as the PascalCase
 * class name ('IText', 'Textbox'); v5 used lowercase/hyphenated ('i-text').
 * Normalize so both serializations match.
 */
export function isTextType(type: string | undefined): boolean {
  const t = (type ?? '').toLowerCase().replace(/-/g, '')
  return t === 'itext' || t === 'text' || t === 'textbox'
}

/**
 * True for a Fabric Image that carries the QR custom prop.
 * QR elements serialize as type "Image" (same as real image elements), so
 * they must be distinguished by the custom prop — exactly as the backend does.
 */
export function isQrType(obj: FabricObject | null | undefined): boolean {
  if (!obj) return false
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (obj as any)['labelforge_qr_payload'] !== undefined
}

/**
 * True for a Fabric Image that carries the barcode custom prop.
 * Mirrors isQrType — same Fabric Image type, distinguished only by the prop.
 */
export function isBarcodeType(obj: FabricObject | null | undefined): boolean {
  if (!obj) return false
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (obj as any)['labelforge_barcode_payload'] !== undefined
}

/**
 * Generate a placeholder data URL for a QR element so users can see where the
 * element sits on the canvas. The actual QR bitmap is generated server-side at
 * preview/print time — this is purely a positioning aid.
 *
 * Returns a data URL of a square PNG with a bordered box, "QR" label, and
 * truncated payload text. Size is `px` × `px`.
 */
export function makeQrPlaceholderDataUrl(payload: string, px = 150): string {
  const c = document.createElement('canvas')
  c.width = px
  c.height = px
  const ctx = c.getContext('2d')!

  // White background
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, px, px)

  // Border
  ctx.strokeStyle = '#888888'
  ctx.lineWidth = 2
  ctx.strokeRect(2, 2, px - 4, px - 4)

  // Corner decorators to evoke a QR feel
  const cSize = Math.max(10, Math.round(px * 0.18))
  ctx.fillStyle = '#333333'
  for (const [cx, cy] of [[4, 4], [px - 4 - cSize, 4], [4, px - 4 - cSize]] as [number, number][]) {
    ctx.fillRect(cx, cy, cSize, cSize)
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(cx + 3, cy + 3, cSize - 6, cSize - 6)
    ctx.fillStyle = '#333333'
    ctx.fillRect(cx + 6, cy + 6, cSize - 12, cSize - 12)
    ctx.fillStyle = '#333333'
  }

  // "QR" label
  const labelSize = Math.max(12, Math.round(px * 0.18))
  ctx.fillStyle = '#333333'
  ctx.font = `bold ${labelSize}px sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText('QR', px / 2, px / 2 - labelSize * 0.4)

  // Truncated payload text below label
  const maxPayload = 20
  const display = payload.length > maxPayload ? payload.slice(0, maxPayload - 1) + '…' : payload
  const payloadSize = Math.max(8, Math.round(px * 0.09))
  ctx.font = `${payloadSize}px sans-serif`
  ctx.fillStyle = '#555555'
  ctx.fillText(display, px / 2, px / 2 + labelSize * 0.9)

  return c.toDataURL('image/png')
}

/**
 * Generate a placeholder data URL for a barcode element. Barcodes are wide, not
 * square — the placeholder draws a bordered rectangle with a few vertical bars, a
 * "BARCODE" label, and the truncated payload text. Width and height are separate
 * so the placeholder can match the element's landscape aspect ratio.
 *
 * The actual barcode is generated server-side at preview/print time.
 */
export function makeBarcodePlaceholderDataUrl(payload: string, w = 300, h = 100): string {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const ctx = c.getContext('2d')!

  // White background
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, w, h)

  // Border
  ctx.strokeStyle = '#888888'
  ctx.lineWidth = 2
  ctx.strokeRect(2, 2, w - 4, h - 4)

  // Vertical bars to evoke a barcode — draw in middle 60% of width, upper 55% of height
  const barAreaX = Math.round(w * 0.20)
  const barAreaW = Math.round(w * 0.60)
  const barAreaY = Math.round(h * 0.10)
  const barAreaH = Math.round(h * 0.55)
  const barWidths = [3, 1, 2, 1, 3, 1, 2, 1, 3, 1, 2, 1, 3]
  const totalBarW = barWidths.reduce((a, b) => a + b, 0)
  const barScale = barAreaW / totalBarW
  let bx = barAreaX
  let drawBlack = true
  for (const bw of barWidths) {
    if (drawBlack) {
      ctx.fillStyle = '#222222'
      ctx.fillRect(Math.round(bx), barAreaY, Math.max(1, Math.round(bw * barScale)), barAreaH)
    }
    bx += bw * barScale
    drawBlack = !drawBlack
  }

  // "BARCODE" label below bars
  const labelSize = Math.max(8, Math.round(h * 0.18))
  ctx.fillStyle = '#333333'
  ctx.font = `bold ${labelSize}px sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  ctx.fillText('BARCODE', w / 2, barAreaY + barAreaH + Math.round(h * 0.05))

  // Truncated payload text
  const maxPayload = 24
  const display = payload.length > maxPayload ? payload.slice(0, maxPayload - 1) + '…' : payload
  const payloadSize = Math.max(7, Math.round(h * 0.13))
  ctx.font = `${payloadSize}px sans-serif`
  ctx.fillStyle = '#555555'
  ctx.fillText(display, w / 2, barAreaY + barAreaH + labelSize + Math.round(h * 0.08))

  return c.toDataURL('image/png')
}

/** Create a Fabric Canvas sized to label pixels, displayed scaled to fit the container. */
export function initCanvas(
  el: HTMLCanvasElement,
  labelW: number,
  labelH: number,
  containerW: number,
): { canvas: Canvas; scale: number } {
  const maxDisplayH = 600
  const scale = Math.min(1, (containerW - 48) / labelW, maxDisplayH / labelH)
  const displayW = Math.round(labelW * scale)
  const displayH = Math.round(labelH * scale)

  const canvas = new Canvas(el, {
    backgroundColor: '#ffffff',
    selection: true,
  })
  canvas.setDimensions({ width: displayW, height: displayH })
  canvas.setZoom(scale)

  // Sync labelforge_raw_content whenever text is edited inline.
  // text:changed target is IText — no manual annotation needed.
  canvas.on('text:changed', (e) => {
    e.target.set('labelforge_raw_content', e.target.text ?? '')
  })

  return { canvas, scale }
}

export function addTextElement(canvas: Canvas, defaultFont: string, fill = '#000000'): void {
  const vp = canvas.viewportTransform ?? [1, 0, 0, 1, 0, 0]
  const scale = vp[0]
  const canvasVirtualW = (canvas.width ?? 400) / scale
  const canvasVirtualH = (canvas.height ?? 200) / scale

  const text = new IText('Text', {
    left: Math.round(canvasVirtualW * 0.05),
    top: Math.round(canvasVirtualH * 0.05),
    fontFamily: defaultFont,
    fontSize: 48,
    fill,
  })
  text.set('labelforge_raw_content', 'Text')

  // Keep raw content in sync when text changes
  text.on('changed', () => {
    text.set('labelforge_raw_content', text.text ?? '')
  })

  canvas.add(text)
  canvas.setActiveObject(text)
  canvas.renderAll()
}

/**
 * Add a QR placeholder element to the canvas.
 *
 * The element is a Fabric Image carrying labelforge_qr_payload and
 * labelforge_qr_error_correction as custom props. Fabric serializes Image as
 * type "Image", which the backend normalizes to "image" and dispatches to the
 * QR renderer — so this must be Image, not Rect or Group.
 *
 * The visible bitmap is a client-generated placeholder; the real QR is rendered
 * server-side on Preview/print. Tooltip on the button makes this clear.
 */
export async function addQrElement(
  canvas: Canvas,
  payload = 'https://example.com',
  errorCorrection = 'M',
): Promise<void> {
  const vp = canvas.viewportTransform ?? [1, 0, 0, 1, 0, 0]
  const scale = vp[0]
  const canvasVirtualW = (canvas.width ?? 400) / scale
  const canvasVirtualH = (canvas.height ?? 200) / scale

  const size = 150  // default square in label pixels
  const left = Math.round(canvasVirtualW * 0.05)
  const top = Math.round(canvasVirtualH * 0.05)

  const dataUrl = makeQrPlaceholderDataUrl(payload, size)

  const img = await FabricImage.fromURL(dataUrl)
  img.set({
    left,
    top,
    // scaleX/scaleY stay 1; width/height come from the native image dimensions.
    // Backend uses width*scaleX × height*scaleY for QR size, so natural size = size px.
    originX: 'left',
    originY: 'top',
  })
  img.set('labelforge_qr_payload', payload)
  img.set('labelforge_qr_error_correction', errorCorrection)

  canvas.add(img)
  canvas.setActiveObject(img)
  canvas.renderAll()
}

/**
 * Add a barcode placeholder element to the canvas.
 *
 * Mirrors addQrElement — Fabric Image with custom props. The backend dispatches
 * image elements to the barcode renderer when labelforge_barcode_payload is
 * present. Default box is landscape (300×100 label px) since barcodes are wide.
 */
export async function addBarcodeElement(
  canvas: Canvas,
  payload = '12345678',
  symbology = 'code128',
): Promise<void> {
  const vp = canvas.viewportTransform ?? [1, 0, 0, 1, 0, 0]
  const scale = vp[0]
  const canvasVirtualW = (canvas.width ?? 400) / scale
  const canvasVirtualH = (canvas.height ?? 200) / scale

  const defaultW = 300
  const defaultH = 100
  const left = Math.round(canvasVirtualW * 0.05)
  const top = Math.round(canvasVirtualH * 0.05)

  const dataUrl = makeBarcodePlaceholderDataUrl(payload, defaultW, defaultH)

  const img = await FabricImage.fromURL(dataUrl)
  img.set({
    left,
    top,
    originX: 'left',
    originY: 'top',
  })
  img.set('labelforge_barcode_payload', payload)
  img.set('labelforge_barcode_symbology', symbology)

  canvas.add(img)
  canvas.setActiveObject(img)
  canvas.renderAll()
}

/**
 * Regenerate the placeholder bitmap for a loaded QR Image object.
 * Called after loadFromJSON so the stored data URL (if any) is replaced with a
 * freshly generated one — avoids bloating canvas_json with a stored data URL
 * and ensures the visible payload text is always current.
 */
async function refreshQrPlaceholder(obj: FabricObject): Promise<void> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const o = obj as any
  const payload: string = o['labelforge_qr_payload'] ?? 'https://example.com'
  // Use the element's current pixel size for the placeholder bitmap
  const px = Math.round((o.width ?? 150) * (o.scaleX ?? 1))
  const clampedPx = Math.max(50, Math.min(px, 600))
  const dataUrl = makeQrPlaceholderDataUrl(payload, clampedPx)
  await (obj as FabricImage).setSrc(dataUrl)
}

/**
 * Regenerate the placeholder bitmap for a loaded barcode Image object.
 * Mirrors refreshQrPlaceholder — called from loadCanvasJSON so the bitmap
 * matches the element's current size and payload without storing a data URL.
 */
async function refreshBarcodePlaceholder(obj: FabricObject): Promise<void> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const o = obj as any
  const payload: string = o['labelforge_barcode_payload'] ?? '12345678'
  const w = Math.max(50, Math.min(Math.round((o.width ?? 300) * (o.scaleX ?? 1)), 1200))
  const h = Math.max(20, Math.min(Math.round((o.height ?? 100) * (o.scaleY ?? 1)), 600))
  const dataUrl = makeBarcodePlaceholderDataUrl(payload, w, h)
  await (obj as FabricImage).setSrc(dataUrl)
}

export function deleteSelected(canvas: Canvas): void {
  const active = canvas.getActiveObjects()
  if (active.length === 0) return
  active.forEach(obj => canvas.remove(obj))
  canvas.discardActiveObject()
  canvas.renderAll()
}

export function getCanvasJSON(canvas: Canvas): Record<string, unknown> {
  // customProperties registered above ensures all labelforge_* props are included.
  return canvas.toJSON() as Record<string, unknown>
}

export async function loadCanvasJSON(
  canvas: Canvas,
  json: Record<string, unknown>,
): Promise<void> {
  await canvas.loadFromJSON(json)
  // Re-attach raw content sync to each loaded text object; regenerate QR/barcode placeholders.
  const refreshes: Promise<void>[] = []
  canvas.getObjects().forEach(obj => {
    if (isTextType(obj.type)) {
      const t = obj as IText
      t.on('changed', () => {
        t.set('labelforge_raw_content', t.text ?? '')
      })
    } else if (isQrType(obj)) {
      refreshes.push(refreshQrPlaceholder(obj))
    } else if (isBarcodeType(obj)) {
      refreshes.push(refreshBarcodePlaceholder(obj))
    }
  })
  if (refreshes.length > 0) {
    await Promise.all(refreshes)
  }
  canvas.renderAll()
}
