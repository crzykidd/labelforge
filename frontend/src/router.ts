type MountFn = (root: HTMLElement) => void

const routes: Record<string, MountFn> = {}
const prefixRoutes: Array<{ prefix: string; mount: MountFn }> = []

export function register(path: string, mount: MountFn): void {
  routes[path] = mount
}

/** Register a handler for all paths that start with `prefix`. */
export function registerPrefix(prefix: string, mount: MountFn): void {
  prefixRoutes.push({ prefix, mount })
}

function setActiveNav(path: string): void {
  document.querySelectorAll<HTMLAnchorElement>('[data-route]').forEach(a => {
    a.classList.toggle('active', a.dataset.route === path || path.startsWith(a.dataset.route! + '/'))
  })
}

export function navigate(path: string): void {
  history.pushState(null, '', path)
  render(path)
}

function render(path: string): void {
  const root = document.getElementById('app')
  if (!root) return
  const exact = routes[path]
  if (exact) {
    setActiveNav(path)
    exact(root)
    return
  }
  for (const { prefix, mount } of prefixRoutes) {
    if (path.startsWith(prefix)) {
      setActiveNav(path)
      mount(root)
      return
    }
  }
  const fallback = routes['/']
  if (fallback) {
    setActiveNav(path)
    fallback(root)
  }
}

export function initRouter(): void {
  document.addEventListener('click', e => {
    const target = (e.target as HTMLElement).closest<HTMLAnchorElement>('[data-route]')
    if (!target) return
    e.preventDefault()
    navigate(target.dataset.route!)
  })
  window.addEventListener('popstate', () => render(window.location.pathname))
  render(window.location.pathname)
}
