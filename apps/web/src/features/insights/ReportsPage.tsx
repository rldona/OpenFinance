import { useEffect, useState } from 'react'
import { ApiError, api, downloadReportCsv, type Account, type Category, type Report, type ReportDefinition, type SavedReport } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { currentMonth, formatMoney, shiftMonth } from '../../lib/format'

const MEASURES: { id: ReportDefinition['measure']; label: string }[] = [
  { id: 'spent', label: 'Gasto' },
  { id: 'income', label: 'Ingresos' },
  { id: 'saved', label: 'Ahorro' },
  { id: 'net', label: 'Ingresos menos gasto' },
]
const GROUPS: { id: ReportDefinition['group_by']; label: string }[] = [
  { id: 'category', label: 'Categoría' },
  { id: 'merchant', label: 'Comercio' },
  { id: 'account', label: 'Cuenta' },
  { id: 'month', label: 'Mes' },
]

/** Informes a medida (ADR-0025, OF-1503): se ejecutan con lo que ve quien los pide. */
export function ReportsPage() {
  const { notify } = useHousehold()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [saved, setSaved] = useState<SavedReport[]>([])
  const [from, setFrom] = useState(shiftMonth(currentMonth(), -2))
  const [to, setTo] = useState(currentMonth())
  const [measure, setMeasure] = useState<ReportDefinition['measure']>('spent')
  const [groupBy, setGroupBy] = useState<ReportDefinition['group_by']>('category')
  const [accountId, setAccountId] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [minAmount, setMinAmount] = useState('')
  const [tags, setTags] = useState('')
  const [name, setName] = useState('')
  const [shared, setShared] = useState(false)
  const [result, setResult] = useState<{ title: string; report: Report } | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    api.accounts(controller.signal).then(setAccounts, () => undefined)
    api.categories(controller.signal).then(setCategories, () => undefined)
    api.savedReports(controller.signal).then(setSaved, () => undefined)
    return () => controller.abort()
  }, [])

  const definition: ReportDefinition = {
    from_month: from,
    to_month: to,
    measure,
    group_by: groupBy,
    account_ids: accountId ? [accountId] : [],
    category_ids: categoryId ? [categoryId] : [],
    uncategorized: false,
    tags: tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean),
    min_amount: minAmount.trim() || null,
  }

  async function run(action: () => Promise<void>, failure: string) {
    setBusy(true)
    try {
      await action()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : failure)
    } finally {
      setBusy(false)
    }
  }

  const execute = () =>
    run(async () => setResult({ title: 'Resultado', report: await api.runReport(definition) }), 'No se ha podido ejecutar el informe')

  const csv = () =>
    run(async () => {
      const blob = await downloadReportCsv(definition)
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = 'informe.csv'
      link.click()
      URL.revokeObjectURL(link.href)
    }, 'No se ha podido descargar el informe')

  const save = () =>
    run(async () => {
      const created = await api.saveReport(name.trim(), shared, definition)
      setSaved((all) => [...all, created].sort((a, b) => a.name.localeCompare(b.name)))
      setName('')
      notify('Informe guardado')
    }, 'No se ha podido guardar el informe')

  const runSaved = (r: SavedReport) =>
    run(async () => setResult({ title: r.name, report: await api.runSavedReport(r.id) }), 'No se ha podido ejecutar el informe')

  const remove = (r: SavedReport) =>
    run(async () => {
      await api.deleteSavedReport(r.id)
      setSaved((all) => all.filter((x) => x.id !== r.id))
      notify('Informe borrado')
    }, 'No se ha podido borrar el informe')

  return (
    <div className="stack">
      <section className="card stack" aria-label="Definir informe">
        <h2>Informe a medida</h2>
        <p className="small muted">
          Se calcula con las cuentas que ves tú. Si lo compartes, la otra persona lo ejecuta con las suyas: se comparte la definición,
          no los datos.
        </p>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            void execute()
          }}
        >
          <label className="field">
            <span>Desde</span>
            <input type="month" value={from} onChange={(e) => setFrom(e.target.value)} required />
          </label>
          <label className="field">
            <span>Hasta</span>
            <input type="month" value={to} onChange={(e) => setTo(e.target.value)} required />
          </label>
          <label className="field">
            <span>Qué medir</span>
            <select value={measure} onChange={(e) => setMeasure(e.target.value as ReportDefinition['measure'])}>
              {MEASURES.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Agrupar por</span>
            <select value={groupBy} onChange={(e) => setGroupBy(e.target.value as ReportDefinition['group_by'])}>
              {GROUPS.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Cuenta</span>
            <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              <option value="">Todas las que veo</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Categoría</span>
            <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">Todas</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Importe mínimo</span>
            <input inputMode="decimal" value={minAmount} onChange={(e) => setMinAmount(e.target.value)} placeholder="10.00" />
          </label>
          <label className="field">
            <span>Etiquetas (separadas por comas)</span>
            <input value={tags} onChange={(e) => setTags(e.target.value)} />
          </label>
          <div className="row">
            <button type="submit" className="btn primary" disabled={busy}>
              Ejecutar
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void csv()}>
              Descargar CSV
            </button>
          </div>
        </form>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            void save()
          }}
        >
          <label className="field">
            <span>Nombre para guardarlo</span>
            <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="check">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} /> Compartir con el hogar
          </label>
          <button type="submit" className="btn" disabled={busy || !name.trim()}>
            Guardar informe
          </button>
        </form>
      </section>

      {result && (
        <section className="card" aria-label="Resultado del informe">
          <h2>{result.title}</h2>
          {result.report.rows.length === 0 ? (
            <p className="muted">Sin movimientos para esta definición.</p>
          ) : (
            <table className="table">
              <caption className="sr-only">Resultado del informe</caption>
              <thead>
                <tr>
                  <th scope="col">Grupo</th>
                  <th scope="col">Importe</th>
                  <th scope="col">Movimientos</th>
                </tr>
              </thead>
              <tbody>
                {result.report.rows.map((r) => (
                  <tr key={r.key ?? 'none'}>
                    <th scope="row">{r.label}</th>
                    <td className="num">{formatMoney(r.amount)}</td>
                    <td className="num">{r.count}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row">Total</th>
                  <td className="num">
                    <strong>{formatMoney(result.report.total)}</strong>
                  </td>
                  <td className="num">{result.report.count}</td>
                </tr>
              </tfoot>
            </table>
          )}
          {result.report.hidden_rows > 0 && (
            <p className="small muted">Hay {result.report.hidden_rows} grupos más pequeños que no caben en la lista; el total los incluye.</p>
          )}
          {result.report.ignored_accounts > 0 && (
            <p className="small warn">
              {result.report.ignored_accounts} cuentas del filtro no las ves tú, así que no entran en este resultado.
            </p>
          )}
          {result.report.missing_rates.length > 0 && (
            <p className="small warn">No entran los movimientos en {result.report.missing_rates.join(', ')}: falta su tipo de cambio.</p>
          )}
        </section>
      )}

      <section className="card" aria-label="Informes guardados">
        <h2>Guardados</h2>
        {saved.length === 0 ? (
          <p className="muted">Todavía no has guardado ninguno.</p>
        ) : (
          <ul className="plain">
            {saved.map((r) => (
              <li key={r.id}>
                <strong>{r.name}</strong>
                {r.shared && !r.mine && ' · compartido contigo'}
                {r.shared && r.mine && ' · compartido'}{' '}
                <button type="button" className="btn small" disabled={busy} onClick={() => void runSaved(r)}>
                  Ejecutar {r.name}
                </button>{' '}
                {r.mine && (
                  <button type="button" className="btn small" disabled={busy} onClick={() => void remove(r)}>
                    Borrar {r.name}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
