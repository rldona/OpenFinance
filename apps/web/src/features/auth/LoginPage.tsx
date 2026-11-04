import { type FormEvent, useRef, useState } from 'react'
import { ApiError, api, type Me } from '../../api/client'
import { FieldError } from '../../components/FieldError'
import { invalid } from '../../lib/invalid'

export function LoginPage({ onLogin }: { onLogin: (me: Me) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const passwordInput = useRef<HTMLInputElement>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onLogin(await api.login(email, password))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido conectar con OpenFinance')
      passwordInput.current?.focus()
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <form className="card login-card" onSubmit={submit} aria-label="Iniciar sesión">
        <div className="brand">OpenFinance</div>
        <p className="muted">Las finanzas de casa, claras.</p>
        <label>
          Email
          <input
            className="field"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Contraseña
          <input
            className="field"
            type="password"
            autoComplete="current-password"
            required
            ref={passwordInput}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            {...invalid('login-error', error)}
          />
        </label>
        <FieldError id="login-error" message={error} />
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </main>
  )
}
