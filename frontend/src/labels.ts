import type { LabelEntry, PrinterStatus } from './types'
import { getPrinterStatus } from './api'

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

// True when label dimensions exactly match the loaded roll — groups mono and
// two-color variants of the same width (e.g. 62 + 62red) and excludes die-cuts
// of the same width (62x29 has length_mm=29, not 0).
export function matchesLoadedMedia(label: LabelEntry, loaded: { width_mm: number; length_mm: number }): boolean {
  return label.tape_size[0] === loaded.width_mm && label.tape_size[1] === loaded.length_mm
}

export interface LabelMediaSelectHandle {
  getValue(): string
  setValue(id: string): void
}

// Shared label-media selector with a "Show all / Loaded in printer" mode toggle.
// Renders into `container`, populating via buildLabelOptionsHtml. Printer status
// is fetched once on the first switch to Loaded mode and cached for the control's
// lifetime.
export function mountLabelMediaSelect(opts: {
  container: HTMLElement
  labels: LabelEntry[]
  initialValue?: string
  onChange: (id: string) => void
}): LabelMediaSelectHandle {
  const { container, labels, initialValue, onChange } = opts

  container.innerHTML = `
    <div class="media-filter-toggle">
      <button type="button" class="media-filter-btn active" data-mode="all">Show all</button>
      <button type="button" class="media-filter-btn" data-mode="loaded">Loaded in printer</button>
    </div>
    <select class="media-filter-select"></select>
    <p class="media-filter-notice" hidden></p>
  `

  const toggleBtns = container.querySelectorAll<HTMLButtonElement>('.media-filter-btn')
  const sel = container.querySelector<HTMLSelectElement>('.media-filter-select')!
  const notice = container.querySelector<HTMLParagraphElement>('.media-filter-notice')!

  let mode: 'all' | 'loaded' = 'all'
  let cachedStatus: { ok: boolean; body: PrinterStatus & Record<string, unknown> } | null = null

  // Populate select; prefers `preferValue` if supported, otherwise first supported entry.
  function populate(list: LabelEntry[], preferValue?: string): void {
    const target = preferValue !== undefined ? preferValue : sel.value
    sel.innerHTML = buildLabelOptionsHtml(list)
    const inList = list.find(l => l.id === target)
    if (inList?.supported) {
      sel.value = target
    } else {
      const fb = firstSupportedId(list)
      if (fb) sel.value = fb
    }
  }

  function setToggle(newMode: 'all' | 'loaded'): void {
    mode = newMode
    toggleBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === newMode)
    })
  }

  // Initialize in Show-all mode
  populate(labels, initialValue)

  sel.addEventListener('change', () => onChange(sel.value))

  toggleBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
      const newMode = btn.dataset.mode as 'all' | 'loaded'
      if (newMode === mode) return

      if (newMode === 'all') {
        setToggle('all')
        populate(labels)
        notice.hidden = true
        onChange(sel.value)
        return
      }

      // Switching to "Loaded in printer" — fetch once, then cache
      if (!cachedStatus) {
        btn.disabled = true
        try {
          cachedStatus = await getPrinterStatus()
        } catch {
          cachedStatus = { ok: false, body: { ready: false, model: '', loaded_media: null, errors: [] } as PrinterStatus & Record<string, unknown> }
        } finally {
          btn.disabled = false
        }
      }

      if (!cachedStatus.ok) {
        notice.textContent = "Couldn't reach printer — showing all"
        notice.hidden = false
        return  // stay in Show-all mode
      }

      const loaded = cachedStatus.body.loaded_media
      if (!loaded) {
        notice.textContent = 'Printer reports no media loaded'
        notice.hidden = false
        return  // stay in Show-all mode
      }

      const filtered = labels.filter(l => matchesLoadedMedia(l, loaded))
      setToggle('loaded')

      if (filtered.length === 0) {
        populate(labels)
        notice.textContent = 'Loaded media not in catalog — showing all'
        notice.hidden = false
      } else {
        populate(filtered)
        notice.hidden = true
      }
      onChange(sel.value)
    })
  })

  return {
    getValue: () => sel.value,
    setValue: (id: string) => {
      sel.value = id
      onChange(id)
    },
  }
}
