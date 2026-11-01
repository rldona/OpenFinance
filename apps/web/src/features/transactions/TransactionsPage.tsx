import { Fragment, useEffect, useState } from 'react'
import { ApiError, TRANSACTIONS_LIMIT, api, type Account, type Transaction } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate, formatMoney } from '../../lib/format'
import { notifyUndoable } from '../../lib/undo'
import { MonthPicker } from '../insights/common'
import { kindLabel } from './labels'
import { TransactionDetail } from './TransactionDetail'

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
  // La clave lleva la consulta tal cual: la búsqueda puede contener cualquier carácter.
  const key = JSON.stringify([query, version])

  useEffect(() => {
    const controller = new AbortController()
    api
      .transactions((JSON.parse(key) as [typeof query, number])[0], controller.signal)
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
  const [openId, setOpenId] = useState<string | null>(null)

  function refresh() {
    setVersion((v) => v + 1)
    refreshUncategorized()
  }

  async function changeCategory(t: Transaction, categoryId: string | null) {
    setPending(t.id)
    try {
      const r = await api.categorize(t.id, categoryId)
      const category = categoryId ? categoryById.get(categoryId) : undefined
      const message =
        r.rule && category
          ? `Regla guardada: «${r.rule.merchant}» → ${category.name}${r.also_categorized ? ` · ${r.also_categorized} más clasificados` : ''}`
          : category
            ? `Categoría: ${category.name}`
            : 'Categoría quitada'
      notifyUndoable(notify, me, message, r.operation_id, refresh)
      refresh()
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

        {error && <ErrorState message={error} onRetry={() => setVersion((v) => v + 1)} />}
        {!error && rows === null && <Loading />}
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
          <table role="table" className={`rows tx${stale ? ' stale' : ''}`} aria-busy={stale}>
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader">Fecha</th>
                <th role="columnheader">Concepto</th>
                <th role="columnheader">Categoría</th>
                <th role="columnheader" className="num">Importe</th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {rows.map((t) => {
                const label = kindLabel(t, me, categoryById)
                const open = openId === t.id
                return (
                  <Fragment key={t.id}>
                  <tr role="row">
                    <td role="cell" className="muted small">{formatDate(t.booked_at)}</td>
                    <td role="cell">
                      <button
                        type="button"
                        className="linkish"
                        aria-expanded={open}
                        aria-label={`Detalle de ${t.description}`}
                        onClick={() => setOpenId(open ? null : t.id)}
                      >
                        {t.merchant || t.description}
                      </button>
                      <div className="small muted">
                        {t.description} · {accountName(t.account_id)}
                        {t.note && <> · 📝 {t.note}</>}
                      </div>
                    </td>
                    <td role="cell">
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
                    <td role="cell" className={`num ${t.amount.amount.startsWith('-') ? '' : 'pos'}`}>
                      {formatMoney(t.amount, { signed: true })}
                    </td>
                  </tr>
                  {open && (
                    <tr role="row" className="detail-row">
                      <td role="cell" colSpan={4}>
                        <TransactionDetail
                          key={`${t.id}|${t.kind}|${t.member_id}|${t.note}`}
                          t={t}
                          version={version}
                          onClose={() => setOpenId(null)}
                          onSaved={(r) => {
                            notifyUndoable(notify, me, 'Movimiento corregido', r.operation_id, refresh)
                            refresh()
                          }}
                        />
                      </td>
                    </tr>
                  )}
                  </Fragment>
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
