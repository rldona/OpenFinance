import { type FormEvent, useState } from 'react'
import { ApiError, api, type Account, type Reconciliation } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { FieldError } from '../../components/FieldError'
import { ErrorState } from '../../components/LoadState'
import { formatDate, formatMoney } from '../../lib/format'
import { invalid } from '../../lib/invalid'
import { useLoad } from '../../lib/useLoad'

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Comprobar el saldo de una cuenta contra el que da el banco en una fecha (OF-1006). */
export function Reconcile({ account }: { account: Account }) {
  const { notify } = useHousehold()
  const history = useLoad<Reconciliation[]>(`recon|${account.id}`, (s) => api.reconciliations(account.id, s))
  const [asOf, setAsOf] = useState(today)
  const [balance, setBalance] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [last, setLast] = useState<Reconciliation | null>(null)

  async function check(e: FormEvent) {
    e.preventDefault()
    const text = balance.trim().replace(/\s/g, '').replace(',', '.')
    if (!/^-?\d{1,9}(\.\d{1,2})?$/.test(text)) {
      setError('Escribe el saldo del banco, por ejemplo 1227,26')
      return
    }
    setError(null)
    try {
      setLast(await api.reconcileAccount(account.id, asOf, text))
      history.reload()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido comprobar el saldo')
    }
  }

  const verdict = (r: Reconciliation) =>
    r.matches
      ? 'Cuadra con el banco.'
      : Number(r.difference.amount) > 0
        ? `Faltan ${formatMoney(r.difference)} en OpenFinance respecto al banco.`
        : `Sobran ${formatMoney({ ...r.difference, amount: r.difference.amount.replace('-', '') })} en OpenFinance respecto al banco.`

  return (
    <details className="card reconcile">
      <summary>Comprobar el saldo de «{account.name}» con el banco</summary>
      <form className="toolbar wrap" aria-label="Comprobar el saldo" onSubmit={(e) => void check(e)}>
        <label className="small">
          Día{' '}
          <input className="field" type="date" required max={today()} value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </label>
        <label className="small">
          Saldo según el banco{' '}
          <input
            className="field amount"
            inputMode="decimal"
            required
            value={balance}
            onChange={(e) => {
              setBalance(e.target.value)
              setError(null)
            }}
            {...invalid('reconcile-error', error)}
          />
        </label>
        <button className="btn small" type="submit">
          Comprobar
        </button>
      </form>
      <FieldError id="reconcile-error" message={error} />
      {last && (
        <p role="status" className={last.matches ? 'notice ok' : 'notice warn'}>
          {verdict(last)} OpenFinance tiene {formatMoney(last.computed_balance)} a {formatDate(last.as_of)}.
        </p>
      )}
      {history.error && <ErrorState message={history.error} onRetry={history.reload} />}
      {history.data && history.data.length > 0 && (
        <ul className="plain small" aria-label="Comprobaciones anteriores">
          {history.data.map((r) => (
            <li key={r.id}>
              {formatDate(r.as_of)} · banco {formatMoney(r.bank_balance)} · {r.matches ? 'cuadraba' : `diferencia ${formatMoney(r.difference, { signed: true })}`}
            </li>
          ))}
        </ul>
      )}
    </details>
  )
}
