import { useEffect, useState } from 'react'

export const ROUTES = [
  { id: 'mes', label: 'Este mes' },
  { id: 'gastos', label: '¿En qué gastamos?' },
  { id: 'evolucion', label: 'Evolución' },
  { id: 'ahorrar', label: 'Ahorrar' },
  { id: 'movimientos', label: 'Movimientos' },
  { id: 'importar', label: 'Importar' },
] as const

const HIDDEN_ROUTES = ['categorias', 'presupuestos', 'reglas', 'ajustes', 'cambios'] as const

export type RouteId = (typeof ROUTES)[number]['id'] | (typeof HIDDEN_ROUTES)[number]

function parse(hash: string): RouteId {
  const id = hash.replace(/^#\/?/, '')
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
