import { useState } from 'react'
import { ApiStatus } from '../components/ApiStatus'
import { DashboardPage } from '../features/dashboard/DashboardPage'

const SECTIONS = [
  { id: 'month', label: 'Este mes' },
  { id: 'spending', label: '¿En qué gastamos?' },
  { id: 'trends', label: 'Evolución' },
  { id: 'savings', label: 'Ahorrar' },
  { id: 'transactions', label: 'Movimientos' },
  { id: 'import', label: 'Importar' },
] as const

type SectionId = (typeof SECTIONS)[number]['id']

export function App() {
  const [active, setActive] = useState<SectionId>('month')
  const current = SECTIONS.find((s) => s.id === active)

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">OpenFinance</div>
        <nav aria-label="Principal">
          <ul>
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  aria-current={s.id === active ? 'page' : undefined}
                  onClick={() => setActive(s.id)}
                >
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <ApiStatus />
      </aside>
      <main className="content">
        {active === 'month' ? (
          <DashboardPage />
        ) : (
          <section>
            <h1>{current?.label}</h1>
            <p>Próximamente.</p>
          </section>
        )}
      </main>
    </div>
  )
}
