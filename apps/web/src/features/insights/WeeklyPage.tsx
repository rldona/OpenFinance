import { api } from '../../api/client'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate, formatMoney } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'
import { useCategoryMeta } from './meta'

/** Resumen de la última semana completa (ADR-0023, OF-1303). */
export function WeeklyPage() {
  const meta = useCategoryMeta()
  const { data, error, reload } = useLoad('weekly', (signal) => api.weeklySummary(signal), 'No se ha podido cargar el resumen')
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <Loading />

  const change = data.change_percent
  return (
    <div className="stack">
      <section className="card" aria-label="Gasto de la semana">
        <h2>
          Semana del {formatDate(data.start)} al {formatDate(data.end)}
        </h2>
        <p>
          <strong className="num big">{formatMoney(data.spent)}</strong> gastados
        </p>
        <p className="small muted">
          {change === null
            ? `La semana anterior fueron ${formatMoney(data.previous)}: no hay base para comparar.`
            : change === 0
              ? `Igual que la semana anterior (${formatMoney(data.previous)}).`
              : `${Math.abs(change)} % ${change > 0 ? 'más' : 'menos'} que la semana anterior (${formatMoney(data.previous)}).`}
        </p>
      </section>

      <section className="card" aria-label="Lo que más pesó">
        <h2>Lo que más pesó</h2>
        {data.top.length === 0 ? (
          <p className="muted">Sin gastos esa semana.</p>
        ) : (
          <ul className="plain">
            {data.top.map((c) => (
              <li key={c.category_id ?? 'none'}>
                {meta(c.category_id).icon} {meta(c.category_id).name} · <strong className="num">{formatMoney(c.amount)}</strong>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card" aria-label="Próximos 7 días">
        <h2>Próximos 7 días</h2>
        {data.upcoming.length === 0 ? (
          <p className="muted">
            No hay pagos programados. <a href="#pagos">Programar un pago</a>
          </p>
        ) : (
          <ul className="plain">
            {data.upcoming.map((u) => (
              <li key={`${u.name}-${u.due}`}>
                {formatDate(u.due)} · {u.name} · {formatMoney(u.amount)}
              </li>
            ))}
          </ul>
        )}
      </section>

      {data.open_alerts > 0 && (
        <p>
          Tienes {data.open_alerts === 1 ? '1 aviso abierto' : `${data.open_alerts} avisos abiertos`}. <a href="#mes">Verlos en Este mes</a>
        </p>
      )}
    </div>
  )
}
