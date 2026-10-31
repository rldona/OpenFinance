import { useEffect, useState } from 'react'
import { ApiError, api, type MonthOverview } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { Donut, LineChart, geometry } from '../../components/charts'
import { centsToAmount, formatMoney, formatMoneyRounded, monthLabel, shortMonth, toCents } from '../../lib/format'
import { Delta, MonthPicker, NoData } from './common'
import { sharePercent, useCategoryMeta } from './meta'

const MIN_CHANGE_CENTS = 2000n
const abs = (x: bigint) => (x < 0n ? -x : x)

export function MonthPage() {
  const { me, month, uncategorized, setFocusCategory } = useHousehold()
  const meta = useCategoryMeta()
  const [result, setResult] = useState<{ month: string; data?: MonthOverview; error?: string } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    api.insightsMonth(month, controller.signal).then(
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
  const o = current.data
  if (!o.has_data) return <NoData title="Este mes" />

  const money = (amount: string) => ({ amount, currency: o.currency })
  const positive = o.categories.filter((c) => toCents(c.amount.amount) > 0n)
  const top = positive[0]
  const topMeta = top ? meta(top.category_id) : null
  const memberName = (id: string) => me.members.find((m) => m.id === id)?.display_name ?? '—'

  const changes = o.categories
    .filter((c) => {
      const now = toCents(c.amount.amount)
      const avg = c.average ? toCents(c.average.amount) : 0n
      return now >= MIN_CHANGE_CENTS || avg >= MIN_CHANGE_CENTS
    })
    .map((c) => ({ ...c, diff: toCents(c.amount.amount) - (c.average ? toCents(c.average.amount) : 0n) }))
    .sort((a, b) => (abs(b.diff) === abs(a.diff) ? 0 : abs(b.diff) > abs(a.diff) ? 1 : -1))
    .slice(0, 4)

  const days = Math.max(o.daily.length, o.previous_daily.length)
  const pad = (xs: string[]) => [...xs.map((x) => geometry(toCents(x))), ...Array<null>(days - xs.length).fill(null)]
  const base = positive.reduce((s, c) => s + toCents(c.amount.amount), 0n)
  const share = (amount: string) => sharePercent(toCents(amount), base)

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Este mes</h1>
          <p className="lead">
            Cuenta conjunta y huchas · {monthLabel(month)}
            {o.is_partial && ` · mes en curso, hasta el día ${o.days_elapsed}`}
          </p>
        </div>
        <MonthPicker />
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
          <div className="label">Habéis gastado en {shortMonth(month)}</div>
          <div className="value">{formatMoneyRounded(o.spent)}</div>
          <div className="delta">
            {o.is_partial ? (
              <Delta now={o.spent} before={o.previous_spent_to_date} suffix="que a estas alturas del mes anterior" />
            ) : (
              <Delta now={o.spent} before={o.previous_spent} suffix="que el mes anterior" />
            )}
          </div>
          {o.average_spent && (
            <div className="small muted">
              Vuestra media: {formatMoneyRounded(o.average_spent)}/mes{o.is_partial ? ' (meses completos)' : ''}
            </div>
          )}
        </div>
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
                <a
                  className="cat"
                  href="#gastos"
                  onClick={() => setFocusCategory(c.category_id)}
                >
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

          <h2 className="spaced">Lo que más ha cambiado frente a vuestra media</h2>
          {changes.length === 0 && <p className="muted small">Aún no hay meses anteriores con los que comparar.</p>}
          <ul className="catlist plain" aria-label="Cambios frente a la media">
            {changes.map((c) => {
              const m = meta(c.category_id)
              const up = c.diff > 0n
              return (
                <li key={m.id ?? 'none'}>
                <a className="cat" href="#gastos" onClick={() => setFocusCategory(c.category_id)}>
                  <span className="ic">{m.icon}</span>
                  <span>
                    <span className="name">
                      <span>{m.name}</span>
                      <span className={up ? 'neg' : 'pos'}>
                        {up ? '+' : '−'}
                        {formatMoneyRounded(money(centsToAmount(abs(c.diff))))}
                      </span>
                    </span>
                    <span className="small muted">
                      {formatMoneyRounded(c.amount)} este mes · media {c.average ? formatMoneyRounded(c.average) : '—'}
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
    </section>
  )
}
