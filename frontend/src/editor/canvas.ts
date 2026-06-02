import { Canvas, FabricObject, IText } from 'fabric'

export const CUSTOM_PROPS = ['labelforge_raw_content'] as const

// Register the custom prop so canvas.toJSON() includes it on every object automatically.
FabricObject.customProperties.push('labelforge_raw_content')

/**
 * True for any Fabric text object. Fabric v6 reports `type` as the PascalCase
 * class name ('IText', 'Textbox'); v5 used lowercase/hyphenated ('i-text').
 * Normalize so both serializations match.
 */
export function isTextType(type: string | undefined): boolean {
  const t = (type ?? '').toLowerCase().replace(/-/g, '')
  return t === 'itext' || t === 'text' || t === 'textbox'
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

export function addTextElement(canvas: Canvas, defaultFont: string): void {
  const vp = canvas.viewportTransform ?? [1, 0, 0, 1, 0, 0]
  const scale = vp[0]
  const canvasVirtualW = (canvas.width ?? 400) / scale
  const canvasVirtualH = (canvas.height ?? 200) / scale

  const text = new IText('Text', {
    left: Math.round(canvasVirtualW * 0.05),
    top: Math.round(canvasVirtualH * 0.05),
    fontFamily: defaultFont,
    fontSize: 48,
    fill: '#000000',
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

export function deleteSelected(canvas: Canvas): void {
  const active = canvas.getActiveObjects()
  if (active.length === 0) return
  active.forEach(obj => canvas.remove(obj))
  canvas.discardActiveObject()
  canvas.renderAll()
}

export function getCanvasJSON(canvas: Canvas): Record<string, unknown> {
  // customProperties registered above ensures labelforge_raw_content is included.
  return canvas.toJSON() as Record<string, unknown>
}

export async function loadCanvasJSON(
  canvas: Canvas,
  json: Record<string, unknown>,
): Promise<void> {
  await canvas.loadFromJSON(json)
  // Re-attach raw content sync to each loaded text object
  canvas.getObjects().forEach(obj => {
    if (isTextType(obj.type)) {
      const t = obj as IText
      t.on('changed', () => {
        t.set('labelforge_raw_content', t.text ?? '')
      })
    }
  })
  canvas.renderAll()
}
