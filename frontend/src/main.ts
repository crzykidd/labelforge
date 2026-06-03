import './style.css'
import { initAuthMode } from './api'
import { mountQuickPrint } from './pages/quick-print'
import { mountTemplates } from './pages/templates'
import { mountTemplateEditor } from './pages/template-editor'
import { mountTemplateRecall } from './pages/template-recall'
import { mountHistory } from './pages/history'
import { mountSettings } from './pages/settings'
import { initRouter, register, registerPrefix } from './router'

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
void initAuthMode().finally(() => initRouter())
