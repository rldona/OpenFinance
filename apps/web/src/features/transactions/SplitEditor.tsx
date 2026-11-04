import { type FormEvent, useState } from 'react'
import { ApiError, api, type Transaction } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { centsToAmount, formatMoney, parseAmountInput, toCents } from '../../lib/format'

type Row = { amount: string; category: string }

const MAX_PARTS = 10

/** Dividir un gasto en partes con su categoría (OF-1003). Las partes han de sumar el total. */
export function SplitEditor({ t, onChanged }: { t: Transaction; onChanged: (message: string, operationId: string | null) => void }) {
  const { categories, categoryById } = useHousehold()
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const split = t.parts.length > 0
  const negative = toCents(t.amount.amount) < 0n
  const total = negative ? -toCents(t.amount.amount) : toCents(t.amount.amount)
  const initial = (): Row[] =>
    split
      ? t.parts.map((p) => ({ amount: centsToAmount(negative ? -toCents(p.amount.amount) : toCents(p.amount.amount)), category: p.category_id }))
      : [
          { amount: '', category: t.category_id ?? '' },
          { amount: '', category: '' },
        ]
  const [rows, setRows] = useState<Row[]>(initial)

  const parsed = rows.map((r) => parseAmountInput(r.amount))
  const sum = parsed.reduce((acc, a) => acc + (a ? toCents(a) : 0n), 0n)
  const remaining = total - sum
  const valid =
    rows.length >= 2 && parsed.every((a) => a !== null && toCents(a) > 0n) && rows.every((r) => r.category) && remaining === 0n

  function update(i: number, patch: Partial<Row>) {
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
    setError(null)
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!valid) return
    setSaving(true)
    try {
      const sign = negative ? '-' : ''
      const r = await api.splitTransaction(
        t.id,
        rows.map((row, i) => ({ amount: `${sign}${parsed[i]}`, category_id: row.category })),
      )
      setOpen(false)
      onChanged('Gasto dividido', r.operation_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido dividir')
    } finally {
      setSaving(false)
    }
  }

  async function unsplit() {
    setSaving(true)
    try {
      const r = await api.unsplitTransaction(t.id)
      onChanged('División deshecha', r.operation_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido deshacer la división')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="split">
      {split && !open && (
        <>
          <ul className="plain" aria-label="Partes del gasto">
            {t.parts.map((p, i) => {
              const c = categoryById.get(p.category_id)
              return (
                <li key={i}>
                  {c ? `${c.icon} ${c.name}` : 'Categoría'} · {formatMoney(p.amount)}
                </li>
              )
            })}
          </ul>
          <div className="toolbar">
            <button className="btn small" type="button" onClick={() => setOpen(true)}>
              Cambiar las partes
            </button>
            <button className="btn small" type="button" disabled={saving} onClick={() => void unsplit()}>
              Deshacer la división
            </button>
          </div>
        </>
      )}
      {!split && !open && (
        <button className="btn small" type="button" onClick={() => setOpen(true)}>
          Dividir en partes
        </button>
      )}
      {open && (
        <form aria-label="Dividir el gasto" onSubmit={(e) => void save(e)}>
          {rows.map((r, i) => (
            <div className="toolbar" key={i}>
              <label className="small">
                Importe de la parte {i + 1}{' '}
                <input
                  className="field amount"
                  inputMode="decimal"
                  placeholder="0,00"
                  value={r.amount}
                  onChange={(e) => update(i, { amount: e.target.value })}
                />
              </label>
              <label className="small">
                Categoría de la parte {i + 1}{' '}
                <select className="field" value={r.category} onChange={(e) => update(i, { category: e.target.value })}>
                  <option value="">Elige…</option>
                  {categories
                    .filter((c) => !c.hidden || c.id === r.category)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.icon} {c.name}
                      </option>
                    ))}
                </select>
              </label>
              {rows.length > 2 && (
                <button className="btn small" type="button" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                  Quitar
                </button>
              )}
            </div>
          ))}
          <p className="small" role="status">
            {remaining === 0n
              ? 'Todo repartido.'
              : remaining > 0n
                ? `Falta por repartir ${formatMoney({ amount: centsToAmount(remaining), currency: t.amount.currency })}`
                : `Te pasas ${formatMoney({ amount: centsToAmount(-remaining), currency: t.amount.currency })}`}
          </p>
          {error && (
            <p className="error small" role="alert">
              {error}
            </p>
          )}
          <div className="toolbar">
            <button className="btn small" type="button" disabled={rows.length >= MAX_PARTS} onClick={() => setRows([...rows, { amount: '', category: '' }])}>
              Añadir parte
            </button>
            <button className="btn primary small" type="submit" disabled={!valid || saving}>
              Guardar la división
            </button>
            <button className="btn small" type="button" onClick={() => { setOpen(false); setRows(initial()); setError(null) }}>
              Cancelar
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
