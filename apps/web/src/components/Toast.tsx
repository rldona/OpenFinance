export function Toast({ message }: { message: string | null }) {
  return (
    <div className={`toast ${message ? 'show' : ''}`} role="status" aria-live="polite">
      {message}
    </div>
  )
}
