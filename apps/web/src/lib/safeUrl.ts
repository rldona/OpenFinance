/** Un enlace de la API solo se pinta si es https: lo que llega de fuera no se fía a ciegas. */
export function safeUrl(url: string | null): string | null {
  if (!url) return null
  try {
    return new URL(url).protocol === 'https:' ? url : null
  } catch {
    return null
  }
}
