import { type FormEvent, useState } from 'react'
import { ApiError, api, type CategorizeResult, type Operation, type Transaction, type TransactionKind } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate } from '../../lib/format'
import { Attachments } from './Attachments'
import { SplitEditor } from './SplitEditor'
import { TransferLink } from './TransferLink'
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
  onDelete,
  onTagsSaved,
  onSplitChanged,
  onLinkChanged,
  accountName,
  onReviewChanged,
}: {
  t: Transaction
  /** Cambia cuando el movimiento se ha corregido o deshecho, para recargar el historial. */
  version: number
  onSaved: (result: CategorizeResult) => void
  onClose: () => void
  /** Solo en los movimientos añadidos a mano (OF-705). */
  onDelete?: () => void
  /** Tras guardar las etiquetas, con la operación para «Deshacer» (OF-1002). */
  onTagsSaved?: (operationId: string | null) => void
  /** Tras dividir o deshacer la división, con la operación para «Deshacer» (OF-1003). */
  onSplitChanged?: (message: string, operationId: string | null) => void
  /** Tras enlazar o desenlazar un traspaso (OF-1004). */
  onLinkChanged?: (message: string, operationId: string | null) => void
  accountName?: (id: string) => string
  /** Tras marcar o desmarcar como revisado (OF-1006). */
  onReviewChanged?: (message: string, operationId: string | null) => void
}) {
  const { me, notify } = useHousehold()
  const [kind, setKind] = useState<TransactionKind>(t.kind)
  const [memberId, setMemberId] = useState(t.member_id ?? me.user.id)
  const [note, setNote] = useState(t.note)
  const [saving, setSaving] = useState(false)
  const [tagText, setTagText] = useState(t.tags.join(', '))
  const [tagError, setTagError] = useState<string | null>(null)
  const history = useLoad<Operation[]>(`${t.id}|${version}`, (s) => api.transactionHistory(t.id, s))
  const memberName = (id: string) => me.members.find((m) => m.id === id)?.display_name ?? 'Alguien'

  const changed = kind !== t.kind || (kind === 'contribution' && memberId !== t.member_id) || note.trim() !== t.note

  const newTags = tagText
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
  const tagsChanged = newTags.join('|') !== t.tags.join('|')

  async function saveTags(e: FormEvent) {
    e.preventDefault()
    if (!tagsChanged) return
    setSaving(true)
    setTagError(null)
    try {
      const r = await api.setTags(t.id, newTags)
      onTagsSaved?.(r.operation_id)
    } catch (err) {
      setTagError(err instanceof ApiError ? err.message : 'No se han podido guardar las etiquetas')
    } finally {
      setSaving(false)
    }
  }

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
          <textarea className="field" rows={note.includes('\n') || note.length > 80 ? 4 : 1} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button className="btn primary small" type="submit" disabled={!changed || saving}>
          Guardar
        </button>
        <button className="btn small" type="button" onClick={onClose}>
          Cerrar
        </button>
        {onDelete && (
          <button className="btn small danger" type="button" onClick={onDelete}>
            Borrar
          </button>
        )}
      </form>
      <form className="toolbar wrap" onSubmit={(e) => void saveTags(e)} aria-label="Etiquetas">
        <label className="small grow">
          Etiquetas (separadas por comas){' '}
          <input
            className="field"
            value={tagText}
            maxLength={440}
            placeholder="viaje, regalos"
            onChange={(e) => {
              setTagText(e.target.value)
              setTagError(null)
            }}
            aria-invalid={tagError ? true : undefined}
            aria-describedby={tagError ? `tags-error-${t.id}` : undefined}
          />
        </label>
        <button className="btn small" type="submit" disabled={!tagsChanged || saving}>
          Guardar etiquetas
        </button>
        {tagError && (
          <p id={`tags-error-${t.id}`} className="error small" role="alert">
            {tagError}
          </p>
        )}
      </form>
      {t.kind === 'expense' && onSplitChanged && <SplitEditor t={t} onChanged={onSplitChanged} />}
      {onReviewChanged && <Attachments transactionId={t.id} onChanged={onReviewChanged} />}
      {onReviewChanged && (
        <label className="small">
          <input
            type="checkbox"
            checked={t.reviewed}
            onChange={(e) => {
              const reviewed = e.target.checked
              api.reviewTransactions([t.id], reviewed).then(
                (r) => onReviewChanged(reviewed ? 'Marcado como revisado' : 'Marca de revisado quitada', r.operation_id),
                (err: unknown) => notify(err instanceof ApiError ? err.message : 'No se ha podido marcar'),
              )
            }}
          />{' '}
          Revisado con el banco
        </label>
      )}
      {onLinkChanged && accountName && <TransferLink t={t} accountName={accountName} onChanged={onLinkChanged} />}
      <p className="small muted">
        {onDelete
          ? 'Añadido a mano: puedes borrarlo y deshacerlo después.'
          : 'El importe, la fecha y el concepto vienen del banco y no se cambian.'}
      </p>
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
