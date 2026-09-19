import type { Canvas, FabricObject } from 'fabric'
import { clampObjectToCanvas, deleteSelected } from './canvas'

const NUDGE = 1
const NUDGE_LARGE = 10

function isEditingText(canvas: Canvas): boolean {
  const obj = canvas.getActiveObject() as (FabricObject & { isEditing?: boolean }) | undefined
  return obj?.isEditing === true
}

function isFormField(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  const tag = el?.tagName
  return tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA'
}

export interface KeyboardHandlers {
  undo: () => void
  redo: () => void
}

/**
 * Wire arrow-nudge, delete, escape and undo/redo shortcuts. Returns a cleanup
 * function to remove the listener.
 *
 * Must never fire while a text element is in inline editing mode (Fabric's
 * isEditing) or while a toolbar input/select has focus — otherwise typing in a
 * text box or a payload field would move or delete the selected element.
 */
export function attachKeyboardHandlers(
  canvas: Canvas,
  designBounds: () => [number, number],
  handlers: KeyboardHandlers,
): () => void {
  function onKeyDown(e: KeyboardEvent): void {
    if (isFormField(e.target) || isEditingText(canvas)) return

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault()
      if (e.shiftKey) handlers.redo(); else handlers.undo()
      return
    }

    const active = canvas.getActiveObject()
    if (!active) return

    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault()
      deleteSelected(canvas)
      return
    }
    if (e.key === 'Escape') {
      canvas.discardActiveObject()
      canvas.renderAll()
      return
    }

    const step = e.shiftKey ? NUDGE_LARGE : NUDGE
    let dx = 0
    let dy = 0
    if (e.key === 'ArrowLeft') dx = -step
    else if (e.key === 'ArrowRight') dx = step
    else if (e.key === 'ArrowUp') dy = -step
    else if (e.key === 'ArrowDown') dy = step
    else return

    e.preventDefault()
    active.set({ left: active.left + dx, top: active.top + dy })
    active.setCoords()
    const [w, h] = designBounds()
    clampObjectToCanvas(active, w, h)
    canvas.fire('object:modified', { target: active })
    canvas.renderAll()
  }

  window.addEventListener('keydown', onKeyDown)
  return () => window.removeEventListener('keydown', onKeyDown)
}
