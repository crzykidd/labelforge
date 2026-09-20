const QUICK_KEY = 'lf:last-copies:quick'

function tplKey(name: string): string {
  return `lf:last-copies:tpl:${name}`
}

function parseStored(raw: string | null): number | null {
  if (raw === null) return null
  const n = Number(raw)
  if (!Number.isFinite(n) || !Number.isInteger(n) || n < 1 || n > 100) return null
  return n
}

export function getLastCopies(key: string): number | null {
  try { return parseStored(localStorage.getItem(key)) } catch { return null }
}

export function setLastCopies(key: string, n: number): void {
  if (!Number.isFinite(n) || n < 1 || n > 100) return
  try { localStorage.setItem(key, String(Math.round(n))) } catch { /* storage may be unavailable */ }
}

export function quickCopiesKey(): string {
  return QUICK_KEY
}

export function templateCopiesKey(name: string): string {
  return tplKey(name)
}
