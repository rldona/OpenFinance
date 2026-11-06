import { api, type CategoryDetail, type MonthOverview, type Transaction } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { BarChart, Donut, geometry } from '../../components/charts'
import { ErrorState, Loading } from '../../components/LoadState'
import { useLoad } from '../../lib/useLoad'
import { formatDate, formatMoney, formatMoneyRounded, monthLabel, shortMonth, toCents } from '../../lib/format'
import { Delta, MonthPicker, NoData, ViewPicker } from './common'
import { sharePercent } from './meta'
import { useCategoryMeta } from './meta'

function CategoryPanel({ categoryId, month }: { categoryId: string | null; month: string }) {
  const { me, view } = useHousehold()
  const meta = useCategoryMeta()
  const m = meta(categoryId)
  const detail = useLoad<CategoryDetail>(`${view}|${categoryId}|${month}`, (s) =>
    api.insightsCategory(month, categoryId, view, s),
  )
  const accounts = view === 'mine' ? { mine_only: true } : { shared_only: true }
  const txns = useLoad<Transaction[]>(`tx|${view}|${categoryId}|${month}`, (s) =>
    api.transactions(
      categoryId ? { month, category_id: categoryId, ...accounts } : { month, uncategorized: true, ...accounts },
      s,
    ),
  )
  if (detail.error) return <ErrorState message={detail.error} onRetry={detail.reload} />
  if (!detail.data) return <Loading />
  const d = detail.data
  const now = d.months[d.months.length - 1]
  const maxMerchant = d.merchants.reduce((mx, x) => (toCents(x.amount.amount) > mx ? toCents(x.amount.amount) : mx), 1n)

  return (
    <div className="grid stack">
      <div className="card">
        <h2>
          {m.icon} {m.name} · últimos 12 meses
        </h2>
        <BarChart
          label={`${m.name}: ${formatMoney(now.amount)} en ${monthLabel(month)}`}
          data={d.months.map((x) => ({
            label: shortMonth(x.month),
            value: geometry(toCents(x.amount.amount)),
            valueText: x.has_data ? formatMoney(x.amount) : 'sin datos',
            color: m.color,
          }))}
          reference={d.average ? { value: geometry(toCents(d.average.amount)), label: `Media ${formatMoneyRounded(d.average)}` } : undefined}
          highlight={d.months.length - 1}
        />
        <p className="small muted">
          Este mes: <strong>{formatMoney(now.amount)}</strong>{' '}
          <Delta now={now.amount} before={d.average} suffix="que la media" />
        </p>
      </div>
      <div className="card">
        <h2>Dónde (últimos 3 meses)</h2>
        {d.merchants.length === 0 && <p className="muted">Sin datos.</p>}
        {d.merchants.map((x) => (
          <div key={x.merchant} className="merchant">
            <div className="name">
              <span>
                {x.merchant} <span className="small muted">· {x.count}</span>
              </span>
              <span className="num">{formatMoney(x.amount)}</span>
            </div>
            <div className="track">
              <i
                style={{
                  width: `${Number((toCents(x.amount.amount) * 100n) / maxMerchant)}%`,
                  background: m.color,
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <div className="card">
        <h2>Movimientos de {monthLabel(month)}</h2>
        {txns.error && <ErrorState message={txns.error} onRetry={txns.reload} />}
        {!txns.data && !txns.error && <Loading />}
        {txns.data && txns.data.length === 0 && <p className="muted">No hay movimientos.</p>}
        {txns.data && txns.data.length > 0 && (
          <table>
            <tbody>
              {txns.data.map((t) => (
                <tr key={t.id}>
                  <td className="muted small nowrap">{formatDate(t.booked_at)}</td>
                  <td>
                    {t.merchant || t.description}
                    <div className="small muted">{t.description}</div>
                  </td>
                  <td className="num">{formatMoney(t.amount, { signed: true })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="small muted">
          <a href="#movimientos">Cambiar categorías en Movimientos</a> ·{' '}
          {view === 'mine' ? 'Tus cuentas personales' : me.household.name}
        </p>
      </div>
    </div>
  )
}

export function SpendingPage() {
  const { month, view, focusCategory, setFocusCategory } = useHousehold()
  const meta = useCategoryMeta()
  const overview = useLoad<MonthOverview>(`${view}|${month}`, (s) => api.insightsMonth(month, view, s))
  if (overview.error) return <ErrorState message={overview.error} onRetry={overview.reload} />
  if (!overview.data) return <Loading />
  const o = overview.data
  if (!o.has_data) return <NoData title="¿En qué gastamos?" />

  const positive = o.categories.filter((c) => toCents(c.amount.amount) > 0n)
  const base = positive.reduce((s, c) => s + toCents(c.amount.amount), 0n)
  const selected =
    focusCategory !== undefined && o.categories.some((c) => c.category_id === focusCategory)
      ? focusCategory
      : (positive[0]?.category_id ?? null)

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>¿En qué gastamos?</h1>
          <p className="lead">
            {view === 'mine' ? 'Tus cuentas personales. ' : ''}Elige una categoría para ver su detalle.
          </p>
        </div>
        <div className="page-tools">
          <ViewPicker />
          <MonthPicker />
        </div>
      </div>
      <div className="grid g12">
        <div className="card">
          <Donut
            label={`Gasto de ${monthLabel(month)} por categoría: ${formatMoney(o.spent)}`}
            title={formatMoneyRounded(o.spent)}
            subtitle={monthLabel(month)}
            active={selected ?? 'none'}
            segments={positive.map((c) => {
              const m = meta(c.category_id)
              return {
                id: m.id ?? 'none',
                label: m.name,
                value: geometry(toCents(c.amount.amount)),
                valueText: formatMoney(c.amount),
                color: m.color,
              }
            })}
          />
          <ul className="catlist plain" aria-label="Categorías">
            {o.categories.map((c) => {
              const m = meta(c.category_id)
              const amount = toCents(c.amount.amount)
              const pct = sharePercent(amount, base)
              const active = c.category_id === selected
              return (
                <li key={m.id ?? 'none'}>
                <button
                  type="button"
                  className={`cat ${active ? 'active' : ''}`}
                  aria-pressed={active}
                  onClick={() => setFocusCategory(c.category_id)}
                >
                  <span className="ic">{m.icon}</span>
                  <span>
                    <span className="name">
                      <span>{m.name}</span>
                      <strong className="num">{formatMoney(c.amount)}</strong>
                    </span>
                    <span className="track">
                      <i style={{ width: `${Math.max(pct > 0 ? 2 : 0, pct)}%`, background: m.color }} />
                    </span>
                  </span>
                  <span className="small muted num">{pct} %</span>
                </button>
                </li>
              )
            })}
          </ul>
        </div>
        <CategoryPanel key={`${view}|${selected}|${month}`} categoryId={selected} month={month} />
      </div>
    </section>
  )
}
