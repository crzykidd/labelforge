import type { FabricObject } from 'fabric'

// All math here operates in label-pixel (Fabric scene) coordinates, same as
// clampObjectToCanvas in ./canvas.ts — never in display pixels. The grid is
// painted as a CSS background on the canvas wrapper, never as Fabric objects:
// anything added to the canvas serializes into canvas_json and would print.

const GRID_ENABLED_KEY = 'lf:grid-enabled'
export const DEFAULT_GRID_SIZE = 10 // label pixels
const SNAP_THRESHOLD = 8 // label pixels

export function isGridEnabled(): boolean {
  try { return localStorage.getItem(GRID_ENABLED_KEY) === '1' } catch { return false }
}

export function setGridEnabled(enabled: boolean): void {
  try { localStorage.setItem(GRID_ENABLED_KEY, enabled ? '1' : '0') } catch { /* storage may be unavailable */ }
}

/** Paint (or clear) the grid as a CSS background sized to the current display zoom. */
export function updateGridOverlay(innerEl: HTMLElement, enabled: boolean, zoom: number, gridSize = DEFAULT_GRID_SIZE): void {
  if (!enabled) {
    innerEl.style.backgroundImage = ''
    return
  }
  const px = Math.max(2, gridSize * zoom)
  innerEl.style.backgroundImage =
    'linear-gradient(to right, rgba(0,0,0,0.14) 1px, transparent 1px),' +
    'linear-gradient(to bottom, rgba(0,0,0,0.14) 1px, transparent 1px)'
  innerEl.style.backgroundSize = `${px}px ${px}px`
}

function nearestMultiple(value: number, step: number): number {
  return Math.round(value / step) * step
}

interface Candidate { value: number; guide: number }

function snapAxis(current: number, candidates: Candidate[], gridEnabled: boolean, gridSize: number): { value: number; guide: number | null } {
  let best: Candidate | null = null
  let bestDist = SNAP_THRESHOLD
  for (const c of candidates) {
    const d = Math.abs(current - c.value)
    if (d < bestDist) { bestDist = d; best = c }
  }
  if (best) return { value: best.value, guide: best.guide }
  if (gridEnabled) {
    const g = nearestMultiple(current, gridSize)
    if (Math.abs(current - g) < SNAP_THRESHOLD) return { value: g, guide: null }
  }
  return { value: current, guide: null }
}

export interface SnapGuides { x: number | null; y: number | null }

/**
 * Snap obj's position to the canvas edges, horizontal/vertical centerlines, and
 * (when enabled) the grid. Centerline snap always applies, independent of the
 * grid toggle — it's the one people actually reach for when centering label
 * content. Returns guide-line positions (label px) for the edge/center matches
 * only; grid snaps don't get a guide line since the grid itself is visible.
 */
export function applyMoveSnap(
  obj: FabricObject,
  canvasW: number,
  canvasH: number,
  gridEnabled: boolean,
  gridSize = DEFAULT_GRID_SIZE,
): SnapGuides {
  const r = obj.getBoundingRect()
  const xCandidates: Candidate[] = [
    { value: 0, guide: 0 },
    { value: canvasW - r.width, guide: canvasW },
    { value: (canvasW - r.width) / 2, guide: canvasW / 2 },
  ]
  const yCandidates: Candidate[] = [
    { value: 0, guide: 0 },
    { value: canvasH - r.height, guide: canvasH },
    { value: (canvasH - r.height) / 2, guide: canvasH / 2 },
  ]
  const xr = snapAxis(r.left, xCandidates, gridEnabled, gridSize)
  const yr = snapAxis(r.top, yCandidates, gridEnabled, gridSize)
  const dx = xr.value - r.left
  const dy = yr.value - r.top
  if (dx !== 0 || dy !== 0) {
    obj.set({ left: obj.left + dx, top: obj.top + dy })
    obj.setCoords()
  }
  return { x: xr.guide, y: yr.guide }
}

/**
 * Snap the edge(s) actively being dragged during a resize to the canvas edge or
 * the grid. `corner` (from the object:scaling event's transform) says which
 * handle is being dragged, so the opposite, anchored edge is left untouched —
 * matching Fabric's own anchor behavior instead of assuming top-left.
 */
export function applyScaleSnap(
  obj: FabricObject,
  corner: string,
  canvasW: number,
  canvasH: number,
  gridEnabled: boolean,
  gridSize = DEFAULT_GRID_SIZE,
): void {
  if (corner === 'mtr') return // rotation handle, nothing to snap

  // Re-pin the anchor (the edge/corner opposite the one being dragged) via
  // getPositionByOrigin/setPositionByOrigin rather than obj.left/top
  // arithmetic. Unlike a pure move, resizing mixes a scale change with a
  // position change, and that mix is origin-dependent — setPositionByOrigin
  // computes the correct left/top for whatever originX/Y the object actually
  // has (e.g. a multi-selection, which Fabric anchors at its center), where
  // manual translation math would only have been correct for left/top origins.
  if (corner.includes('l')) {
    const r = obj.getBoundingRect()
    const snapped = snapAxis(r.left, [{ value: 0, guide: 0 }], gridEnabled, gridSize).value
    const newWidth = r.width + (r.left - snapped)
    if (snapped !== r.left && newWidth > 1) {
      const anchor = obj.getPositionByOrigin('right', 'top') // fixed edge; 'top' is an arbitrary stable Y reference
      obj.set('scaleX', obj.scaleX * (newWidth / r.width))
      obj.setPositionByOrigin(anchor, 'right', 'top')
    }
  } else if (corner.includes('r')) {
    const r = obj.getBoundingRect()
    const rightEdge = r.left + r.width
    const snapped = snapAxis(rightEdge, [{ value: canvasW, guide: canvasW }], gridEnabled, gridSize).value
    const newWidth = r.width + (snapped - rightEdge)
    if (snapped !== rightEdge && newWidth > 1) {
      const anchor = obj.getPositionByOrigin('left', 'top')
      obj.set('scaleX', obj.scaleX * (newWidth / r.width))
      obj.setPositionByOrigin(anchor, 'left', 'top')
    }
  }

  if (corner.includes('t')) {
    const r = obj.getBoundingRect()
    const snapped = snapAxis(r.top, [{ value: 0, guide: 0 }], gridEnabled, gridSize).value
    const newHeight = r.height + (r.top - snapped)
    if (snapped !== r.top && newHeight > 1) {
      const anchor = obj.getPositionByOrigin('left', 'bottom') // fixed edge; 'left' is an arbitrary stable X reference
      obj.set('scaleY', obj.scaleY * (newHeight / r.height))
      obj.setPositionByOrigin(anchor, 'left', 'bottom')
    }
  } else if (corner.includes('b')) {
    const r = obj.getBoundingRect()
    const bottomEdge = r.top + r.height
    const snapped = snapAxis(bottomEdge, [{ value: canvasH, guide: canvasH }], gridEnabled, gridSize).value
    const newHeight = r.height + (snapped - bottomEdge)
    if (snapped !== bottomEdge && newHeight > 1) {
      const anchor = obj.getPositionByOrigin('left', 'top')
      obj.set('scaleY', obj.scaleY * (newHeight / r.height))
      obj.setPositionByOrigin(anchor, 'left', 'top')
    }
  }
  obj.setCoords()
}

function ensureGuideElements(innerEl: HTMLElement): [HTMLElement, HTMLElement] {
  let v = innerEl.querySelector<HTMLElement>(':scope > .snap-guide-v')
  let h = innerEl.querySelector<HTMLElement>(':scope > .snap-guide-h')
  if (!v) {
    v = document.createElement('div')
    v.className = 'snap-guide snap-guide-v'
    v.hidden = true
    innerEl.appendChild(v)
  }
  if (!h) {
    h = document.createElement('div')
    h.className = 'snap-guide snap-guide-h'
    h.hidden = true
    innerEl.appendChild(h)
  }
  return [v, h]
}

/** Show brief guide lines at the label-pixel positions returned by applyMoveSnap. */
export function updateSnapGuides(innerEl: HTMLElement, guides: SnapGuides, zoom: number): void {
  const [v, h] = ensureGuideElements(innerEl)
  if (guides.x !== null) {
    v.style.left = `${guides.x * zoom}px`
    v.hidden = false
  } else {
    v.hidden = true
  }
  if (guides.y !== null) {
    h.style.top = `${guides.y * zoom}px`
    h.hidden = false
  } else {
    h.hidden = true
  }
}

export function clearSnapGuides(innerEl: HTMLElement): void {
  const v = innerEl.querySelector<HTMLElement>(':scope > .snap-guide-v')
  const h = innerEl.querySelector<HTMLElement>(':scope > .snap-guide-h')
  if (v) v.hidden = true
  if (h) h.hidden = true
}
