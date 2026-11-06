import { type FormEvent, useState } from 'react'
import { ApiError, api, type Goal, type SavingsOverview } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { Ring } from '../../components/charts'
import { ErrorState, Loading } from '../../components/LoadState'
import {
  ceilDiv,
  centsToAmount,
  currentMonth,
  formatMoney,
  formatMoneyRounded,
  monthLabel,
  parseAmountInput,
  shiftMonth,
  toCents,
} from '../../lib/format'
import { useLoad } from '../../lib/useLoad'
import { useCategoryMeta } from '../insights/meta'

const SIMULATED = ['restaurantes', 'super', 'suscripciones', 'transporte', 'ocio', 'ropa']

function GoalCard({ goal, onChanged }: { goal: Goal; onChanged: () => void }) {
  const { notify } = useHousehold()
  const [editing, setEditing] = useState(false)
  const [monthly, setMonthly] = useState(goal.monthly.amount)
  const [saved, setSaved] = useState(goal.saved.amount)

  async function save(e: FormEvent) {
    e.preventDefault()
    const m = parseAmountInput(monthly)
    const s = parseAmountInput(saved)
    if (m === null || (!goal.account_id && s === null)) {
      notify('Revisa las cantidades (por ejemplo 150 o 150,50)')
      return
    }
    try {
      await api.updateGoal(goal.id, goal.account_id ? { monthly: m } : { monthly: m, saved: s })
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
          </div>
        )}
      </div>
    </article>
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
      await api.createGoal({ name: name.trim(), icon, target: t, monthly: m, saved: s, deadline: deadline || null })
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
  const [cuts, setCuts] = useState<Record<string, number>>({ restaurantes: 25, super: 10 })
  const rows = overview.averages
    .filter((a) => a.category_id && SIMULATED.includes(categoryById.get(a.category_id)?.slug ?? ''))
    .filter((a) => toCents(a.average.amount) > 0n)
    .sort((a, b) => SIMULATED.indexOf(categoryById.get(a.category_id!)!.slug!) - SIMULATED.indexOf(categoryById.get(b.category_id!)!.slug!))
  if (rows.length === 0) return <p className="muted">Hacen falta movimientos categorizados para simular recortes.</p>

  const currency = rows[0].average.currency
  const saving = (avg: string, slug: string) => (toCents(avg) * BigInt(cuts[slug] ?? 0)) / 100n
  const extra = rows.reduce((s, r) => s + saving(r.average.amount, categoryById.get(r.category_id!)!.slug!), 0n)
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
        const slug = categoryById.get(r.category_id!)!.slug!
        const pct = cuts[slug] ?? 0
        return (
          <div className="sim-row" key={slug}>
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
              onChange={(e) => setCuts((c) => ({ ...c, [slug]: Number(e.target.value) }))}
            />
            <strong className="num">{pct} %</strong>
            <span className="num pos">+{formatMoneyRounded({ amount: centsToAmount(saving(r.average.amount, slug)), currency })}/mes</span>
          </div>
        )
      })}
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
      <NewGoal onCreated={reload} />

      <div className="grid g2 spaced-card">
        <div className="card">
          <h2>Ideas para ahorrar</h2>
          {o.ideas.length === 0 && <p className="muted">Aún no hay datos suficientes para proponer ideas.</p>}
          <ul className="plain">
            {o.ideas.map((i) => (
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
                </div>
                <span className="save">{formatMoneyRounded(i.yearly_saving)}/año</span>
              </li>
            ))}
          </ul>
        </div>
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
                      {m.name} · {r.months} meses
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
