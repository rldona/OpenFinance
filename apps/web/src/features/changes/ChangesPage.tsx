import { ApiError, api, type Operation } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate } from '../../lib/format'
import { revertMessage } from '../../lib/undo'
import { useLoad } from '../../lib/useLoad'

/** Tus últimas correcciones, con deshacer y rehacer (OF-706, ADR-0017). */
export function ChangesPage() {
  const { me, notify, refreshUncategorized } = useHousehold()
  const ops = useLoad<Operation[]>('changes', (s) => api.changes(s))

  async function revert(o: Operation) {
    try {
      const r = o.undone ? await api.redo(o.id) : await api.undo(o.id)
      notify(revertMessage(r, me, o.undone ? 'Rehecho' : 'Deshecho'))
      ops.reload()
      refreshUncategorized()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido completar')
    }
  }

  return (
    <section>
      <h1>Mis cambios</h1>
      <p className="lead">
        Tus últimas correcciones. Deshacer nunca pisa lo que alguien cambió después: eso se respeta y se avisa. Solo ves y deshaces
        las tuyas. <a href="#ajustes">Ajustes</a>
      </p>
      {ops.error && <ErrorState message={ops.error} onRetry={ops.reload} />}
      {!ops.data && !ops.error && <Loading />}
      {ops.data && ops.data.length === 0 && (
        <div className="card empty">
          <p>Aún no has corregido nada.</p>
        </div>
      )}
      {ops.data && ops.data.length > 0 && (
        <div className="card">
          <ul className="plain imports" aria-label="Mis cambios">
            {ops.data.map((o) => (
              <li key={o.id} className={o.undone ? 'undone' : ''}>
                <div>
                  {o.summary}
                  <div className="small muted">
                    {formatDate(o.created_at)}
                    {o.undone && ' · deshecho'}
                  </div>
                </div>
                <button className="btn small" type="button" onClick={() => void revert(o)}>
                  {o.undone ? 'Rehacer' : 'Deshacer'}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
