export type Theme = 'auto' | 'light' | 'dark'

const KEY = 'openfinance-theme'

export function getTheme(): Theme {
  try {
    const v = window.localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'auto'
  } catch {
    return 'auto' // almacenamiento bloqueado (modo privado): se sigue al sistema
  }
}

/** Aplica el tema al documento. «auto» no fija nada: manda `prefers-color-scheme`. */
export function applyTheme(theme: Theme) {
  const root = document.documentElement
  if (theme === 'auto') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
  const dark = theme === 'dark' || (theme === 'auto' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#162130' : '#0f766e')
}

export function setTheme(theme: Theme) {
  try {
    if (theme === 'auto') window.localStorage.removeItem(KEY)
    else window.localStorage.setItem(KEY, theme)
  } catch {
    // no se puede recordar: vale para esta visita
  }
  applyTheme(theme)
}
