import { type FormEvent, useState } from 'react'
import { ApiError, api, type CategorizeResult, type Operation, type Transaction, type TransactionKind } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

const KINDS: { value: TransactionKind; label: string }[] = [
  { value: 'expense', label: 'Gasto' },
  { value: 'income', label: 'Ingreso' },
  { value: 'contribution', label: 'Aportación' },
  { value: 'savings_transfer', label: 'Hucha' },
  { value: 'internal_transfer', label: 'Entre cuentas' },
]

/** Detalle de un movimiento: corregir tipo, persona y nota, y ver quién lo cambió (OF-701). */
export function TransactionDetail({
  t,
  version,
  onSaved,
  onClose,
}: {
  t: Transaction
  /** Cambia cuando el movimiento se ha corregido o deshecho, para recargar el historial. */
  version: number
  onSaved: (result: CategorizeResult) => void
  onClose: () => void
}) {
  const { me, notify } = useHousehold()
  const [kind, setKind] = useState<TransactionKind>(t.kind)
  const [memberId, setMemberId] = useState(t.member_id ?? me.user.id)
  const [note, setNote] = useState(t.note)
  const [saving, setSaving] = useState(false)
  const history = useLoad<Operation[]>(`${t.id}|${version}`, (s) => api.transactionHistory(t.id, s))
  const memberName = (id: string) => me.members.find((m) => m.id === id)?.display_name ?? 'Alguien'

  const changed = kind !== t.kind || (kind === 'contribution' && memberId !== t.member_id) || note.trim() !== t.note

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!changed) return
    setSaving(true)
    try {
      const patch: Parameters<typeof api.editTransaction>[1] = { note: note.trim() }
      if (kind !== t.kind || kind === 'contribution') patch.kind = kind
      if (kind === 'contribution') patch.member_id = memberId
      onSaved(await api.editTransaction(t.id, patch))
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido guardar')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="tx-detail">
      <form className="toolbar wrap" onSubmit={(e) => void save(e)}>
        <label className="small">
          Tipo{' '}
          <select className="field" value={kind} onChange={(e) => setKind(e.target.value as TransactionKind)}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        {kind === 'contribution' && (
          <label className="small">
            De{' '}
            <select className="field" value={memberId} onChange={(e) => setMemberId(e.target.value)}>
              {me.members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="small grow">
          Nota{' '}
          <input className="field" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button className="btn primary small" type="submit" disabled={!changed || saving}>
          Guardar
        </button>
        <button className="btn small" type="button" onClick={onClose}>
          Cerrar
        </button>
      </form>
      <p className="small muted">El importe, la fecha y el concepto vienen del banco y no se cambian.</p>
      <h3 className="small">Historial</h3>
      {history.error && <ErrorState message={history.error} onRetry={history.reload} />}
      {!history.data && !history.error && <Loading />}
      {history.data && history.data.length === 0 && <p className="small muted">Sin correcciones.</p>}
      {history.data && history.data.length > 0 && (
        <ul className="plain history" aria-label="Historial de correcciones">
          {history.data.map((o) => (
            <li key={o.id} className={o.undone ? 'undone' : ''}>
              <strong>{o.actor_id === me.user.id ? 'Tú' : memberName(o.actor_id)}</strong> · {formatDate(o.created_at)} ·{' '}
              {o.summary}
              {o.undone && ' (deshecho)'}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
