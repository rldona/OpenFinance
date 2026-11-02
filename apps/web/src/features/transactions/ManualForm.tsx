import { type FormEvent, useRef, useState } from 'react'
import { ApiError, api, type Account, type ManualTransactionResult, type Template } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { FieldError } from '../../components/FieldError'
import { invalid } from '../../lib/invalid'
import { formatMoney, parseAmountInput } from '../../lib/format'
import { notifyUndoable } from '../../lib/undo'
import { useLoad } from '../../lib/useLoad'

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Alta a mano de un gasto o un ingreso, p. ej. en efectivo (OF-705). */
export function ManualForm({
  accounts,
  onSaved,
  onClose,
}: {
  accounts: Account[]
  onSaved: (result: ManualTransactionResult) => void
  onClose: () => void
}) {
  const { me, categories, notify } = useHousehold()
  const templates = useLoad<Template[]>('templates', (s) => api.templates(s))
  // Mejor en una cuenta que no sea de un banco: en la del banco, el saldo dejará de cuadrar.
  const preferred = accounts.find((a) => a.institution === 'other') ?? accounts[0]
  const [accountId, setAccountId] = useState(preferred?.id ?? '')
  const [bookedOn, setBookedOn] = useState(today)
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [kind, setKind] = useState<'expense' | 'income'>('expense')
  const [categoryId, setCategoryId] = useState('')
  const [saving, setSaving] = useState(false)
  const [templateName, setTemplateName] = useState<string | null>(null)
  const [amountError, setAmountError] = useState<string | null>(null)
  const amountInput = useRef<HTMLInputElement>(null)
  const account = accounts.find((a) => a.id === accountId)

  async function save(e: FormEvent) {
    e.preventDefault()
    const value = parseAmountInput(amount)
    if (!value) {
      setAmountError('Escribe un importe mayor que cero, por ejemplo 7,50')
      amountInput.current?.focus()
      return
    }
    setAmountError(null)
    setSaving(true)
    try {
      onSaved(
        await api.addManual({
          account_id: accountId,
          booked_on: bookedOn,
          description,
          amount: value,
          kind,
          category_id: kind === 'expense' && categoryId ? categoryId : null,
          note: '',
        }),
      )
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido añadir')
    } finally {
      setSaving(false)
    }
  }

  async function createFromTemplate(t: Template) {
    setSaving(true)
    try {
      onSaved(await api.useTemplate(t.id, bookedOn))
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido usar la plantilla')
    } finally {
      setSaving(false)
    }
  }

  async function removeTemplate(t: Template) {
    try {
      const r = await api.deleteTemplate(t.id)
      notifyUndoable(notify, me, `Plantilla «${t.name}» borrada`, r.operation_id, templates.reload)
      templates.reload()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido borrar la plantilla')
    }
  }

  async function saveTemplate() {
    const value = parseAmountInput(amount)
    if (!value) {
      setAmountError('Escribe un importe mayor que cero, por ejemplo 7,50')
      amountInput.current?.focus()
      return
    }
    setAmountError(null)
    try {
      const r = await api.createTemplate({
        name: templateName ?? '',
        kind,
        amount: value,
        description,
        account_id: accountId,
        // Una cuenta personal solo la ve su titular: la plantilla también.
        personal: account?.kind === 'personal',
        category_id: kind === 'expense' && categoryId ? categoryId : null,
        tags: [],
        note: '',
      })
      setTemplateName(null)
      notifyUndoable(notify, me, `Plantilla «${r.template.name}» guardada`, r.operation_id, templates.reload)
      templates.reload()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido guardar la plantilla')
    }
  }

  return (
    <form className="card manual" aria-label="Añadir a mano" onSubmit={(e) => void save(e)}>
      <h2>Añadir a mano</h2>
      {templates.data && templates.data.length > 0 && (
        <div className="stack">
          <p className="small muted">Desde una plantilla (con la fecha de abajo):</p>
          <ul className="plain toolbar wrap" aria-label="Plantillas">
            {templates.data.map((t) => (
              <li key={t.id} className="toolbar inline">
                <button className="btn small" type="button" disabled={saving} onClick={() => void createFromTemplate(t)}>
                  {t.name} · {formatMoney(t.amount)}
                </button>
                <button className="btn small" type="button" aria-label={`Borrar la plantilla ${t.name}`} onClick={() => void removeTemplate(t)}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="toolbar wrap">
        <label className="small">
          Tipo{' '}
          <select className="field" value={kind} onChange={(e) => setKind(e.target.value as 'expense' | 'income')}>
            <option value="expense">Gasto</option>
            <option value="income">Ingreso</option>
          </select>
        </label>
        <label className="small">
          Fecha <input className="field" type="date" required value={bookedOn} onChange={(e) => setBookedOn(e.target.value)} />
        </label>
        <label className="small">
          Concepto{' '}
          <input className="field" required maxLength={200} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label className="small">
          Importe{' '}
          <input
            ref={amountInput}
            className="field amount"
            required
            inputMode="decimal"
            placeholder="7,50"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            {...invalid('manual-amount-error', amountError)}
          />
        </label>
        <label className="small">
          Cuenta{' '}
          <select className="field" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        {kind === 'expense' && (
          <label className="small">
            Categoría{' '}
            <select className="field" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">Sin categoría</option>
              {categories
                .filter((c) => !c.hidden)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.icon} {c.name}
                  </option>
                ))}
            </select>
          </label>
        )}
      </div>
      <FieldError id="manual-amount-error" message={amountError} />
      {account && account.institution !== 'other' && (
        <p className="small muted">
          «{account.name}» es una cuenta del banco: con un movimiento a mano, su saldo dejará de cuadrar con el extracto.
        </p>
      )}
      <div className="toolbar">
        <button className="btn primary" type="submit" disabled={saving || !accountId}>
          Añadir
        </button>
        <button className="btn" type="button" onClick={onClose}>
          Cancelar
        </button>
        {templateName === null && (
          <button className="btn" type="button" disabled={!accountId || !description.trim()} onClick={() => setTemplateName(description.trim().slice(0, 60))}>
            Guardar como plantilla
          </button>
        )}
      </div>
      {templateName !== null && (
        <div className="toolbar wrap">
          <label className="small">
            Nombre de la plantilla{' '}
            <input className="field" maxLength={60} value={templateName} onChange={(e) => setTemplateName(e.target.value)} />
          </label>
          <button className="btn" type="button" disabled={!templateName.trim()} onClick={() => void saveTemplate()}>
            Guardar plantilla
          </button>
          <button className="btn" type="button" onClick={() => setTemplateName(null)}>
            No guardar
          </button>
        </div>
      )}
    </form>
  )
}
