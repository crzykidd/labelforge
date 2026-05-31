import { deleteHistory, fetchHistoryPreview, listHistory, pinHistory, reprintHistory } from '../api'
import type { HistoryItem } from '../types'

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function fmtFields(fields: Record<string, string> | null): string {
  if (!fields || Object.keys(fields).length === 0) return ''
  return Object.entries(fields)
    .map(([k, v]) => `${esc(k)}=${esc(String(v))}`)
    .join(', ')
}

// Track object URLs created for thumbnails; revoked on each remount and on successful regen
let _gen = 0
let _objectUrls: string[] = []

function revokeAll(): void {
  for (const url of _objectUrls) URL.revokeObjectURL(url)
  _objectUrls = []
  _gen++
}

async function loadThumb(
  imgEl: HTMLImageElement,
  placeholder: HTMLDivElement,
  id: number,
  gen: number,
): Promise<void> {
  try {
    const blob = await fetchHistoryPreview(id)
    if (_gen !== gen) return
    const url = URL.createObjectURL(blob)
    _objectUrls.push(url)
    imgEl.src = url
    imgEl.hidden = false
    placeholder.hidden = true
  } catch {
    if (_gen !== gen) return
    // 404 or error: placeholder stays visible
  }
}

export function mountHistory(root: HTMLElement): void {
  revokeAll()

  const LIMIT = 25
  let offset = 0
  let filterTemplate = ''
  let filterPinned = false

  root.innerHTML = `
    <div class="history-page">
      <h2>Print History</h2>
      <div class="history-filters">
        <label class="filter-label">
          Template
          <input type="text" id="filter-template" placeholder="filter by name…" autocomplete="off" />
        </label>
        <label class="filter-pinned">
          <input type="checkbox" id="filter-pinned" /> Pinned only
        </label>
      </div>
      <div id="history-status" class="status-msg" hidden></div>
      <div id="history-list"></div>
      <div id="history-more" hidden><button id="btn-load-more">Load more</button></div>
      <p id="history-empty" class="empty-state" hidden>No print jobs found.</p>
    </div>
  `

  const filterTemplateEl = root.querySelector<HTMLInputElement>('#filter-template')!
  const filterPinnedEl = root.querySelector<HTMLInputElement>('#filter-pinned')!
  const statusEl = root.querySelector<HTMLDivElement>('#history-status')!
  const listEl = root.querySelector<HTMLDivElement>('#history-list')!
  const moreEl = root.querySelector<HTMLDivElement>('#history-more')!
  const emptyEl = root.querySelector<HTMLParagraphElement>('#history-empty')!
  const btnLoadMore = root.querySelector<HTMLButtonElement>('#btn-load-more')!

  function showStatus(msg: string, kind: 'success' | 'error'): void {
    statusEl.textContent = msg
    statusEl.className = `status-msg ${kind}`
    statusEl.hidden = false
  }

  function hideStatus(): void { statusEl.hidden = true }

  function buildRow(item: HistoryItem): HTMLDivElement {
    const gen = _gen
    const row = document.createElement('div')
    row.className = 'history-row'

    const templateLabel = item.template_id
      ? `<span class="history-tpl-name">${esc(item.template_id)}</span>`
      : `<span class="badge-quick">Quick print</span>`
    const fieldsStr = fmtFields(item.field_values)
    const reprintMarker = item.reprint_of != null
      ? `<span class="reprint-marker">↩ reprint of #${item.reprint_of}</span>`
      : ''

    row.innerHTML = `
      <div class="history-thumb-wrap">
        <div class="history-thumb-placeholder"></div>
        <img class="history-thumb" hidden alt="Preview" />
      </div>
      <div class="history-row-body">
        <div class="history-row-name">${templateLabel}</div>
        ${fieldsStr ? `<div class="history-row-fields">${fieldsStr}</div>` : ''}
        <div class="history-row-meta">
          <span>${esc(fmtDate(item.created_at))}</span>
          ${reprintMarker}
        </div>
        <div class="history-row-actions">
          <button class="btn-pin${item.pinned ? ' btn-pinned' : ''}" data-pinned="${item.pinned}">${item.pinned ? 'Unpin' : 'Pin'}</button>
          <button class="btn-reprint">Reprint</button>
          <button class="btn-danger">Delete</button>
        </div>
      </div>
    `

    const imgEl = row.querySelector<HTMLImageElement>('.history-thumb')!
    const placeholderEl = row.querySelector<HTMLDivElement>('.history-thumb-placeholder')!
    void loadThumb(imgEl, placeholderEl, item.id, gen)

    const btnPin = row.querySelector<HTMLButtonElement>('.btn-pin')!
    btnPin.addEventListener('click', async () => {
      const currentPinned = btnPin.dataset.pinned === 'true'
      btnPin.disabled = true
      try {
        const updated = await pinHistory(item.id, !currentPinned)
        btnPin.dataset.pinned = String(updated.pinned)
        btnPin.textContent = updated.pinned ? 'Unpin' : 'Pin'
        btnPin.classList.toggle('btn-pinned', updated.pinned)
        item.pinned = updated.pinned
      } catch (err) {
        showStatus((err as Error).message, 'error')
      } finally {
        btnPin.disabled = false
      }
    })

    const btnReprint = row.querySelector<HTMLButtonElement>('.btn-reprint')!
    btnReprint.addEventListener('click', async () => {
      btnReprint.disabled = true
      btnReprint.textContent = 'Reprinting…'
      hideStatus()
      try {
        await reprintHistory(item.id)
        resetAndLoad()
      } catch (err) {
        showStatus((err as Error).message, 'error')
        btnReprint.textContent = 'Reprint'
        btnReprint.disabled = false
      }
    })

    const btnDelete = row.querySelector<HTMLButtonElement>('.btn-danger')!
    btnDelete.addEventListener('click', async () => {
      if (!confirm('Delete this print job? This cannot be undone.')) return
      btnDelete.disabled = true
      try {
        await deleteHistory(item.id)
        row.remove()
        if (listEl.children.length === 0 && moreEl.hidden) {
          emptyEl.hidden = false
        }
      } catch (err) {
        showStatus((err as Error).message, 'error')
        btnDelete.disabled = false
      }
    })

    return row
  }

  async function loadPage(reset: boolean): Promise<void> {
    if (reset) {
      offset = 0
      revokeAll()
      listEl.innerHTML = ''
      moreEl.hidden = true
      emptyEl.hidden = true
    }
    btnLoadMore.disabled = true
    try {
      const params: Record<string, string> = {
        limit: String(LIMIT),
        offset: String(offset),
      }
      if (filterTemplate.trim()) params.template = filterTemplate.trim()
      if (filterPinned) params.pinned = 'true'

      const items = await listHistory(params)
      if (items.length === 0 && offset === 0) {
        emptyEl.hidden = false
        moreEl.hidden = true
      } else {
        emptyEl.hidden = true
        for (const item of items) listEl.appendChild(buildRow(item))
        moreEl.hidden = items.length < LIMIT
        offset += items.length
      }
    } catch (err) {
      showStatus((err as Error).message, 'error')
    } finally {
      btnLoadMore.disabled = false
    }
  }

  function resetAndLoad(): void {
    hideStatus()
    void loadPage(true)
  }

  let debounce: number | undefined
  filterTemplateEl.addEventListener('input', () => {
    filterTemplate = filterTemplateEl.value
    window.clearTimeout(debounce)
    debounce = window.setTimeout(resetAndLoad, 350)
  })
  filterPinnedEl.addEventListener('change', () => {
    filterPinned = filterPinnedEl.checked
    resetAndLoad()
  })
  btnLoadMore.addEventListener('click', () => void loadPage(false))

  void loadPage(true)
}
