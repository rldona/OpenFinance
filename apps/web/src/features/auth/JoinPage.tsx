import { type FormEvent, useState } from 'react'
import { ApiError, api, type Me } from '../../api/client'
import { FieldError } from '../../components/FieldError'

/** Unirse al hogar con una invitación (ADR-0026, OF-1601). No hay registro sin enlace. */
export function JoinPage({ token, onJoined }: { token: string; onJoined: (me: Me) => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (password !== repeat) {
      setError('Las contraseñas no coinciden')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const me = await api.acceptInvitation(token, name, email, password)
      window.location.hash = '#mes'
      onJoined(me)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido conectar con OpenFinance')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <form className="card login-card" onSubmit={submit} aria-label="Unirse al hogar">
        <div className="brand">OpenFinance</div>
        <p className="muted">Te han invitado a un hogar. Elige cómo quieres entrar.</p>
        <label>
          Tu nombre
          <input className="field" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Email
          <input className="field" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Contraseña (10 caracteres o más)
          <input
            className="field"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label>
          Repite la contraseña
          <input
            className="field"
            type="password"
            autoComplete="new-password"
            required
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
          />
        </label>
        <FieldError id="join-error" message={error} />
        <button className="btn primary" type="submit" disabled={busy}>
          Unirme
        </button>
      </form>
    </main>
  )
}
