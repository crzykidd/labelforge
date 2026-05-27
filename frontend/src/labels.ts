import type { LabelEntry } from './types'

const FORM_FACTOR_LABEL: Record<number, string> = {
  1: 'Die-cut',
  2: 'Continuous',
  3: 'Round',
  4: 'P-touch Continuous',
}

const FF_ORDER = [2, 1, 3, 4]

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

// "DK-22205: 62mm Continuous (Black)" when the catalog entry carries a Brother
// part number, otherwise just the display name (e.g. 52x29 has no consumer roll).
export function labelOptionText(l: LabelEntry): string {
  return l.brother_part ? `${l.brother_part}: ${l.display_name}` : l.display_name
}

// Grouped <optgroup> markup for a label-media <select>: ordered by form factor
// (continuous, die-cut, round, …), sorted by display name within each group.
export function buildLabelOptionsHtml(labels: LabelEntry[]): string {
  const groups = new Map<number, LabelEntry[]>()
  for (const l of labels) {
    if (!groups.has(l.form_factor)) groups.set(l.form_factor, [])
    groups.get(l.form_factor)!.push(l)
  }
  for (const entries of groups.values()) {
    entries.sort((a, b) => a.display_name.localeCompare(b.display_name))
  }
  return [...new Set([...FF_ORDER, ...groups.keys()])]
    .filter(k => groups.has(k))
    .map(k => {
      const groupLabel = FORM_FACTOR_LABEL[k] ?? 'Other'
      const opts = groups
        .get(k)!
        .map(l => {
          if (l.supported) {
            return `<option value="${esc(l.id)}">${esc(labelOptionText(l))}</option>`
          }
          const reason = l.incompatible_reason ?? 'Not supported by the configured printer'
          return `<option value="${esc(l.id)}" disabled title="${esc(reason)}">${esc(labelOptionText(l))} — unavailable</option>`
        })
        .join('')
      return `<optgroup label="${esc(groupLabel)}">${opts}</optgroup>`
    })
    .join('')
}

// First label id the configured printer can actually print, in the same group
// order the picker renders. Used to redirect a default/restored selection away
// from media the printer can't handle (the browser blocks picking a disabled
// <option>, but a programmatic .value set can still land on one).
export function firstSupportedId(labels: LabelEntry[]): string | undefined {
  const groups = new Map<number, LabelEntry[]>()
  for (const l of labels) {
    if (!groups.has(l.form_factor)) groups.set(l.form_factor, [])
    groups.get(l.form_factor)!.push(l)
  }
  for (const entries of groups.values()) {
    entries.sort((a, b) => a.display_name.localeCompare(b.display_name))
  }
  for (const k of [...new Set([...FF_ORDER, ...groups.keys()])].filter(k => groups.has(k))) {
    const hit = groups.get(k)!.find(l => l.supported)
    if (hit) return hit.id
  }
  return undefined
}
