import { getVersionInfo } from './api'

const DISMISSED_KEY = 'lf:dismissed-release'

function getDismissed(): string | null {
  try { return localStorage.getItem(DISMISSED_KEY) } catch { return null }
}

function setDismissed(version: string): void {
  try { localStorage.setItem(DISMISSED_KEY, version) } catch { /* storage may be unavailable */ }
}

function buildModal(releaseName: string, releaseNotes: string, releaseUrl: string, onClose: () => void): HTMLElement {
  const overlay = document.createElement('div')
  overlay.className = 'modal-overlay version-release-overlay'
  overlay.setAttribute('role', 'dialog')
  overlay.setAttribute('aria-modal', 'true')

  const box = document.createElement('div')
  box.className = 'modal version-release-modal'

  const header = document.createElement('div')
  header.className = 'version-release-header'

  const title = document.createElement('h3')
  title.textContent = releaseName

  const closeBtn = document.createElement('button')
  closeBtn.className = 'version-release-close'
  closeBtn.setAttribute('aria-label', 'Close')
  closeBtn.textContent = '×'
  closeBtn.addEventListener('click', onClose)

  header.appendChild(title)
  header.appendChild(closeBtn)

  const body = document.createElement('pre')
  body.className = 'release-notes-body'
  // Untrusted text from GitHub: always textContent, never innerHTML
  body.textContent = releaseNotes

  const footer = document.createElement('div')
  footer.className = 'version-release-footer'
  const link = document.createElement('a')
  link.href = releaseUrl
  link.target = '_blank'
  link.rel = 'noopener'
  link.textContent = 'View full release notes on GitHub'
  footer.appendChild(link)

  box.appendChild(header)
  box.appendChild(body)
  box.appendChild(footer)
  overlay.appendChild(box)

  // Close on backdrop click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) onClose()
  })

  // Close on Esc
  const onKeydown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose()
      document.removeEventListener('keydown', onKeydown)
    }
  }
  document.addEventListener('keydown', onKeydown)

  return overlay
}

export function mountVersionFooter(): void {
  const footer = document.getElementById('app-footer')
  if (!footer) return

  getVersionInfo().then(info => {
    // For dev builds the link always points to the base release tag (the SHA suffix
    // has no corresponding GitHub release page).
    const versionUrl = (info.release_url && !info.update_available)
      ? info.release_url
      : `https://github.com/crzykidd/labelforge/releases/tag/v${info.current}`

    const wrap = document.createElement('span')
    wrap.className = 'version-footer-wrap'

    const link = document.createElement('a')
    link.href = versionUrl
    link.target = '_blank'
    link.rel = 'noopener'
    link.className = 'version-footer-link'
    link.textContent = info.build ?? `v${info.current}`
    wrap.appendChild(link)

    if (info.update_available && info.latest && info.release_url) {
      const pill = document.createElement('a')
      pill.href = info.release_url
      pill.target = '_blank'
      pill.rel = 'noopener'
      pill.className = 'version-update-pill'
      pill.textContent = `Update available: v${info.latest}`
      wrap.appendChild(pill)

      // Show release-notes popup once per new version
      const dismissed = getDismissed()
      if (dismissed !== info.latest) {
        const releaseName = info.release_name ?? `v${info.latest}`
        const releaseNotes = info.release_notes ?? ''
        const releaseUrl = info.release_url

        const close = () => {
          if (modal.parentNode) modal.parentNode.removeChild(modal)
          setDismissed(info.latest!)
        }
        const modal = buildModal(releaseName, releaseNotes, releaseUrl, close)
        document.body.appendChild(modal)
      }
    }

    footer.appendChild(wrap)
  }).catch(() => {
    // Non-fatal: leave footer empty on any failure
  })
}
