import { useEffect, useState } from 'react'
import { ApiError, api, type Budgets, type SavingsOverview } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { centsToAmount, formatMoneyRounded, parseAmountInput, toCents } from '../../lib/format'

function roundUpTo10(cents: bigint): string {
  return centsToAmount(((cents + 999n) / 1000n) * 1000n)
}

function BudgetInput({
  categoryId,
  name,
  current,
  suggestion,
  onSaved,
}: {
  categoryId: string
  name: string
  current: string | null
  suggestion: { amount: string; currency: string } | null
  onSaved: () => void
}) {
  const { notify } = useHousehold()
  const [value, setValue] = useState(current ?? '')

  async function save(text: string) {
    if ((current ?? '') === text) return
    try {
      if (!text.trim()) {
        if (current) await api.deleteBudget(categoryId)
      } else {
        const amount = parseAmountInput(text)
        if (amount === null || toCents(amount) === 0n) {
          notify('Escribe un importe mayor que cero, por ejemplo 150')
          setValue(current ?? '')
          return
        }
        await api.setBudget(categoryId, amount)
      }
      onSaved()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido guardar')
      setValue(current ?? '')
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
      />
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

export function BudgetsPage() {
  const { categories, month } = useHousehold()
  const [version, setVersion] = useState(0)
  const [data, setData] = useState<{ budgets: Budgets; overview: SavingsOverview } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([api.budgets(month, controller.signal), api.savingsOverview(controller.signal)]).then(
      ([budgets, overview]) => setData({ budgets, overview }),
      (err: unknown) => {
        if (!controller.signal.aborted)
          setError(err instanceof ApiError ? err.message : 'No se han podido cargar los presupuestos')
      },
    )
    return () => controller.abort()
  }, [month, version])

  if (error) return <p className="error" role="alert">{error}</p>
  if (!data)
    return (
      <p className="muted" role="status">
        Cargando…
      </p>
    )
  const byCategory = new Map(data.budgets.items.map((b) => [b.category_id, b]))
  const averages = new Map(data.overview.averages.map((a) => [a.category_id, a.average]))
  const visible = categories.filter((c) => !c.hidden || byCategory.has(c.id))

  return (
    <section>
      <h1>Presupuestos</h1>
      <p className="lead">
        Un límite mensual por categoría. Os avisamos al llegar al 85 % y al pasaros. Como punto de partida podéis usar vuestra
        media de los últimos meses. <a href="#mes">Volver a Este mes</a>
      </p>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Categoría</th>
              <th className="num">Vuestra media</th>
              <th>Presupuesto mensual</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((c) => {
              const avg = averages.get(c.id)
              const avgCents = avg ? toCents(avg.amount) : 0n
              return (
                <tr key={`${c.id}-${byCategory.get(c.id)?.amount.amount ?? ''}`}>
                  <td>
                    {c.icon} {c.name}
                  </td>
                  <td className="num muted">{avg && avgCents > 0n ? `${formatMoneyRounded(avg)}/mes` : '—'}</td>
                  <td>
                    <BudgetInput
                      categoryId={c.id}
                      name={c.name}
                      current={byCategory.get(c.id)?.amount.amount ?? null}
                      suggestion={avg && avgCents > 0n ? { amount: roundUpTo10(avgCents), currency: avg.currency } : null}
                      onSaved={() => setVersion((v) => v + 1)}
                    />
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
