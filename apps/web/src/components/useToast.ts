import { useCallback, useEffect, useState } from 'react'

/** Botón del aviso, p. ej. «Deshacer» (OF-702). */
export type ToastAction = { label: string; run: () => void }
export type Notice = { message: string; action?: ToastAction; id: number }
export type Notify = (message: string, action?: ToastAction) => void

const PLAIN_MS = 3500
/** Con botón, más tiempo para pulsarlo. */
const ACTION_MS = 8000

export function useToast(): [Notice | null, Notify, () => void] {
  const [toast, setToast] = useState<Notice | null>(null)
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), toast.action ? ACTION_MS : PLAIN_MS)
    return () => clearTimeout(t)
  }, [toast])
  // Cada aviso es un objeto nuevo: repetir el mismo mensaje reinicia el temporizador.
  const notify = useCallback<Notify>((message, action) => setToast({ message, action, id: Date.now() }), [])
  const dismiss = useCallback(() => setToast(null), [])
  return [toast, notify, dismiss]
}
