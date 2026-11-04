import { type FormEvent, useState } from 'react'
import { ApiError, api, type AutomationRule, type AutomationRuleInput, type RulePreview } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { FieldError } from '../../components/FieldError'
import { ErrorState, Loading } from '../../components/LoadState'
import { notifyUndoable } from '../../lib/undo'
import { useLoad } from '../../lib/useLoad'

type Cond = AutomationRuleInput['conditions'][number]
type Act = AutomationRuleInput['actions'][number]

const PHASES = { before: 'Antes', normal: 'Normal', after: 'Después' } as const
const FIELDS: Record<Cond['field'], string> = {
  description: 'El concepto',
  merchant: 'El comercio',
  amount: 'El importe (en valor absoluto)',
  direction: 'Sale o entra dinero',
  account: 'La cuenta',
  bank_type: 'El tipo del banco',
}
const TEXT_OPS = { contains: 'contiene', starts_with: 'empieza por', equals: 'es igual a' } as const
const ACTIONS: Record<Act['type'], string> = {
  set_category: 'Poner la categoría',
  set_kind: 'Poner el tipo',
  add_tags: 'Añadir etiquetas',
  set_note: 'Poner la nota',
  set_merchant: 'Asignar el comercio',
}
const KINDS = { expense: 'Gasto', income: 'Ingreso', internal_transfer: 'Entre cuentas', savings_transfer: 'Hucha' } as const
const FIELD_LABELS: Record<string, string> = { category_id: 'Categoría', kind: 'Tipo', tags: 'Etiquetas', note: 'Nota', merchant: 'Comercio' }

type CondDraft = { field: Cond['field']; op: string; a: string; b: string }
type ActDraft = { type: Act['type']; value: string }
type Draft = { name: string; personal: boolean; phase: keyof typeof PHASES; priority: string; conditions: CondDraft[]; actions: ActDraft[] }

const blank = (): Draft => ({
  name: '',
  personal: false,
  phase: 'normal',
  priority: '',
  conditions: [{ field: 'description', op: 'contains', a: '', b: '' }],
  actions: [{ type: 'set_category', value: '' }],
})

function toCond(c: CondDraft): Cond {
  switch (c.field) {
    case 'amount':
      return { field: 'amount', op: 'between', value: [c.a, c.b] }
    case 'direction':
      return { field: 'direction', op: 'is', value: c.a || 'expense' }
    case 'account':
      return { field: 'account', op: 'in', value: c.a ? [c.a] : [] }
    case 'description':
      return { field: 'description', op: c.op, value: c.a }
    default:
      return { field: c.field, op: 'equals', value: c.a }
  }
}

function toAct(a: ActDraft): Act {
  return a.type === 'add_tags'
    ? { type: 'add_tags', value: a.value.split(',').map((x) => x.trim()).filter(Boolean) }
    : { type: a.type, value: a.value }
}

function fromRule(r: AutomationRule): Draft {
  return {
    name: r.name,
    personal: r.personal,
    phase: r.phase,
    priority: String(r.priority),
    conditions: r.conditions.map((c) => {
      const v = c.value
      return {
        field: c.field,
        op: c.op,
        a: Array.isArray(v) ? (c.field === 'amount' ? (v[0] ?? '') : (v[0] ?? '')) : v,
        b: Array.isArray(v) && c.field === 'amount' ? (v[1] ?? '') : '',
      }
    }),
    actions: r.actions.map((a) => ({ type: a.type, value: Array.isArray(a.value) ? a.value.join(', ') : a.value })),
  }
}

function toInput(d: Draft): AutomationRuleInput {
  return {
    name: d.name,
    personal: d.personal,
    phase: d.phase,
    priority: d.priority.trim() === '' ? null : Number(d.priority),
    enabled: true,
    conditions: d.conditions.map(toCond),
    actions: d.actions.map(toAct),
  }
}

/** Reglas con condiciones, acciones y fases (ADR-0020, OF-1101 y OF-1102). */
export function AutomationRules() {
  const { me, categories, categoryById, notify } = useHousehold()
  const rules = useLoad<AutomationRule[]>('automation', (s) => api.automationRules(s))
  const [editing, setEditing] = useState<string | 'new' | null>(null)
  const [draft, setDraft] = useState<Draft>(blank)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<{ title: string; data: RulePreview; ruleId?: string } | null>(null)

  function open(rule?: AutomationRule) {
    setEditing(rule ? rule.id : 'new')
    setDraft(rule ? fromRule(rule) : blank())
    setError(null)
    setPreview(null)
  }

  function describe(c: Cond): string {
    const v = c.value
    if (c.field === 'description') return `${FIELDS.description} ${TEXT_OPS[c.op as keyof typeof TEXT_OPS] ?? c.op} «${String(v)}»`
    if (c.field === 'amount' && Array.isArray(v)) return `importe entre ${v[0]} y ${v[1]}`
    if (c.field === 'direction') return v === 'income' ? 'entra dinero' : 'sale dinero'
    if (c.field === 'account') return `cuenta ${Array.isArray(v) ? v.length : 1} elegida`
    return `${FIELDS[c.field]} «${String(v)}»`
  }

  function describeAct(a: Act): string {
    if (a.type === 'set_category') return `categoría ${categoryById.get(String(a.value))?.name ?? '—'}`
    if (a.type === 'set_kind') return `tipo ${KINDS[a.value as keyof typeof KINDS] ?? String(a.value)}`
    if (a.type === 'add_tags') return `etiquetas ${(a.value as string[]).map((t) => `#${t}`).join(' ')}`
    if (a.type === 'set_note') return `nota «${String(a.value)}»`
    return `comercio ${String(a.value)}`
  }

  async function run<T>(fn: () => Promise<T>, fallback: string): Promise<T | undefined> {
    try {
      return await fn()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : fallback)
      return undefined
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const input = toInput(draft)
    const r = await run(
      () => (editing === 'new' ? api.createAutomationRule(input) : api.updateAutomationRule(String(editing), input)),
      'No se ha podido guardar la regla',
    )
    if (!r) return
    setEditing(null)
    notifyUndoable(notify, me, `Regla «${r.rule.name}» guardada`, r.operation_id, rules.reload)
    rules.reload()
  }

  async function test() {
    setError(null)
    const data = await run(() => api.previewAutomationDraft(toInput(draft)), 'No se ha podido probar la regla')
    if (data) setPreview({ title: draft.name || 'Regla nueva', data })
  }

  async function testSaved(r: AutomationRule) {
    const data = await run(() => api.previewAutomationRule(r.id), 'No se ha podido probar la regla')
    if (data) setPreview({ title: r.name, data, ruleId: r.id })
  }

  async function apply(id: string, name: string) {
    const r = await run(() => api.applyAutomationRule(id), 'No se ha podido aplicar la regla')
    if (!r) return
    setPreview(null)
    notifyUndoable(notify, me, `«${name}»: ${r.changed} ${r.changed === 1 ? 'movimiento cambiado' : 'movimientos cambiados'}`, r.operation_id, rules.reload)
  }

  async function toggle(r: AutomationRule) {
    const input = { ...toInput(fromRule(r)), enabled: !r.enabled }
    const res = await run(() => api.updateAutomationRule(r.id, input), 'No se ha podido cambiar la regla')
    if (res) {
      rules.reload()
      notifyUndoable(notify, me, `Regla «${r.name}» ${r.enabled ? 'desactivada' : 'activada'}`, res.operation_id, rules.reload)
    }
  }

  async function remove(r: AutomationRule) {
    const res = await run(() => api.deleteAutomationRule(r.id), 'No se ha podido borrar la regla')
    if (res) {
      notifyUndoable(notify, me, `Regla «${r.name}» borrada`, res.operation_id, rules.reload)
      rules.reload()
    }
  }

  const setCond = (i: number, patch: Partial<CondDraft>) =>
    setDraft({ ...draft, conditions: draft.conditions.map((c, j) => (j === i ? { ...c, ...patch } : c)) })
  const setAct = (i: number, patch: Partial<ActDraft>) =>
    setDraft({ ...draft, actions: draft.actions.map((a, j) => (j === i ? { ...a, ...patch } : a)) })

  return (
    <section className="automation" aria-label="Reglas con condiciones">
      <h2>Reglas con condiciones</h2>
      <p className="small muted">
        «Si pasa esto, haz aquello». Se evalúan por fases (antes, normal y después) y por prioridad: la primera que fija un campo gana, y
        nunca se pisa lo que fijaste a mano. Las reglas aprendidas de arriba deciden la categoría cuando ninguna de estas lo hace.
      </p>
      {rules.error && <ErrorState message={rules.error} onRetry={rules.reload} />}
      {!rules.data && !rules.error && <Loading />}
      {rules.data && rules.data.length > 0 && (
        <ul className="plain" aria-label="Tus reglas con condiciones">
          {rules.data.map((r) => (
            <li key={r.id} className="card">
              <strong>{r.name}</strong>{' '}
              <span className="small muted">
                · {PHASES[r.phase]} · prioridad {r.priority}
                {r.personal ? ' · Personal, solo la ves tú' : ''}
                {r.enabled ? '' : ' · desactivada'}
              </span>
              <div className="small">Si {r.conditions.map(describe).join(' y ')} → {r.actions.map(describeAct).join(', ')}</div>
              <div className="toolbar">
                <button className="btn small" type="button" aria-label={`Probar la regla ${r.name}`} onClick={() => void testSaved(r)}>
                  Probar
                </button>
                <button className="btn small" type="button" aria-label={`Editar la regla ${r.name}`} onClick={() => open(r)}>
                  Editar
                </button>
                <button className="btn small" type="button" aria-label={`${r.enabled ? 'Desactivar' : 'Activar'} la regla ${r.name}`} onClick={() => void toggle(r)}>
                  {r.enabled ? 'Desactivar' : 'Activar'}
                </button>
                <button className="btn small" type="button" aria-label={`Borrar la regla ${r.name}`} onClick={() => void remove(r)}>
                  Borrar
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {editing === null && (
        <button className="btn" type="button" onClick={() => open()}>
          Nueva regla
        </button>
      )}
      {editing !== null && (
        <form className="card stack" aria-label="Regla" onSubmit={(e) => void save(e)}>
          <label>
            Nombre
            <input className="field" required maxLength={80} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </label>
          <div className="toolbar wrap">
            <label className="small">
              Fase{' '}
              <select className="field" value={draft.phase} onChange={(e) => setDraft({ ...draft, phase: e.target.value as Draft['phase'] })}>
                {Object.entries(PHASES).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label className="small">
              Prioridad (menor, antes){' '}
              <input className="field amount" inputMode="numeric" value={draft.priority} placeholder="auto" onChange={(e) => setDraft({ ...draft, priority: e.target.value })} />
            </label>
            {editing === 'new' && (
              <label className="small">
                <input type="checkbox" checked={draft.personal} onChange={(e) => setDraft({ ...draft, personal: e.target.checked })} /> Solo mía
              </label>
            )}
          </div>
          <fieldset className="stack">
            <legend className="small">Si… (todas a la vez)</legend>
            {draft.conditions.map((c, i) => (
              <div className="toolbar wrap" key={i}>
                <select className="field" aria-label={`Condición ${i + 1}`} value={c.field} onChange={(e) => setCond(i, { field: e.target.value as Cond['field'], op: 'contains', a: '', b: '' })}>
                  {Object.entries(FIELDS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
                {c.field === 'description' && (
                  <select className="field" aria-label={`Cómo compara la condición ${i + 1}`} value={c.op} onChange={(e) => setCond(i, { op: e.target.value })}>
                    {Object.entries(TEXT_OPS).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                )}
                {c.field === 'direction' ? (
                  <select className="field" aria-label={`Valor de la condición ${i + 1}`} value={c.a || 'expense'} onChange={(e) => setCond(i, { a: e.target.value })}>
                    <option value="expense">Sale dinero</option>
                    <option value="income">Entra dinero</option>
                  </select>
                ) : c.field === 'amount' ? (
                  <>
                    <input className="field amount" aria-label={`Importe mínimo de la condición ${i + 1}`} inputMode="decimal" placeholder="mín." value={c.a} onChange={(e) => setCond(i, { a: e.target.value })} />
                    <input className="field amount" aria-label={`Importe máximo de la condición ${i + 1}`} inputMode="decimal" placeholder="máx." value={c.b} onChange={(e) => setCond(i, { b: e.target.value })} />
                  </>
                ) : (
                  <input className="field" aria-label={`Valor de la condición ${i + 1}`} maxLength={100} value={c.a} onChange={(e) => setCond(i, { a: e.target.value })} />
                )}
                {draft.conditions.length > 1 && (
                  <button className="btn small" type="button" onClick={() => setDraft({ ...draft, conditions: draft.conditions.filter((_, j) => j !== i) })}>
                    Quitar
                  </button>
                )}
              </div>
            ))}
            <button className="btn small" type="button" disabled={draft.conditions.length >= 8} onClick={() => setDraft({ ...draft, conditions: [...draft.conditions, { field: 'description', op: 'contains', a: '', b: '' }] })}>
              Añadir condición
            </button>
          </fieldset>
          <fieldset className="stack">
            <legend className="small">Entonces…</legend>
            {draft.actions.map((a, i) => (
              <div className="toolbar wrap" key={i}>
                <select className="field" aria-label={`Acción ${i + 1}`} value={a.type} onChange={(e) => setAct(i, { type: e.target.value as Act['type'], value: '' })}>
                  {Object.entries(ACTIONS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
                {a.type === 'set_category' ? (
                  <select className="field" aria-label={`Valor de la acción ${i + 1}`} value={a.value} onChange={(e) => setAct(i, { value: e.target.value })}>
                    <option value="">Elige…</option>
                    {categories.filter((c) => !c.hidden).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.icon} {c.name}
                      </option>
                    ))}
                  </select>
                ) : a.type === 'set_kind' ? (
                  <select className="field" aria-label={`Valor de la acción ${i + 1}`} value={a.value} onChange={(e) => setAct(i, { value: e.target.value })}>
                    <option value="">Elige…</option>
                    {Object.entries(KINDS).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="field"
                    aria-label={`Valor de la acción ${i + 1}`}
                    placeholder={a.type === 'add_tags' ? 'viaje, regalos' : a.type === 'set_merchant' ? 'MERCADONA' : ''}
                    maxLength={200}
                    value={a.value}
                    onChange={(e) => setAct(i, { value: e.target.value })}
                  />
                )}
                {draft.actions.length > 1 && (
                  <button className="btn small" type="button" onClick={() => setDraft({ ...draft, actions: draft.actions.filter((_, j) => j !== i) })}>
                    Quitar
                  </button>
                )}
              </div>
            ))}
            <button className="btn small" type="button" disabled={draft.actions.length >= 6} onClick={() => setDraft({ ...draft, actions: [...draft.actions, { type: 'add_tags', value: '' }] })}>
              Añadir acción
            </button>
          </fieldset>
          <FieldError id="automation-error" message={error} />
          <div className="toolbar">
            <button className="btn primary" type="submit">
              Guardar la regla
            </button>
            <button className="btn" type="button" onClick={() => void test()}>
              Probar sin guardar
            </button>
            <button className="btn" type="button" onClick={() => setEditing(null)}>
              Cancelar
            </button>
          </div>
        </form>
      )}
      {preview && (
        <div className="card" role="region" aria-label="Vista previa de la regla">
          <h3>«{preview.title}»</h3>
          <p role="status">
            {preview.data.count === 0
              ? 'No cambiaría ningún movimiento de los que ves.'
              : `Cambiaría ${preview.data.count} ${preview.data.count === 1 ? 'movimiento' : 'movimientos'}${preview.data.count > preview.data.items.length ? ` (se enseñan ${preview.data.items.length})` : ''}.`}
          </p>
          {preview.data.items.length > 0 && (
            <ul className="plain small" aria-label="Movimientos que cambiarían">
              {preview.data.items.map((p) => (
                <li key={p.transaction.id}>
                  <strong>{p.transaction.description}</strong>:{' '}
                  {p.changes.map((c) => `${FIELD_LABELS[c.field] ?? c.field}: ${fmt(c.field, c.before, categoryById)} → ${fmt(c.field, c.after, categoryById)}`).join(' · ')}
                </li>
              ))}
            </ul>
          )}
          <div className="toolbar">
            {preview.ruleId && preview.data.count > 0 && (
              <button className="btn primary" type="button" onClick={() => void apply(preview.ruleId!, preview.title)}>
                Aplicar a lo existente
              </button>
            )}
            <button className="btn" type="button" onClick={() => setPreview(null)}>
              Cerrar
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

function fmt(field: string, value: string | boolean | null, categoryById: Map<string, { icon: string; name: string }>): string {
  if (value === null || value === '') return '—'
  if (field === 'category_id') {
    const c = categoryById.get(String(value))
    return c ? `${c.icon} ${c.name}` : '—'
  }
  if (field === 'kind') return KINDS[String(value) as keyof typeof KINDS] ?? String(value)
  if (field === 'tags') return String(value).split('|').map((t) => `#${t}`).join(' ')
  return String(value)
}
