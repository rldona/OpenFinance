import { type FormEvent, useRef, useState } from 'react'
import { ApiError, api, type Account, type AccountType, type MemberPattern, type VersionInfo } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { FieldError } from '../../components/FieldError'
import { invalid } from '../../lib/invalid'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatMoney } from '../../lib/format'
import { ExchangeRates } from './ExchangeRates'
import { BankSettings } from './BankSettings'
import { NotificationSettings } from './NotificationSettings'
import { type Theme, getTheme, setTheme } from '../../lib/theme'
import { useLoad } from '../../lib/useLoad'

const MIN_PASSWORD = 10

function PasswordForm() {
  const { notify } = useHousehold()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [saving, setSaving] = useState(false)
  const [currentError, setCurrentError] = useState<string | null>(null)
  const currentInput = useRef<HTMLInputElement>(null)
  const mismatch = repeat.length > 0 && next !== repeat

  async function save(e: FormEvent) {
    e.preventDefault()
    if (next !== repeat) return
    setSaving(true)
    setCurrentError(null)
    try {
      const r = await api.changePassword(current, next)
      notify(
        r.revoked
          ? `Contraseña cambiada · ${r.revoked === 1 ? '1 sesión cerrada' : `${r.revoked} sesiones cerradas`} en otros dispositivos`
          : 'Contraseña cambiada',
      )
      setCurrent('')
      setNext('')
      setRepeat('')
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        // La contraseña actual es incorrecta: el error va en su campo y el foco vuelve a él.
        setCurrentError(err.message)
        currentInput.current?.focus()
      } else notify(err instanceof ApiError ? err.message : 'No se ha podido cambiar la contraseña')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card settings-form" aria-label="Cambiar la contraseña" onSubmit={(e) => void save(e)}>
      <h2>Tu contraseña</h2>
      <label>
        Contraseña actual
        <input
          ref={currentInput}
          className="field"
          type="password"
          autoComplete="current-password"
          required
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          {...invalid('current-password-error', currentError)}
        />
      </label>
      <FieldError id="current-password-error" message={currentError} />
      <label>
        Nueva contraseña (mín. {MIN_PASSWORD} caracteres)
        <input
          className="field"
          type="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD}
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
      </label>
      <label>
        Repite la nueva
        <input
          className="field"
          type="password"
          autoComplete="new-password"
          required
          value={repeat}
          onChange={(e) => setRepeat(e.target.value)}
          {...invalid('repeat-password-error', mismatch ? 'No coinciden.' : null)}
        />
      </label>
      <FieldError id="repeat-password-error" message={mismatch ? 'No coinciden.' : null} />
      <p className="small muted">Al cambiarla se cierran tus sesiones en otros dispositivos; esta sigue abierta.</p>
      <div className="toolbar">
        <button className="btn primary" type="submit" disabled={saving || mismatch || next.length < MIN_PASSWORD}>
          Cambiar la contraseña
        </button>
      </div>
    </form>
  )
}

const THEMES: Array<[Theme, string]> = [
  ['auto', 'Como el sistema'],
  ['light', 'Claro'],
  ['dark', 'Oscuro'],
]

/** Apariencia (OF-805): se recuerda en este navegador, no en el servidor. */
function Appearance() {
  const [theme, setChoice] = useState<Theme>(getTheme)
  return (
    <fieldset className="card stack appearance">
      <legend className="h2">Apariencia</legend>
      <div className="toolbar" role="radiogroup" aria-label="Apariencia">
        {THEMES.map(([value, label]) => (
          <label key={value} className="small">
            <input
              type="radio"
              name="theme"
              checked={theme === value}
              onChange={() => {
                setChoice(value)
                setTheme(value)
              }}
            />{' '}
            {label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

const TYPE_LABELS: Record<AccountType, string> = {
  bank: 'Banco',
  cash: 'Efectivo',
  card: 'Tarjeta de crédito',
  loan: 'Préstamo',
  investment: 'Inversión',
}
const NEW_TYPES: AccountType[] = ['cash', 'card', 'loan', 'investment']

/** Cuentas de seguimiento: efectivo, tarjeta, préstamo e inversión (OF-1005). */
function Accounts() {
  const { notify } = useHousehold()
  const accounts = useLoad<Account[]>('accounts', (s) => api.accounts(s))
  const [name, setName] = useState('')
  const [type, setType] = useState<AccountType>('cash')
  const [shared, setShared] = useState(true)
  const [opening, setOpening] = useState('0')
  const [currency, setCurrency] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function add(e: FormEvent) {
    e.preventDefault()
    const text = opening.trim().replace(',', '.') || '0'
    if (!/^-?\d{1,9}(\.\d{1,2})?$/.test(text)) {
      setError('Escribe un saldo como 1500 o -150000,50')
      return
    }
    try {
      await api.createAccount({ name, type, shared, opening_balance: text, ...(currency.trim() ? { currency: currency.trim().toUpperCase() } : {}) })
      setName('')
      setOpening('0')
      setError(null)
      accounts.reload()
      notify(`Cuenta «${name.trim()}» añadida`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido añadir la cuenta')
    }
  }

  return (
    <div className="card stack">
      <h2>Cuentas</h2>
      <p className="small muted">
        Solo de seguimiento: OpenFinance no mueve ni contrata nada. Las tarjetas y los préstamos van con saldo negativo (lo que se debe);
        los préstamos y las inversiones no cuentan como gasto.
      </p>
      {accounts.error && <ErrorState message={accounts.error} onRetry={accounts.reload} />}
      {!accounts.data && !accounts.error && <Loading />}
      {accounts.data && (
        <ul className="plain" aria-label="Tus cuentas">
          {accounts.data.map((a) => (
            <li key={a.id}>
              {a.name} · <span className="small muted">{TYPE_LABELS[a.type]}{a.kind === 'personal' ? ' · solo tuya' : ''}</span> ·{' '}
              {a.type === 'card' || a.type === 'loan'
                ? Number(a.balance.amount) < 0
                  ? `Debes ${formatMoney({ ...a.balance, amount: a.balance.amount.replace('-', '') })}`
                  : formatMoney(a.balance)
                : formatMoney(a.balance)}
            </li>
          ))}
        </ul>
      )}
      <form className="stack" aria-label="Añadir una cuenta" onSubmit={(e) => void add(e)}>
        <label>
          Nombre
          <input className="field" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Tipo
          <select className="field" value={type} onChange={(e) => setType(e.target.value as AccountType)}>
            {NEW_TYPES.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Saldo de partida
          <input
            className="field amount"
            inputMode="decimal"
            value={opening}
            onChange={(e) => setOpening(e.target.value)}
            {...invalid('account-opening-error', error)}
          />
        </label>
        <FieldError id="account-opening-error" message={error} />
        <label>
          Moneda (vacío = la del hogar)
          <input className="field amount" maxLength={3} placeholder="USD" value={currency} onChange={(e) => setCurrency(e.target.value)} />
        </label>
        <label className="small">
          <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} /> De todo el hogar (si no, solo tuya)
        </label>
        <div className="toolbar">
          <button className="btn" type="submit">
            Añadir cuenta
          </button>
        </div>
      </form>
    </div>
  )
}

/** Versión instalada y, si está activada la consulta, si hay una nueva (OF-907). */
function Version() {
  const version = useLoad<VersionInfo>('version', (s) => api.version(s))
  const info = version.data
  return (
    <div className="card stack">
      <h2>Versión</h2>
      {version.error && <p className="small muted">No se ha podido comprobar la versión.</p>}
      {!info && !version.error && <Loading />}
      {info && (
        <>
          <p>
            OpenFinance <strong>{info.current}</strong>
            {info.update_available && info.latest && <> · hay una nueva: {info.latest}</>}
          </p>
          {!info.enabled && (
            <p className="small muted">
              No se busca si hay versiones nuevas. Para que avise, quien administra la instalación puede poner{' '}
              <code>OPENFINANCE_UPDATE_CHECK=true</code> en <code>.env</code>: así el servidor consulta GitHub una vez al día.
            </p>
          )}
        </>
      )}
    </div>
  )
}

function Sessions() {
  const { notify } = useHousehold()
  async function revoke() {
    try {
      const r = await api.revokeOtherSessions()
      notify(r.revoked ? `${r.revoked === 1 ? '1 sesión cerrada' : `${r.revoked} sesiones cerradas`}` : 'No había otras sesiones abiertas')
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se han podido cerrar las sesiones')
    }
  }
  return (
    <div className="card stack">
      <h2>Sesiones</h2>
      <p className="small muted">Si has entrado desde un móvil o un ordenador que ya no usas, cierra allí la sesión desde aquí.</p>
      <div className="toolbar">
        <button className="btn" type="button" onClick={() => void revoke()}>
          Cerrar sesión en los demás dispositivos
        </button>
      </div>
    </div>
  )
}

function RechargeCards() {
  const { notify } = useHousehold()
  const patterns = useLoad<MemberPattern[]>('patterns', (s) => api.myPatterns(s))
  const [value, setValue] = useState('')
  const inflow = patterns.data?.filter((p) => p.direction === 'inflow') ?? []

  async function add(e: FormEvent) {
    e.preventDefault()
    const digits = value.trim().replace(/^\*/, '')
    try {
      await api.addPattern(`*${digits}`)
      setValue('')
      patterns.reload()
      notify(`Guardada la tarjeta *${digits}`)
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido guardar')
    }
  }

  async function remove(p: MemberPattern) {
    try {
      await api.removePattern(p)
      patterns.reload()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido quitar')
    }
  }

  return (
    <div className="card stack">
      <h2>Recargas de la conjunta</h2>
      <p className="small muted">
        Revolut enseña tus recargas como «Recarga de *1234», sin tu nombre. Guarda los últimos dígitos de la tarjeta con la que
        recargas para que cuenten como tu aportación. Solo tú ves y cambias los tuyos.
      </p>
      {patterns.error && <ErrorState message={patterns.error} onRetry={patterns.reload} />}
      {!patterns.data && !patterns.error && <Loading />}
      {patterns.data && (
        <ul className="plain" aria-label="Tus tarjetas de recarga">
          {inflow.length === 0 && <li className="small muted">Aún no has guardado ninguna.</li>}
          {inflow.map((p) => (
            <li key={p.pattern} className="toolbar">
              <code>{p.pattern}</code>
              <button className="btn small" type="button" aria-label={`Quitar ${p.pattern}`} onClick={() => void remove(p)}>
                Quitar
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="toolbar" onSubmit={(e) => void add(e)}>
        <label className="small">
          Últimos dígitos{' '}
          <input
            className="field amount"
            inputMode="numeric"
            placeholder="1234"
            pattern="\*?\d{3,8}"
            required
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <button className="btn" type="submit">
          Guardar
        </button>
      </form>
    </div>
  )
}

/** Ajustes de cada persona (OF-704). */
export function SettingsPage() {
  const { me } = useHousehold()
  return (
    <section>
      <h1>Ajustes</h1>
      <p className="lead">
        {me.user.display_name} · {me.user.email}
      </p>
      <div className="grid g2">
        <PasswordForm />
        <div className="grid stack">
          <RechargeCards />
          <Appearance />
          <Accounts />
          <BankSettings />
          <NotificationSettings />
          <ExchangeRates />
          <Sessions />
          <Version />
          <div className="card stack">
            <h2>Más ajustes</h2>
            <ul className="plain links">
              <li>
                <a href="#categorias">Categorías</a>
              </li>
              <li>
                <a href="#presupuestos">Presupuestos</a>
              </li>
              <li>
                <a href="#pagos">Pagos programados</a> · alquiler, seguros, nóminas: lo que sabéis que va a llegar
              </li>
              <li>
                <a href="#reglas">Reglas</a>
              </li>
              <li>
                <a href="#comercios">Comercios</a> · renombrar y fusionar los nombres que escribe el banco
              </li>
              <li>
                <a href="#cambios">Mis cambios</a> · deshacer y rehacer lo que has corregido
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}
