import { useState } from 'react'
import { ApiError, api, type Transaction } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { formatDate, formatMoney } from '../../lib/format'

/** Enlazar los dos lados de un traspaso entre cuentas propias (OF-1004). */
export function TransferLink({
  t,
  accountName,
  onChanged,
}: {
  t: Transaction
  accountName: (id: string) => string
  onChanged: (message: string, operationId: string | null) => void
}) {
  const { notify } = useHousehold()
  const [candidates, setCandidates] = useState<Transaction[] | null>(null)
  const [busy, setBusy] = useState(false)

  async function search() {
    setBusy(true)
    try {
      setCandidates(await api.transferCandidates(t.id))
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se han podido buscar traspasos')
    } finally {
      setBusy(false)
    }
  }

  async function link(peer: Transaction) {
    setBusy(true)
    try {
      const r = await api.linkTransfer(t.id, peer.id)
      setCandidates(null)
      onChanged('Traspaso enlazado', r.operation_id)
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido enlazar')
    } finally {
      setBusy(false)
    }
  }

  async function unlink() {
    setBusy(true)
    try {
      const r = await api.unlinkTransfer(t.id)
      onChanged('Traspaso desenlazado', r.operation_id)
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido desenlazar')
    } finally {
      setBusy(false)
    }
  }

  if (t.transfer_peer_id) {
    return (
      <div className="toolbar" aria-label="Traspaso">
        <span className="small">🔗 Enlazado con el otro lado del traspaso.</span>
        <button className="btn small" type="button" disabled={busy} onClick={() => void unlink()}>
          Desenlazar
        </button>
      </div>
    )
  }
  return (
    <div className="transfer-link">
      {candidates === null && (
        <button className="btn small" type="button" disabled={busy} onClick={() => void search()}>
          Enlazar como traspaso
        </button>
      )}
      {candidates !== null && candidates.length === 0 && (
        <p className="small muted">
          No hay un movimiento de otra cuenta tuya con el importe contrario en los días de alrededor.{' '}
          <button className="linkish" type="button" onClick={() => setCandidates(null)}>
            Cerrar
          </button>
        </p>
      )}
      {candidates !== null && candidates.length > 0 && (
        <>
          <p className="small">Elige el otro lado del traspaso:</p>
          <ul className="plain" aria-label="Posibles otros lados">
            {candidates.map((c) => (
              <li key={c.id} className="toolbar">
                <span>
                  {formatDate(c.booked_at)} · {c.description} · {accountName(c.account_id)} · {formatMoney(c.amount, { signed: true })}
                </span>
                <button className="btn small primary" type="button" disabled={busy} aria-label={`Enlazar con ${c.description}`} onClick={() => void link(c)}>
                  Enlazar
                </button>
              </li>
            ))}
          </ul>
          <button className="btn small" type="button" onClick={() => setCandidates(null)}>
            Cancelar
          </button>
        </>
      )}
    </div>
  )
}
