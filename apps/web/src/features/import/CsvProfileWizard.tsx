import { type FormEvent, useState } from 'react'
import { ApiError, api, type CsvProfile, type CsvProfileInput, type CsvSample, type CsvTest } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { formatDate, formatMoney } from '../../lib/format'
import { notifyUndoable } from '../../lib/undo'

const DELIMITERS = { ',': 'coma', ';': 'punto y coma', '\t': 'tabulador', '|': 'barra vertical' }
const ENCODINGS = { 'utf-8': 'UTF-8', cp1252: 'Windows-1252 (Excel en español)', 'latin-1': 'Latin-1' }
const DATE_FORMATS: Record<string, string> = {
  '%d/%m/%Y': '31/12/2026',
  '%d/%m/%y': '31/12/26',
  '%d-%m-%Y': '31-12-2026',
  '%d.%m.%Y': '31.12.2026',
  '%Y-%m-%d': '2026-12-31',
  '%Y/%m/%d': '2026/12/31',
  '%m/%d/%Y': '12/31/2026 (mes primero)',
  '%m/%d/%y': '12/31/26 (mes primero)',
}

/** Crear un perfil de CSV desde un archivo de ejemplo: elegir columnas, probar y guardar (OF-1105). */
export function CsvProfileWizard({ onSaved, onClose }: { onSaved: (profile: CsvProfile) => void; onClose: () => void }) {
  const { me, notify } = useHousehold()
  const [file, setFile] = useState<File | null>(null)
  const [sample, setSample] = useState<CsvSample | null>(null)
  const [name, setName] = useState('')
  const [cfg, setCfg] = useState<Omit<CsvProfileInput, 'name'>>({
    delimiter: ',',
    encoding: 'utf-8',
    skip_rows: 0,
    has_header: true,
    date_column: 0,
    date_format: '%d/%m/%Y',
    description_columns: [1],
    amount_mode: 'single',
    amount_column: 2,
    debit_column: null,
    credit_column: null,
    decimal_separator: ',',
    invert_sign: false,
    balance_column: null,
  })
  const [test, setTest] = useState<CsvTest | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const columns = Math.max(0, ...(sample?.rows.map((r) => r.length) ?? [0]))
  const options = Array.from({ length: columns }, (_, i) => i)
  const label = (i: number) => `Columna ${i + 1}`
  const input: CsvProfileInput = { name, ...cfg }

  async function run<T>(fn: () => Promise<T>, then: (v: T) => void, fallback: string) {
    setBusy(true)
    setError(null)
    try {
      then(await fn())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : fallback)
    } finally {
      setBusy(false)
    }
  }

  async function pick(f: File | null) {
    setFile(f)
    setSample(null)
    setTest(null)
    if (!f) return
    await run(
      () => api.csvSample(f),
      (s) => {
        setSample(s)
        setCfg((c) => ({ ...c, delimiter: s.delimiter, encoding: s.encoding }))
      },
      'No se ha podido leer el archivo',
    )
  }

  const set = (patch: Partial<typeof cfg>) => {
    setCfg({ ...cfg, ...patch })
    setTest(null)
  }

  async function probe() {
    if (!file) return
    await run(() => api.testCsvProfile(file, input), setTest, 'No se ha podido probar el perfil')
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    await run(
      () => api.createCsvProfile(input),
      (r) => {
        notifyUndoable(notify, me, `Perfil «${r.profile.name}» guardado`, r.operation_id, () => undefined)
        onSaved(r.profile)
      },
      'No se ha podido guardar el perfil',
    )
  }

  const select = (labelText: string, value: number | null, onChange: (v: number | null) => void, optional = false) => (
    <label className="small">
      {labelText}{' '}
      <select className="field" value={value ?? ''} onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}>
        {optional && <option value="">Ninguna</option>}
        {options.map((i) => (
          <option key={i} value={i}>
            {label(i)}
          </option>
        ))}
      </select>
    </label>
  )

  return (
    <form className="card stack" aria-label="Nuevo perfil de CSV" onSubmit={(e) => void save(e)}>
      <h2>Nuevo perfil de CSV</h2>
      <p className="small muted">Elige un extracto de ejemplo de tu banco y dime en qué columna está cada dato. El archivo se procesa en tu servidor.</p>
      <label>
        Extracto de ejemplo
        <input type="file" accept=".csv,.txt" aria-label="Extracto de ejemplo" onChange={(e) => void pick(e.target.files?.[0] ?? null)} />
      </label>
      {sample && (
        <>
          <div className="scroll" role="region" aria-label="Primeras filas del archivo" tabIndex={0}>
            <table className="rows small">
              <thead>
                <tr>
                  {options.map((i) => (
                    <th key={i}>{label(i)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sample.rows.map((r, n) => (
                  <tr key={n}>
                    {options.map((i) => (
                      <td key={i}>{r[i] ?? ''}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <label>
            Nombre del perfil
            <input className="field" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <div className="toolbar wrap">
            <label className="small">
              Separador{' '}
              <select className="field" value={cfg.delimiter} onChange={(e) => set({ delimiter: e.target.value })}>
                {Object.entries(DELIMITERS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label className="small">
              Codificación{' '}
              <select className="field" value={cfg.encoding} onChange={(e) => set({ encoding: e.target.value })}>
                {Object.entries(ENCODINGS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label className="small">
              Líneas antes de la cabecera{' '}
              <input className="field amount" type="number" min={0} max={50} value={cfg.skip_rows} onChange={(e) => set({ skip_rows: Number(e.target.value) })} />
            </label>
            <label className="small">
              <input type="checkbox" checked={cfg.has_header} onChange={(e) => set({ has_header: e.target.checked })} /> Tiene fila de cabecera
            </label>
          </div>
          <div className="toolbar wrap">
            {select('Fecha en', cfg.date_column, (v) => set({ date_column: v ?? 0 }))}
            <label className="small">
              Formato de fecha{' '}
              <select className="field" value={cfg.date_format} onChange={(e) => set({ date_format: e.target.value })}>
                {Object.entries(DATE_FORMATS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <fieldset className="toolbar wrap">
            <legend className="small">Concepto (hasta 4 columnas)</legend>
            {options.map((i) => (
              <label className="small" key={i}>
                <input
                  type="checkbox"
                  checked={cfg.description_columns.includes(i)}
                  onChange={(e) => {
                    const next = e.target.checked ? [...cfg.description_columns, i].sort() : cfg.description_columns.filter((c) => c !== i)
                    set({ description_columns: next.slice(0, 4) })
                  }}
                />{' '}
                {label(i)}
              </label>
            ))}
          </fieldset>
          <fieldset className="toolbar wrap">
            <legend className="small">Importe</legend>
            <label className="small">
              <input type="radio" name="amount-mode" checked={cfg.amount_mode === 'single'} onChange={() => set({ amount_mode: 'single', amount_column: 2 })} /> Una columna
            </label>
            <label className="small">
              <input type="radio" name="amount-mode" checked={cfg.amount_mode === 'debit_credit'} onChange={() => set({ amount_mode: 'debit_credit', debit_column: 3, credit_column: 4 })} /> Debe y haber
            </label>
            {cfg.amount_mode === 'single' ? (
              <>
                {select('Importe en', cfg.amount_column ?? 0, (v) => set({ amount_column: v }))}
                <label className="small">
                  <input type="checkbox" checked={cfg.invert_sign} onChange={(e) => set({ invert_sign: e.target.checked })} /> Los gastos vienen en positivo
                </label>
              </>
            ) : (
              <>
                {select('Debe (salidas) en', cfg.debit_column ?? 0, (v) => set({ debit_column: v }))}
                {select('Haber (entradas) en', cfg.credit_column ?? 0, (v) => set({ credit_column: v }))}
              </>
            )}
            <label className="small">
              Separador decimal{' '}
              <select className="field" value={cfg.decimal_separator} onChange={(e) => set({ decimal_separator: e.target.value as ',' | '.' })}>
                <option value=",">coma (12,30)</option>
                <option value=".">punto (12.30)</option>
              </select>
            </label>
            {select('Saldo en', cfg.balance_column ?? null, (v) => set({ balance_column: v }), true)}
          </fieldset>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {test && (
            <div role="region" aria-label="Resultado de la prueba">
              <p role="status">
                {test.total} {test.total === 1 ? 'fila se lee' : 'filas se leen'} bien
                {test.skipped_total > 0 ? ` y ${test.skipped_total} se descartan` : ''}.
              </p>
              <ul className="plain small" aria-label="Filas de ejemplo">
                {test.rows.slice(0, 6).map((r) => (
                  <li key={r.line}>
                    {formatDate(r.booked_at)} · {r.description} · {formatMoney(r.amount, { signed: true })}
                  </li>
                ))}
              </ul>
              {test.skipped.length > 0 && (
                <ul className="plain small muted" aria-label="Filas descartadas">
                  {test.skipped.slice(0, 4).map((s) => (
                    <li key={s.line}>
                      Línea {s.line}: {s.reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
      {!sample && error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="toolbar">
        <button className="btn" type="button" disabled={!sample || busy} onClick={() => void probe()}>
          Probar con el archivo
        </button>
        <button className="btn primary" type="submit" disabled={!sample || !name.trim() || !test || test.total === 0 || busy}>
          Guardar el perfil
        </button>
        <button className="btn" type="button" onClick={onClose}>
          Cancelar
        </button>
      </div>
    </form>
  )
}
