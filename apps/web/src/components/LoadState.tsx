/** Estados comunes de una pantalla que carga datos. */

export function Loading() {
  return (
    <p className="muted" role="status">
      Cargando…
    </p>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error-state" role="alert">
      <p className="error">{message}</p>
      <button className="btn small" type="button" onClick={onRetry}>
        Reintentar
      </button>
    </div>
  )
}
