import type { Canvas } from 'fabric'
import { getCanvasJSON, loadCanvasJSON } from './canvas'

const MAX_ENTRIES = 50

/**
 * Bounded undo/redo snapshot stack for the template editor canvas.
 *
 * Restores go through loadCanvasJSON (not a bare loadFromJSON) so the raw-text
 * sync handlers and QR/barcode placeholder bitmaps are regenerated exactly as
 * they are on initial template load — a bare loadFromJSON would silently drop
 * both.
 */
export class EditorHistory {
  private entries: Record<string, unknown>[] = []
  private index = -1
  private restoring = false

  constructor(private canvas: Canvas) {}

  /** Seed the stack with the current canvas state. Call once, after the canvas is fully loaded. */
  init(): void {
    this.entries = [getCanvasJSON(this.canvas)]
    this.index = 0
  }

  isRestoring(): boolean {
    return this.restoring
  }

  canUndo(): boolean {
    return this.index > 0
  }

  canRedo(): boolean {
    return this.index < this.entries.length - 1
  }

  /** Record the current canvas state as a new entry. No-op while a restore is in flight. */
  push(): void {
    if (this.restoring) return
    const snapshot = getCanvasJSON(this.canvas)
    this.entries = this.entries.slice(0, this.index + 1)
    this.entries.push(snapshot)
    this.index = this.entries.length - 1
    if (this.entries.length > MAX_ENTRIES) {
      this.entries.shift()
      this.index--
    }
  }

  async undo(): Promise<void> {
    // Checked and set synchronously (before the first await) so a rapid second
    // Ctrl+Z can't interleave with a restore already in flight.
    if (!this.canUndo() || this.restoring) return
    this.restoring = true
    try {
      this.index--
      await loadCanvasJSON(this.canvas, this.entries[this.index])
    } finally {
      this.restoring = false
    }
  }

  async redo(): Promise<void> {
    if (!this.canRedo() || this.restoring) return
    this.restoring = true
    try {
      this.index++
      await loadCanvasJSON(this.canvas, this.entries[this.index])
    } finally {
      this.restoring = false
    }
  }
}
