import type { Canvas } from 'fabric'
import { describeObject, isObjectOutOfBounds } from './canvas'

export interface ElementsPanelHandle {
  refresh(): void
}

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * List every canvas object beside the canvas so an element dragged off the
 * visible area — otherwise unselectable and unrecoverable — can be found and
 * clicked back into the selection. Rows outside the canvas bounds are flagged.
 */
export function mountElementsPanel(
  listEl: HTMLElement,
  canvas: Canvas,
  designBounds: () => [number, number],
): ElementsPanelHandle {
  function render(): void {
    const [w, h] = designBounds()
    const objects = canvas.getObjects()
    if (objects.length === 0) {
      listEl.innerHTML = '<div class="elements-panel-empty">No elements yet.</div>'
      return
    }
    listEl.innerHTML = objects.map((obj, i) => {
      const { label, snippet } = describeObject(obj)
      const outOfBounds = isObjectOutOfBounds(obj, w, h)
      const snippetShort = snippet.length > 40 ? snippet.slice(0, 39) + '…' : snippet
      return `
        <div class="elements-panel-row${outOfBounds ? ' out-of-bounds' : ''}" data-index="${i}">
          <span class="elements-panel-type">${esc(label)}</span>
          <span class="elements-panel-snippet">${esc(snippetShort)}</span>
          ${outOfBounds ? '<span class="elements-panel-warn" title="Off canvas — click to select, or use Bring all on-canvas">off canvas</span>' : ''}
        </div>
      `
    }).join('')
  }

  listEl.addEventListener('click', (e) => {
    const row = (e.target as HTMLElement).closest<HTMLElement>('.elements-panel-row')
    if (!row) return
    const idx = Number(row.dataset.index)
    const obj = canvas.getObjects()[idx]
    if (obj) {
      canvas.setActiveObject(obj)
      canvas.renderAll()
    }
  })

  render()
  return { refresh: render }
}
