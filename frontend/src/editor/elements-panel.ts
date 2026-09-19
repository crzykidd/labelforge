import type { Canvas } from 'fabric'
import { clampObjectToCanvas, describeObject, isObjectOutOfBounds } from './canvas'

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
 * clicked back into the selection. Rows outside the canvas bounds are flagged
 * with an "off canvas" button that recovers that one element on click (not
 * just a passive label — a user reported not finding the fix even with the
 * flag and the toolbar's "Bring all on-canvas" both present).
 *
 * onFlaggedChange, if given, fires with the current off-canvas count whenever
 * it changes (add/remove/modify/text-edit all re-render), so the caller can
 * surface a one-line hint the first time an element goes out of bounds.
 */
export function mountElementsPanel(
  listEl: HTMLElement,
  canvas: Canvas,
  designBounds: () => [number, number],
  onFlaggedChange?: (count: number) => void,
): ElementsPanelHandle {
  let lastFlagged = -1

  function render(): void {
    const [w, h] = designBounds()
    const objects = canvas.getObjects()
    let flagged = 0
    if (objects.length === 0) {
      listEl.innerHTML = '<div class="elements-panel-empty">No elements yet.</div>'
    } else {
      listEl.innerHTML = objects.map((obj, i) => {
        const { label, snippet } = describeObject(obj)
        const outOfBounds = isObjectOutOfBounds(obj, w, h)
        if (outOfBounds) flagged++
        const snippetShort = snippet.length > 40 ? snippet.slice(0, 39) + '…' : snippet
        return `
          <div class="elements-panel-row${outOfBounds ? ' out-of-bounds' : ''}" data-index="${i}">
            <span class="elements-panel-type">${esc(label)}</span>
            <span class="elements-panel-snippet">${esc(snippetShort)}</span>
            ${outOfBounds ? `<button type="button" class="elements-panel-fix" data-index="${i}" title="Click to bring this element back inside the label">off canvas ↩</button>` : ''}
          </div>
        `
      }).join('')
    }
    if (flagged !== lastFlagged) {
      lastFlagged = flagged
      onFlaggedChange?.(flagged)
    }
  }

  listEl.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    const fixBtn = target.closest<HTMLElement>('.elements-panel-fix')
    if (fixBtn) {
      const idx = Number(fixBtn.dataset.index)
      const obj = canvas.getObjects()[idx]
      if (obj) {
        clampObjectToCanvas(obj, ...designBounds())
        canvas.setActiveObject(obj)
        canvas.renderAll()
        canvas.fire('object:modified', { target: obj })
      }
      return
    }
    const row = target.closest<HTMLElement>('.elements-panel-row')
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
