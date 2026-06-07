const LAST_LABEL_KEY = 'lf:last-label'

export function getLastLabel(): string | null {
  try { return localStorage.getItem(LAST_LABEL_KEY) } catch { return null }
}

export function setLastLabel(id: string): void {
  if (!id) return
  try { localStorage.setItem(LAST_LABEL_KEY, id) } catch { /* storage may be unavailable */ }
}
