import type { FontInfo, LabelEntry, PrintJobResponse, QuickPrintRequest } from './types'

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

export function getSettings(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/settings')
}

export function putSettings(partial: Record<string, unknown>): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>('/api/settings', {
    method: 'PUT',
    body: JSON.stringify(partial),
  })
}
