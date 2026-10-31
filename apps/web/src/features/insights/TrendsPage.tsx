import { useEffect, useState } from 'react'
import { ApiError, api, type Trends } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { BarChart, StackedBars, geometry } from '../../components/charts'
import { centsToAmount, formatMoney, formatMoneyRounded, monthLabel, shortMonth, toCents } from '../../lib/format'
import { MonthPicker, NoData } from './common'
import { useCategoryMeta } from './meta'

const MAIN_CATEGORIES = 6
const REST_COLOR = '#cbd5e1'

export function TrendsPage() {
  const { month } = useHousehold()
  const meta = useCategoryMeta()
  const [result, setResult] = useState<{ month: string; data?: Trends; error?: string } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    api.insightsTrends(month, controller.signal).then(
      (data) => setResult({ month, data }),
      (err: unknown) => {
        if (!controller.signal.aborted)
          setResult({ month, error: err instanceof ApiError ? err.message : 'No se han podido cargar los datos' })
      },
    )
    return () => controller.abort()
  }, [month])

  const current = result?.month === month ? result : null
  if (current?.error) return <p className="error" role="alert">{current.error}</p>
  if (!current?.data)
    return (
      <p className="muted" role="status">
        Cargando…
      </p>
    )
  const t = current.data
  const withData = t.months.filter((m) => m.has_data)
  if (withData.length === 0) return <NoData title="Evolución" />

  const totals = new Map<string, bigint>()
  for (const m of t.months)
    for (const c of m.categories) {
      const key = c.category_id ?? 'none'
      totals.set(key, (totals.get(key) ?? 0n) + toCents(c.amount.amount))
    }
  const main = [...totals.entries()]
    .filter(([, v]) => v > 0n)
    .sort((a, b) => (b[1] > a[1] ? 1 : b[1] < a[1] ? -1 : 0))
    .slice(0, MAIN_CATEGORIES)
    .map(([k]) => k)

  const rows = t.months.map((m) => {
    const byId = new Map(m.categories.map((c) => [c.category_id ?? 'none', toCents(c.amount.amount)]))
    const rest = [...byId.entries()].filter(([k]) => !main.includes(k)).reduce((s, [, v]) => s + v, 0n)
    const parts = main.map((k) => {
      const info = meta(k === 'none' ? null : k)
      const v = byId.get(k) ?? 0n
      const valueText = formatMoney({ amount: centsToAmount(v), currency: m.spent.currency })
      return { id: k, label: info.name, value: geometry(v), valueText, color: info.color }
    })
    const restText = formatMoney({ amount: centsToAmount(rest), currency: m.spent.currency })
    parts.push({ id: 'rest', label: 'Resto', value: geometry(rest), valueText: restText, color: REST_COLOR })
    return { label: shortMonth(m.month), totalText: m.has_data ? formatMoneyRounded(m.spent) : '', parts }
  })

  const rate = t.saving_rate
  const averageSaved = t.average_saved

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Evolución</h1>
          <p className="lead">
            Los {withData.length === 12 ? '12' : withData.length} meses hasta {monthLabel(month)} de un vistazo.
          </p>
        </div>
        <MonthPicker />
      </div>
      <div className="grid g3">
        <div className="card hero kpi">
          <div className="label">Ahorrado en el periodo</div>
          <div className="value">{formatMoneyRounded(t.total_saved)}</div>
          {rate !== null && <div className="small muted">{rate} % de todo lo que entró</div>}
        </div>
        <div className="card kpi">
          <div className="label">Gasto medio al mes</div>
          <div className="value">{t.average_spent ? formatMoneyRounded(t.average_spent) : '—'}</div>
          <div className="small muted">{formatMoneyRounded(t.total_spent)} en total</div>
        </div>
        <div className="card kpi">
          <div className="label">Mejor y peor mes</div>
          {t.best && (
            <div className="value medium pos">
              {shortMonth(t.best.month)} {formatMoneyRounded(t.best.saved)}
            </div>
          )}
          {t.worst && (
            <div className="small">
              <span className={t.worst.saved.amount.startsWith('-') ? 'neg' : ''}>
                {shortMonth(t.worst.month)} {formatMoneyRounded(t.worst.saved)}
              </span>{' '}
              <span className="muted">
                {t.worst.saved.amount.startsWith('-') ? '(gastasteis más de lo que entró)' : '(el que menos)'}
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h2>Gasto mensual por categoría</h2>
        <StackedBars label="Gasto mensual por categoría en los últimos 12 meses" rows={rows} />
        <div className="legend">
          {main.map((k) => {
            const info = meta(k === 'none' ? null : k)
            return (
              <span key={k}>
                <i style={{ background: info.color }} />
                {info.name}
              </span>
            )
          })}
          <span>
            <i style={{ background: REST_COLOR }} />
            Resto
          </span>
        </div>
      </div>

      <div className="card spaced-card">
        <h2>Ahorro de cada mes</h2>
        <BarChart
          label={`Ahorro mensual: ${formatMoney(t.total_saved)} en el periodo`}
          data={t.months.map((m) => ({
            label: shortMonth(m.month),
            value: geometry(toCents(m.saved.amount)),
            valueText: m.has_data ? formatMoney(m.saved) : 'sin datos',
            color: '#16a34a',
          }))}
          reference={
            averageSaved
              ? { value: geometry(toCents(averageSaved.amount)), label: `Media ${formatMoneyRounded(averageSaved)}` }
              : undefined
          }
        />
        <p className="small muted">
          Ahorro = lo que entra en la cuenta conjunta − lo que se gasta. Lo que pasa a la hucha cuenta como ahorro, no como
          gasto.
        </p>
      </div>
    </section>
  )
}
