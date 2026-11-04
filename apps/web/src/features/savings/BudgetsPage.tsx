import { useState } from 'react'
import { ApiError, api, type Budget, type Budgets, type SavingsOverview } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { FieldError } from '../../components/FieldError'
import { invalid } from '../../lib/invalid'
import { ErrorState, Loading } from '../../components/LoadState'
import { useLoad } from '../../lib/useLoad'
import { centsToAmount, formatMoney, formatMoneyRounded, monthLabel, parseAmountInput, toCents } from '../../lib/format'

function roundUpTo10(cents: bigint): string {
  return centsToAmount(((cents + 999n) / 1000n) * 1000n)
}

function BudgetInput({
  categoryId,
  name,
  current,
  mode,
  suggestion,
  onSaved,
}: {
  categoryId: string
  name: string
  current: string | null
  mode: Budget['mode']
  suggestion: { amount: string; currency: string } | null
  onSaved: () => void
}) {
  const [value, setValue] = useState(current ?? '')
  // El error se ve junto al campo y el texto se conserva para poder corregirlo.
  const [error, setError] = useState<string | null>(null)
  const errorId = `budget-error-${categoryId}`

  async function save(text: string) {
    if ((current ?? '') === text) {
      setError(null)
      return
    }
    setError(null)
    try {
      if (!text.trim()) {
        if (current) await api.deleteBudget(categoryId)
      } else {
        const amount = parseAmountInput(text)
        if (amount === null || toCents(amount) === 0n) {
          setError('Escribe un importe mayor que cero, por ejemplo 150')
          return
        }
        await api.setBudget(categoryId, amount, mode)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido guardar')
    }
  }

  return (
    <span className="toolbar inline">
      <input
        className="field amount"
        aria-label={`Presupuesto de ${name}`}
        placeholder="Sin límite"
        inputMode="decimal"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => void save(value.trim())}
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
        {...invalid(errorId, error)}
      />
      <FieldError id={errorId} message={error} />
      {suggestion && !current && (
        <button
          className="btn small"
          type="button"
          onClick={() => {
            setValue(suggestion.amount)
            void save(suggestion.amount)
          }}
        >
          Usar {formatMoneyRounded(suggestion)}
        </button>
      )}
    </span>
  )
}

/** Un importe distinto solo para el mes elegido (vacaciones, un gasto grande…). */
function MonthAmount({ item, name, month, onSaved }: { item: Budget; name: string; month: string; onSaved: () => void }) {
  const current = item.has_override ? item.amount.amount : ''
  const [value, setValue] = useState(current)
  const [error, setError] = useState<string | null>(null)
  const errorId = `budget-month-error-${item.category_id}`

  async function save(text: string) {
    if (current === text) return setError(null)
    setError(null)
    try {
      if (!text) {
        await api.clearBudgetMonth(item.category_id, month)
      } else {
        const amount = parseAmountInput(text)
        if (amount === null || toCents(amount) === 0n) return setError('Escribe un importe mayor que cero')
        await api.setBudgetMonth(item.category_id, month, amount)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido guardar')
    }
  }

  return (
    <span className="toolbar inline">
      <input
        className="field amount"
        aria-label={`Importe de ${name} solo en ${monthLabel(month)}`}
        placeholder="el de siempre"
        inputMode="decimal"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => void save(value.trim())}
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
        {...invalid(errorId, error)}
      />
      <FieldError id={errorId} message={error} />
    </span>
  )
}

export function BudgetsPage() {
  const { categories, month } = useHousehold()
  const load = useLoad<{ budgets: Budgets; overview: SavingsOverview }>(
    month,
    async (s) => {
      const [budgets, overview] = await Promise.all([api.budgets(month, s), api.savingsOverview(s)])
      return { budgets, overview }
    },
    'No se han podido cargar los presupuestos',
  )
  const [modeError, setModeError] = useState<string | null>(null)
  if (load.error) return <ErrorState message={load.error} onRetry={load.reload} />
  const data = load.data
  if (!data) return <Loading />
  const byCategory = new Map(data.budgets.items.map((b) => [b.category_id, b]))
  const averages = new Map(data.overview.averages.map((a) => [a.category_id, a.average]))
  async function changeMode(item: Budget, mode: Budget['mode']) {
    try {
      await api.setBudget(item.category_id, item.base_amount.amount, mode)
      load.reload()
    } catch (err) {
      setModeError(err instanceof ApiError ? err.message : 'No se ha podido cambiar el tipo')
    }
  }
  const visible = categories.filter((c) => !c.hidden || byCategory.has(c.id))

  return (
    <section>
      <h1>Presupuestos</h1>
      <p className="lead">
        Un importe mensual por categoría. Os avisamos al llegar al 85 % y al pasaros. Como punto de partida podéis usar vuestra
        media de los últimos meses. <a href="#mes">Volver a Este mes</a>
      </p>
      <p className="small muted">
        <strong>Límite</strong>: un tope por mes; lo que no gastáis se pierde. <strong>Sobre</strong>: lo que sobra (o falta) pasa al mes
        siguiente. Si un mes necesita otro importe, escribidlo en «Solo este mes».
      </p>
      {modeError && <p className="error small" role="alert">{modeError}</p>}
      <div className="card">
        <table role="table" className="rows budget-table">
          <thead role="rowgroup">
            <tr role="row">
              <th role="columnheader">Categoría</th>
              <th role="columnheader" className="num">Vuestra media</th>
              <th role="columnheader">Presupuesto mensual</th>
              <th role="columnheader">Tipo</th>
              <th role="columnheader">Solo en {monthLabel(month)}</th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {visible.map((c) => {
              const avg = averages.get(c.id)
              const avgCents = avg ? toCents(avg.amount) : 0n
              const item = byCategory.get(c.id)
              return (
                <tr role="row" key={`${c.id}-${item?.base_amount.amount ?? ''}-${item?.mode ?? ''}-${item?.has_override ?? ''}`}>
                  <td role="cell">
                    {c.icon} {c.name}
                  </td>
                  <td role="cell" className="num muted">{avg && avgCents > 0n ? `${formatMoneyRounded(avg)}/mes` : '—'}</td>
                  <td role="cell">
                    <BudgetInput
                      categoryId={c.id}
                      name={c.name}
                      current={item?.base_amount.amount ?? null}
                      mode={item?.mode ?? 'limit'}
                      suggestion={avg && avgCents > 0n ? { amount: roundUpTo10(avgCents), currency: avg.currency } : null}
                      onSaved={load.reload}
                    />
                    {item?.mode === 'envelope' && (
                      <div className="small muted">
                        Sobre desde {monthLabel(item.started ?? month)} · arrastra {formatMoney(item.carried)} · disponible {formatMoney(item.available)}
                      </div>
                    )}
                  </td>
                  <td role="cell">
                    {item && (
                      <select
                        className="field"
                        aria-label={`Tipo de presupuesto de ${c.name}`}
                        value={item.mode}
                        onChange={(e) => void changeMode(item, e.target.value as Budget['mode'])}
                      >
                        <option value="limit">Límite</option>
                        <option value="envelope">Sobre</option>
                      </select>
                    )}
                  </td>
                  <td role="cell">
                    {item && <MonthAmount item={item} name={c.name} month={month} onSaved={load.reload} />}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {data.budgets.total_amount && (
          <p className="small muted">Total presupuestado: {formatMoneyRounded(data.budgets.total_amount)} al mes</p>
        )}
      </div>
    </section>
  )
}
