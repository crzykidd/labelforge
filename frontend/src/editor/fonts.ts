import { TOKEN_KEY } from '../api'
import type { FontInfo } from '../types'

/**
 * Load server-hosted fonts into the browser's FontFace registry.
 *
 * Auth note: the API uses a Bearer token sent via the Authorization header.
 * A bare `url(...)` inside FontFace cannot attach a header, so we fetch the
 * bytes through an authenticated request and construct the FontFace from the
 * resulting ArrayBuffer — the same pattern used for preview PNGs and history
 * previews in api.ts.
 *
 * The FontFace family name is set to FontInfo.name (e.g. 'DejaVuSans-Bold')
 * because that is what the canvas stores in fontFamily on every text element.
 * Fonts already registered in document.fonts are skipped to avoid duplicates.
 */
export async function loadServerFonts(fonts: FontInfo[]): Promise<void> {
  await Promise.all(
    fonts.map(async (f) => {
      // Guard double-registration: check by family name (which we use as the identifier).
      if ([...document.fonts].some((face) => face.family === f.name)) {
        return
      }
      try {
        const res = await fetch(`/api/fonts/${encodeURIComponent(f.name)}/file`, {
          headers: { Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY) ?? ''}` },
        })
        if (!res.ok) {
          console.warn(`Font fetch failed (${res.status}): ${f.name}`)
          return
        }
        const buffer = await res.arrayBuffer()
        const face = new FontFace(f.name, buffer)
        await face.load()
        document.fonts.add(face)
      } catch (err) {
        console.warn(`Font failed to load: ${f.name}`, err)
      }
    }),
  )
}
