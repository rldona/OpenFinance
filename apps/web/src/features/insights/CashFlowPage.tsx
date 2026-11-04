import { api } from '../../api/client'
import { LineChart } from '../../components/charts'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatMoney, monthLabel } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

/** Flujo de caja mensual del dinero líquido de quien mira (ADR-0025, OF-1502). */
export function CashFlowPage() {
  const { data, error, reload } = useLoad('cash-flow', (signal) => api.cashFlow(signal), 'No se ha podido cargar el flujo de caja')
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <Loading />

  const balances = data.months.map((m) => Number(m.end_balance.amount))
  const canChart = balances.length > 1 && balances.every((v) => v >= 0)

  return (
    <div className="stack">
      <section className="card" aria-label="Flujo de caja">
        <h2>Flujo de caja</h2>
        <p className="small muted">
          Dinero líquido de las {data.accounts} cuentas bancarias y de efectivo que ves. Ingresos y aportaciones, menos gasto y ahorro,
          dan la variación del saldo de cada mes.
        </p>
        {data.excluded_foreign > 0 && (
          <p className="small warn">
            {data.excluded_foreign === 1 ? 'Una cuenta en otra moneda no entra' : `${data.excluded_foreign} cuentas en otra moneda no entran`}:
            sus cifras no se pueden sumar sin perder exactitud.
          </p>
        )}
        {canChart && (
          <LineChart
            label="Saldo líquido a fin de cada mes"
            series={[
              {
                id: 'balance',
                label: 'Saldo líquido',
                points: balances,
                color: 'var(--accent, #2563eb)',
                area: true,
                summary: `${formatMoney(data.months[0].end_balance)} → ${formatMoney(data.months[data.months.length - 1].end_balance)}`,
              },
            ]}
          />
        )}
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Flujo de caja por mes</caption>
            <thead>
              <tr>
                <th scope="col">Mes</th>
                <th scope="col">Ingresos</th>
                <th scope="col">Aportaciones</th>
                <th scope="col">Gasto</th>
                <th scope="col">Al ahorro</th>
                <th scope="col">Traspasos</th>
                <th scope="col">Variación</th>
                <th scope="col">Saldo</th>
              </tr>
            </thead>
            <tbody>
              {[...data.months].reverse().map((m) => (
                <tr key={m.month}>
                  <th scope="row">
                    {monthLabel(m.month)}
                    {m.is_partial && ' (en curso)'}
                  </th>
                  <td className="num">{formatMoney(m.income)}</td>
                  <td className="num">{formatMoney(m.contributions)}</td>
                  <td className="num">{formatMoney(m.spending)}</td>
                  <td className="num">{formatMoney(m.savings)}</td>
                  <td className="num">{formatMoney(m.transfers)}</td>
                  <td className="num">
                    <strong>{formatMoney(m.change, { signed: true })}</strong>
                  </td>
                  <td className="num">{formatMoney(m.end_balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted">Las tarjetas, los préstamos y las inversiones no son dinero líquido y quedan fuera.</p>
      </section>
    </div>
  )
}
