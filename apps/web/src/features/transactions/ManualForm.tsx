import { type FormEvent, useState } from 'react'
import { ApiError, api, type Account, type ManualTransactionResult } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { parseAmountInput } from '../../lib/format'

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
  const { categories, notify } = useHousehold()
  // Mejor en una cuenta que no sea de un banco: en la del banco, el saldo dejará de cuadrar.
  const preferred = accounts.find((a) => a.institution === 'other') ?? accounts[0]
  const [accountId, setAccountId] = useState(preferred?.id ?? '')
  const [bookedOn, setBookedOn] = useState(today)
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [kind, setKind] = useState<'expense' | 'income'>('expense')
  const [categoryId, setCategoryId] = useState('')
  const [saving, setSaving] = useState(false)
  const account = accounts.find((a) => a.id === accountId)

  async function save(e: FormEvent) {
    e.preventDefault()
    const value = parseAmountInput(amount)
    if (!value) {
      notify('Escribe un importe mayor que cero, por ejemplo 7,50')
      return
    }
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

  return (
    <form className="card manual" aria-label="Añadir a mano" onSubmit={(e) => void save(e)}>
      <h2>Añadir a mano</h2>
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
          <input className="field amount" required inputMode="decimal" placeholder="7,50" value={amount} onChange={(e) => setAmount(e.target.value)} />
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
      </div>
    </form>
  )
}
