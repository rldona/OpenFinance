import { useEffect, useState } from 'react'
import { api, type Budgets, type MonthOverview } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { Donut, LineChart, geometry } from '../../components/charts'
import { ErrorState, Loading } from '../../components/LoadState'
import { useLoad } from '../../lib/useLoad'
import { centsToAmount, currentMonth, formatMoney, formatMoneyRounded, monthLabel, shortMonth, toCents } from '../../lib/format'
import { routeHref } from '../../app/router'
import { AlertsCard } from './AlertsCard'
import { AllowanceCard } from './AllowanceCard'
import { Delta, MonthPicker, NoData, ViewPicker } from './common'
import { sharePercent, useCategoryMeta } from './meta'

const abs = (x: bigint) => (x < 0n ? -x : x)

/** El detalle de una categoría va en la URL (`cat=none` es «sin categoría»), no en un estado oculto. */
const categoryHref = (id: string | null) => routeHref('gastos', { cat: id ?? 'none' })

export function MonthPage() {
  const { me, month, view, uncategorized } = useHousehold()
  const meta = useCategoryMeta()
  const [budgets, setBudgets] = useState<Budgets | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    // Los presupuestos son un complemento: si fallan, la pantalla sigue funcionando sin ellos.
    api.budgets(month, controller.signal).then(setBudgets, () => undefined)
    return () => controller.abort()
  }, [month])

  const overview = useLoad<MonthOverview>(`${view}|${month}`, (s) => api.insightsMonth(month, view, s))

  const mine = view === 'mine'
  if (overview.error) return <ErrorState message={overview.error} onRetry={overview.reload} />
  if (!overview.data) return <Loading />
  const o = overview.data
  if (!o.has_data) return <NoData title="Este mes" />

  const money = (amount: string) => ({ amount, currency: o.currency })
  const positive = o.categories.filter((c) => toCents(c.amount.amount) > 0n)
  const top = positive[0]
  const topMeta = top ? meta(top.category_id) : null
  const memberName = (id: string) => me.members.find((m) => m.id === id)?.display_name ?? '—'


  const days = Math.max(o.daily.length, o.previous_daily.length)
  const pad = (xs: string[]) => [...xs.map((x) => geometry(toCents(x))), ...Array<null>(days - xs.length).fill(null)]
  const currentBudgets = budgets?.month === month ? budgets : null
  // La línea de presupuesto total solo tiene sentido si cubre todo lo que se gasta.
  const budgeted = new Set(currentBudgets?.items.map((b) => b.category_id) ?? [])
  const budgetCoversSpending =
    !!currentBudgets?.total_amount &&
    o.categories.every((c) => toCents(c.amount.amount) <= 0n || (c.category_id !== null && budgeted.has(c.category_id)))
  const base = positive.reduce((s, c) => s + toCents(c.amount.amount), 0n)
  const share = (amount: string) => sharePercent(toCents(amount), base)

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Este mes</h1>
          <p className="lead">
            {mine ? 'Tus cuentas personales · solo las ves tú' : 'Cuenta conjunta y huchas'} · {monthLabel(month)}
            {o.is_partial && ` · mes en curso, hasta el día ${o.days_elapsed}`}
          </p>
        </div>
        <div className="page-tools">
          <ViewPicker />
          <MonthPicker />
        </div>
      </div>

      {uncategorized > 0 && (
        <div className="notice warn row">
          <span>
            🏷️ <strong>{uncategorized === 1 ? '1 gasto' : `${uncategorized} gastos`} sin categoría.</strong> Clasificarlos
            hará que estos gráficos sean fiables.
          </span>
          <a className="btn" href="#movimientos">
            Clasificar
          </a>
        </div>
      )}

      <div className="grid g3">
        <div className="card hero kpi">
          <div className="label">
            {mine ? 'Has gastado' : 'Habéis gastado'} en {shortMonth(month)}
          </div>
          <div className="value">{formatMoneyRounded(o.spent)}</div>
          <div className="delta">
            {o.is_partial ? (
              <Delta now={o.spent} before={o.previous_spent_to_date} suffix="que a estas alturas del mes anterior" />
            ) : (
              <Delta now={o.spent} before={o.previous_spent} suffix="que el mes anterior" />
            )}
          </div>
          {o.is_partial && o.forecast && (
            <div className="small">
              Al ritmo actual {mine ? 'cerrarías' : 'cerraríais'} el mes en torno a <strong>{formatMoneyRounded(o.forecast)}</strong>
              {o.pending_charges.some((p) => !p.late) && ' (con las cuotas que faltan)'}.
            </div>
          )}
          {o.average_spent && (
            <div className="small muted">
              {mine ? 'Tu media' : 'Vuestra media'}: {formatMoneyRounded(o.average_spent)}/mes{o.is_partial ? ' (meses completos)' : ''}
            </div>
          )}
        </div>
        {mine ? (
          <div className="card kpi">
            <div className="label">Has aportado a la conjunta</div>
            <div className="value">{formatMoneyRounded(o.contributed)}</div>
            <div className="small muted">
              No cuenta como gasto tuyo · ingresos {formatMoneyRounded(o.income)}
            </div>
          </div>
        ) : (
          <div className="card kpi">
            <div className="label">Habéis ahorrado</div>
            <div className={`value ${o.saved.amount.startsWith('-') ? 'neg' : 'pos'}`}>{formatMoneyRounded(o.saved)}</div>
            {o.saving_rate !== null && (
              <span className={`pill ${o.saving_rate >= 20 ? 'down' : o.saving_rate >= 0 ? 'neutral' : 'up'}`}>
                {o.saving_rate} % de lo que entra
              </span>
            )}
            <div className="small muted">
              Entró {formatMoneyRounded(o.inflow)}
              {o.contributions.length > 0 &&
                ` · ${o.contributions.map((c) => `${memberName(c.member_id)} ${formatMoneyRounded(c.amount)}`).join(', ')}`}
            </div>
          </div>
        )}
        <div className="card kpi">
          <div className="label">Donde más se va</div>
          <div className="value">{top && topMeta ? `${topMeta.icon} ${formatMoneyRounded(top.amount)}` : '—'}</div>
          {top && topMeta && (
            <div className="small muted">
              {topMeta.name} · {share(top.amount.amount)} % del gasto
            </div>
          )}
        </div>
      </div>

      {o.is_partial && o.pending_charges.length > 0 && (
        <div className="card spaced-card">
          <h2>Cargos que faltan este mes</h2>
          <ul className="plain pending" aria-label="Cargos pendientes">
            {o.pending_charges.map((p) => (
              <li key={p.merchant} className={p.late ? 'late' : undefined}>
                <span>{p.merchant}</span>
                <span className="small muted">
                  {p.late ? `solía llegar el día ${p.expected_day} y aún no ha llegado` : `suele llegar el día ${p.expected_day}`}
                </span>
                <strong className="num">{formatMoneyRounded(p.amount)}</strong>
              </li>
            ))}
          </ul>
          <p className="small muted">Las cuotas que aún no han llegado se suman a la previsión; las retrasadas, no.</p>
        </div>
      )}

      {month === currentMonth() && <AlertsCard />}

      {month === currentMonth() && <AllowanceCard />}

      <div className="grid g12">
        <div className="card">
          <h2>¿En qué se ha ido?</h2>
          <Donut
            label={`Gasto de ${monthLabel(month)} por categoría: ${formatMoney(o.spent)}`}
            title={formatMoneyRounded(o.spent)}
            subtitle={`${positive.length} categorías`}
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
          <ul className="catlist plain" aria-label="Categorías principales">
            {positive.slice(0, 5).map((c) => {
              const m = meta(c.category_id)
              return (
                <li key={m.id ?? 'none'}>
                <a className="cat" href={categoryHref(c.category_id)}>
                  <span className="ic">{m.icon}</span>
                  <span>
                    <span className="name">
                      <span>{m.name}</span>
                      <strong className="num">{formatMoney(c.amount)}</strong>
                    </span>
                    <span className="track">
                      <i style={{ width: `${Math.max(2, share(c.amount.amount))}%`, background: m.color }} />
                    </span>
                  </span>
                  <span className="small muted num">{share(c.amount.amount)} %</span>
                </a>
                </li>
              )
            })}
          </ul>
          <p>
            <a href="#gastos">Ver todas las categorías →</a>
          </p>
        </div>
        <div className="card">
          <h2>Ritmo de gasto del mes</h2>
          <LineChart
            label={`Gasto acumulado de ${monthLabel(month)} frente al mes anterior`}
            series={[
              ...(o.previous_daily.length
                ? [
                    {
                      id: 'prev',
                      label: 'Mes anterior',
                      points: pad(o.previous_daily),
                      color: '#94a3b8',
                      dashed: true,
                      summary: formatMoney(money(o.previous_daily[o.previous_daily.length - 1])),
                    },
                  ]
                : []),
              {
                id: 'now',
                label: 'Este mes',
                points: pad(o.daily),
                color: '#0f766e',
                area: true,
                summary: formatMoney(o.spent),
              },
            ]}
            reference={
              budgetCoversSpending && currentBudgets?.total_amount
                ? {
                    value: geometry(toCents(currentBudgets.total_amount.amount)),
                    label: `Presupuesto ${formatMoneyRounded(currentBudgets.total_amount)}`,
                  }
                : undefined
            }
            xLabels={[
              [0, '1'],
              [9, '10'],
              [19, '20'],
              [days - 1, String(days)],
            ]}
          />
          <div className="legend">
            <span>
              <i style={{ background: '#0f766e' }} />
              Este mes
            </span>
            {o.previous_daily.length > 0 && (
              <span>
                <i className="dash" style={{ borderColor: '#94a3b8' }} />
                Mes anterior
              </span>
            )}
          </div>

          <h2 className="spaced">Lo que más ha cambiado frente a {mine ? 'tu' : 'vuestra'} media</h2>
          {o.changes.length === 0 && <p className="muted small">Aún no hay meses anteriores con los que comparar.</p>}
          <ul className="catlist plain" aria-label="Cambios frente a la media">
            {o.changes.map((c) => {
              const m = meta(c.category_id)
              const diff = c.change ? toCents(c.change.amount) : 0n
              const up = diff > 0n
              return (
                <li key={m.id ?? 'none'}>
                <a className="cat" href={categoryHref(c.category_id)}>
                  <span className="ic">{m.icon}</span>
                  <span>
                    <span className="name">
                      <span>{m.name}</span>
                      <span className={up ? 'neg' : 'pos'}>
                        {up ? '+' : '−'}
                        {formatMoneyRounded(money(centsToAmount(abs(diff))))}
                      </span>
                    </span>
                    <span className="small muted">
                      {formatMoneyRounded(c.amount)} este mes ·{' '}
                      {o.is_partial ? `media hasta el día ${o.days_elapsed}` : 'media'}{' '}
                      {c.reference ? formatMoneyRounded(c.reference) : '—'}
                    </span>
                  </span>
                  <span />
                </a>
                </li>
              )
            })}
          </ul>
        </div>
      </div>

      {/* Los presupuestos son del hogar: en «Mío» no aplican. */}
      {!mine && (
        <div className="card spaced-card">
          <div className="page-head">
            <h2>Presupuestos del mes</h2>
            <a href="#presupuestos">{currentBudgets?.items.length ? 'Editar presupuestos' : 'Poner presupuestos'}</a>
          </div>
          {currentBudgets && currentBudgets.items.length === 0 && (
            <p className="muted small">
              Aún no tenéis presupuestos. Poned un límite mensual a las categorías que queráis vigilar.
            </p>
          )}
          <ul className="plain budgets">
            {currentBudgets?.items.map((b) => {
              const m = meta(b.category_id)
              return (
                <li key={b.category_id} className={`budget budget-${b.status}`}>
                  <span className="ic" aria-hidden="true">
                    {m.icon}
                  </span>
                  <span>
                    <span className="name">
                      <span>{m.name}</span>
                      <span className="small">
                        {formatMoneyRounded(b.spent)} de {formatMoneyRounded({ ...b.amount, amount: centsToAmount(toCents(b.amount.amount) + toCents(b.carried.amount)) })}
                      </span>
                    </span>
                    {b.mode === 'envelope' && (
                      <span className="small muted block">
                        Sobre: {toCents(b.carried.amount) < 0n ? 'arrastra un exceso de' : 'incluye'} {formatMoneyRounded({ ...b.carried, amount: b.carried.amount.replace(/^-/, '') })} del mes anterior
                      </span>
                    )}
                    {toCents(b.fixed.amount) > 0n && (
                      <span className="small muted block">{formatMoneyRounded(b.fixed)} son cuotas fijas</span>
                    )}
                    <span
                      className="track"
                      role="meter"
                      aria-label={`${m.name}: ${b.percent} % del presupuesto`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.min(b.percent, 100)}
                    >
                      <i style={{ width: `${Math.min(b.percent, 100)}%` }} />
                    </span>
                  </span>
                  <span className="small num">
                    {b.percent} %{b.status === 'over' ? ' · pasado' : b.status === 'warning' ? ' · cerca' : ''}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </section>
  )
}
