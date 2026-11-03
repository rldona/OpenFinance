import { api, type NetWorth } from '../../api/client'
import { LineChart } from '../../components/charts'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate, formatMoney } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

const TYPE_LABEL: Record<NetWorth['by_type'][number]['type'], string> = {
  bank: 'Cuentas bancarias',
  cash: 'Efectivo',
  card: 'Tarjetas',
  loan: 'Préstamos',
  investment: 'Inversiones',
}

/** Patrimonio neto de quien mira: activos menos deudas, hoy y a fin de cada mes (ADR-0025, OF-1501). */
export function NetWorthPage() {
  const { data, error, reload } = useLoad('net-worth', (signal) => api.netWorth(signal), 'No se ha podido cargar el patrimonio')
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <Loading />

  const values = data.history.map((p) => Number(p.net.amount))
  // El gráfico no dibuja por debajo de cero: si alguna vez fue negativo, queda la tabla.
  const canChart = values.every((v) => v >= 0)

  return (
    <div className="stack">
      <section className="card" aria-label="Patrimonio neto">
        <h2>Patrimonio neto</h2>
        <p>
          <strong className="num big">{formatMoney(data.today.net)}</strong>
        </p>
        <p className="small muted">
          {formatMoney(data.today.assets)} de activos menos {formatMoney(data.today.debts)} de deudas, a {formatDate(data.today.on)}.
          Solo cuentas que ves tú.
        </p>
        {data.missing_rates.length > 0 && (
          <p className="small warn">
            No entran las cuentas en {data.missing_rates.join(', ')}: falta su tipo de cambio en Ajustes.
          </p>
        )}
      </section>

      <section className="card" aria-label="Evolución del patrimonio">
        <h2>Evolución</h2>
        {canChart && (
          <LineChart
            label="Patrimonio neto a fin de cada mes"
            series={[
              {
                id: 'net',
                label: 'Patrimonio neto',
                points: values,
                color: 'var(--accent, #2563eb)',
                area: true,
                summary: `${formatMoney(data.history[0].net)} → ${formatMoney(data.today.net)}`,
              },
            ]}
          />
        )}
        <table className="table">
          <caption className="sr-only">Patrimonio a fin de cada mes</caption>
          <thead>
            <tr>
              <th scope="col">Fecha</th>
              <th scope="col">Activos</th>
              <th scope="col">Deudas</th>
              <th scope="col">Neto</th>
            </tr>
          </thead>
          <tbody>
            {[...data.history].reverse().map((p) => (
              <tr key={p.on}>
                <th scope="row">{formatDate(p.on)}</th>
                <td className="num">{formatMoney(p.assets)}</td>
                <td className="num">{formatMoney(p.debts)}</td>
                <td className="num">{formatMoney(p.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card" aria-label="Por tipo de cuenta">
        <h2>Por tipo</h2>
        <ul className="plain">
          {data.by_type.map((t) => (
            <li key={t.type}>
              {TYPE_LABEL[t.type]} · <strong className="num">{formatMoney(t.net)}</strong>
            </li>
          ))}
        </ul>
      </section>

      <section className="card" aria-label="Cuentas del patrimonio">
        <h2>Cuentas</h2>
        <ul className="plain">
          {data.accounts.map((a) => (
            <li key={a.account_id}>
              {a.name} · <strong className="num">{formatMoney(a.balance)}</strong>
              {a.value === null && <span className="small warn"> · sin tipo de cambio, no entra</span>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
