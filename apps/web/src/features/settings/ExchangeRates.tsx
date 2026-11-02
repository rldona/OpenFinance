import { type FormEvent, useState } from 'react'
import { ApiError, api, type ExchangeRate } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { FieldError } from '../../components/FieldError'
import { Loading } from '../../components/LoadState'
import { formatDate } from '../../lib/format'
import { invalid } from '../../lib/invalid'
import { notifyUndoable } from '../../lib/undo'
import { useLoad } from '../../lib/useLoad'

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Tipos de cambio manuales para las cuentas en otra moneda (ADR-0019, OF-1008). */
export function ExchangeRates() {
  const { me, notify } = useHousehold()
  const rates = useLoad<ExchangeRate[]>('rates', (s) => api.exchangeRates(s))
  const missing = useLoad('rates-missing', (s) => api.missingRates(s))
  const [currency, setCurrency] = useState('')
  const [on, setOn] = useState(today)
  const [rate, setRate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const reference = me.household.currency

  function reload() {
    rates.reload()
    missing.reload()
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    try {
      const r = await api.setExchangeRate(currency.trim().toUpperCase(), on, rate)
      setError(null)
      setRate('')
      notifyUndoable(notify, me, `Tipo de cambio ${r.rate.currency} guardado`, r.operation_id, reload)
      reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido guardar el tipo de cambio')
    }
  }

  async function remove(r: ExchangeRate) {
    try {
      const res = await api.deleteExchangeRate(r.currency, r.on)
      notifyUndoable(notify, me, `Tipo de cambio ${r.currency} borrado`, res.operation_id, reload)
      reload()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido borrar')
    }
  }

  return (
    <div className="card stack">
      <h2>Tipos de cambio</h2>
      <p className="small muted">
        Los informes se calculan en {reference}. Para las cuentas en otra moneda, apunta cuántos {reference} vale 1 unidad ese día; sirve
        desde esa fecha hasta el siguiente tipo. OpenFinance no consulta ninguna cotización en línea.
      </p>
      {missing.data && missing.data.length > 0 && (
        <p className="notice warn" role="status">
          {missing.data.map((m) => `${m.count} ${m.count === 1 ? 'movimiento' : 'movimientos'} en ${m.currency} sin tipo de cambio (desde ${formatDate(m.first)})`).join(' · ')}
          : no entran en los informes hasta que lo añadas.
        </p>
      )}
      {rates.error && <p className="small muted">No se han podido cargar los tipos de cambio.</p>}
      {!rates.data && !rates.error && <Loading />}
      {rates.data && rates.data.length > 0 && (
        <ul className="plain" aria-label="Tipos de cambio">
          {rates.data.map((r) => (
            <li key={`${r.currency}|${r.on}`} className="toolbar">
              <span>
                {formatDate(r.on)} · 1 {r.currency} = {Number(r.rate)} {reference}
              </span>
              <button className="btn small" type="button" aria-label={`Borrar el tipo de ${r.currency} del ${r.on}`} onClick={() => void remove(r)}>
                Borrar
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="toolbar wrap" aria-label="Añadir un tipo de cambio" onSubmit={(e) => void save(e)}>
        <label className="small">
          Moneda{' '}
          <input className="field amount" required maxLength={3} placeholder="USD" value={currency} onChange={(e) => setCurrency(e.target.value)} />
        </label>
        <label className="small">
          Día <input className="field" type="date" required max={today()} value={on} onChange={(e) => setOn(e.target.value)} />
        </label>
        <label className="small">
          Vale en {reference}{' '}
          <input
            className="field amount"
            inputMode="decimal"
            required
            placeholder="0,92"
            value={rate}
            onChange={(e) => {
              setRate(e.target.value)
              setError(null)
            }}
            {...invalid('rate-error', error)}
          />
        </label>
        <button className="btn small" type="submit">
          Guardar tipo
        </button>
      </form>
      <FieldError id="rate-error" message={error} />
    </div>
  )
}
