import type { BatchPrintResponse, FontInfo, HistoryDetail, HistoryItem, LabelEntry, PrintJobResponse, QuickPrintRequest, ReprintResponse, Template, TemplateCreate } from './types'

export const TOKEN_KEY = 'labelforge_token'

function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
      ...(options.headers as Record<string, string>),
    },
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: unknown }
      if (body.detail) detail = String(body.detail)
    } catch { /* use status fallback */ }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export function getLabels(): Promise<LabelEntry[]> {
  return apiFetch<LabelEntry[]>('/api/labels')
}

export function getFonts(): Promise<FontInfo[]> {
  return apiFetch<FontInfo[]>('/api/fonts')
}

export function quickPrint(req: QuickPrintRequest): Promise<PrintJobResponse> {
  return apiFetch<PrintJobResponse>('/api/print/quick', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export async function previewQuick(req: QuickPrintRequest): Promise<Blob> {
  const res = await fetch('/api/preview/quick', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: unknown }
      if (body.detail) detail = String(body.detail)
    } catch { /* use status fallback */ }
    throw new Error(detail)
  }
  return res.blob()
}

export function listTemplates(): Promise<Template[]> {
  return apiFetch<Template[]>('/api/templates')
}

export function getTemplate(name: string): Promise<Template> {
  return apiFetch<Template>(`/api/templates/${encodeURIComponent(name)}`)
}

export function createTemplate(body: TemplateCreate): Promise<Template> {
  return apiFetch<Template>('/api/templates', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateTemplate(name: string, body: Partial<TemplateCreate>): Promise<Template> {
  return apiFetch<Template>(`/api/templates/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function deleteTemplate(name: string): Promise<void> {
  return apiFetch<void>(`/api/templates/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export async function previewTemplate(name: string, fields: Record<string, string>): Promise<Blob> {
  const res = await fetch(`/api/preview/${encodeURIComponent(name)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ fields }),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: unknown }
      if (body.detail) detail = String(body.detail)
    } catch { /* use status fallback */ }
    throw new Error(detail)
  }
  return res.blob()
}

export function printTemplate(name: string, fields: Record<string, string>): Promise<PrintJobResponse> {
  return apiFetch<PrintJobResponse>(`/api/print/${encodeURIComponent(name)}`, {
    method: 'POST',
    body: JSON.stringify({ fields }),
  })
}

export function batchPrint(name: string, labels: Record<string, string>[]): Promise<BatchPrintResponse> {
  return apiFetch<BatchPrintResponse>(`/api/print/${encodeURIComponent(name)}/batch`, {
    method: 'POST',
    body: JSON.stringify({ labels }),
  })
}

export function listHistory(params: Record<string, string>): Promise<HistoryItem[]> {
  const qs = new URLSearchParams(params).toString()
  return apiFetch<HistoryItem[]>(`/api/history${qs ? '?' + qs : ''}`)
}

export function getHistory(id: number): Promise<HistoryDetail> {
  return apiFetch<HistoryDetail>(`/api/history/${id}`)
}

export async function fetchHistoryPreview(id: number): Promise<Blob> {
  const res = await fetch(`/api/history/${id}/preview.png`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: unknown }
      if (body.detail) detail = String(body.detail)
    } catch { /* use status fallback */ }
    throw new Error(detail)
  }
  return res.blob()
}

export function reprintHistory(id: number): Promise<ReprintResponse> {
  return apiFetch<ReprintResponse>(`/api/history/${id}/reprint`, { method: 'POST' })
}

export function pinHistory(id: number, pinned: boolean): Promise<HistoryItem> {
  return apiFetch<HistoryItem>(`/api/history/${id}/pin`, {
    method: 'POST',
    body: JSON.stringify({ pinned }),
  })
}

export function deleteHistory(id: number): Promise<void> {
  return apiFetch<void>(`/api/history/${id}`, { method: 'DELETE' })
}

export function pruneHistory(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/admin/prune-history', { method: 'POST' })
}

export function getSettings(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/settings')
}

export async function getPrinterStatus(): Promise<{ ok: boolean; body: Record<string, unknown> }> {
  const res = await fetch('/api/printer/status', {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  const body = await res.json() as Record<string, unknown>
  return { ok: res.ok, body }
}

export function putSettings(partial: Record<string, unknown>): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/settings', {
    method: 'PUT',
    body: JSON.stringify(partial),
  })
}
