/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// Vitest no procesa el CSS (`?raw` llegaría vacío): se lee el fichero tal cual.
const css = readFileSync(join(import.meta.dirname, '../index.css'), 'utf8')

/**
 * OF-804/OF-805: el texto de cada par de colores del tema claro y del oscuro llega a 4,5:1
 * (WCAG 2.1 AA). axe no puede medirlo en jsdom, así que se calcula aquí desde el propio CSS.
 */
function tokens(selector: RegExp): Record<string, string> {
  const block = selector.exec(css)?.[1]
  if (!block) throw new Error(`No se encuentra ${selector}`)
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9a-f]{3,6})\s*;/gi)].map((m) => [m[1], m[2]]))
}

const light = tokens(/^:root \{([^}]*)\}/m)
const dark = tokens(/^:root\[data-theme='dark'\] \{([^}]*)\}/m)
const darkAuto = tokens(/prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme='light'\]\) \{([^}]*)\}/)

function channel(v: number) {
  const c = v / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}
function luminance(hex: string) {
  const h = hex.length === 4 ? `#${[...hex.slice(1)].map((x) => x + x).join('')}` : hex
  const [r, g, b] = [1, 3, 5].map((i) => channel(parseInt(h.slice(i, i + 2), 16)))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
export function ratio(a: string, b: string) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** [texto, fondo]: lo que de verdad se pinta una sobre otra en index.css. */
const PAIRS: Array<[string, string]> = [
  ['text', 'bg'],
  ['text', 'surface'],
  ['muted', 'bg'],
  ['muted', 'surface'],
  ['accent', 'surface'],
  ['accent', 'bg'],
  ['accent', 'accent-soft'],
  ['on-accent', 'accent'],
  ['pos', 'surface'],
  ['pos', 'bg'],
  ['pos', 'pos-soft'],
  ['neg', 'surface'],
  ['neg', 'bg'],
  ['neg', 'neg-soft'],
  ['on-neg', 'neg'],
  ['warn', 'warn-soft'],
  ['warn', 'surface'],
  ['text', 'warn-soft'],
]

describe.each([
  ['claro', light],
  ['oscuro (Ajustes)', { ...light, ...dark }],
  ['oscuro (sistema)', { ...light, ...darkAuto }],
])('contraste del tema %s', (_name, theme) => {
  it.each(PAIRS)('%s sobre %s llega a 4,5:1', (fg, bg) => {
    expect(ratio(theme[fg], theme[bg]), `${fg} ${theme[fg]} sobre ${bg} ${theme[bg]}`).toBeGreaterThanOrEqual(4.5)
  })
})

describe('los dos temas oscuros son el mismo', () => {
  it('el de Ajustes y el del sistema definen los mismos colores', () => {
    expect(darkAuto).toEqual(dark)
  })
})
