type MountFn = (root: HTMLElement) => void

const routes: Record<string, MountFn> = {}

export function register(path: string, mount: MountFn): void {
  routes[path] = mount
}

function setActiveNav(path: string): void {
  document.querySelectorAll<HTMLAnchorElement>('[data-route]').forEach(a => {
    a.classList.toggle('active', a.dataset.route === path)
  })
}

export function navigate(path: string): void {
  history.pushState(null, '', path)
  render(path)
}

function render(path: string): void {
  const root = document.getElementById('app')
  if (!root) return
  const mount = routes[path] ?? routes['/']
  if (mount) {
    setActiveNav(path)
    mount(root)
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
