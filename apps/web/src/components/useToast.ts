import { useCallback, useEffect, useState } from 'react'

export function useToast(): [string | null, (message: string) => void] {
  const [toast, setToast] = useState<{ message: string; id: number } | null>(null)
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])
  // Cada aviso es un objeto nuevo: repetir el mismo mensaje reinicia el temporizador.
  const notify = useCallback((message: string) => setToast({ message, id: Date.now() }), [])
  return [toast?.message ?? null, notify]
}
