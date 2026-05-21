const routes = {};
const prefixRoutes = [];
export function register(path, mount) {
    routes[path] = mount;
}
/** Register a handler for all paths that start with `prefix`. */
export function registerPrefix(prefix, mount) {
    prefixRoutes.push({ prefix, mount });
}
function setActiveNav(path) {
    document.querySelectorAll('[data-route]').forEach(a => {
        a.classList.toggle('active', a.dataset.route === path || path.startsWith(a.dataset.route + '/'));
    });
}
export function navigate(path) {
    history.pushState(null, '', path);
    render(path);
}
function render(path) {
    const root = document.getElementById('app');
    if (!root)
        return;
    const exact = routes[path];
    if (exact) {
        setActiveNav(path);
        exact(root);
        return;
    }
    for (const { prefix, mount } of prefixRoutes) {
        if (path.startsWith(prefix)) {
            setActiveNav(path);
            mount(root);
            return;
        }
    }
    const fallback = routes['/'];
    if (fallback) {
        setActiveNav(path);
        fallback(root);
    }
}
export function initRouter() {
    document.addEventListener('click', e => {
        const target = e.target.closest('[data-route]');
        if (!target)
            return;
        e.preventDefault();
        navigate(target.dataset.route);
    });
    window.addEventListener('popstate', () => render(window.location.pathname));
    render(window.location.pathname);
}
