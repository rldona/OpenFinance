import { useEffect, useState } from 'react'
import { ApiError, TRANSACTIONS_LIMIT, api, type Account, type Me, type Transaction } from '../../api/client'
import { currentMonth, formatDate, formatMoney, monthLabel, shiftMonth } from '../../lib/format'
import { kindLabel } from './labels'

export function TransactionsPage({ me }: { me: Me }) {
  const [month, setMonth] = useState(currentMonth)
  const [allMonths, setAllMonths] = useState(false)
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [uncategorized, setUncategorized] = useState(false)
  const [accountId, setAccountId] = useState('')
  const [accounts, setAccounts] = useState<Account[]>([])
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
    month: allMonths ? undefined : month,
    q: debouncedQ || undefined,
    uncategorized,
    account_id: accountId || undefined,
  }
  const key = JSON.stringify(query)

  useEffect(() => {
    const controller = new AbortController()
    api
      .transactions(JSON.parse(key) as typeof query, controller.signal)
      .then((rows) => setResult({ key, rows }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const error = err instanceof ApiError ? err.message : 'No se han podido cargar los movimientos'
        setResult({ key, error })
      })
    return () => controller.abort()
  }, [key])

  const current = result?.key === key ? result : null
  const rows = current?.rows ?? null
  const error = current?.error ?? null

  const accountName = (id: string) => accounts.find((a) => a.id === id)?.name ?? ''

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Movimientos</h1>
          <p className="lead">Todo lo que ha pasado por vuestras cuentas.</p>
        </div>
        <div className="month-picker" role="group" aria-label="Mes">
          <button type="button" onClick={() => setMonth((m) => shiftMonth(m, -1))} disabled={allMonths} aria-label="Mes anterior">
            ‹
          </button>
          <strong>{allMonths ? 'Todos los meses' : monthLabel(month)}</strong>
          <button type="button" onClick={() => setMonth((m) => shiftMonth(m, 1))} disabled={allMonths} aria-label="Mes siguiente">
            ›
          </button>
        </div>
      </div>

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
            <input type="checkbox" checked={uncategorized} onChange={(e) => setUncategorized(e.target.checked)} /> Solo sin
            categoría
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
            <p>No hay movimientos con estos filtros.</p>
            <a className="btn" href="#importar">
              Importar un extracto
            </a>
          </div>
        )}
        {rows && rows.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Concepto</th>
                <th>Tipo</th>
                <th className="num">Importe</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => {
                const label = kindLabel(t, me)
                return (
                  <tr key={t.id}>
                    <td className="muted small">{formatDate(t.booked_at)}</td>
                    <td>
                      {t.description}
                      <div className="small muted">{accountName(t.account_id)}</div>
                    </td>
                    <td>
                      <span className={`tag tag-${label.tone}`}>{label.text}</span>
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
