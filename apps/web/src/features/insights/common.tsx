import type { Money } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { currentMonth, monthLabel, percentChange, shiftMonth } from '../../lib/format'

export function MonthPicker({ disabled = false }: { disabled?: boolean }) {
  const { month, setMonth } = useHousehold()
  const isCurrent = month >= currentMonth()
  return (
    <div className="month-picker" role="group" aria-label="Mes">
      <button type="button" onClick={() => setMonth(shiftMonth(month, -1))} disabled={disabled} aria-label="Mes anterior">
        ‹
      </button>
      <strong aria-live="polite">{disabled ? 'Todos los meses' : monthLabel(month)}</strong>
      <button
        type="button"
        onClick={() => setMonth(shiftMonth(month, 1))}
        disabled={disabled || isCurrent}
        aria-label="Mes siguiente"
      >
        ›
      </button>
    </div>
  )
}

/** Variación frente a una referencia; `lowerIsBetter` para gastos. */
export function Delta({
  now,
  before,
  suffix,
  lowerIsBetter = true,
}: {
  now: Money
  before: Money | null | undefined
  suffix: string
  lowerIsBetter?: boolean
}) {
  const p = before ? percentChange(now, before) : null
  if (p === null) return null
  if (p === 0) return <span className="pill neutral">= {suffix}</span>
  const good = lowerIsBetter ? p < 0 : p > 0
  return (
    <span className={`pill ${good ? 'down' : 'up'}`}>
      {p > 0 ? '▲' : '▼'} {Math.abs(p)} % {suffix}
    </span>
  )
}

export function NoData({ title }: { title: string }) {
  return (
    <section>
      <div className="page-head">
        <h1>{title}</h1>
        <MonthPicker />
      </div>
      <div className="card empty">
        <p>No hay movimientos de la cuenta conjunta en este mes.</p>
        <a className="btn primary" href="#importar">
          Importar un extracto
        </a>
      </div>
    </section>
  )
}
