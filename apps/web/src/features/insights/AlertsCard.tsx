import { useEffect, useState } from 'react'
import { api, type Alert } from '../../api/client'
import { formatDate, formatMoney } from '../../lib/format'

const WHERE: Record<Alert['kind'], { href: string; label: string }> = {
  late_payment: { href: '#pagos', label: 'Ver pagos' },
  low_balance: { href: '#pagos', label: 'Ver previsión' },
  budget_over: { href: '#presupuestos', label: 'Ver presupuestos' },
  duplicate: { href: '#movimientos', label: 'Ver movimientos' },
  price_rise: { href: '#ahorrar', label: 'Ver cuotas' },
  fee: { href: '#movimientos', label: 'Ver movimientos' },
  consent: { href: '#ajustes', label: 'Ir a Ajustes' },
}

/** Avisos deterministas (ADR-0023, OF-1301): lo que conviene mirar hoy, y se puede descartar. */
export function AlertsCard() {
  const [alerts, setAlerts] = useState<Alert[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    // Es un complemento: si falla, «Este mes» sigue funcionando sin él.
    api.alerts(controller.signal).then(setAlerts, () => undefined)
    return () => controller.abort()
  }, [])

  async function dismiss(key: string) {
    setFailed(false)
    try {
      await api.dismissAlert(key)
      setAlerts((list) => list?.filter((a) => a.key !== key) ?? null)
    } catch {
      setFailed(true)
    }
  }

  if (!alerts || alerts.length === 0) return null
  return (
    <section className="card alerts" aria-label="Avisos">
      <h2>Avisos</h2>
      <ul className="plain">
        {alerts.map((a) => (
          <li key={a.key} className={`alert ${a.severity}`}>
            <div>
              <strong>{a.title}</strong>
              <p className="small muted">
                {a.detail} <span>{formatDate(a.on)}</span>
                {a.amount && a.kind !== 'duplicate' && a.kind !== 'fee' && ` · ${formatMoney(a.amount)}`}
              </p>
            </div>
            <div className="actions">
              <a href={WHERE[a.kind].href}>{WHERE[a.kind].label}</a>
              <button type="button" className="linkish small" onClick={() => dismiss(a.key)} aria-label={`Descartar: ${a.title}`}>
                Descartar
              </button>
            </div>
          </li>
        ))}
      </ul>
      {failed && (
        <p className="error" role="alert">
          No se ha podido descartar el aviso. Inténtalo de nuevo.
        </p>
      )}
    </section>
  )
}
