import { useLayoutEffect, useRef, useState } from 'react'

/** Ancho de dibujo cuando aún no se ha medido (o el entorno no puede medir, como jsdom). */
export const DEFAULT_WIDTH = 640

/**
 * Mide el ancho real del gráfico para dibujar 1 unidad = 1 px (OF-503): así el texto conserva
 * su tamaño en pantallas estrechas en lugar de encogerse con el `viewBox`.
 *
 * La primera medición es síncrona y anterior al pintado (`useLayoutEffect`): el gráfico nunca se
 * ve dibujado a 640. `ResizeObserver` sigue después los cambios de tamaño.
 */
export function useChartWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const initial = Math.round(el.getBoundingClientRect().width)
    if (initial > 0) setWidth(initial)
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width)
      if (w > 0) setWidth(w)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

/** Ancho aproximado de una etiqueta del eje (12 px, sistema) para decidir cuántas caben. */
export function labelWidth(text: string, fontSize = 12): number {
  return text.length * fontSize * 0.6 + 8
}

/**
 * Cada cuántas posiciones se escribe una etiqueta para que no se pisen. Se cuenta desde el
 * final para que el último dato (el mes en curso) siempre tenga etiqueta.
 */
export function labelStep(slot: number, widest: number): number {
  return slot > 0 ? Math.max(1, Math.ceil(widest / slot)) : 1
}

export function showLabel(i: number, count: number, step: number): boolean {
  return (count - 1 - i) % step === 0
}
