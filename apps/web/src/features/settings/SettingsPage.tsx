import { type FormEvent, useState } from 'react'
import { ApiError, api, type MemberPattern } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { ErrorState, Loading } from '../../components/LoadState'
import { useLoad } from '../../lib/useLoad'

const MIN_PASSWORD = 10

function PasswordForm() {
  const { notify } = useHousehold()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [saving, setSaving] = useState(false)
  const mismatch = repeat.length > 0 && next !== repeat

  async function save(e: FormEvent) {
    e.preventDefault()
    if (next !== repeat) return
    setSaving(true)
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
      notify(err instanceof ApiError ? err.message : 'No se ha podido cambiar la contraseña')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card stack" aria-label="Cambiar la contraseña" onSubmit={(e) => void save(e)}>
      <h2>Tu contraseña</h2>
      <label>
        Contraseña actual
        <input className="field" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
      </label>
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
        <input className="field" type="password" autoComplete="new-password" required value={repeat} onChange={(e) => setRepeat(e.target.value)} />
      </label>
      {mismatch && <p className="small error">No coinciden.</p>}
      <p className="small muted">Al cambiarla se cierran tus sesiones en otros dispositivos; esta sigue abierta.</p>
      <div className="toolbar">
        <button className="btn primary" type="submit" disabled={saving || mismatch || next.length < MIN_PASSWORD}>
          Cambiar la contraseña
        </button>
      </div>
    </form>
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
          <Sessions />
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
                <a href="#reglas">Reglas</a>
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
