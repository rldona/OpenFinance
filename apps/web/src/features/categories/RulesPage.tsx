import { ApiError, api, type RuleView } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { notifyUndoable } from '../../lib/undo'
import { useLoad } from '../../lib/useLoad'

/** Reglas «comercio → categoría» aprendidas al corregir (OF-702). */
export function RulesPage() {
  const { me, categoryById, notify } = useHousehold()
  const rules = useLoad<RuleView[]>('rules', (s) => api.rules(s))

  async function remove(rule: RuleView) {
    try {
      const r = await api.deleteRule(rule.scope, rule.key)
      notifyUndoable(notify, me, `Regla borrada: ${rule.merchant}`, r.operation_id, rules.reload)
      rules.reload()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido borrar la regla')
    }
  }

  return (
    <section>
      <h1>Reglas</h1>
      <p className="lead">
        Al poner una categoría a un gasto, OpenFinance la recuerda para ese comercio y clasifica los demás gastos sin categoría.
        Borrar una regla no cambia lo que ya está clasificado. Los Bizum y las transferencias a personas no crean reglas.{' '}
        <a href="#categorias">Categorías</a>
      </p>
      {rules.error && <ErrorState message={rules.error} onRetry={rules.reload} />}
      {!rules.data && !rules.error && <Loading />}
      {rules.data && rules.data.length === 0 && (
        <div className="card empty">
          <p>Aún no hay reglas. Se crean al poner una categoría en Movimientos.</p>
          <a className="btn" href="#movimientos">
            Ir a Movimientos
          </a>
        </div>
      )}
      {rules.data && rules.data.length > 0 && (
        <div className="card">
          <table role="table" className="rows">
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader">Comercio</th>
                <th role="columnheader">Categoría</th>
                <th role="columnheader" className="num">
                  Movimientos
                </th>
                <th role="columnheader">
                  <span className="sr-only">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {rules.data.map((r) => {
                const c = categoryById.get(r.category_id)
                return (
                  <tr role="row" key={`${r.scope}|${r.key}`}>
                    <td role="cell">
                      {r.merchant}
                      {r.scope === 'personal' && <div className="small muted">Personal · solo la ves tú</div>}
                    </td>
                    <td role="cell">{c ? `${c.icon} ${c.name}` : '—'}</td>
                    <td role="cell" className="num">
                      {r.matches}
                    </td>
                    <td role="cell">
                      <button className="btn small" type="button" aria-label={`Borrar la regla de ${r.merchant}`} onClick={() => void remove(r)}>
                        Borrar
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
