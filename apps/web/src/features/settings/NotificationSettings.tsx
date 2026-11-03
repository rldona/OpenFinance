import { useEffect, useState } from 'react'
import { ApiError, api, type AlertKind, type Notifications } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { currentSubscription, pushSupported, subscribeDevice, subscriptionKeys } from '../../lib/push'

const KINDS: { id: AlertKind; label: string }[] = [
  { id: 'low_balance', label: 'Saldo que se queda en negativo' },
  { id: 'late_payment', label: 'Pagos programados que no llegan' },
  { id: 'budget_over', label: 'Presupuestos superados' },
  { id: 'duplicate', label: 'Posibles cargos duplicados' },
  { id: 'price_rise', label: 'Recibos que suben' },
  { id: 'fee', label: 'Comisiones' },
  { id: 'consent', label: 'Conexión bancaria por caducar' },
]

/** Notificaciones push de esta persona (ADR-0023, OF-1302). */
export function NotificationSettings() {
  const { notify } = useHousehold()
  const [state, setState] = useState<Notifications | null>(null)
  const [here, setHere] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const supported = pushSupported()

  useEffect(() => {
    const controller = new AbortController()
    // Es un complemento de Ajustes: si falla, el resto sigue funcionando.
    api.notifications(controller.signal).then(setState, () => undefined)
    if (supported) currentSubscription().then((s) => setHere(s?.endpoint ?? null), () => undefined)
    return () => controller.abort()
  }, [supported])

  if (!state) return null

  async function run(action: () => Promise<void>, failure: string) {
    setBusy(true)
    try {
      await action()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : failure)
    } finally {
      setBusy(false)
    }
  }

  const enable = () =>
    run(async () => {
      if (!state?.public_key) return
      const sub = await subscribeDevice(state.public_key)
      if (!sub) return notify('Sin permiso del navegador no se pueden enviar avisos')
      const keys = subscriptionKeys(sub)
      if (!keys) return notify('Este navegador no ha dado una suscripción válida')
      await api.subscribePush(keys.endpoint, { p256dh: keys.p256dh, auth: keys.auth })
      setHere(keys.endpoint)
      setState(await api.notifications())
      notify('Avisos activados en este dispositivo')
    }, 'No se han podido activar los avisos')

  const disable = () =>
    run(async () => {
      const sub = await currentSubscription()
      if (sub) {
        await api.unsubscribePush(sub.endpoint)
        await sub.unsubscribe()
      }
      setHere(null)
      setState(await api.notifications())
      notify('Avisos desactivados en este dispositivo')
    }, 'No se han podido desactivar los avisos')

  const save = (kinds: AlertKind[], weekly: boolean) =>
    run(async () => setState(await api.saveNotificationPrefs(kinds, weekly)), 'No se han podido guardar las preferencias')

  function toggle(kind: AlertKind) {
    if (!state) return
    const kinds = state.kinds.includes(kind) ? state.kinds.filter((k) => k !== kind) : [...state.kinds, kind]
    void save(kinds, state.weekly)
  }

  return (
    <section className="card" aria-label="Notificaciones">
      <h2>Notificaciones</h2>
      {!state.configured ? (
        <p className="muted small">
          Este servidor no tiene activadas las notificaciones (faltan las claves VAPID). Los avisos se ven igualmente en «Este mes».
        </p>
      ) : !supported ? (
        <p className="muted small">
          Este navegador no admite notificaciones. Hace falta HTTPS y, en iPhone, iOS 16.4 o superior con la app añadida a la pantalla de inicio.
        </p>
      ) : (
        <>
          <p className="small muted">
            Recibes un único mensaje con cuántos avisos nuevos hay, sin importes ni comercios; el detalle se ve dentro de la app.
            {state.devices > 0 && ` Dispositivos con avisos: ${state.devices}.`}
          </p>
          {here ? (
            <button type="button" className="btn" disabled={busy} onClick={() => void disable()}>
              Desactivar en este dispositivo
            </button>
          ) : (
            <button type="button" className="btn primary" disabled={busy} onClick={() => void enable()}>
              Activar en este dispositivo
            </button>
          )}
          <fieldset className="stack" disabled={busy}>
            <legend className="small muted">Qué quieres que te avise</legend>
            {KINDS.map((k) => (
              <label key={k.id} className="check">
                <input type="checkbox" checked={state.kinds.includes(k.id)} onChange={() => toggle(k.id)} /> {k.label}
              </label>
            ))}
          </fieldset>
        </>
      )}
    </section>
  )
}
