import { describe, expect, it } from 'vitest'
import html from '../index.html?raw'
import manifestText from '../public/manifest.webmanifest?raw'
import sw from '../public/sw.js?raw'

const icons = Object.keys(import.meta.glob('/public/*.png')).map((p) => p.replace('/public', ''))

/** OF-805: lo mínimo para que el móvil ofrezca «Añadir a la pantalla de inicio». */
describe('app instalable', () => {
  const manifest = JSON.parse(manifestText) as {
    name: string
    display: string
    start_url: string
    icons: Array<{ src: string; sizes: string; purpose?: string }>
  }

  it('el manifiesto es instalable y sus iconos existen', () => {
    expect(manifest.display).toBe('standalone')
    expect(manifest.start_url).toMatch(/^\//)
    const sizes = manifest.icons.map((i) => i.sizes)
    expect(sizes).toEqual(expect.arrayContaining(['192x192', '512x512']))
    expect(manifest.icons.some((i) => i.purpose === 'maskable')).toBe(true)
    for (const icon of manifest.icons) expect(icons).toContain(icon.src)
  })

  it('index.html enlaza el manifiesto, el color de tema y el icono de iOS', () => {
    expect(html).toContain('rel="manifest" href="/manifest.webmanifest"')
    expect(html).toContain('name="theme-color"')
    expect(html).toContain('rel="apple-touch-icon"')
  })

  it('el service worker nunca guarda la API', () => {
    expect(sw).toMatch(/pathname\.startsWith\('\/api\/'\)/)
    expect(sw).toMatch(/request\.method !== 'GET'/)
    // la lista de la carcasa no incluye rutas de la API
    expect(/SHELL = \[[^\]]*\/api\//.test(sw)).toBe(false)
  })
})
