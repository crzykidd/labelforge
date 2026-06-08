import './style.css'
import { getFonts, initAuthMode } from './api'
import { loadServerFonts } from './editor/fonts'
import { mountQuickPrint } from './pages/quick-print'
import { mountTemplates } from './pages/templates'
import { mountTemplateEditor } from './pages/template-editor'
import { mountTemplateRecall } from './pages/template-recall'
import { mountHistory } from './pages/history'
import { mountSettings } from './pages/settings'
import { initRouter, register, registerPrefix } from './router'
import { mountVersionFooter } from './version'

register('/', mountQuickPrint)
register('/templates', mountTemplates)
registerPrefix('/templates/', (root) => {
  const path = window.location.pathname
  if (path.endsWith('/print')) {
    mountTemplateRecall(root)
  } else {
    mountTemplateEditor(root)
  }
})
register('/history', mountHistory)
register('/settings', mountSettings)

// Resolve auth mode before routing so the token gate can be skipped when the
// backend runs with DISABLE_AUTH=true. Always routes, even if the probe fails.
// After auth is resolved, pre-load all server fonts into document.fonts so
// every page (Quick Print preview, editor canvas) uses the real typefaces.
void initAuthMode().finally(() => {
  initRouter()
  getFonts().then(loadServerFonts).catch(() => {
    // Non-fatal: font loading failures are already warned per-font inside
    // loadServerFonts; a total failure (e.g. not logged in yet) is silenced here.
  })
})

// Version footer is independent of auth/routing — mount once at startup.
mountVersionFooter()
