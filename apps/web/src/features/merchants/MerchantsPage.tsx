import { type FormEvent, useState } from 'react'
import { ApiError, api, type MerchantGroup } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatMoney } from '../../lib/format'
import { notifyUndoable } from '../../lib/undo'
import { useLoad } from '../../lib/useLoad'

/** Comercios con sus variantes del banco: renombrar y fusionar (OF-1001). */
export function MerchantsPage() {
  const { me, notify } = useHousehold()
  const merchants = useLoad<MerchantGroup[]>('merchants', (s) => api.merchants(s))
  const [renaming, setRenaming] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [nameError, setNameError] = useState<string | null>(null)

  const list = merchants.data ?? []
  const first = (m: MerchantGroup) => m.keys[0]!

  async function rename(e: FormEvent, m: MerchantGroup) {
    e.preventDefault()
    try {
      const r = await api.renameMerchant(first(m), name)
      setRenaming(null)
      notifyUndoable(notify, me, `«${m.name}» ahora es «${r.merchant.name}»`, r.operation_id, merchants.reload)
      merchants.reload()
    } catch (err) {
      setNameError(err instanceof ApiError ? err.message : 'No se ha podido renombrar')
    }
  }

  async function merge(target: MerchantGroup, sourceKey: string) {
    const source = merchants.data?.find((m) => m.keys.includes(sourceKey))
    if (!source) return
    try {
      const r = await api.mergeMerchants(first(target), sourceKey)
      const extra = r.reclassified > 0 ? ` · ${r.reclassified} gastos clasificados` : ''
      notifyUndoable(notify, me, `«${source.name}» fusionado en «${target.name}»${extra}`, r.operation_id, merchants.reload)
      merchants.reload()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido fusionar')
    }
  }

  return (
    <section>
      <h1>Comercios</h1>
      <p className="lead">
        El banco escribe un mismo comercio de varias formas. Aquí puedes ponerle el nombre que quieras y fusionar los que son el mismo:
        sus gastos se juntan en los informes y, si uno ya tenía categoría, los demás sin categoría la toman. Todo se puede deshacer.{' '}
        <a href="#reglas">Reglas</a>
      </p>
      {merchants.error && <ErrorState message={merchants.error} onRetry={merchants.reload} />}
      {!merchants.data && !merchants.error && <Loading />}
      {merchants.data && list.length === 0 && (
        <div className="card empty">
          <p>Aún no hay comercios. Aparecen al importar un extracto.</p>
          <a className="btn" href="#importar">
            Importar
          </a>
        </div>
      )}
      {list.length > 0 && (
        <div className="card">
          <table role="table" className="rows">
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader">Comercio</th>
                <th role="columnheader" className="num">
                  Movimientos
                </th>
                <th role="columnheader" className="num">
                  Total
                </th>
                <th role="columnheader">
                  <span className="sr-only">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {list.map((m) => (
                <tr role="row" key={m.id ?? first(m)}>
                  <td role="cell">
                    {renaming === first(m) ? (
                      <form className="toolbar" onSubmit={(e) => void rename(e, m)} aria-label={`Renombrar ${m.name}`}>
                        <label className="small">
                          Nombre{' '}
                          <input
                            className="field"
                            required
                            maxLength={60}
                            value={name}
                            autoFocus
                            onChange={(e) => {
                              setName(e.target.value)
                              setNameError(null)
                            }}
                            aria-invalid={nameError ? true : undefined}
                            aria-describedby={nameError ? 'merchant-name-error' : undefined}
                          />
                        </label>
                        <button className="btn small primary" type="submit">
                          Guardar
                        </button>
                        <button className="btn small" type="button" onClick={() => setRenaming(null)}>
                          Cancelar
                        </button>
                        {nameError && (
                          <p id="merchant-name-error" className="error small" role="alert">
                            {nameError}
                          </p>
                        )}
                      </form>
                    ) : (
                      <>
                        {m.name}
                        {m.keys.length > 1 && <div className="small muted">{m.keys.length} variantes del banco: {m.keys.join(', ')}</div>}
                      </>
                    )}
                  </td>
                  <td role="cell" className="num">
                    {m.count}
                  </td>
                  <td role="cell" className="num">
                    {formatMoney(m.total)}
                  </td>
                  <td role="cell">
                    <div className="toolbar">
                      <button
                        className="btn small"
                        type="button"
                        aria-label={`Renombrar ${m.name}`}
                        onClick={() => {
                          setRenaming(first(m))
                          setName(m.name)
                          setNameError(null)
                        }}
                      >
                        Renombrar
                      </button>
                      <select
                        className="field small"
                        aria-label={`Fusionar otro comercio en ${m.name}`}
                        value=""
                        onChange={(e) => e.target.value && void merge(m, e.target.value)}
                      >
                        <option value="">Fusionar con…</option>
                        {list
                          .filter((o) => o !== m)
                          .map((o) => (
                            <option key={o.id ?? first(o)} value={first(o)}>
                              {o.name}
                            </option>
                          ))}
                      </select>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
