import { useEffect, useRef, useState } from 'react'
import { ApiError, api, setUnauthorizedHandler, type Me } from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Toast } from '../components/Toast'
import { useToast } from '../components/useToast'
import { LoginPage } from '../features/auth/LoginPage'
import { CategoriesPage } from '../features/categories/CategoriesPage'
import { ChangesPage } from '../features/changes/ChangesPage'
import { RulesPage } from '../features/categories/RulesPage'
import { ExportMenu } from '../features/export/ExportMenu'
import { ImportPage } from '../features/import/ImportPage'
import { MerchantsPage } from '../features/merchants/MerchantsPage'
import { UpdateNotice } from '../features/updates/UpdateNotice'
import { MonthPage } from '../features/insights/MonthPage'
import { SpendingPage } from '../features/insights/SpendingPage'
import { TrendsPage } from '../features/insights/TrendsPage'
import { BudgetsPage } from '../features/savings/BudgetsPage'
import { SchedulePage } from '../features/savings/SchedulePage'
import { SavingsPage } from '../features/savings/SavingsPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { TransactionsPage } from '../features/transactions/TransactionsPage'
import { HouseholdProvider } from './household'
import { useHousehold } from './household-context'
import { ROUTES, type RouteId, TITLES, routeHref, useRoute, useSharedParamsKey } from './router'

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
    case 'reglas':
      return <RulesPage />
    case 'ajustes':
      return <SettingsPage />
    case 'comercios':
      return <MerchantsPage />
    case 'pagos':
      return <SchedulePage />
    case 'cambios':
      return <ChangesPage />
  }
}

export function App() {
  const [session, setSession] = useState<Session>({ kind: 'loading' })
  const route = useRoute()
  const [toast, notify, dismissToast] = useToast()

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
      <Toast notice={toast} onDismiss={dismissToast} />
    </HouseholdProvider>
  )
}

function Shell({ route, onLogout }: { route: RouteId; onLogout: () => void }) {
  const { me, uncategorized, notify } = useHousehold()
  useSharedParamsKey() // el menú conserva el mes y la vista elegidos
  const main = useRef<HTMLElement>(null)
  const first = useRef(true)

  // Cada pantalla pone su título a la pestaña y, al navegar, el foco pasa a su contenido para que
  // un lector de pantalla anuncie el cambio y el teclado no se quede en el menú (OF-804).
  useEffect(() => {
    document.title = `${TITLES[route]} · OpenFinance`
    if (first.current) {
      first.current = false
      return
    }
    main.current?.focus({ preventScroll: true })
    window.scrollTo(0, 0)
  }, [route])

  async function logout() {
    try {
      await api.logout()
      onLogout()
    } catch {
      notify('No se ha podido cerrar la sesión. Inténtalo de nuevo.')
    }
  }

  return (
    <div className="app">
      <a className="skip-link" href="#contenido" onClick={(e) => { e.preventDefault(); main.current?.focus() }}>
        Saltar al contenido
      </a>
      <header className="top">
        <div className="brand">
          OpenFinance<small>{me.household.name}</small>
        </div>
        <div className="top-tools">
          <div className="people" title={me.members.map((m) => m.display_name).join(' y ')}>
            {me.members.map((m, i) => (
              <span key={m.id} style={{ background: COLORS[i % COLORS.length] }}>
                {m.display_name.charAt(0)}
              </span>
            ))}
          </div>
          <ExportMenu />
          <a className={`btn small ${route === 'ajustes' ? 'active' : ''}`} href="#ajustes" aria-label="Ajustes" title="Ajustes">
            ⚙️
          </a>
          <button className="btn small" type="button" onClick={() => void logout()}>
            Salir
          </button>
        </div>
      </header>
      {/* Barra inferior en el móvil, carril en la tableta y barra lateral en el escritorio (OF-801). */}
      <nav className="nav" aria-label="Secciones">
        {ROUTES.map((r) => (
          <a
            key={r.id}
            href={routeHref(r.id)}
            className={route === r.id ? 'active' : ''}
            aria-current={route === r.id ? 'page' : undefined}
          >
            <span className="nav-icon" aria-hidden="true">
              {r.icon}
            </span>
            <span className="nav-label nav-full">{r.label}</span>
            <span className="nav-label nav-short" aria-hidden="true">
              {r.short}
            </span>
            {r.id === 'movimientos' && uncategorized > 0 && (
              <span className="badge" aria-label={`${uncategorized} sin categoría`}>
                {uncategorized}
              </span>
            )}
          </a>
        ))}
      </nav>
      <main id="contenido" tabIndex={-1} ref={main}>
        <UpdateNotice />
        {/* Por pestaña: si una falla, las demás siguen funcionando. */}
        <ErrorBoundary key={route}>
          <Page route={route} />
        </ErrorBoundary>
      </main>
    </div>
  )
}
