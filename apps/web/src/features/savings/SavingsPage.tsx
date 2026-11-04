import { type FormEvent, useState } from 'react'
import { ApiError, api, type Contribution, type Goal, type GoalShare, type SavingsOverview } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { Ring } from '../../components/charts'
import { ErrorState, Loading } from '../../components/LoadState'
import {
  ceilDiv,
  centsToAmount,
  currentMonth,
  formatDate,
  formatMoney,
  formatMoneyRounded,
  monthLabel,
  parseAmountInput,
  shiftMonth,
  toCents,
} from '../../lib/format'
import { notifyUndoable } from '../../lib/undo'
import { useLoad } from '../../lib/useLoad'
import { useCategoryMeta } from '../insights/meta'

/** Recortes con los que arranca el simulador; el resto de categorías empiezan en 0 %. */
const DEFAULT_CUTS: Record<string, number> = { restaurantes: 25, super: 10 }
const VISIBLE_ROWS = 6

/** Aportaciones anotadas a mano en un objetivo sin hucha (OF-1206). */
function Contributions({ goal, onChanged }: { goal: Goal; onChanged: () => void }) {
  const { me, notify } = useHousehold()
  const [open, setOpen] = useState(false)
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const list = useLoad<Contribution[]>(`contrib-${goal.id}-${open}`, (s) => (open ? api.goalContributions(goal.id, s) : Promise.resolve([])))

  async function add(sign: 1 | -1) {
    const value = parseAmountInput(amount)
    if (value === null || toCents(value) === 0n) {
      notify('Escribe una cantidad mayor que cero, por ejemplo 150')
      return
    }
    try {
      const r = await api.addContribution(goal.id, sign === 1 ? value : `-${value}`, note)
      setAmount('')
      setNote('')
      notifyUndoable(notify, me, sign === 1 ? 'Aportación anotada' : 'Retirada anotada', r.operation_id, () => {
        list.reload()
        onChanged()
      })
      list.reload()
      onChanged()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido anotar')
    }
  }

  async function remove(c: Contribution) {
    try {
      const r = await api.deleteContribution(goal.id, c.id)
      notifyUndoable(notify, me, 'Aportación borrada', r.operation_id, () => {
        list.reload()
        onChanged()
      })
      list.reload()
      onChanged()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido borrar')
    }
  }

  return (
    <div className="stack">
      <div className="toolbar wrap">
        <label className="small">
          Cantidad{' '}
          <input className="field amount" aria-label={`Cantidad para ${goal.name}`} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <label className="small">
          Nota{' '}
          <input className="field" aria-label={`Nota para ${goal.name}`} maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button className="btn small" type="button" aria-label={`Aportar a ${goal.name}`} onClick={() => void add(1)}>
          Aportar
        </button>
        <button className="btn small" type="button" aria-label={`Retirar de ${goal.name}`} onClick={() => void add(-1)}>
          Retirar
        </button>
      </div>
      <button className="btn small" type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? 'Ocultar aportaciones' : 'Ver aportaciones'}
      </button>
      {open && list.data && (
        <ul className="plain small" aria-label={`Aportaciones a ${goal.name}`}>
          {list.data.length === 0 && <li className="muted">Aún no hay aportaciones anotadas.</li>}
          {list.data.slice(0, 10).map((c) => (
            <li key={c.id} className="toolbar inline">
              <span>
                {formatDate(c.made_on)} · {formatMoney(c.amount, { signed: true })}
                {c.note ? ` · ${c.note}` : ''}
              </span>
              <button className="btn small" type="button" aria-label={`Borrar la aportación de ${formatMoney(c.amount)}`} onClick={() => void remove(c)}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Un enlace a «Pagos programados» con la aportación mensual ya rellenada: el día 1 del mes que viene. */
function reminderHref(goal: Goal): string {
  const now = new Date()
  const first = new Date(now.getFullYear(), now.getMonth() + 1, 1)
  const date = `${first.getFullYear()}-${String(first.getMonth() + 1).padStart(2, '0')}-01`
  const params = new URLSearchParams({ nombre: `Aportación a ${goal.name}`.slice(0, 60), importe: `-${goal.monthly.amount}`, fecha: date })
  return `#pagos?${params.toString()}`
}

function GoalCard({ goal, onChanged }: { goal: Goal; onChanged: () => void }) {
  const { notify } = useHousehold()
  const [editing, setEditing] = useState(false)
  const [monthly, setMonthly] = useState(goal.monthly.amount)
  const [saved, setSaved] = useState(goal.saved.amount)
  const [priority, setPriority] = useState(String(goal.priority))

  async function save(e: FormEvent) {
    e.preventDefault()
    const m = parseAmountInput(monthly)
    const s = parseAmountInput(saved)
    if (m === null || (!goal.account_id && s === null)) {
      notify('Revisa las cantidades (por ejemplo 150 o 150,50)')
      return
    }
    try {
      const p = Number(priority)
      if (!Number.isInteger(p) || p < 1 || p > 99) {
        notify('La prioridad va de 1 a 99 (1 es la primera)')
        return
      }
      await api.updateGoal(goal.id, goal.account_id ? { monthly: m, priority: p } : { monthly: m, saved: s, priority: p })
      setEditing(false)
      onChanged()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido guardar')
    }
  }

  async function remove() {
    if (!window.confirm(`¿Borrar el objetivo «${goal.name}»?`)) return
    try {
      await api.deleteGoal(goal.id)
      onChanged()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido borrar')
    }
  }

  return (
    <article className="card goal" aria-label={goal.name}>
      <Ring percent={goal.progress} label={goal.name} />
      <div>
        <h2>
          {goal.icon} {goal.name}
        </h2>
        <div>
          <strong>{formatMoneyRounded(goal.saved)}</strong> <span className="muted">de {formatMoneyRounded(goal.target)}</span>
          {goal.account_id && <span className="small muted"> · saldo de la hucha</span>}
        </div>
        <p className="small muted">
          {goal.months_to_go === 0
            ? '¡Conseguido!'
            : goal.eta
              ? `Apartando ${formatMoneyRounded(goal.monthly)}/mes lo alcanzáis en ${monthLabel(goal.eta)}`
              : 'Indica cuánto apartáis al mes para calcular la fecha'}
          {goal.deadline && ` · objetivo ${monthLabel(goal.deadline)}`}
        </p>
        {goal.on_track === false && goal.needed_monthly && (
          <p className="notice warn small">
            Para llegar a tiempo haría falta apartar {formatMoneyRounded(goal.needed_monthly)}/mes.
          </p>
        )}
        {goal.on_track === false && !goal.needed_monthly && (
          <p className="notice warn small">La fecha límite ya ha llegado y aún faltan {formatMoneyRounded(goal.remaining)}.</p>
        )}
        {editing ? (
          <form className="toolbar" onSubmit={save} aria-label={`Editar ${goal.name}`}>
            <label className="small">
              Al mes{' '}
              <input className="field amount" value={monthly} onChange={(e) => setMonthly(e.target.value)} inputMode="decimal" />
            </label>
            {!goal.account_id && (
              <label className="small">
                Ahorrado{' '}
                <input className="field amount" value={saved} onChange={(e) => setSaved(e.target.value)} inputMode="decimal" />
              </label>
            )}
            <label className="small">
              Prioridad{' '}
              <input className="field amount" aria-label="Prioridad (1 es la primera)" value={priority} onChange={(e) => setPriority(e.target.value)} inputMode="numeric" />
            </label>
            <button className="btn primary small" type="submit">
              Guardar
            </button>
            <button className="btn small" type="button" onClick={() => setEditing(false)}>
              Cancelar
            </button>
          </form>
        ) : (
          <div className="toolbar">
            <button className="btn small" type="button" onClick={() => setEditing(true)}>
              Actualizar
            </button>
            <button className="btn small" type="button" onClick={() => void remove()}>
              Borrar
            </button>
            {toCents(goal.monthly.amount) > 0n && (
              <a className="small" href={reminderHref(goal)} aria-label={`Programar la aportación mensual a ${goal.name}`}>
                Programar la aportación mensual
              </a>
            )}
          </div>
        )}
        {!goal.account_id && <Contributions goal={goal} onChanged={onChanged} />}
      </div>
    </article>
  )
}

/** Cómo repartir una cantidad entre los objetivos por prioridad (OF-1206). Solo sugiere. */
function SplitSuggestion() {
  const { notify } = useHousehold()
  const [amount, setAmount] = useState('')
  const [shares, setShares] = useState<GoalShare[] | null>(null)

  async function suggest(e: FormEvent) {
    e.preventDefault()
    const value = parseAmountInput(amount)
    if (value === null || toCents(value) === 0n) {
      notify('Escribe una cantidad mayor que cero, por ejemplo 300')
      return
    }
    try {
      setShares(await api.goalSplit(value))
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido calcular el reparto')
    }
  }

  return (
    <form className="card stack" aria-label="Repartir entre objetivos" onSubmit={(e) => void suggest(e)}>
      <h2>¿Os sobra algo este mes?</h2>
      <p className="small muted">Escribid cuánto y os decimos cómo repartirlo: primero el objetivo más prioritario, hasta lo que le falta.</p>
      <div className="toolbar wrap">
        <label className="small">
          Cantidad{' '}
          <input className="field amount" aria-label="Cantidad a repartir" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <button className="btn small" type="submit">
          Sugerir reparto
        </button>
      </div>
      {shares && shares.length === 0 && <p className="small muted">No hay objetivos a los que les falte dinero.</p>}
      {shares && shares.length > 0 && (
        <ul className="plain" aria-label="Reparto sugerido">
          {shares.map((s) => (
            <li key={s.goal_id}>
              {s.name}: <strong>{formatMoney(s.amount)}</strong> <span className="small muted">(le faltan {formatMoneyRounded(s.remaining)})</span>
            </li>
          ))}
        </ul>
      )}
    </form>
  )
}

function NewGoal({ onCreated }: { onCreated: () => void }) {
  const { notify } = useHousehold()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [icon, setIcon] = useState('🎯')
  const [target, setTarget] = useState('')
  const [monthly, setMonthly] = useState('')
  const [saved, setSaved] = useState('')
  const [deadline, setDeadline] = useState('')

  async function create(e: FormEvent) {
    e.preventDefault()
    const t = parseAmountInput(target)
    const m = parseAmountInput(monthly || '0')
    const s = parseAmountInput(saved || '0')
    if (!name.trim() || t === null || m === null || s === null) {
      notify('Revisa el nombre y las cantidades')
      return
    }
    try {
      await api.createGoal({ name: name.trim(), icon, target: t, monthly: m, saved: s, deadline: deadline || null, priority: 50 })
      setOpen(false)
      setName('')
      setTarget('')
      setMonthly('')
      setSaved('')
      setDeadline('')
      onCreated()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido crear el objetivo')
    }
  }

  if (!open)
    return (
      <button className="btn" type="button" onClick={() => setOpen(true)}>
        + Nuevo objetivo
      </button>
    )
  return (
    <form className="card upload" onSubmit={create} aria-label="Nuevo objetivo">
      <div className="toolbar">
        <input className="field icon-field" aria-label="Icono" value={icon} maxLength={8} onChange={(e) => setIcon(e.target.value)} />
        <input className="field" aria-label="Nombre del objetivo" placeholder="Nombre (p. ej. Coche nuevo)" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="toolbar">
        <label className="small">
          Meta (€) <input className="field amount" aria-label="Meta" value={target} inputMode="decimal" onChange={(e) => setTarget(e.target.value)} />
        </label>
        <label className="small">
          Ya ahorrado <input className="field amount" aria-label="Ya ahorrado" value={saved} inputMode="decimal" onChange={(e) => setSaved(e.target.value)} />
        </label>
        <label className="small">
          Al mes <input className="field amount" aria-label="Al mes" value={monthly} inputMode="decimal" onChange={(e) => setMonthly(e.target.value)} />
        </label>
        <label className="small">
          Fecha límite (opcional){' '}
          <input className="field" type="month" aria-label="Fecha límite" value={deadline} min={shiftMonth(currentMonth(), 1)} onChange={(e) => setDeadline(e.target.value)} />
        </label>
      </div>
      <div className="toolbar end">
        <button className="btn" type="button" onClick={() => setOpen(false)}>
          Cancelar
        </button>
        <button className="btn primary" type="submit">
          Crear objetivo
        </button>
      </div>
    </form>
  )
}

function Simulator({ overview }: { overview: SavingsOverview }) {
  const { categoryById } = useHousehold()
  const meta = useCategoryMeta()
  const [cuts, setCuts] = useState<Record<string, number>>({})
  const [showAll, setShowAll] = useState(false)
  // Todas las categorías con gasto, de mayor a menor media (OF-806).
  const all = overview.averages
    .filter((a) => a.category_id && categoryById.has(a.category_id) && toCents(a.average.amount) > 0n)
    .sort((a, b) => Number(toCents(b.average.amount) - toCents(a.average.amount)))
  const cutOf = (id: string) => cuts[id] ?? DEFAULT_CUTS[categoryById.get(id)?.slug ?? ''] ?? 0
  const rows = showAll ? all : all.filter((a, i) => i < VISIBLE_ROWS || cutOf(a.category_id!) > 0)
  if (all.length === 0) return <p className="muted">Hacen falta movimientos categorizados para simular recortes.</p>

  const currency = all[0].average.currency
  const saving = (avg: string, id: string) => (toCents(avg) * BigInt(cutOf(id))) / 100n
  // El ahorro cuenta todas las categorías, también las que están plegadas.
  const extra = all.reduce((s, r) => s + saving(r.average.amount, r.category_id!), 0n)
  const goal = overview.goals.find((g) => toCents(g.remaining.amount) > 0n)
  // Mismo «hoy» que el servidor, para que coincida con la fecha de la tarjeta del objetivo.
  const etaWith = (monthlyCents: bigint) =>
    goal && monthlyCents > 0n
      ? shiftMonth(overview.month, Number(ceilDiv(toCents(goal.remaining.amount), monthlyCents)))
      : null
  const before = goal ? etaWith(toCents(goal.monthly.amount)) : null
  const after = goal ? etaWith(toCents(goal.monthly.amount) + extra) : null
  const gained = before && after ? monthsBetween(after, before) : 0

  return (
    <div>
      {rows.map((r) => {
        const m = meta(r.category_id)
        const id = r.category_id!
        const pct = cutOf(id)
        return (
          <div className="sim-row" key={id}>
            <span aria-hidden="true">{m.icon}</span>
            <span>
              {m.name}
              <span className="block small muted">media {formatMoneyRounded(r.average)}/mes</span>
            </span>
            <input
              type="range"
              min={0}
              max={50}
              step={5}
              value={pct}
              aria-label={`Recorte en ${m.name}`}
              aria-valuetext={`${pct} %`}
              onChange={(e) => setCuts((c) => ({ ...c, [id]: Number(e.target.value) }))}
            />
            <strong className="num">{pct} %</strong>
            <span className="num pos">+{formatMoneyRounded({ amount: centsToAmount(saving(r.average.amount, id)), currency })}/mes</span>
          </div>
        )
      })}
      {all.length > rows.length && (
        <button className="btn small" type="button" onClick={() => setShowAll(true)}>
          Mostrar las {all.length - rows.length} categorías restantes
        </button>
      )}
      {showAll && all.length > VISIBLE_ROWS && (
        <button className="btn small" type="button" onClick={() => setShowAll(false)}>
          Mostrar menos
        </button>
      )}
      <div className="sim-total">
        <div>
          <div className="small muted">Ahorro extra</div>
          <strong>
            {formatMoneyRounded({ amount: centsToAmount(extra), currency })}/mes ·{' '}
            {formatMoneyRounded({ amount: centsToAmount(extra * 12n), currency })}/año
          </strong>
        </div>
        {goal && after && (
          <div className="small">
            {goal.icon} {goal.name}: <strong>{monthLabel(after)}</strong>
            {before && before !== after && (
              <div className="muted">
                en vez de {monthLabel(before)}
                {gained > 0 && ` (${gained} ${gained === 1 ? 'mes' : 'meses'} antes)`}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function monthsBetween(a: string, b: string): number {
  const [ay, am] = a.split('-').map(Number)
  const [by, bm] = b.split('-').map(Number)
  return by * 12 + bm - (ay * 12 + am)
}

/** Ideas para ahorrar. Las descartadas se esconden para todo el hogar y se pueden recuperar (OF-806). */
function Ideas({ ideas, onChanged }: { ideas: SavingsOverview['ideas']; onChanged: () => void }) {
  const { notify } = useHousehold()
  const [showDismissed, setShowDismissed] = useState(false)
  const active = ideas.filter((i) => !i.dismissed)
  const dismissed = ideas.filter((i) => i.dismissed)

  async function setDismissed(id: string, value: boolean) {
    try {
      if (value) await api.dismissIdea(id)
      else await api.restoreIdea(id)
      onChanged()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido cambiar la idea')
    }
  }

  const item = (i: SavingsOverview['ideas'][number]) => (
    <li key={i.id} className="insight">
      <span className="ic" aria-hidden="true">
        {i.icon}
      </span>
      <div>
        <strong>{i.title}</strong>
        <div className="small muted">{i.detail}</div>
        <div className="small muted">
          {i.evidence}
          {i.assumption && ` · ${i.assumption}`}
        </div>
        <button
          className="linkish small"
          type="button"
          aria-label={`${i.dismissed ? 'Recuperar' : 'Descartar'}: ${i.title}`}
          onClick={() => void setDismissed(i.id, !i.dismissed)}
        >
          {i.dismissed ? 'Recuperar' : 'Descartar'}
        </button>
      </div>
      <span className="save">{formatMoneyRounded(i.yearly_saving)}/año</span>
    </li>
  )

  return (
    <div className="card">
      <h2>Ideas para ahorrar</h2>
      {ideas.length === 0 && <p className="muted">Aún no hay datos suficientes para proponer ideas.</p>}
      {ideas.length > 0 && active.length === 0 && <p className="muted">Has descartado todas las ideas.</p>}
      <ul className="plain" aria-label="Ideas">
        {active.map(item)}
      </ul>
      {dismissed.length > 0 && (
        <>
          <button className="btn small" type="button" aria-expanded={showDismissed} onClick={() => setShowDismissed((v) => !v)}>
            {showDismissed ? 'Ocultar' : 'Ver'} {dismissed.length === 1 ? '1 idea descartada' : `${dismissed.length} ideas descartadas`}
          </button>
          {showDismissed && (
            <ul className="plain dismissed" aria-label="Ideas descartadas">
              {dismissed.map(item)}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

/** El enlace a «Pagos programados» con este cargo ya rellenado: el mes que viene, el mismo día. */
function scheduleHref(r: { merchant: string; amount: { amount: string }; last_date: string; category_id: string | null }): string {
  const [y, m, d] = r.last_date.split('-').map(Number)
  const next = new Date(Date.UTC(y, m, 1))
  const last = new Date(Date.UTC(next.getUTCFullYear(), next.getUTCMonth() + 1, 0)).getUTCDate()
  next.setUTCDate(Math.min(d, last))
  const params = new URLSearchParams({ nombre: r.merchant, importe: `-${r.amount.amount.replace(/^-/, '')}`, fecha: next.toISOString().slice(0, 10) })
  if (r.category_id) params.set('categoria', r.category_id)
  return `#pagos?${params.toString()}`
}

export function SavingsPage() {
  const meta = useCategoryMeta()
  const overview = useLoad<SavingsOverview>('overview', (s) => api.savingsOverview(s))
  const reload = overview.reload
  if (overview.error) return <ErrorState message={overview.error} onRetry={reload} />
  if (!overview.data) return <Loading />
  const o = overview.data

  return (
    <section>
      <h1>Ahorrar</h1>
      <p className="lead">
        {o.average_saved ? (
          <>
            Ahorráis de media <strong>{formatMoneyRounded(o.average_saved)}</strong> al mes (
            {o.months.length === 1 ? 'último mes' : `últimos ${o.months.length} meses`}). Aquí tenéis vuestros objetivos e ideas
            calculadas con vuestros propios gastos.
          </>
        ) : (
          'Importad algunos meses de movimientos para ver vuestra media de ahorro e ideas.'
        )}
      </p>

      <div className="grid g2">
        {o.goals.map((g) => (
          <GoalCard key={`${g.id}-${g.monthly.amount}-${g.saved.amount}`} goal={g} onChanged={reload} />
        ))}
      </div>
      {o.goals.length > 0 && <SplitSuggestion />}
      <NewGoal onCreated={reload} />

      <div className="grid g2 spaced-card">
        <Ideas ideas={o.ideas} onChanged={reload} />
        <div className="card">
          <h2>Simulador: ¿y si recortamos…?</h2>
          <Simulator overview={o} />
        </div>
      </div>

      <div className="card spaced-card">
        <h2>Cuotas fijas: {formatMoney(o.recurring_total)} al mes</h2>
        {o.recurring.length === 0 && <p className="muted">No se han detectado cargos que se repitan cada mes.</p>}
        <table role="table" className="rows recurring">
          <caption className="sr-only">Cargos que se repiten cada mes</caption>
          <thead role="rowgroup">
            <tr role="row">
              <th role="columnheader">Comercio</th>
              <th role="columnheader">Cambios de precio</th>
              <th role="columnheader" className="num">Cuota</th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {o.recurring.map((r) => {
              const m = meta(r.category_id)
              const last = r.changes[r.changes.length - 1]
              return (
                <tr role="row" key={`${r.merchant}-${r.last_date}-${r.amount.amount}`}>
                  <td role="cell">
                    {m.icon} {r.merchant}
                    <div className="small muted">
                      {m.name} · {r.months} meses ·{' '}
                      <a href={scheduleHref(r)} aria-label={`Programar el pago de ${r.merchant}`}>
                        Programar
                      </a>
                    </div>
                  </td>
                  <td role="cell">
                    {last && (
                      <span className={`pill ${toCents(last.after.amount) > toCents(last.before.amount) ? 'up' : 'down'}`}>
                        {formatMoney(last.before)} → {formatMoney(last.after)} en {monthLabel(last.month)}
                      </span>
                    )}
                  </td>
                  <td role="cell" className="num">{formatMoney(r.amount)}/mes</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
