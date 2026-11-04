import { useEffect, useState } from 'react'
import { api, type Allowance } from '../../api/client'
import { formatDate, formatMoney } from '../../lib/format'
import { useCategoryMeta } from './meta'

/** «Hoy podéis gastar» (ADR-0021, OF-1205): un reparto honesto, con su cuenta a la vista. */
export function AllowanceCard() {
  const meta = useCategoryMeta()
  const [data, setData] = useState<Allowance | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    // Es un complemento: si falla, «Este mes» sigue funcionando sin él.
    api.allowance(controller.signal).then(setData, () => undefined)
    return () => controller.abort()
  }, [])

  if (!data || data.status === 'no_balance') return null
  if (data.status === 'no_schedule' || !data.balance || !data.committed || !data.per_day || !data.until) {
    return (
      <section className="card allowance" aria-label="Hoy podéis gastar">
        <h2>Hoy podéis gastar</h2>
        <p className="muted">
          Sin vuestros pagos fijos no se puede calcular una cifra que signifique algo. <a href="#pagos">Programad el alquiler, los seguros o la nómina</a>{' '}
          y os diremos cuánto podéis gastar al día.
        </p>
      </section>
    )
  }
  const until = formatDate(data.until)
  return (
    <section className="card allowance" aria-label="Hoy podéis gastar">
      <h2>Hoy podéis gastar</h2>
      {data.short ? (
        <p className="error" role="alert">
          Los pagos que quedan ({formatMoney(data.committed)}) son más que el saldo ({formatMoney(data.balance)}): no llega hasta el {until}.
        </p>
      ) : (
        <p>
          <strong className="num big">{formatMoney(data.per_day)}</strong> al día
        </p>
      )}
      <p className="small muted">
        {data.horizon === 'income'
          ? `Hasta el ${until}, cuando llega ${data.next_income?.name ?? 'vuestra próxima entrada'} (${data.days} ${data.days === 1 ? 'día' : 'días'}).`
          : `Hasta fin de mes, el ${until} (${data.days} ${data.days === 1 ? 'día' : 'días'}).`}{' '}
        Saldo de la conjunta {formatMoney(data.balance)} menos {formatMoney(data.committed)} de pagos pendientes.
      </p>
      {data.pending.length > 0 && (
        <ul className="plain small" aria-label="Pagos que se descuentan">
          {data.pending.slice(0, 5).map((p) => (
            <li key={`${p.name}-${p.due}`}>
              {formatDate(p.due)} · {p.name} · {formatMoney(p.amount)}
            </li>
          ))}
          {data.pending.length > 5 && <li className="muted">y {data.pending.length - 5} más</li>}
        </ul>
      )}
      {data.envelopes.length > 0 && (
        <ul className="plain small" aria-label="Sobres">
          {data.envelopes.map((e) => (
            <li key={e.category_id} className={e.status === 'over' ? 'error' : undefined}>
              {meta(e.category_id).icon} {meta(e.category_id).name}: quedan {formatMoney(e.available)} en el sobre
            </li>
          ))}
        </ul>
      )}
      <p className="small muted">
        Es un cálculo, no una promesa: no sabe de gastos que no hayáis programado. <a href="#pagos">Ver pagos programados</a>
      </p>
    </section>
  )
}
