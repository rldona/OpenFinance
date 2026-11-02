import { type FormEvent, useEffect, useState } from 'react'
import { ApiError, api, type ScheduleItem, type ScheduledPaymentInput } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { setHashParams, useHashParam } from '../../app/router'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate, formatMoney } from '../../lib/format'
import { notifyUndoable } from '../../lib/undo'
import { useLoad } from '../../lib/useLoad'

const FREQUENCIES = { monthly: 'Cada mes', weekly: 'Cada semana', yearly: 'Cada año', once: 'Una vez' } as const
const UNITS = { monthly: 'meses', weekly: 'semanas', yearly: 'años', once: '' } as const
const STATUS = { paid: 'Cobrado', pending: 'Pendiente', late: 'Atrasado' } as const
const HORIZON_DAYS = 90

type Draft = {
  name: string
  income: boolean
  amount: string
  account_id: string
  frequency: keyof typeof FREQUENCIES
  interval: string
  first_due: string
  ends_on: string
  category_id: string
  merchant: string
  variable: boolean
  active: boolean
}

const today = () => new Date().toISOString().slice(0, 10)

const blank = (account_id = ''): Draft => ({
  name: '',
  income: false,
  amount: '',
  account_id,
  frequency: 'monthly',
  interval: '1',
  first_due: today(),
  ends_on: '',
  category_id: '',
  merchant: '',
  variable: false,
  active: true,
})

function toInput(d: Draft): ScheduledPaymentInput {
  const amount = d.amount.trim().replace(/^[-+]/, '')
  return {
    name: d.name,
    amount: d.income ? amount : `-${amount}`,
    account_id: d.account_id,
    frequency: d.frequency,
    interval: d.frequency === 'once' ? 1 : Number(d.interval) || 1,
    first_due: d.first_due,
    ends_on: d.ends_on || null,
    category_id: !d.income && d.category_id ? d.category_id : null,
    merchant: d.merchant,
    variable: d.variable,
    active: d.active,
  }
}

function describe(p: ScheduleItem['payment']): string {
  if (p.frequency === 'once') return 'Una vez'
  return p.interval === 1 ? FREQUENCIES[p.frequency] : `Cada ${p.interval} ${UNITS[p.frequency]}`
}

/** Pagos programados (ADR-0021, OF-1201): lo que sabéis que va a llegar, con su estado. */
export function SchedulePage() {
  const { me, categories, notify } = useHousehold()
  const schedule = useLoad<ScheduleItem[]>('schedule', (s) => api.schedule(HORIZON_DAYS, s))
  const accounts = useLoad('schedule-accounts', (s) => api.accounts(s))
  const [editing, setEditing] = useState<string | 'new' | null>(null)
  const [draft, setDraft] = useState<Draft>(blank)
  const [error, setError] = useState<string | null>(null)

  // Un cargo detectado en «Ahorrar» trae su nombre, importe y fecha en la URL (OF-1201).
  const [preName] = useHashParam('nombre')
  const [preAmount] = useHashParam('importe')
  const [preDate] = useHashParam('fecha')
  const [preCategory] = useHashParam('categoria')
  const firstAccount = accounts.data?.[0]?.id
  const [prefilled, setPrefilled] = useState<string | null>(null)
  const prefillKey = preName ? [preName, preAmount, preDate, preCategory].join('|') : null
  if (prefillKey && firstAccount && prefillKey !== prefilled) {
    setPrefilled(prefillKey)
    setEditing('new')
    setDraft({
      ...blank(firstAccount),
      name: String(preName).slice(0, 60),
      income: !(preAmount ?? '').startsWith('-'),
      amount: (preAmount ?? '').replace(/^-/, ''),
      first_due: /^\d{4}-\d{2}-\d{2}$/.test(preDate ?? '') ? String(preDate) : today(),
      category_id: preCategory ?? '',
    })
  }
  useEffect(() => {
    if (prefilled) setHashParams({ nombre: null, importe: null, fecha: null, categoria: null })
  }, [prefilled])

  const accountName = new Map((accounts.data ?? []).map((a) => [a.id, a.name]))
  const categoryName = new Map(categories.map((c) => [c.id, c.name]))

  function open(item?: ScheduleItem) {
    setError(null)
    if (!item) {
      setEditing('new')
      setDraft(blank(accounts.data?.[0]?.id ?? ''))
      return
    }
    const p = item.payment
    setEditing(p.id)
    setDraft({
      name: p.name,
      income: !p.amount.amount.startsWith('-'),
      amount: p.amount.amount.replace(/^-/, ''),
      account_id: p.account_id,
      frequency: p.frequency,
      interval: String(p.interval),
      first_due: p.first_due,
      ends_on: p.ends_on ?? '',
      category_id: p.category_id ?? '',
      merchant: p.merchant,
      variable: p.variable,
      active: p.active,
    })
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const input = toInput(draft)
    try {
      const r = editing === 'new' ? await api.createScheduledPayment(input) : await api.updateScheduledPayment(String(editing), input)
      setEditing(null)
      notifyUndoable(notify, me, `Pago «${r.payment.name}» guardado`, r.operation_id, schedule.reload)
      schedule.reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido guardar el pago')
    }
  }

  async function remove(item: ScheduleItem) {
    try {
      const r = await api.deleteScheduledPayment(item.payment.id)
      notifyUndoable(notify, me, `Pago «${item.payment.name}» borrado`, r.operation_id, schedule.reload)
      schedule.reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido borrar el pago')
    }
  }

  const items = schedule.data
  return (
    <section className="stack" aria-label="Pagos programados">
      <h1>Pagos programados</h1>
      <p className="small muted">
        Lo que sabéis que va a llegar: el alquiler, un seguro anual, la nómina. Son fechas esperadas, no movimientos: no se apunta nada hasta
        que el banco lo cobre y lo importéis. Cuando llega un cobro parecido (misma cuenta, importe similar, en una semana), la fecha se da por
        cumplida.
      </p>
      {error && editing === null && <p className="error small" role="alert">{error}</p>}
      {schedule.error && <ErrorState message={schedule.error} onRetry={schedule.reload} />}
      {!items && !schedule.error && <Loading />}
      {items && items.length === 0 && editing === null && <p className="muted">Todavía no hay pagos programados.</p>}
      {items && items.length > 0 && (
        <ul className="plain" aria-label="Tus pagos programados">
          {items.map((item) => {
            const p = item.payment
            const shown = item.occurrences.filter((o) => o.status !== 'paid').slice(0, 3)
            return (
              <li key={p.id} className="card">
                <strong>{p.name}</strong>{' '}
                <span className="small muted">
                  · {formatMoney(p.amount, { signed: true })}
                  {p.variable ? ' (variable)' : ''} · {describe(p)} · {accountName.get(p.account_id) ?? 'Cuenta'}
                  {p.category_id ? ` · ${categoryName.get(p.category_id) ?? ''}` : ''}
                  {p.active ? '' : ' · en pausa'}
                </span>
                {shown.length > 0 && (
                  <ul className="plain small" aria-label={`Próximas fechas de ${p.name}`}>
                    {shown.map((o) => (
                      <li key={o.due} className={o.status === 'late' ? 'error' : undefined}>
                        {formatDate(o.due)} · {STATUS[o.status]}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="toolbar">
                  <button className="btn small" type="button" aria-label={`Editar el pago ${p.name}`} onClick={() => open(item)}>
                    Editar
                  </button>
                  <button className="btn small" type="button" aria-label={`Borrar el pago ${p.name}`} onClick={() => void remove(item)}>
                    Borrar
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      {editing === null && (
        <button className="btn" type="button" disabled={!accounts.data?.length} onClick={() => open()}>
          Nuevo pago programado
        </button>
      )}
      {editing !== null && (
        <form className="card stack" aria-label="Pago programado" onSubmit={(e) => void save(e)}>
          <label>
            Nombre
            <input className="field" required maxLength={60} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </label>
          <div className="toolbar wrap">
            <label className="small">
              Tipo{' '}
              <select className="field" value={draft.income ? 'in' : 'out'} onChange={(e) => setDraft({ ...draft, income: e.target.value === 'in' })}>
                <option value="out">Pago</option>
                <option value="in">Ingreso</option>
              </select>
            </label>
            <label className="small">
              Importe{' '}
              <input className="field amount" required inputMode="decimal" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} />
            </label>
            <label className="small">
              <input type="checkbox" checked={draft.variable} onChange={(e) => setDraft({ ...draft, variable: e.target.checked })} /> Importe variable
            </label>
          </div>
          <label>
            Cuenta
            <select className="field" required value={draft.account_id} onChange={(e) => setDraft({ ...draft, account_id: e.target.value })}>
              {(accounts.data ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <div className="toolbar wrap">
            <label className="small">
              Se repite{' '}
              <select className="field" value={draft.frequency} onChange={(e) => setDraft({ ...draft, frequency: e.target.value as Draft['frequency'] })}>
                {Object.entries(FREQUENCIES).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            {draft.frequency !== 'once' && (
              <label className="small">
                Cada{' '}
                <input className="field amount" inputMode="numeric" aria-label="Cada cuántos" value={draft.interval} onChange={(e) => setDraft({ ...draft, interval: e.target.value })} />{' '}
                {UNITS[draft.frequency]}
              </label>
            )}
          </div>
          <div className="toolbar wrap">
            <label className="small">
              Primera fecha{' '}
              <input className="field" type="date" required value={draft.first_due} onChange={(e) => setDraft({ ...draft, first_due: e.target.value })} />
            </label>
            {draft.frequency !== 'once' && (
              <label className="small">
                Hasta (opcional){' '}
                <input className="field" type="date" value={draft.ends_on} onChange={(e) => setDraft({ ...draft, ends_on: e.target.value })} />
              </label>
            )}
          </div>
          {!draft.income && (
            <label>
              Categoría (opcional)
              <select className="field" value={draft.category_id} onChange={(e) => setDraft({ ...draft, category_id: e.target.value })}>
                <option value="">Sin categoría</option>
                {categories
                  .filter((c) => !c.hidden)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
              </select>
            </label>
          )}
          <label className="small">
            <input type="checkbox" checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} /> Activo
          </label>
          {error && <p className="error small" role="alert">{error}</p>}
          <div className="toolbar">
            <button className="btn primary" type="submit">
              Guardar
            </button>
            <button className="btn" type="button" onClick={() => setEditing(null)}>
              Cancelar
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
