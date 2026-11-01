/**
 * Service worker mínimo (OF-805): guarda solo la carcasa de la aplicación para que se abra al
 * instante desde el icono. Nunca toca `/api/`: los datos siempre salen del servidor.
 */
export function registerServiceWorker() {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator) || !window.isSecureContext) return
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined) // sin SW la app funciona igual
  })
}
