import type { BatchPrintResponse, FontInfo, HistoryDetail, HistoryItem, LabelEntry, PrintJobResponse, PrinterStatus, QuickPrintRequest, ReprintResponse, Template, TemplateCreate, TemplateLastValues } from './types'

export const TOKEN_KEY = 'labelforge_token'

function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

// Whether the backend enforces app-level auth. Resolved once at startup from
// /api/health (unauthenticated). Defaults to true so we fail closed if the
// probe fails. See initAuthMode().
let authRequired = true

export function isAuthRequired(): boolean {
  return authRequired
}

export async function initAuthMode(): Promise<void> {
  try {
    const res = await fetch('/api/health')
    const body = await res.json() as { auth_required?: boolean }
    authRequired = body.auth_required !== false
  } catch {
    authRequired = true  // fail closed
  }
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
      const d = body.detail
      if (typeof d === 'string') {
        detail = d
      } else if (d && typeof d === 'object' && typeof (d as { message?: unknown }).message === 'string') {
        // structured errors (e.g. 409 media_mismatch / printer_error) carry a human message
        detail = (d as { message: string }).message
      } else if (d != null) {
        detail = JSON.stringify(d)
      }
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
      const d = body.detail
      if (typeof d === 'string') {
        detail = d
      } else if (d && typeof d === 'object' && typeof (d as { message?: unknown }).message === 'string') {
        // structured errors (e.g. 409 media_mismatch / printer_error) carry a human message
        detail = (d as { message: string }).message
      } else if (d != null) {
        detail = JSON.stringify(d)
      }
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

export function duplicateTemplate(source: string, body: { name: string; label_media: string }): Promise<Template> {
  return apiFetch<Template>(`/api/templates/${encodeURIComponent(source)}/duplicate`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getLastValues(name: string): Promise<TemplateLastValues> {
  return apiFetch<TemplateLastValues>(`/api/templates/${encodeURIComponent(name)}/last-values`)
}

export async function previewTemplate(
  name: string,
  fields: Record<string, string>,
  labelMedia?: string,
): Promise<{ blob: Blob; overflow: boolean }> {
  const body: Record<string, unknown> = { fields }
  if (labelMedia !== undefined) body.label_media = labelMedia
  const res = await fetch(`/api/preview/${encodeURIComponent(name)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const errBody = await res.json() as { detail?: unknown }
      const d = errBody.detail
      if (typeof d === 'string') {
        detail = d
      } else if (d && typeof d === 'object' && typeof (d as { message?: unknown }).message === 'string') {
        // structured errors (e.g. 409 media_mismatch / printer_error) carry a human message
        detail = (d as { message: string }).message
      } else if (d != null) {
        detail = JSON.stringify(d)
      }
    } catch { /* use status fallback */ }
    throw new Error(detail)
  }
  const overflow = res.headers.get('X-Label-Overflow') === 'true'
  return { blob: await res.blob(), overflow }
}

export function printTemplate(
  name: string,
  fields: Record<string, string>,
  labelMedia?: string,
): Promise<PrintJobResponse> {
  const body: Record<string, unknown> = { fields }
  if (labelMedia !== undefined) body.label_media = labelMedia
  return apiFetch<PrintJobResponse>(`/api/print/${encodeURIComponent(name)}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function batchPrint(
  name: string,
  labels: Record<string, string>[],
  labelMedia?: string,
): Promise<BatchPrintResponse> {
  const body: Record<string, unknown> = { labels }
  if (labelMedia !== undefined) body.label_media = labelMedia
  return apiFetch<BatchPrintResponse>(`/api/print/${encodeURIComponent(name)}/batch`, {
    method: 'POST',
    body: JSON.stringify(body),
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
      const d = body.detail
      if (typeof d === 'string') {
        detail = d
      } else if (d && typeof d === 'object' && typeof (d as { message?: unknown }).message === 'string') {
        // structured errors (e.g. 409 media_mismatch / printer_error) carry a human message
        detail = (d as { message: string }).message
      } else if (d != null) {
        detail = JSON.stringify(d)
      }
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

export async function getPrinterStatus(): Promise<{ ok: boolean; body: PrinterStatus & Record<string, unknown> }> {
  const res = await fetch('/api/printer/status', {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  const body = await res.json() as PrinterStatus & Record<string, unknown>
  return { ok: res.ok, body }
}

export function putSettings(partial: Record<string, unknown>): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/settings', {
    method: 'PUT',
    body: JSON.stringify(partial),
  })
}
