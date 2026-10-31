import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

type State =
  | { kind: 'loading' }
  | { kind: 'ok'; version: string }
  | { kind: 'down' }

export function ApiStatus() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then((h) => setState({ kind: 'ok', version: h.version }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'down' })
      })
    return () => controller.abort()
  }, [])

  const label =
    state.kind === 'loading'
      ? 'Comprobando API…'
      : state.kind === 'ok'
        ? `API ${state.version}`
        : 'API no disponible'

  return (
    <span className={`api-status api-status--${state.kind}`} role="status">
      {label}
    </span>
  )
}
