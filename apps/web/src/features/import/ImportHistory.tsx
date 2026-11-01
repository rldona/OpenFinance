import { useState } from 'react'
import { ApiError, api, type Account, type ImportItem } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate } from '../../lib/format'
import { notifyUndoable } from '../../lib/undo'
import { useLoad } from '../../lib/useLoad'

/** Importaciones hechas y deshacer la última de cada cuenta (OF-703). */
export function ImportHistory({ accounts }: { accounts: Account[] }) {
  const { me, notify, refreshUncategorized } = useHousehold()
  const items = useLoad<ImportItem[]>('imports', (s) => api.imports(s))
  const [confirming, setConfirming] = useState<string | null>(null)
  const accountName = (id: string) => accounts.find((a) => a.id === id)?.name ?? 'Cuenta'
  const who = (id: string) => (id === me.user.id ? 'tú' : (me.members.find((m) => m.id === id)?.display_name ?? 'alguien'))

  function refresh() {
    items.reload()
    refreshUncategorized()
  }

  async function undo(item: ImportItem) {
    setConfirming(null)
    try {
      const r = await api.undoImport(item.id)
      notifyUndoable(notify, me, `Importación deshecha: ${r.voided} movimientos anulados`, r.operation_id, refresh)
      refresh()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido deshacer la importación')
    }
  }

  if (items.error) return <ErrorState message={items.error} onRetry={items.reload} />
  if (!items.data) return <Loading />
  if (items.data.length === 0) return null
  return (
    <div className="card">
      <h2>Importaciones</h2>
      <ul className="plain imports" aria-label="Importaciones">
        {items.data.map((i) => (
          <li key={i.id} className={i.status === 'undone' ? 'undone' : ''}>
            <div>
              <strong>{i.filename}</strong> · {accountName(i.account_id)}
              <div className="small muted">
                {i.committed_at ? formatDate(i.committed_at) : ''} · {who(i.created_by)} · {i.created} nuevos ·{' '}
                {i.duplicates} ya estaban · {i.skipped} descartados
                {i.status === 'undone' && ' · deshecha'}
              </div>
            </div>
            {i.can_undo && confirming !== i.id && (
              <button className="btn small" type="button" onClick={() => setConfirming(i.id)}>
                Deshacer
              </button>
            )}
            {confirming === i.id && (
              <span className="toolbar" role="group" aria-label="Confirmar deshacer">
                <span className="small">Se anularán sus {i.created} movimientos (con sus correcciones).</span>
                <button className="btn small danger" type="button" onClick={() => void undo(i)}>
                  Sí, deshacer
                </button>
                <button className="btn small" type="button" onClick={() => setConfirming(null)}>
                  No
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      <p className="small muted">Solo se puede deshacer la última importación de cada cuenta. Volver a importar el mismo archivo la recupera.</p>
    </div>
  )
}
