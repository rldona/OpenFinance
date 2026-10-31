import { useEffect, useState } from 'react'
import { ApiError, api, setUnauthorizedHandler, type Me } from '../api/client'
import { LoginPage } from '../features/auth/LoginPage'
import { ImportPage } from '../features/import/ImportPage'
import { ComingSoon } from '../features/placeholder/ComingSoon'
import { TransactionsPage } from '../features/transactions/TransactionsPage'
import { ROUTES, type RouteId, useRoute } from './router'

type Session = { kind: 'loading' } | { kind: 'anonymous' } | { kind: 'error' } | { kind: 'ready'; me: Me }

const COLORS = ['#0f766e', '#db2777', '#2563eb']

function Page({ route, me }: { route: RouteId; me: Me }) {
  switch (route) {
    case 'movimientos':
      return <TransactionsPage me={me} />
    case 'importar':
      return <ImportPage me={me} />
    case 'mes':
      return <ComingSoon title="Este mes" ticket="OF-303" />
    case 'gastos':
      return <ComingSoon title="¿En qué gastamos?" ticket="OF-304" />
    case 'evolucion':
      return <ComingSoon title="Evolución" ticket="OF-305" />
    case 'ahorrar':
      return <ComingSoon title="Ahorrar" ticket="OF-401 … OF-405" />
  }
}

export function App() {
  const [session, setSession] = useState<Session>({ kind: 'loading' })
  const route = useRoute()

  useEffect(() => {
    setUnauthorizedHandler(() => setSession({ kind: 'anonymous' }))
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    api.me(controller.signal).then(
      (me) => setSession({ kind: 'ready', me }),
      (err: unknown) => {
        if (controller.signal.aborted) return
        setSession(err instanceof ApiError && err.status === 401 ? { kind: 'anonymous' } : { kind: 'error' })
      },
    )
    return () => controller.abort()
  }, [])

  if (session.kind === 'loading') return <p className="center muted">Cargando…</p>
  if (session.kind === 'error')
    return (
      <p className="center error" role="alert">
        No se puede conectar con OpenFinance. ¿Está la API en marcha?
      </p>
    )
  if (session.kind === 'anonymous') return <LoginPage onLogin={(me) => setSession({ kind: 'ready', me })} />

  const { me } = session

  async function logout() {
    try {
      await api.logout()
      setSession({ kind: 'anonymous' })
    } catch {
      window.alert('No se ha podido cerrar la sesión. Inténtalo de nuevo.')
    }
  }

  return (
    <>
      <header className="top">
        <div className="brand">
          OpenFinance<small>{me.household.name}</small>
        </div>
        <nav className="tabs" aria-label="Secciones">
          {ROUTES.map((r) => (
            <a key={r.id} href={`#${r.id}`} className={route === r.id ? 'active' : ''} aria-current={route === r.id ? 'page' : undefined}>
              {r.label}
            </a>
          ))}
        </nav>
        <div className="people" title={me.members.map((m) => m.display_name).join(' y ')}>
          {me.members.map((m, i) => (
            <span key={m.id} style={{ background: COLORS[i % COLORS.length] }}>
              {m.display_name.charAt(0)}
            </span>
          ))}
        </div>
        <button className="btn small" type="button" onClick={() => void logout()}>
          Salir
        </button>
      </header>
      <main>
        <Page route={route} me={me} />
      </main>
    </>
  )
}
