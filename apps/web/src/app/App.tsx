import { useEffect, useState } from 'react'
import { ApiError, api, setUnauthorizedHandler, type Me } from '../api/client'
import { Toast } from '../components/Toast'
import { useToast } from '../components/useToast'
import { LoginPage } from '../features/auth/LoginPage'
import { CategoriesPage } from '../features/categories/CategoriesPage'
import { ImportPage } from '../features/import/ImportPage'
import { MonthPage } from '../features/insights/MonthPage'
import { SpendingPage } from '../features/insights/SpendingPage'
import { TrendsPage } from '../features/insights/TrendsPage'
import { BudgetsPage } from '../features/savings/BudgetsPage'
import { SavingsPage } from '../features/savings/SavingsPage'
import { TransactionsPage } from '../features/transactions/TransactionsPage'
import { HouseholdProvider } from './household'
import { useHousehold } from './household-context'
import { ROUTES, type RouteId, useRoute } from './router'

type Session = { kind: 'loading' } | { kind: 'anonymous' } | { kind: 'error' } | { kind: 'ready'; me: Me }

const COLORS = ['#0f766e', '#db2777', '#2563eb']

function Page({ route }: { route: RouteId }) {
  switch (route) {
    case 'movimientos':
      return <TransactionsPage />
    case 'importar':
      return <ImportPage />
    case 'categorias':
      return <CategoriesPage />
    case 'mes':
      return <MonthPage />
    case 'gastos':
      return <SpendingPage />
    case 'evolucion':
      return <TrendsPage />
    case 'ahorrar':
      return <SavingsPage />
    case 'presupuestos':
      return <BudgetsPage />
  }
}

export function App() {
  const [session, setSession] = useState<Session>({ kind: 'loading' })
  const route = useRoute()
  const [toast, notify] = useToast()

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

  return (
    <HouseholdProvider me={session.me} notify={notify}>
      <Shell route={route} onLogout={() => setSession({ kind: 'anonymous' })} />
      <Toast message={toast} />
    </HouseholdProvider>
  )
}

function Shell({ route, onLogout }: { route: RouteId; onLogout: () => void }) {
  const { me, uncategorized, notify } = useHousehold()

  async function logout() {
    try {
      await api.logout()
      onLogout()
    } catch {
      notify('No se ha podido cerrar la sesión. Inténtalo de nuevo.')
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
            <a
              key={r.id}
              href={`#${r.id}`}
              className={route === r.id ? 'active' : ''}
              aria-current={route === r.id ? 'page' : undefined}
            >
              {r.label}
              {r.id === 'movimientos' && uncategorized > 0 && (
                <span className="badge" aria-label={`${uncategorized} sin categoría`}>
                  {uncategorized}
                </span>
              )}
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
        <Page route={route} />
      </main>
    </>
  )
}
