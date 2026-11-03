import { useEffect, useState } from 'react'
import { ApiError, api, type Account, type Bank, type BankConnection } from '../../api/client'
import { useHousehold } from '../../app/household-context'

const STATUS: Record<BankConnection['status'], string> = {
  pending: 'Sin terminar',
  active: 'Activa',
  expired: 'Caducada',
  revoked: 'Revocada',
}

/** Estados de vuelta ya en curso: el código del banco solo vale una vez, aunque React monte dos veces. */
const completing = new Set<string>()

function dateLabel(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' }) : ''
}

/** Conexión con el banco (ADR-0024, OF-1401): consentimiento, cuentas enlazadas y revocación. */
export function BankSettings() {
  const { notify } = useHousehold()
  const [bank, setBank] = useState<Bank | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [names, setNames] = useState<string[]>([])
  const [country, setCountry] = useState('ES')
  const [aspsp, setAspsp] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    // Es un complemento de Ajustes: si falla, el resto sigue funcionando.
    api.bank(controller.signal).then(setBank, () => undefined)
    api.accounts(controller.signal).then(setAccounts, () => undefined)
    return () => controller.abort()
  }, [])

  // El banco devuelve a la raíz con ?code=…&state=…: se completa aquí y se limpia la dirección.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const state = params.get('state')
    if (!code || !state || completing.has(state)) return
    completing.add(state)
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.hash}`)
    api
      .completeBank(state, code)
      .then(async () => {
        notify('Banco conectado: elige a qué cuenta alimenta cada una')
        setBank(await api.bank())
      })
      .catch((err) => notify(err instanceof ApiError ? err.message : 'No se ha podido completar la conexión'))
  }, [notify])

  const configured = bank?.configured ?? false
  useEffect(() => {
    if (!configured || country.length !== 2) return
    const controller = new AbortController()
    api.bankNames(country, controller.signal).then(setNames, () => setNames([]))
    return () => controller.abort()
  }, [configured, country])

  if (!bank) return null

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

  const connect = () =>
    run(async () => {
      const started = await api.startBank(aspsp.trim(), country.trim())
      window.location.assign(started.url)
    }, 'No se ha podido iniciar la conexión')

  const link = (c: BankConnection, remoteUid: string, accountId: string) =>
    run(async () => {
      const updated = await api.linkBank(c.id, remoteUid, accountId || null)
      setBank((b) => b && { ...b, connections: b.connections.map((x) => (x.id === updated.id ? updated : x)) })
    }, 'No se ha podido enlazar la cuenta')

  const sync = (c: BankConnection) =>
    run(async () => {
      const result = await api.syncBank(c.id)
      setBank(await api.bank())
      const error = result.links.find((l) => l.error)?.error
      if (result.skipped_reason) notify(result.skipped_reason)
      else if (error) notify(`El banco no respondió: ${error}`)
      else notify(result.created === 1 ? '1 movimiento nuevo' : `${result.created} movimientos nuevos`)
    }, 'No se ha podido sincronizar')

  const revoke = (c: BankConnection) =>
    run(async () => {
      const result = await api.revokeBank(c.id)
      setBank(await api.bank())
      notify(
        result.closed_at_bank
          ? 'Conexión revocada'
          : 'Conexión revocada aquí; el banco no confirmó el cierre, caducará por sí sola',
      )
    }, 'No se ha podido revocar la conexión')

  const visible = bank.connections.filter((c) => c.status !== 'revoked')

  return (
    <section className="card stack" aria-label="Banco">
      <h2>Conexión con el banco</h2>
      {!bank.configured ? (
        <p className="muted small">
          Este servidor no tiene configurada la conexión con el banco (faltan los datos de la aplicación en Enable Banking). Los
          extractos se siguen importando a mano.
        </p>
      ) : (
        <>
          <p className="small muted">
            Solo lectura: OpenFinance trae tus movimientos y nunca mueve dinero. El consentimiento es tuyo y caduca; puedes revocarlo
            cuando quieras.
          </p>
          {visible.map((c) => (
            <div key={c.id} className="stack" aria-label={`Conexión ${c.aspsp}`}>
              <p>
                <strong>{c.aspsp}</strong> · {STATUS[c.status]}
                {c.valid_until && c.status === 'active' && ` hasta el ${dateLabel(c.valid_until)}`}
                {c.expires_soon && ' (caduca pronto)'}
              </p>
              {c.status === 'active' && (
                <p className="small muted">
                  {c.last_sync_at ? `Última sincronización: ${dateLabel(c.last_sync_at)}` : 'Aún sin sincronizar'}
                </p>
              )}
              {c.last_error && <p className="small warn">Último error: {c.last_error}</p>}
              {c.status === 'active' &&
                c.links.map((l) => (
                  <label key={l.remote_uid} className="field">
                    <span>
                      {l.name} ····{l.iban_tail} ({l.currency})
                    </span>
                    <select
                      value={l.account_id ?? ''}
                      disabled={busy}
                      onChange={(e) => void link(c, l.remote_uid, e.target.value)}
                    >
                      <option value="">No traer movimientos</option>
                      {accounts
                        .filter((a) => a.balance.currency === l.currency)
                        .map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.name}
                          </option>
                        ))}
                    </select>
                  </label>
                ))}
              {c.status === 'active' && (
                <button type="button" className="btn" disabled={busy} onClick={() => void sync(c)}>
                  Sincronizar ahora
                </button>
              )}
              {c.status !== 'pending' && (
                <button type="button" className="btn" disabled={busy} onClick={() => void revoke(c)}>
                  Revocar conexión
                </button>
              )}
            </div>
          ))}
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault()
              void connect()
            }}
          >
            <h3>Conectar un banco</h3>
            <label className="field">
              <span>País</span>
              <input value={country} maxLength={2} onChange={(e) => setCountry(e.target.value.toUpperCase())} />
            </label>
            <label className="field">
              <span>Banco</span>
              <input value={aspsp} list="bank-names" onChange={(e) => setAspsp(e.target.value)} />
              <datalist id="bank-names">
                {names.map((n) => (
                  <option key={n} value={n} />
                ))}
              </datalist>
            </label>
            <button type="submit" className="btn primary" disabled={busy || !aspsp.trim() || country.length !== 2}>
              Conectar
            </button>
          </form>
        </>
      )}
    </section>
  )
}
