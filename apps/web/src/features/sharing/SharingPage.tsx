import { useMemo, useState } from 'react'
import {
  ApiError,
  api,
  type Balances,
  type TripEvent,
  type Expense,
  type ExpenseInput,
  type Participant,
  type Settlement,
  type SplitPart,
} from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate, formatMoney } from '../../lib/format'
import { useLoad } from '../../lib/useLoad'

type Method = ExpenseInput['method']

const METHODS: { id: Method; label: string; hint: string }[] = [
  { id: 'equal', label: 'A partes iguales', hint: '' },
  { id: 'percentage', label: 'Por porcentaje', hint: 'Porcentaje (suman 100)' },
  { id: 'exact', label: 'Por importe', hint: 'Importe (suman el total)' },
  { id: 'shares', label: 'Por pesos', hint: 'Peso (2 es el doble que 1)' },
]

const today = () => new Date().toISOString().slice(0, 10)

type Data = {
  participants: Participant[]
  expenses: Expense[]
  balances: Balances
  settlements: Settlement[]
  events: TripEvent[]
}

/** Reparto de gastos del hogar y sus invitados (ADR-0026, OF-1602). */
export function SharingPage() {
  const { me, notify } = useHousehold()
  const canWrite = me.role !== 'viewer'
  const [busy, setBusy] = useState(false)
  const { data, error, reload } = useLoad<Data>(
    'sharing',
    async (signal) => {
      const [participants, expenses, balances, settlements, events] = await Promise.all([
        api.participants(signal),
        api.expenses(signal),
        api.balances(signal),
        api.settlements(signal),
        api.events(signal),
      ])
      return { participants, expenses, balances, settlements, events }
    },
    'No se ha podido cargar el reparto',
  )

  async function run(action: () => Promise<void>, failure: string) {
    setBusy(true)
    try {
      await action()
      reload()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : failure)
    } finally {
      setBusy(false)
    }
  }

  const names = useMemo(() => new Map((data?.participants ?? []).map((p) => [p.id, p.name])), [data])
  const nameOf = (id: string) => names.get(id) ?? data?.balances.balances.find((b) => b.participant.id === id)?.participant.name ?? 'Alguien'
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <Loading />

  const active = data.participants.filter((p) => p.active)
  const guests = data.participants.filter((p) => p.is_guest && p.active)
  const guestIds = new Set(guests.map((g) => g.id))

  return (
    <div className="stack">
      <section className="card" aria-label="Quién debe a quién">
        <h2>Quién debe a quién</h2>
        <ul className="plain" aria-label="Saldos">
          {data.balances.balances
            .filter((b) => b.participant.active || Number(b.net.amount) !== 0)
            .map((b) => (
              <li key={b.participant.id}>
                {b.participant.name}
                {!b.participant.active && ' (ya no está)'} ·{' '}
                <strong className="num">{formatMoney(b.net, { signed: true })}</strong>{' '}
                <span className="small muted">
                  pagó {formatMoney(b.paid)} · le tocaba {formatMoney(b.share)}
                </span>
              </li>
            ))}
        </ul>
        {data.balances.suggestions.length === 0 ? (
          <p className="muted">Todo saldado.</p>
        ) : (
          <ul className="plain" aria-label="Pagos sugeridos">
            {data.balances.suggestions.map((t) => (
              <li key={`${t.from_id}-${t.to_id}`}>
                {nameOf(t.from_id)} paga <strong className="num">{formatMoney(t.amount)}</strong> a {nameOf(t.to_id)}{' '}
                {canWrite && (t.from_id === me.user.id || guestIds.has(t.from_id)) && (
                  <button
                    type="button"
                    className="btn small"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        await api.createSettlement({ from_id: t.from_id, to_id: t.to_id, amount: t.amount.amount, on: today() })
                        notify('Pago registrado: falta que lo confirme quien lo recibe')
                      }, 'No se ha podido registrar el pago')
                    }
                  >
                    Registrar pago de {nameOf(t.from_id)}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card" aria-label="Pagos entre personas">
        <h2>Pagos entre personas</h2>
        {data.settlements.length === 0 ? (
          <p className="muted">Todavía no hay pagos registrados.</p>
        ) : (
          <ul className="plain">
            {data.settlements.map((s) => {
              const mine = s.to_id === me.user.id || guestIds.has(s.to_id)
              return (
                <li key={s.id}>
                  {nameOf(s.from_id)} → {nameOf(s.to_id)} · <strong className="num">{formatMoney(s.amount)}</strong> ·{' '}
                  {formatDate(s.on)} · {s.status === 'pending' ? 'pendiente de confirmar' : s.status === 'confirmed' ? 'confirmado' : 'cancelado'}{' '}
                  {canWrite && s.status === 'pending' && mine && (
                    <button
                      type="button"
                      className="btn small"
                      disabled={busy}
                      onClick={() => void run(async () => void (await api.confirmSettlement(s.id)), 'No se ha podido confirmar')}
                    >
                      Confirmar pago de {nameOf(s.from_id)}
                    </button>
                  )}{' '}
                  {canWrite && s.status === 'pending' && (
                    <button
                      type="button"
                      className="btn small"
                      disabled={busy}
                      onClick={() => void run(async () => void (await api.cancelSettlement(s.id)), 'No se ha podido cancelar')}
                    >
                      Cancelar pago de {nameOf(s.from_id)}
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <EventsCard events={data.events} canWrite={canWrite} busy={busy} run={run} nameOf={nameOf} />

      {canWrite && (
        <ExpenseForm people={active} events={data.events.filter((e) => !e.closed)} me={me.user.id} busy={busy} run={run} notify={notify} />
      )}

      <section className="card" aria-label="Gastos compartidos">
        <h2>Gastos compartidos</h2>
        {data.expenses.length === 0 ? (
          <p className="muted">Todavía no hay gastos repartidos.</p>
        ) : (
          <ul className="plain">
            {data.expenses.map((e) => (
              <li key={e.id}>
                <strong>{e.description}</strong> · {formatDate(e.on)} · <span className="num">{formatMoney(e.amount)}</span> ·{' '}
                pagó {e.payers.map((p) => nameOf(p.participant_id)).join(' y ')} · se reparte entre{' '}
                {e.parts.map((p) => `${nameOf(p.participant_id)} ${formatMoney(p.amount)}`).join(', ')}{' '}
                {canWrite && (
                  <button
                    type="button"
                    className="btn small"
                    disabled={busy}
                    onClick={() => void run(async () => api.voidExpense(e.id), 'No se ha podido anular el gasto')}
                  >
                    Anular {e.description}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {canWrite && <GuestForm busy={busy} run={run} />}
    </div>
  )
}

type Run = (action: () => Promise<void>, failure: string) => Promise<void>

function GuestForm({ busy, run }: { busy: boolean; run: Run }) {
  const [name, setName] = useState('')
  return (
    <section className="card" aria-label="Invitados">
      <h2>Alguien sin cuenta</h2>
      <p className="small muted">Un invitado no tiene acceso a nada: quien edita anota por él.</p>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault()
          void run(async () => {
            await api.addGuest(name.trim())
            setName('')
          }, 'No se ha podido añadir')
        }}
      >
        <label className="field">
          <span>Nombre</span>
          <input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
        </label>
        <button type="submit" className="btn" disabled={busy || !name.trim()}>
          Añadir invitado
        </button>
      </form>
    </section>
  )
}

function ExpenseForm({
  people,
  events,
  me,
  busy,
  run,
  notify,
}: {
  people: Participant[]
  events: TripEvent[]
  me: string
  busy: boolean
  run: Run
  notify: (message: string) => void
}) {
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [on, setOn] = useState(today())
  const [payer, setPayer] = useState(me)
  const [method, setMethod] = useState<Method>('equal')
  const [chosen, setChosen] = useState<Record<string, boolean>>(() => Object.fromEntries(people.map((p) => [p.id, true])))
  const [values, setValues] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<SplitPart[] | null>(null)
  const [eventId, setEventId] = useState('')

  const shares = (): ExpenseInput['shares'] =>
    people
      .filter((p) => chosen[p.id] ?? false)
      .map((p) => ({ participant_id: p.id, value: method === 'equal' ? null : (values[p.id] ?? '') || null }))

  const body = (): ExpenseInput => ({
    on,
    description: description.trim(),
    amount: amount.trim(),
    payers: [{ participant_id: payer, amount: amount.trim() }],
    method,
    shares: shares(),
    event_id: eventId || null,
  })

  return (
    <section className="card stack" aria-label="Nuevo gasto compartido">
      <h2>Repartir un gasto</h2>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault()
          void run(async () => {
            await api.createExpense(body())
            setDescription('')
            setAmount('')
            setPreview(null)
            notify('Gasto repartido')
          }, 'No se ha podido repartir el gasto')
        }}
      >
        <label className="field">
          <span>Concepto</span>
          <input required value={description} maxLength={200} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label className="field">
          <span>Importe</span>
          <input required inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="90.00" />
        </label>
        <label className="field">
          <span>Fecha</span>
          <input type="date" required value={on} onChange={(e) => setOn(e.target.value)} />
        </label>
        <label className="field">
          <span>Quién pagó</span>
          <select value={payer} onChange={(e) => setPayer(e.target.value)}>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {events.length > 0 && (
          <label className="field">
            <span>Viaje o evento</span>
            <select value={eventId} onChange={(e) => setEventId(e.target.value)}>
              <option value="">Ninguno</option>
              {events.map((ev) => (
                <option key={ev.id} value={ev.id}>
                  {ev.icon} {ev.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="field">
          <span>Cómo se reparte</span>
          <select value={method} onChange={(e) => setMethod(e.target.value as Method)}>
            {METHODS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="stack">
          <legend className="small muted">Entre quién</legend>
          {people.map((p) => (
            <div key={p.id} className="row">
              <label className="check">
                <input
                  type="checkbox"
                  checked={chosen[p.id] ?? false}
                  onChange={(e) => setChosen((c) => ({ ...c, [p.id]: e.target.checked }))}
                />{' '}
                {p.name}
              </label>
              {method !== 'equal' && (chosen[p.id] ?? false) && (
                <input
                  aria-label={`${METHODS.find((m) => m.id === method)?.hint} de ${p.name}`}
                  inputMode="decimal"
                  value={values[p.id] ?? ''}
                  onChange={(e) => setValues((v) => ({ ...v, [p.id]: e.target.value }))}
                />
              )}
            </div>
          ))}
        </fieldset>
        <div className="row">
          <button
            type="button"
            className="btn"
            disabled={busy || !amount.trim()}
            onClick={() =>
              void run(async () => setPreview(await api.previewSplit(amount.trim(), method, shares())), 'No se ha podido calcular el reparto')
            }
          >
            Ver reparto
          </button>
          <button type="submit" className="btn primary" disabled={busy}>
            Repartir
          </button>
        </div>
      </form>
      {preview && (
        <ul className="plain" aria-label="Así quedaría">
          {preview.map((p) => (
            <li key={p.participant_id}>
              {people.find((x) => x.id === p.participant_id)?.name ?? 'Alguien'} · <strong className="num">{formatMoney(p.amount)}</strong>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function EventsCard({
  events,
  canWrite,
  busy,
  run,
  nameOf,
}: {
  events: TripEvent[]
  canWrite: boolean
  busy: boolean
  run: Run
  nameOf: (id: string) => string
}) {
  const [name, setName] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  return (
    <section className="card stack" aria-label="Viajes y eventos">
      <h2>Viajes y eventos</h2>
      {events.length === 0 ? (
        <p className="muted">Un viaje o un evento agrupa gastos para ver cuánto costó y quién debe a quién solo con ellos.</p>
      ) : (
        <ul className="plain">
          {events.map((ev) => (
            <li key={ev.id}>
              {ev.icon} <strong>{ev.name}</strong>
              {ev.closed && ' · cerrado'}{' '}
              <button type="button" className="btn small" onClick={() => setOpen(open === ev.id ? null : ev.id)}>
                {open === ev.id ? `Ocultar resumen de ${ev.name}` : `Ver resumen de ${ev.name}`}
              </button>{' '}
              {canWrite && (
                <button
                  type="button"
                  className="btn small"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => void (ev.closed ? await api.reopenEvent(ev.id) : await api.closeEvent(ev.id)), 'No se ha podido cambiar el evento')
                  }
                >
                  {ev.closed ? `Reabrir ${ev.name}` : `Cerrar ${ev.name}`}
                </button>
              )}
              {open === ev.id && <EventSummaryView id={ev.id} nameOf={nameOf} />}
            </li>
          ))}
        </ul>
      )}
      {canWrite && (
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault()
            void run(async () => {
              await api.createEvent(name.trim())
              setName('')
            }, 'No se ha podido crear el evento')
          }}
        >
          <label className="field">
            <span>Nuevo viaje o evento</span>
            <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </label>
          <button type="submit" className="btn" disabled={busy || !name.trim()}>
            Crear evento
          </button>
        </form>
      )}
    </section>
  )
}

function EventSummaryView({ id, nameOf }: { id: string; nameOf: (id: string) => string }) {
  const { data, error, reload } = useLoad(`event-${id}`, (signal) => api.eventSummary(id, signal), 'No se ha podido cargar el resumen')
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <Loading />
  return (
    <div className="stack" role="region" aria-label={`Resumen de ${data.event.name}`}>
      <p>
        <strong className="num">{formatMoney(data.total)}</strong> en {data.count} {data.count === 1 ? 'gasto' : 'gastos'}.
      </p>
      <ul className="plain" aria-label="Por persona">
        {data.balances.map((b) => (
          <li key={b.participant.id}>
            {b.participant.name} · pagó {formatMoney(b.paid)} · le tocaba {formatMoney(b.share)} ·{' '}
            <strong className="num">{formatMoney(b.net, { signed: true })}</strong>
          </li>
        ))}
      </ul>
      {data.by_category.length > 0 && (
        <ul className="plain" aria-label="Por categoría">
          {data.by_category.map((c) => (
            <li key={c.category_id ?? 'none'}>
              {c.name} · <strong className="num">{formatMoney(c.amount)}</strong>
            </li>
          ))}
        </ul>
      )}
      {data.suggestions.length > 0 && (
        <ul className="plain" aria-label="Para saldarlo">
          {data.suggestions.map((t) => (
            <li key={`${t.from_id}-${t.to_id}`}>
              {nameOf(t.from_id)} paga {formatMoney(t.amount)} a {nameOf(t.to_id)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
