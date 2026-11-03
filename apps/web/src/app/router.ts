import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

/** `icon` y `short` son para la barra inferior del móvil y el carril de la tableta (OF-801). */
export const ROUTES = [
  { id: 'mes', label: 'Este mes', short: 'Mes', icon: '📅' },
  { id: 'gastos', label: '¿En qué gastamos?', short: 'Gastos', icon: '🍩' },
  { id: 'evolucion', label: 'Evolución', short: 'Evolución', icon: '📈' },
  { id: 'ahorrar', label: 'Ahorrar', short: 'Ahorrar', icon: '🐷' },
  { id: 'movimientos', label: 'Movimientos', short: 'Movim.', icon: '🧾' },
  { id: 'importar', label: 'Importar', short: 'Importar', icon: '⬆️' },
] as const

const HIDDEN_ROUTES = ['categorias', 'presupuestos', 'reglas', 'ajustes', 'cambios', 'comercios', 'pagos', 'semana', 'patrimonio', 'flujo'] as const

export type RouteId = (typeof ROUTES)[number]['id'] | (typeof HIDDEN_ROUTES)[number]

/** Título de la pestaña del navegador y de lectores de pantalla para cada pantalla (OF-804). */
export const TITLES: Record<RouteId, string> = {
  mes: 'Este mes',
  gastos: '¿En qué gastamos?',
  evolucion: 'Evolución',
  ahorrar: 'Ahorrar',
  movimientos: 'Movimientos',
  importar: 'Importar extracto',
  categorias: 'Categorías',
  presupuestos: 'Presupuestos',
  reglas: 'Reglas',
  ajustes: 'Ajustes',
  cambios: 'Mis cambios',
  comercios: 'Comercios',
  pagos: 'Pagos programados',
  semana: 'Resumen de la semana',
  patrimonio: 'Patrimonio neto',
  flujo: 'Flujo de caja',
}

const PARAMS_EVENT = 'of-hash-params'

/** `#movimientos?mes=2026-09&q=luz` → la pantalla y sus parámetros. */
function split(hash: string): { id: string; params: URLSearchParams } {
  const raw = hash.replace(/^#\/?/, '')
  const i = raw.indexOf('?')
  return { id: i < 0 ? raw : raw.slice(0, i), params: new URLSearchParams(i < 0 ? '' : raw.slice(i + 1)) }
}

function parse(hash: string): RouteId {
  const { id } = split(hash)
  const hidden = HIDDEN_ROUTES.find((r) => r === id)
  return hidden ?? ROUTES.find((r) => r.id === id)?.id ?? 'mes'
}

export function useRoute(): RouteId {
  const [route, setRoute] = useState<RouteId>(() => parse(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  window.addEventListener(PARAMS_EVENT, onChange)
  return () => {
    window.removeEventListener('hashchange', onChange)
    window.removeEventListener(PARAMS_EVENT, onChange)
  }
}

/** Cambia parámetros de la URL sin añadir entradas al historial (`null` quita el parámetro). */
export function setHashParams(updates: Record<string, string | null>) {
  const { id, params } = split(window.location.hash)
  for (const [key, value] of Object.entries(updates)) {
    if (value === null || value === '') params.delete(key)
    else params.set(key, value)
  }
  const qs = params.toString()
  const hash = `#${id}${qs ? `?${qs}` : ''}`
  if (hash === window.location.hash) return
  window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${hash}`)
  window.dispatchEvent(new Event(PARAMS_EVENT))
}

/** Un parámetro del hash como estado: se comparte con un enlace y sobrevive a recargar. */
export function useHashParam(key: string): [string | null, (value: string | null) => void] {
  const value = useSyncExternalStore(subscribe, () => split(window.location.hash).params.get(key))
  const set = useCallback((v: string | null) => setHashParams({ [key]: v }), [key])
  return [value, set]
}

/** Parámetros que se mantienen al cambiar de pantalla desde el menú: el mes y «Hogar/Mío». */
const SHARED_PARAMS = ['mes', 'vista'] as const

export function routeHref(id: RouteId, extra: Record<string, string> = {}): string {
  const { params } = split(window.location.hash)
  const shared = new URLSearchParams(extra)
  for (const key of SHARED_PARAMS) {
    const v = params.get(key)
    if (v && !shared.has(key)) shared.set(key, v)
  }
  const qs = shared.toString()
  return `#${id}${qs ? `?${qs}` : ''}`
}

/** Para que el menú se vuelva a pintar cuando cambia el mes o la vista. */
export function useSharedParamsKey(): string {
  return useSyncExternalStore(subscribe, () => SHARED_PARAMS.map((k) => split(window.location.hash).params.get(k) ?? '').join('|'))
}
