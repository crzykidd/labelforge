import './style.css'
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
initRouter()
