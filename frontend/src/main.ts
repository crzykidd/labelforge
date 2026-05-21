import './style.css'
import { mountQuickPrint } from './pages/quick-print'
import { mountTemplates } from './pages/templates'
import { initRouter, register } from './router'

register('/', mountQuickPrint)
register('/templates', mountTemplates)
initRouter()
