import { useEffect, useState } from 'react'
import { api, type VersionInfo } from '../../api/client'
import { safeUrl } from '../../lib/safeUrl'

const DISMISSED_KEY = 'of-update-dismissed'

function dismissedVersion(): string | null {
  try {
    return window.localStorage.getItem(DISMISSED_KEY)
  } catch {
    return null
  }
}

/**
 * Aviso de versión nueva (OF-907). Solo informa: no se actualiza nada solo. Si la consulta está
 * apagada, falla o ya se ha descartado esa versión, no se pinta nada.
 */
export function UpdateNotice() {
  const [info, setInfo] = useState<VersionInfo | null>(null)
  const [dismissed, setDismissed] = useState<string | null>(dismissedVersion)

  useEffect(() => {
    const controller = new AbortController()
    api.version(controller.signal).then(setInfo, () => undefined)
    return () => controller.abort()
  }, [])

  if (!info?.update_available || !info.latest || dismissed === info.latest) return null
  const latest = info.latest
  const url = safeUrl(info.url)

  function dismiss() {
    try {
      window.localStorage.setItem(DISMISSED_KEY, latest)
    } catch {
      /* sin almacenamiento: se oculta hasta recargar */
    }
    setDismissed(latest)
  }

  return (
    <div className="notice info row" role="status">
      <span>
        Hay una versión nueva de OpenFinance: <strong>{latest}</strong> (tenéis la {info.current}).
        {url && (
          <>
            {' '}
            <a href={url} target="_blank" rel="noopener noreferrer">
              Ver novedades
            </a>
          </>
        )}
      </span>
      <button className="btn small" type="button" onClick={dismiss}>
        Ahora no
      </button>
    </div>
  )
}
