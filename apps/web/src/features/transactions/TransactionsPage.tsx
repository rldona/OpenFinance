import { useEffect, useState } from 'react'
import { ApiError, TRANSACTIONS_LIMIT, api, type Account, type Transaction } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { formatDate, formatMoney } from '../../lib/format'
import { MonthPicker } from '../insights/common'
import { kindLabel } from './labels'

function CategorySelect({
  t,
  disabled,
  onChange,
}: {
  t: Transaction
  disabled: boolean
  onChange: (categoryId: string | null) => void
}) {
  const { categories, categoriesReady } = useHousehold()
  const options = categories.filter((c) => !c.hidden || c.id === t.category_id)
  return (
    <select
      className={`catsel ${t.category_id ? '' : 'empty'}`}
      aria-label={`Categoría de ${t.description}`}
      value={t.category_id ?? ''}
      disabled={disabled || !categoriesReady}
      onChange={(e) => onChange(e.target.value || null)}
    >
      <option value="">🏷️ Sin categoría</option>
      {options.map((c) => (
        <option key={c.id} value={c.id}>
          {c.icon} {c.name}
        </option>
      ))}
    </select>
  )
}

export function TransactionsPage() {
  const { me, categoryById, uncategorized, refreshUncategorized, notify, month } = useHousehold()
  const [allMonths, setAllMonths] = useState(false)
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [onlyUncategorized, setOnlyUncategorized] = useState(false)
  const [accountId, setAccountId] = useState('')
  const [accounts, setAccounts] = useState<Account[]>([])
  const [version, setVersion] = useState(0)
  const [pending, setPending] = useState<string | null>(null)
  const [result, setResult] = useState<{ key: string; rows?: Transaction[]; error?: string } | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 250)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    const controller = new AbortController()
    api.accounts(controller.signal).then(setAccounts, () => undefined) // los nombres de cuenta son opcionales
    return () => controller.abort()
  }, [])

  const query = {
    month: allMonths || onlyUncategorized ? undefined : month,
    q: debouncedQ || undefined,
    uncategorized: onlyUncategorized,
    account_id: accountId || undefined,
  }
  const key = `${JSON.stringify(query)}#${version}`

  useEffect(() => {
    const controller = new AbortController()
    api
      .transactions(JSON.parse(key.split('#')[0]) as typeof query, controller.signal)
      .then((rows) => setResult({ key, rows }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const error = err instanceof ApiError ? err.message : 'No se han podido cargar los movimientos'
        setResult({ key, error })
      })
    return () => controller.abort()
  }, [key])

  const current = result?.key === key ? result : null
  // Mientras llega la consulta nueva se siguen viendo las filas anteriores, atenuadas y sin
  // poder editarse, para evitar parpadeos sin permitir cambios sobre datos desactualizados.
  const stale = !current
  const rows = current?.rows ?? (stale && !result?.error ? (result?.rows ?? null) : null)
  const error = current?.error ?? null
  const accountName = (id: string) => accounts.find((a) => a.id === id)?.name ?? ''

  async function changeCategory(t: Transaction, categoryId: string | null) {
    setPending(t.id)
    try {
      const r = await api.categorize(t.id, categoryId)
      const category = categoryId ? categoryById.get(categoryId) : undefined
      if (r.rule && category) {
        const more = r.also_categorized ? ` · ${r.also_categorized} más clasificados` : ''
        notify(`Regla guardada: «${r.rule.merchant}» → ${category.name}${more}`)
      } else {
        notify(category ? `Categoría: ${category.name}` : 'Categoría quitada')
      }
      setVersion((v) => v + 1)
      refreshUncategorized()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido cambiar la categoría')
    } finally {
      setPending(null)
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Movimientos</h1>
          <p className="lead">
            Cambia la categoría en la tabla y OpenFinance aprende la regla para ese comercio.{' '}
            <a href="#categorias">Gestionar categorías</a>
          </p>
        </div>
        <MonthPicker disabled={allMonths || onlyUncategorized} />
      </div>

      {uncategorized > 0 && !onlyUncategorized && (
        <div className="notice warn row">
          <span>
            🏷️ <strong>{uncategorized === 1 ? '1 gasto' : `${uncategorized} gastos`} sin categoría.</strong>{' '}
            Clasificarlos hará que los gráficos sean fiables.
          </span>
          <button className="btn" type="button" onClick={() => setOnlyUncategorized(true)}>
            Clasificar
          </button>
        </div>
      )}

      <div className="card">
        <div className="toolbar">
          <input
            type="search"
            className="field"
            placeholder="Buscar concepto…"
            aria-label="Buscar"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select className="field" aria-label="Cuenta" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Todas las cuentas</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          <label className="small">
            <input
              type="checkbox"
              checked={onlyUncategorized}
              onChange={(e) => setOnlyUncategorized(e.target.checked)}
            />{' '}
            Solo sin categoría ({uncategorized})
          </label>
          <label className="small">
            <input type="checkbox" checked={allMonths} onChange={(e) => setAllMonths(e.target.checked)} /> Todos los meses
          </label>
        </div>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {!error && rows === null && <p className="muted">Cargando…</p>}
        {rows && rows.length === 0 && (
          <div className="empty">
            {onlyUncategorized ? (
              <p>✓ Todos los gastos tienen categoría.</p>
            ) : (
              <>
                <p>No hay movimientos con estos filtros.</p>
                <a className="btn" href="#importar">
                  Importar un extracto
                </a>
              </>
            )}
          </div>
        )}
        {rows && rows.length > 0 && (
          <table className={stale ? 'stale' : ''} aria-busy={stale}>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Concepto</th>
                <th>Categoría</th>
                <th className="num">Importe</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => {
                const label = kindLabel(t, me, categoryById)
                return (
                  <tr key={t.id}>
                    <td className="muted small">{formatDate(t.booked_at)}</td>
                    <td>
                      {t.merchant || t.description}
                      <div className="small muted">
                        {t.description} · {accountName(t.account_id)}
                      </div>
                    </td>
                    <td>
                      {t.kind === 'expense' ? (
                        <CategorySelect
                          t={t}
                          disabled={stale || pending !== null}
                          onChange={(id) => void changeCategory(t, id)}
                        />
                      ) : (
                        <span className={`tag tag-${label.tone}`}>{label.text}</span>
                      )}
                    </td>
                    <td className={`num ${t.amount.amount.startsWith('-') ? '' : 'pos'}`}>
                      {formatMoney(t.amount, { signed: true })}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        {rows && rows.length >= TRANSACTIONS_LIMIT && (
          <p className="notice warn small">
            Se muestran los {TRANSACTIONS_LIMIT} más recientes. Filtra por mes o busca para ver el resto.
          </p>
        )}
        {rows && rows.length > 0 && rows.length < TRANSACTIONS_LIMIT && (
          <p className="small muted">{rows.length} movimientos</p>
        )}
      </div>
    </section>
  )
}
