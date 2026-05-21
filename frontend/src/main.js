import './style.css';
import { mountQuickPrint } from './pages/quick-print';
import { mountTemplates } from './pages/templates';
import { mountTemplateEditor } from './pages/template-editor';
import { initRouter, register, registerPrefix } from './router';
register('/', mountQuickPrint);
register('/templates', mountTemplates);
registerPrefix('/templates/', mountTemplateEditor);
initRouter();
