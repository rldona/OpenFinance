import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

type Loaded<T> = { key: string; data?: T; error?: string } | null

export type Load<T> = {
  data: T | null
  error: string | null
  /** Vuelve a pedir los datos. Con datos ya cargados se siguen viendo hasta que llegan los nuevos. */
  reload: () => void
}

/**
 * Carga datos de la API para una clave: `key` resume todo lo que cambia la consulta.
 *
 * Al cambiar de clave no se muestran los datos de la anterior. Un error deja `error` con el
 * mensaje de la API y `reload` lo reintenta.
 */
export function useLoad<T>(
  key: string,
  load: (signal: AbortSignal) => Promise<T>,
  fallbackError = 'No se han podido cargar los datos',
): Load<T> {
  const [state, setState] = useState<Loaded<T>>(null)
  const [version, setVersion] = useState(0)
  const loadRef = useRef(load)
  const fallbackRef = useRef(fallbackError)
  useEffect(() => {
    loadRef.current = load
    fallbackRef.current = fallbackError
  })
  useEffect(() => {
    const controller = new AbortController()
    loadRef.current(controller.signal).then(
      (data) => setState({ key, data }),
      (err: unknown) => {
        if (!controller.signal.aborted)
          setState({ key, error: err instanceof ApiError ? err.message : fallbackRef.current })
      },
    )
    return () => controller.abort()
  }, [key, version])
  const reload = useCallback(() => {
    // Un error se quita al reintentar para que se vea «Cargando…» y no el error viejo.
    setState((s) => (s?.error ? null : s))
    setVersion((v) => v + 1)
  }, [])
  const current = state?.key === key ? state : null
  return { data: current?.data ?? null, error: current?.error ?? null, reload }
}
