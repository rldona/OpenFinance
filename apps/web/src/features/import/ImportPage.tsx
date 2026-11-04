import { type FormEvent, useEffect, useState } from 'react'
import {
  ApiError,
  api,
  type Account,
  type ImportPreview,
  type ImportResult,
} from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { centsToAmount, formatDate, formatMoney, toCents } from '../../lib/format'
import { kindLabel } from '../transactions/labels'
import { ImportHistory } from './ImportHistory'

const FORMATS: Record<string, { accept: string; label: string }> = {
  revolut: { accept: '.csv,.xlsx', label: 'CSV o Excel' },
  bankinter: { accept: '.xlsx', label: 'Excel' },
}
const SUPPORTED = new Set(Object.keys(FORMATS))

type Step = { kind: 'upload' } | { kind: 'review'; preview: ImportPreview } | { kind: 'done'; result: ImportResult }

function Steps({ current }: { current: number }) {
  return (
    <div className="steps">
      {['Subir extracto', 'Revisar', 'Listo'].map((label, i) => (
        <div
          key={label}
          className={`step ${i === current ? 'on' : i < current ? 'done' : ''}`}
          aria-current={i === current ? 'step' : undefined}
        >
          {i < current ? '✓' : i + 1}. {label}
        </div>
      ))}
    </div>
  )
}

export function ImportPage() {
  const { me, categoryById, refreshUncategorized } = useHousehold()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountId, setAccountId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [step, setStep] = useState<Step>({ kind: 'upload' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [acceptMissing, setAcceptMissing] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    api.accounts(controller.signal).then(
      (list) => {
        setAccounts(list)
        const first = list.find((a) => SUPPORTED.has(a.institution))
        if (first) setAccountId(first.id)
        else setError('Ninguna de vuestras cuentas admite todavía importar extractos')
      },
      () => {
        if (!controller.signal.aborted) setError('No se han podido cargar las cuentas')
      },
    )
    return () => controller.abort()
  }, [])

  async function run<T>(fn: () => Promise<T>, then: (value: T) => void) {
    setBusy(true)
    setError(null)
    try {
      then(await fn())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido conectar con OpenFinance')
    } finally {
      setBusy(false)
    }
  }

  function preview(e: FormEvent) {
    e.preventDefault()
    if (!file || !accountId) return
    void run(
      () => api.previewImport(accountId, file),
      (p) => {
        setAcceptMissing(false)
        setStep({ kind: 'review', preview: p })
      },
    )
  }

  function restart() {
    setFile(null)
    setError(null)
    setStep({ kind: 'upload' })
  }

  const errorBox = error && (
    <p className="error" role="alert">
      {error}
    </p>
  )

  if (step.kind === 'done') {
    const r = step.result
    return (
      <section>
        <h1>Importar extracto</h1>
        <Steps current={2} />
        <div className="card">
          <h2>✓ {r.created === 1 ? 'Importado 1 movimiento' : `Importados ${r.created} movimientos`}</h2>
          <p className="muted">
            {r.duplicates} ya estaban en OpenFinance y {r.skipped} filas no se han importado. Volver a subir el mismo
            extracto no crea duplicados.
          </p>
          <div className="toolbar">
            <a className="btn primary" href="#movimientos">
              Ver movimientos
            </a>
            <button className="btn" type="button" onClick={restart}>
              Importar otro
            </button>
          </div>
        </div>
      </section>
    )
  }

  if (step.kind === 'review') {
    const p = step.preview
    const account = accounts.find((a) => a.id === p.account_id)
    const missing = p.members_without_recharge
    const others = missing.filter((id) => id !== me.user.id).map((id) => me.members.find((m) => m.id === id)?.display_name ?? 'Alguien')
    const iMiss = missing.includes(me.user.id)
    const who = iMiss
      ? others.length
        ? `Ni tú ni ${others.join(' ni ')} tenéis`
        : 'No tienes'
      : `${others.join(' y ')} no ${others.length === 1 ? 'tiene' : 'tienen'}`
    const diff = p.bank_balance ? toCents(p.balance_after_import.amount) - toCents(p.bank_balance.amount) : 0n
    return (
      <section>
        <h1>Importar extracto</h1>
        <Steps current={1} />
        <div className="grid g3">
          <div className="card kpi">
            <div className="label">Nuevos</div>
            <div className="value pos">{p.new_count}</div>
          </div>
          <div className="card kpi">
            <div className="label">Ya importados</div>
            <div className="value">{p.duplicate_count}</div>
          </div>
          <div className="card kpi">
            <div className="label">No se importan</div>
            <div className="value">{p.skipped_count}</div>
          </div>
        </div>

        {p.bank_balance &&
          (diff === 0n ? (
            <div className="notice ok">
              ✓ Tras importar, el saldo de {account?.name ?? 'la cuenta'} coincidirá con el del banco:{' '}
              <strong>{formatMoney(p.bank_balance)}</strong>
            </div>
          ) : (
            <div className="notice warn" role="status">
              El saldo no cuadrará con el del banco: OpenFinance tendrá {formatMoney(p.balance_after_import)} y el banco
              dice {formatMoney(p.bank_balance)} (diferencia{' '}
              {formatMoney({ amount: centsToAmount(diff), currency: p.bank_balance.currency }, { signed: true })}). Puede
              faltar un extracto anterior o el saldo inicial no ser correcto.
            </div>
          ))}
        {missing.length > 0 && (
          <div className="notice warn" role="alert">
            <p>
              <strong>{who} guardada la tarjeta con la que se recarga la conjunta.</strong>{' '}
              Sus «Recarga de *NNNN» entrarán como ingreso y no como su aportación. Guardadla en <a href="#ajustes">Ajustes</a>{' '}
              antes de importar, o corregidlas después una a una.
            </p>
            <label className="small">
              <input type="checkbox" checked={acceptMissing} onChange={(e) => setAcceptMissing(e.target.checked)} /> Importar
              igualmente
            </label>
          </div>
        )}
        {p.balance_mismatches.length > 0 && (
          <div className="notice warn">
            El propio extracto no cuadra en {p.balance_mismatches.length} punto(s) (líneas{' '}
            {p.balance_mismatches.map((m) => m.line).join(', ')}): puede que falten movimientos.
          </div>
        )}

        <div className="card">
          <table role="table" className="rows preview">
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader">Fecha</th>
                <th role="columnheader">Concepto</th>
                <th role="columnheader">Tipo</th>
                <th role="columnheader" className="num">Importe</th>
                <th role="columnheader">
                  <span className="sr-only">Estado</span>
                </th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {p.rows.map((r) => {
                const label = kindLabel(r, me, categoryById)
                return (
                  <tr role="row" key={r.line} className={r.duplicate ? 'dim' : ''}>
                    <td role="cell" className="muted small">{formatDate(r.booked_at)}</td>
                    <td role="cell">{r.description}</td>
                    <td role="cell">
                      <span className={`tag tag-${label.tone}`}>{label.text}</span>
                      {r.category_id && <span className="small muted"> · regla</span>}
                    </td>
                    <td role="cell" className="num">{formatMoney(r.amount, { signed: true })}</td>
                    <td role="cell" className="small muted">{r.duplicate ? 'Ya importado' : 'Nuevo'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {p.skipped.length > 0 && (
            <details>
              <summary className="small">Filas que no se importan ({p.skipped.length})</summary>
              <ul className="small muted">
                {p.skipped.map((s) => (
                  <li key={s.line}>
                    Línea {s.line}: {s.description || '—'} · {s.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {errorBox}
          <div className="toolbar end">
            <button className="btn" type="button" onClick={restart} disabled={busy}>
              Atrás
            </button>
            <button
              className="btn primary"
              type="button"
              disabled={busy || p.new_count === 0 || (missing.length > 0 && !acceptMissing)}
              onClick={() =>
                void run(
                  () => api.commitImport(p.id),
                  (result) => {
                    setStep({ kind: 'done', result })
                    refreshUncategorized()
                  },
                )
              }
            >
              {p.new_count === 0
                ? 'Nada nuevo que importar'
                : busy
                  ? 'Importando…'
                  : `Importar ${p.new_count} movimiento${p.new_count === 1 ? '' : 's'}`}
            </button>
          </div>
        </div>
      </section>
    )
  }

  const selected = accounts.find((a) => a.id === accountId)
  const format = (selected && FORMATS[selected.institution]) ?? FORMATS.revolut

  return (
    <section>
      <h1>Importar extracto</h1>
      <p className="lead">
        Revolut: cuenta → Extracto → formato Excel o CSV. Bankinter: Movimientos → descargar en Excel (.xlsx). Nada se
        guarda hasta que lo confirméis.
      </p>
      <Steps current={0} />
      <form className="card upload" onSubmit={preview}>
        <label>
          Cuenta
          <select className="field" value={accountId} onChange={(e) => setAccountId(e.target.value)} required>
            {accounts.map((a) => (
              <option key={a.id} value={a.id} disabled={!SUPPORTED.has(a.institution)}>
                {a.name}
                {SUPPORTED.has(a.institution) ? '' : ' (próximamente)'}
              </option>
            ))}
          </select>
        </label>
        <label className="dropzone">
          <span>{file ? `📄 ${file.name}` : `📄 Elige el extracto (${format.label})`}</span>
          <input
            type="file"
            accept={format.accept}
            aria-label="Extracto"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <p className="small muted">El archivo se procesa en vuestro servidor y no sale a ningún servicio externo.</p>
        {errorBox}
        <div className="toolbar end">
          <button className="btn primary" type="submit" disabled={!file || !accountId || busy}>
            {busy ? 'Leyendo…' : 'Ver vista previa'}
          </button>
        </div>
      </form>
      <ImportHistory accounts={accounts} />
    </section>
  )
}
