import { useState } from 'react'
import { ApiError, api, type Budgets, type SavingsOverview } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { useLoad } from '../../lib/useLoad'
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
  const load = useLoad<{ budgets: Budgets; overview: SavingsOverview }>(
    month,
    async (s) => {
      const [budgets, overview] = await Promise.all([api.budgets(month, s), api.savingsOverview(s)])
      return { budgets, overview }
    },
    'No se han podido cargar los presupuestos',
  )
  if (load.error) return <ErrorState message={load.error} onRetry={load.reload} />
  const data = load.data
  if (!data) return <Loading />
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
        <table role="table" className="rows budget-table">
          <thead role="rowgroup">
            <tr role="row">
              <th role="columnheader">Categoría</th>
              <th role="columnheader" className="num">Vuestra media</th>
              <th role="columnheader">Presupuesto mensual</th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {visible.map((c) => {
              const avg = averages.get(c.id)
              const avgCents = avg ? toCents(avg.amount) : 0n
              return (
                <tr role="row" key={`${c.id}-${byCategory.get(c.id)?.amount.amount ?? ''}`}>
                  <td role="cell">
                    {c.icon} {c.name}
                  </td>
                  <td role="cell" className="num muted">{avg && avgCents > 0n ? `${formatMoneyRounded(avg)}/mes` : '—'}</td>
                  <td role="cell">
                    <BudgetInput
                      categoryId={c.id}
                      name={c.name}
                      current={byCategory.get(c.id)?.amount.amount ?? null}
                      suggestion={avg && avgCents > 0n ? { amount: roundUpTo10(avgCents), currency: avg.currency } : null}
                      onSaved={load.reload}
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
