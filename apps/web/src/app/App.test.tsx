import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ACCOUNTS, CATEGORIES, ME, PREVIEW, TRANSACTIONS, mockApi } from '../test/api'
import { App } from './App'

beforeEach(() => {
  window.location.hash = '#movimientos'
  // Fecha fija: las pantallas parten del mes en curso y los datos simulados son de octubre.
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 9, 15, 12))
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

const loggedIn = (extra: Parameters<typeof mockApi>[0] = {}) =>
  mockApi({
    'GET /api/v1/me': { body: ME },
    'GET /api/v1/accounts': { body: ACCOUNTS },
    'GET /api/v1/transactions': { body: TRANSACTIONS },
    'GET /api/v1/categories': { body: CATEGORIES },
    'GET /api/v1/transactions/uncategorized-count': { body: { count: 1 } },
    ...extra,
  })

describe('Inicio de sesión', () => {
  it('pide credenciales sin sesión y entra con ellas', async () => {
    const calls = mockApi({
      'GET /api/v1/me': { status: 401, body: { detail: 'Inicia sesión' } },
      'POST /api/v1/auth/login': { body: ME },
      'GET /api/v1/accounts': { body: ACCOUNTS },
      'GET /api/v1/transactions': { body: [] },
      'GET /api/v1/categories': { body: CATEGORIES },
      'GET /api/v1/transactions/uncategorized-count': { body: { count: 0 } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Email'), 'raul@example.org')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'clave-larga-raul')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByText('Nuestra casa')).toBeInTheDocument()
    const login = calls.find((c) => c.url.pathname === '/api/v1/auth/login')!
    expect(login.headers.get('X-Requested-With')).toBe('OpenFinance')
    expect(JSON.parse(String(login.body))).toEqual({ email: 'raul@example.org', password: 'clave-larga-raul' })
  })

  it('muestra el error de credenciales', async () => {
    mockApi({
      'GET /api/v1/me': { status: 401 },
      'POST /api/v1/auth/login': { status: 401, body: { detail: 'Email o contraseña incorrectos' } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Email'), 'raul@example.org')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'mala-clave')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Email o contraseña incorrectos')
  })

  it('sale de la sesión', async () => {
    const calls = loggedIn({ 'POST /api/v1/auth/logout': { status: 204 } })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Salir' }))
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
    expect(calls.some((c) => c.url.pathname === '/api/v1/auth/logout')).toBe(true)
  })
})

describe('Movimientos', () => {
  it('lista los movimientos con su tipo y su importe', async () => {
    loggedIn()
    render(<App />)
    const table = await screen.findByRole('table')
    const row = (text: string) => within(table).getByText(text).closest('tr')!
    expect(row('Payment from Raul')).toHaveTextContent('Aportación de Raúl')
    expect(row('Payment from Raul')).toHaveTextContent(/\+1600,00\s€|\+1\.600,00\s€/)
    expect(row('To pocket Ahorro')).toHaveTextContent('A la hucha')
    expect(screen.getByLabelText('Categoría de Glovo')).toHaveValue('')
    expect(screen.getByLabelText('Categoría de Mercadona')).toHaveValue('c-super')
    expect(within(screen.getByLabelText('Categoría de Glovo')).queryByText(/Antigua/)).toBeNull()
    expect(within(table).getAllByText(/Cuenta conjunta/).length).toBeGreaterThan(0)
  })

  it('filtra por mes y por «sin categoría»', async () => {
    const calls = loggedIn()
    render(<App />)
    await screen.findByRole('table')
    const month = calls.filter((c) => c.url.pathname === '/api/v1/transactions').at(-1)!
    expect(month.url.searchParams.get('month')).toMatch(/^\d{4}-\d{2}$/)

    await userEvent.click(screen.getByLabelText(/Solo sin categoría/))
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions').at(-1)!
      expect(last.url.searchParams.get('uncategorized')).toBe('true')
    })

    await userEvent.click(screen.getByLabelText(/Solo sin categoría/))
    await userEvent.click(screen.getByRole('button', { name: 'Mes anterior' }))
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions').at(-1)!
      expect(last.url.searchParams.get('month')).not.toBe(month.url.searchParams.get('month'))
    })
  })
})

describe('Corregir un movimiento (OF-701)', () => {
  const HISTORY = [
    {
      id: 'op-1',
      actor_id: 'u-elena',
      created_at: '2026-11-03T10:00:00Z',
      action: 'transaction.edit',
      summary: 'Glovo: Ingreso → Gasto',
      undone: false,
      changes: [],
    },
  ]

  it('cambia el tipo a aportación de la pareja, enseña el historial y se puede deshacer', async () => {
    const calls = loggedIn({
      'GET /api/v1/transactions/t4/history': { body: HISTORY },
      'PATCH /api/v1/transactions/t4': {
        body: { transaction: TRANSACTIONS[3], rule: null, also_categorized: 0, operation_id: 'op-2' },
      },
      'POST /api/v1/changes/op-2/undo': {
        body: { operation: { ...HISTORY[0], id: 'op-2', undone: true }, applied: 2, kept: 1, kept_by: ['u-elena'] },
      },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    expect(await screen.findByText(/Glovo: Ingreso → Gasto/)).toHaveTextContent('Elena')
    await userEvent.selectOptions(screen.getByLabelText('Tipo'), 'contribution')
    await userEvent.selectOptions(screen.getByLabelText('De'), 'u-elena')
    await userEvent.type(screen.getByLabelText('Nota'), 'Su parte')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))

    const edit = calls.find((c) => c.method === 'PATCH')!
    expect(JSON.parse(String(edit.body))).toEqual({ kind: 'contribution', member_id: 'u-elena', note: 'Su parte' })
    expect(await screen.findByText('Movimiento corregido')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Deshacer' }))
    expect(await screen.findByText('Deshecho. 1 cambio se ha respetado (lo cambió después Elena)')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.url.pathname === '/api/v1/changes/op-2/undo')).toBe(true)
  })

  it('el importe y el concepto no se pueden editar', async () => {
    loggedIn({ 'GET /api/v1/transactions/t4/history': { body: [] } })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    expect(await screen.findByText('Sin correcciones.')).toBeInTheDocument()
    expect(screen.getByText(/no se cambian/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/Importe/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeDisabled()
  })
})

describe('Búsqueda', () => {
  it.each(['#1', '%', '"comillas"', "l'oreal"])('busca «%s» sin romper la pantalla', async (text) => {
    const calls = loggedIn()
    render(<App />)
    await screen.findByRole('table')
    await userEvent.type(screen.getByRole('searchbox'), text)
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions').at(-1)!
      expect(last.url.searchParams.get('q')).toBe(text)
    })
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })
})

describe('Error inesperado', () => {
  it('muestra un aviso con «Recargar» en vez de dejar la pantalla congelada', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined) // React registra el error capturado
    loggedIn({ 'GET /api/v1/transactions': { body: [{ roto: true }] } })
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Algo ha fallado')
    expect(screen.getByRole('button', { name: 'Recargar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Salir' })).toBeInTheDocument()
  })
})

describe('Importar', () => {
  it('sube el extracto, enseña la vista previa y confirma', async () => {
    window.location.hash = '#importar'
    const calls = loggedIn({
      'POST /api/v1/imports': { status: 201, body: PREVIEW },
      'POST /api/v1/imports/imp-1/commit': {
        body: { id: 'imp-1', status: 'committed', created: 2, duplicates: 1, skipped: 1 },
      },
    })
    render(<App />)

    const select = await screen.findByLabelText('Cuenta')
    await waitFor(() => expect(select).toHaveValue('a-joint'))
    expect(within(select).getByRole('option', { name: 'Bankinter Raúl' })).toBeEnabled()
    expect(screen.getByLabelText('Extracto')).toHaveAttribute('accept', '.csv,.xlsx')
    expect(screen.getByText('📄 Elige el extracto (CSV o Excel)')).toBeInTheDocument()

    const file = new File(['Type,Product\n'], 'revolut.csv', { type: 'text/csv' })
    await userEvent.upload(screen.getByLabelText('Extracto'), file)
    await userEvent.click(screen.getByRole('button', { name: 'Ver vista previa' }))

    expect(await screen.findByText(/coincidirá con el del banco/)).toBeInTheDocument()
    expect(screen.getByText('Aportación de Elena')).toBeInTheDocument()
    expect(screen.getByText('🛒 Supermercado')).toBeInTheDocument()
    expect(screen.getByText(/· regla/)).toBeInTheDocument()
    expect(screen.getByText('Ya importado')).toBeInTheDocument()
    expect(screen.getByText(/Filas que no se importan \(1\)/)).toBeInTheDocument()

    const upload = calls.find((c) => c.url.pathname === '/api/v1/imports')!
    expect(upload.headers.get('X-Requested-With')).toBe('OpenFinance')
    const form = upload.body as FormData
    expect(form.get('account_id')).toBe('a-joint')
    expect((form.get('file') as File).name).toBe('revolut.csv')

    await userEvent.click(screen.getByRole('button', { name: 'Importar 2 movimientos' }))
    expect(await screen.findByText('✓ Importados 2 movimientos')).toBeInTheDocument()
  })

  it('en Bankinter solo admite Excel', async () => {
    window.location.hash = '#importar'
    loggedIn({})
    render(<App />)
    const select = await screen.findByLabelText('Cuenta')
    await waitFor(() => expect(select).toHaveValue('a-joint'))
    await userEvent.selectOptions(select, 'a-raul')
    expect(screen.getByLabelText('Extracto')).toHaveAttribute('accept', '.xlsx')
    expect(screen.getByText('📄 Elige el extracto (Excel)')).toBeInTheDocument()
  })

  it('avisa si el saldo no cuadrará con el del banco', async () => {
    window.location.hash = '#importar'
    loggedIn({
      'POST /api/v1/imports': {
        status: 201,
        body: { ...PREVIEW, balance_after_import: { amount: '2600.00', currency: 'EUR' } },
      },
    })
    render(<App />)
    await waitFor(() => expect(screen.getByLabelText('Cuenta')).toHaveValue('a-joint'))
    await userEvent.upload(screen.getByLabelText('Extracto'), new File(['x'], 'r.csv'))
    await userEvent.click(screen.getByRole('button', { name: 'Ver vista previa' }))
    expect(await screen.findByText(/no cuadrará/)).toHaveTextContent(/-25,46\s€/)
  })

  it('muestra el error de formato que devuelve la API', async () => {
    window.location.hash = '#importar'
    loggedIn({
      'POST /api/v1/imports': { status: 422, body: { detail: 'No parece un extracto de Revolut' } },
    })
    render(<App />)
    await waitFor(() => expect(screen.getByLabelText('Cuenta')).toHaveValue('a-joint'))
    await userEvent.upload(screen.getByLabelText('Extracto'), new File(['x'], 'otro.csv'))
    await userEvent.click(screen.getByRole('button', { name: 'Ver vista previa' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No parece un extracto de Revolut')
  })
})

describe('Sesión caducada', () => {
  it('vuelve al login si una petición devuelve 401', async () => {
    mockApi({
      'GET /api/v1/me': { body: ME },
      'GET /api/v1/accounts': { body: ACCOUNTS },
      'GET /api/v1/transactions': { status: 401, body: { detail: 'Inicia sesión' } },
    })
    render(<App />)
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
  })

  it('avisa cuando se alcanza el límite de movimientos', async () => {
    const many = Array.from({ length: 1000 }, (_, i) => ({ ...TRANSACTIONS[3], id: `t${i}` }))
    loggedIn({ 'GET /api/v1/transactions': { body: many } })
    render(<App />)
    expect(await screen.findByText(/Se muestran los 1000 más recientes/)).toBeInTheDocument()
  })
})

describe('Categorías', () => {
  it('muestra el número de gastos sin categoría en la pestaña y en el aviso', async () => {
    loggedIn({ 'GET /api/v1/transactions/uncategorized-count': { body: { count: 3 } } })
    render(<App />)
    expect(await screen.findByLabelText('3 sin categoría')).toBeInTheDocument()
    expect(screen.getByText(/3 gastos sin categoría/)).toBeInTheDocument()
  })

  it('cambia la categoría desde la tabla y avisa de la regla aprendida', async () => {
    const calls = loggedIn({
      'PATCH /api/v1/transactions/t4': {
        body: {
          transaction: { ...TRANSACTIONS[3], category_id: 'c-rest' },
          rule: { merchant: 'Glovo', category_id: 'c-rest' },
          also_categorized: 2,
        },
      },
    })
    render(<App />)
    await userEvent.selectOptions(await screen.findByLabelText('Categoría de Glovo'), 'c-rest')
    expect(await screen.findByText('Regla guardada: «Glovo» → Restaurantes · 2 más clasificados')).toBeInTheDocument()
    const patch = calls.find((c) => c.method === 'PATCH')!
    expect(JSON.parse(String(patch.body))).toEqual({ category_id: 'c-rest', learn: true })
    expect(patch.headers.get('X-Requested-With')).toBe('OpenFinance')
    await waitFor(() =>
      expect(calls.filter((c) => c.url.pathname === '/api/v1/transactions/uncategorized-count').length).toBe(2),
    )
  })

  it('crea, renombra y oculta categorías', async () => {
    window.location.hash = '#categorias'
    const calls = loggedIn({
      'POST /api/v1/categories': { status: 201, body: { id: 'c-new', name: 'Mascotas', icon: '🐶', color: '#64748b', hidden: false, slug: null } },
      'PATCH /api/v1/categories/c-super': { body: { ...CATEGORIES[0], name: 'Súper' } },
      'PATCH /api/v1/categories/c-rest': { body: { ...CATEGORIES[1], hidden: true } },
    })
    render(<App />)
    const name = await screen.findByLabelText('Nombre de Supermercado')
    await userEvent.clear(name)
    await userEvent.type(name, 'Súper{Enter}')
    await userEvent.click(screen.getAllByLabelText('Oculta')[1])
    await userEvent.clear(screen.getByLabelText('Icono de la nueva categoría'))
    await userEvent.type(screen.getByLabelText('Icono de la nueva categoría'), '🐶')
    await userEvent.type(screen.getByLabelText('Nombre de la nueva categoría'), 'Mascotas')
    await userEvent.click(screen.getByRole('button', { name: 'Añadir' }))

    expect(await screen.findByText('Categoría «Mascotas» creada')).toBeInTheDocument()
    const bodies = calls.filter((c) => c.method !== 'GET').map((c) => [c.method, c.url.pathname, JSON.parse(String(c.body))])
    expect(bodies).toEqual([
      ['PATCH', '/api/v1/categories/c-super', { name: 'Súper' }],
      ['PATCH', '/api/v1/categories/c-rest', { hidden: true }],
      ['POST', '/api/v1/categories', { name: 'Mascotas', icon: '🐶', color: '#64748b' }],
    ])
  })
})

describe('Errores de carga', () => {
  it('avisa si las categorías no cargan y no deja categorizar', async () => {
    loggedIn({ 'GET /api/v1/categories': { status: 500, body: { detail: 'boom' } } })
    render(<App />)
    expect(await screen.findByText('No se han podido cargar las categorías')).toBeInTheDocument()
    expect(await screen.findByLabelText('Categoría de Glovo')).toBeDisabled()
  })
})

const eur = (amount: string) => ({ amount, currency: 'EUR' })

const amountVsAverage = (category_id: string | null, amount: string, average: string, change: string) => ({
  category_id,
  amount: eur(amount),
  average: eur(average),
  reference: eur(average),
  change: eur(change),
})
const CATEGORY_AMOUNTS = [
  amountVsAverage('c-super', '600.00', '500.00', '100.00'),
  amountVsAverage('c-rest', '300.00', '100.00', '200.00'),
  amountVsAverage(null, '100.00', '0.00', '100.00'),
]

const OVERVIEW = {
  month: '2026-10',
  has_data: true,
  spent: eur('1000.00'),
  previous_spent: eur('800.00'),
  is_partial: false,
  days_elapsed: 31,
  previous_spent_to_date: eur('800.00'),
  average_spent: eur('900.00'),
  inflow: eur('3000.00'),
  income: eur('0.00'),
  saved: eur('2000.00'),
  saved_to_savings: eur('300.00'),
  saving_rate: 67,
  contributions: [
    { member_id: 'u-raul', amount: eur('1600.00') },
    { member_id: 'u-elena', amount: eur('1400.00') },
  ],
  contributed: eur('0.00'),
  categories: CATEGORY_AMOUNTS,
  changes: [CATEGORY_AMOUNTS[1], CATEGORY_AMOUNTS[2], CATEGORY_AMOUNTS[0]],
  currency: 'EUR',
  daily: Array.from({ length: 31 }, (_, i) => (i < 10 ? '100.00' : '1000.00')),
  previous_daily: Array.from({ length: 30 }, () => '800.00'),
}

const DETAIL = {
  category_id: 'c-super',
  month: '2026-10',
  months: Array.from({ length: 12 }, (_, i) => ({
    month: `2026-${String(i + 1).padStart(2, '0')}`,
    amount: eur(i === 11 ? '600.00' : '500.00'),
    has_data: true,
  })),
  average: eur('500.00'),
  merchants: [{ merchant: 'Mercadona', amount: eur('1500.00'), count: 12 }],
}

const TRENDS = {
  months: Array.from({ length: 12 }, (_, i) => ({
    month: `${i < 2 ? 2025 : 2026}-${String(((i + 10) % 12) + 1).padStart(2, '0')}`,
    has_data: true,
    is_partial: false,
    spent: eur('1000.00'),
    inflow: eur('3000.00'),
    saved: eur(i === 9 ? '-500.00' : '2000.00'),
    categories: [
      { category_id: 'c-super', amount: eur('600.00') },
      { category_id: null, amount: eur('400.00') },
    ],
  })),
  total_saved: eur('21500.00'),
  total_inflow: eur('36000.00'),
  total_spent: eur('12000.00'),
  average_spent: eur('1000.00'),
  average_saved: eur('1791.67'),
  saving_rate: 60,
  best: { month: '2026-01', saved: eur('2000.00') },
  worst: { month: '2026-08', saved: eur('-500.00') },
}

describe('Gráficos (fase 3)', () => {
  it('Este mes es la pantalla de inicio y resume el mes', async () => {
    window.location.hash = ''
    const calls = loggedIn({ 'GET /api/v1/insights/month': { body: OVERVIEW } })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Este mes' })).toBeInTheDocument()
    expect(screen.getByText(/▲ 25 % que el mes anterior/)).toBeInTheDocument()
    expect(screen.getByText('67 % de lo que entra')).toBeInTheDocument()
    expect(screen.getByText(/Raúl 1600 €|Raúl 1\.600 €/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Gasto de octubre de 2026 por categoría/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Gasto acumulado/ })).toBeInTheDocument()
    // Restaurantes es lo que más cambia frente a la media: +200 €
    expect(screen.getByText('Lo que más ha cambiado frente a vuestra media').nextElementSibling).toHaveTextContent(
      /Restaurantes\+200/,
    )
    const req = calls.find((c) => c.url.pathname === '/api/v1/insights/month')!
    expect(req.url.searchParams.get('month')).toMatch(/^\d{4}-\d{2}$/)
  })

  it('pulsar una categoría lleva a su detalle', async () => {
    window.location.hash = '#mes'
    const calls = loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/insights/category': { body: { ...DETAIL, category_id: 'c-rest' } },
    })
    render(<App />)
    await userEvent.click((await screen.findAllByRole('link', { name: /Restaurantes/ }))[0])
    expect(await screen.findByRole('heading', { name: /Restaurantes · últimos 12 meses/ })).toBeInTheDocument()
    const req = calls.filter((c) => c.url.pathname === '/api/v1/insights/category').at(-1)!
    expect(req.url.searchParams.get('category_id')).toBe('c-rest')
  })

  it('¿En qué gastamos? enseña 12 meses, media y comercios', async () => {
    window.location.hash = '#gastos'
    const calls = loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/insights/category': { body: DETAIL },
    })
    render(<App />)
    expect(await screen.findByRole('heading', { name: /Supermercado · últimos 12 meses/ })).toBeInTheDocument()
    expect(screen.getByText('Media 500 €')).toBeInTheDocument()
    expect(screen.getByText(/▲ 20 % que la media/)).toBeInTheDocument()
    const merchants = screen.getByRole('heading', { name: 'Dónde (últimos 3 meses)' }).parentElement!
    expect(within(merchants).getByText('Mercadona')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Supermercado/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: /Sin categoría/ }))
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/insights/category').at(-1)!
      expect(last.url.searchParams.has('category_id')).toBe(false)
    })
    const tx = calls.filter((c) => c.url.pathname === '/api/v1/transactions').at(-1)!
    expect(tx.url.searchParams.get('uncategorized')).toBe('true')
  })

  it('Evolución resume 12 meses y marca el peor', async () => {
    window.location.hash = '#evolucion'
    loggedIn({ 'GET /api/v1/insights/trends': { body: TRENDS } })
    const { container } = render(<App />)
    expect(await screen.findByText('(gastasteis más de lo que entró)')).toBeInTheDocument()
    expect(screen.getByText('60 % de todo lo que entró')).toBeInTheDocument()
    expect(screen.getByText('Media 1792 €')).toBeInTheDocument()
    expect(container.querySelectorAll('[data-stack]')).toHaveLength(12)
    expect(screen.getByRole('img', { name: /Ahorro mensual/ })).toBeInTheDocument()
  })

  it('un mes en curso se compara con los mismos días del anterior', async () => {
    window.location.hash = '#mes'
    loggedIn({
      'GET /api/v1/insights/month': {
        body: {
          ...OVERVIEW,
          is_partial: true,
          days_elapsed: 10,
          previous_spent_to_date: eur('500.00'),
          daily: OVERVIEW.daily.slice(0, 10),
        },
      },
    })
    render(<App />)
    expect(await screen.findByText(/mes en curso, hasta el día 10/)).toBeInTheDocument()
    expect(screen.getByText(/▲ 100 % que a estas alturas del mes anterior/)).toBeInTheDocument()
    expect(screen.getByText(/\(meses completos\)/)).toBeInTheDocument()
    // Los cambios por categoría se comparan con lo gastado hasta el mismo día (OF-608).
    const changes = screen.getByRole('list', { name: 'Cambios frente a la media' })
    expect(within(changes).getAllByText(/media hasta el día 10/)).toHaveLength(3)
  })

  it('«Mío» enseña tu gasto y lo aportado a la conjunta aparte (OF-108)', async () => {
    window.location.hash = '#mes'
    const calls = loggedIn({
      'GET /api/v1/insights/month': {
        body: { ...OVERVIEW, contributions: [], contributed: eur('1600.00'), income: eur('2100.00') },
      },
    })
    render(<App />)
    await screen.findByRole('heading', { name: 'Este mes' })
    expect(screen.getByRole('button', { name: 'Hogar' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Mío' }))
    expect(await screen.findByText('Has aportado a la conjunta')).toBeInTheDocument()
    expect(screen.getByText(/Tus cuentas personales · solo las ves tú/)).toBeInTheDocument()
    expect(screen.getByText(/No cuenta como gasto tuyo/)).toBeInTheDocument()
    expect(screen.queryByText('Habéis ahorrado')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Presupuestos del mes' })).not.toBeInTheDocument()
    const req = calls.filter((c) => c.url.pathname === '/api/v1/insights/month').at(-1)!
    expect(req.url.searchParams.get('view')).toBe('mine')
  })

  it('«Mío» en ¿En qué gastamos? pide solo tus cuentas', async () => {
    window.location.hash = '#gastos'
    const calls = loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/insights/category': { body: DETAIL },
    })
    render(<App />)
    await screen.findByRole('heading', { name: /Supermercado · últimos 12 meses/ })
    await userEvent.click(screen.getByRole('button', { name: 'Mío' }))
    await waitFor(() => {
      const detail = calls.filter((c) => c.url.pathname === '/api/v1/insights/category').at(-1)!
      expect(detail.url.searchParams.get('view')).toBe('mine')
      const tx = calls.filter((c) => c.url.pathname === '/api/v1/transactions').at(-1)!
      expect(tx.url.searchParams.get('mine_only')).toBe('true')
      expect(tx.url.searchParams.has('shared_only')).toBe(false)
    })
  })

  it('sin datos en el mes invita a importar', async () => {
    window.location.hash = '#mes'
    loggedIn({ 'GET /api/v1/insights/month': { body: { ...OVERVIEW, has_data: false } } })
    render(<App />)
    expect(await screen.findByText(/No hay movimientos de la cuenta conjunta/)).toBeInTheDocument()
  })
})

const BUDGETS = {
  month: '2026-10',
  items: [
    { category_id: 'c-super', amount: eur('550.00'), spent: eur('600.00'), percent: 109, status: 'over' },
    { category_id: 'c-rest', amount: eur('350.00'), spent: eur('300.00'), percent: 86, status: 'warning' },
  ],
  total_amount: eur('900.00'),
  total_spent: eur('900.00'),
}

const GOAL = {
  id: 'g1',
  name: 'Fondo de emergencia',
  icon: '🛟',
  target: eur('9000.00'),
  monthly: eur('200.00'),
  saved: eur('6120.00'),
  deadline: null,
  account_id: null,
  remaining: eur('2880.00'),
  progress: 68,
  months_to_go: 15,
  eta: '2028-01',
  needed_monthly: null,
  on_track: null,
}

const SAVINGS = {
  month: '2026-10',
  months: ['2026-08', '2026-09', '2026-10'],
  average_saved: eur('588.03'),
  averages: [
    { category_id: 'c-super', average: eur('520.00') },
    { category_id: 'c-rest', average: eur('216.00') },
  ],
  recurring: [
    {
      merchant: 'Netflix',
      category_id: null,
      amount: eur('17.99'),
      first_amount: eur('13.99'),
      last_date: '2026-10-12',
      months: 12,
      changes: [{ month: '2026-07', before: eur('13.99'), after: eur('17.99') }],
    },
  ],
  recurring_total: eur('17.99'),
  ideas: [
    {
      id: 'cut-restaurantes',
      icon: '🍽️',
      title: 'Restaurantes y comida a domicilio: 216,00 € al mes',
      detail: 'Cambiar una cena fuera a la semana por cocinar en casa supone:',
      yearly_saving: eur('648.00'),
      evidence: '48 movimientos de los últimos 3 meses',
      assumption: 'Estimación orientativa: -25 %',
    },
  ],
  goals: [
    GOAL,
    {
      ...GOAL,
      id: 'g2',
      name: 'Vacaciones',
      icon: '🏖️',
      target: eur('2500.00'),
      saved: eur('880.00'),
      monthly: eur('100.00'),
      remaining: eur('1620.00'),
      progress: 35,
      deadline: '2027-07',
      eta: '2028-03',
      needed_monthly: eur('180.00'),
      on_track: false,
    },
  ],
}

const CATS_WITH_SLUGS = [
  ...CATEGORIES,
  { id: 'c-ocio', name: 'Ocio', icon: '🎟️', color: '#0891b2', hidden: false, slug: 'ocio' },
]

describe('Ahorro (fase 4)', () => {
  it('Este mes enseña los presupuestos y su línea en el ritmo de gasto', async () => {
    window.location.hash = '#mes'
    loggedIn({
      // todo el gasto está presupuestado: se dibuja la línea del total
      'GET /api/v1/insights/month': { body: { ...OVERVIEW, categories: OVERVIEW.categories.slice(0, 2) } },
      'GET /api/v1/budgets': { body: BUDGETS },
    })
    render(<App />)
    expect(await screen.findByText(/Presupuesto 900/)).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Supermercado: 109 % del presupuesto' })).toBeInTheDocument()
    expect(screen.getByText('600 € de 550 €').closest('li')).toHaveClass('budget-over')
    expect(screen.getByText('300 € de 350 €').closest('li')).toHaveClass('budget-warning')
    expect(screen.getByText(/86 % · cerca/)).toBeInTheDocument()
    expect(screen.getByText(/109 % · pasado/)).toBeInTheDocument()
  })

  it('sin presupuesto para todo el gasto no dibuja la línea del total', async () => {
    window.location.hash = '#mes'
    loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/budgets': { body: BUDGETS },
    })
    render(<App />)
    expect(await screen.findByText('600 € de 550 €')).toBeInTheDocument()
    expect(screen.queryByText(/Presupuesto 900/)).toBeNull()
    expect(screen.getByRole('link', { name: 'Editar presupuestos' })).toHaveAttribute('href', '#presupuestos')
  })

  it('Presupuestos guarda, propone la media y quita límites', async () => {
    window.location.hash = '#presupuestos'
    const calls = loggedIn({
      'GET /api/v1/categories': { body: CATS_WITH_SLUGS },
      'GET /api/v1/budgets': { body: { ...BUDGETS, items: [BUDGETS.items[0]] } },
      'GET /api/v1/savings/overview': { body: SAVINGS },
      'PUT /api/v1/budgets/c-super': { body: BUDGETS.items[0] },
      'PUT /api/v1/budgets/c-rest': { body: BUDGETS.items[1] },
      'PUT /api/v1/budgets/c-ocio': { body: BUDGETS.items[1] },
      'DELETE /api/v1/budgets/c-super': { status: 204 },
    })
    render(<App />)
    const sup = await screen.findByLabelText('Presupuesto de Supermercado')
    expect(sup).toHaveValue('550.00')
    // la media de restaurantes (216 €) se redondea hacia arriba a 220 €
    await userEvent.click(screen.getByRole('button', { name: /Usar 220/ }))
    await userEvent.type(screen.getByLabelText('Presupuesto de Ocio'), '75,5{Enter}')
    await userEvent.clear(sup)
    sup.blur()
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
    const writes = calls.filter((c) => c.method === 'PUT').map((c) => [c.url.pathname, JSON.parse(String(c.body))])
    expect(writes).toEqual([
      ['/api/v1/budgets/c-rest', { amount: '220.00' }],
      ['/api/v1/budgets/c-ocio', { amount: '75.5' }],
    ])
  })

  it('Ahorrar enseña objetivos, ideas y cuotas fijas', async () => {
    window.location.hash = '#ahorrar'
    loggedIn({
      'GET /api/v1/categories': { body: CATS_WITH_SLUGS },
      'GET /api/v1/savings/overview': { body: SAVINGS },
    })
    render(<App />)
    expect(await screen.findByText(/Ahorráis de media/)).toHaveTextContent('588 €')
    const fund = screen.getByRole('article', { name: 'Fondo de emergencia' })
    expect(within(fund).getByRole('img', { name: 'Fondo de emergencia: 68 %' })).toBeInTheDocument()
    expect(fund).toHaveTextContent('lo alcanzáis en enero de 2028')
    const holidays = screen.getByRole('article', { name: 'Vacaciones' })
    expect(holidays).toHaveTextContent('haría falta apartar 180 €/mes')
    expect(screen.getByText('648 €/año')).toBeInTheDocument()
    expect(screen.getByText(/13,99 € → 17,99 € en julio de 2026/)).toBeInTheDocument()
  })

  it('avisa cuando la fecha límite ya ha llegado', async () => {
    window.location.hash = '#ahorrar'
    const late = { ...GOAL, id: 'g3', name: 'Sofá', deadline: '2026-10', needed_monthly: null, on_track: false }
    loggedIn({ 'GET /api/v1/savings/overview': { body: { ...SAVINGS, goals: [late] } } })
    render(<App />)
    const card = await screen.findByRole('article', { name: 'Sofá' })
    expect(card).toHaveTextContent(/La fecha límite ya ha llegado y aún faltan 2880 €|2\.880 €/)
  })

  it('el simulador calcula el ahorro extra y adelanta el objetivo', async () => {
    window.location.hash = '#ahorrar'
    loggedIn({
      'GET /api/v1/categories': {
        body: [
          { ...CATEGORIES[0], slug: 'super' },
          { ...CATEGORIES[1], slug: 'restaurantes' },
        ],
      },
      'GET /api/v1/savings/overview': { body: SAVINGS },
    })
    render(<App />)
    // por defecto: restaurantes −25 % (54 €) y super −10 % (52 €) = 106 €/mes
    const total = await screen.findByText(/Ahorro extra/)
    const box = total.closest('.sim-total')!
    expect(box).toHaveTextContent(/106 €\/mes · 1272 €\/año|106 €\/mes · 1\.272 €\/año/)
    // 2880 € pendientes: 200 €/mes → 15 meses; 306 €/mes → 10 meses
    expect(box).toHaveTextContent('(5 meses antes)')
    fireEvent.change(screen.getByLabelText('Recorte en Restaurantes'), { target: { value: '50' } })
    // 108 + 52 = 160 €/mes → 360 €/mes → 8 meses
    expect(box).toHaveTextContent('160 €/mes')
    expect(box).toHaveTextContent('(7 meses antes)')
  })

  it('crea y actualiza objetivos', async () => {
    window.location.hash = '#ahorrar'
    const calls = loggedIn({
      'GET /api/v1/savings/overview': { body: SAVINGS },
      'POST /api/v1/goals': { status: 201, body: GOAL },
      'PATCH /api/v1/goals/g1': { body: GOAL },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: '+ Nuevo objetivo' }))
    await userEvent.type(screen.getByLabelText('Nombre del objetivo'), 'Coche')
    await userEvent.type(screen.getByLabelText('Meta'), '12000')
    await userEvent.type(screen.getByLabelText('Al mes'), '250,50')
    await userEvent.click(screen.getByRole('button', { name: 'Crear objetivo' }))
    const fund = screen.getByRole('article', { name: 'Fondo de emergencia' })
    await userEvent.click(within(fund).getByRole('button', { name: 'Actualizar' }))
    const monthly = within(fund).getByDisplayValue('200.00')
    await userEvent.clear(monthly)
    await userEvent.type(monthly, '300')
    await userEvent.click(within(fund).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
    const writes = calls.filter((c) => c.method !== 'GET').map((c) => [c.method, JSON.parse(String(c.body))])
    expect(writes).toEqual([
      ['POST', { name: 'Coche', icon: '🎯', target: '12000', monthly: '250.50', saved: '0', deadline: null }],
      ['PATCH', { clear_account: false, monthly: '300', saved: '6120.00' }],
    ])
  })
})

describe('Errores al cargar (OF-605)', () => {
  it('si fallan los movimientos de una categoría se ve el error con «Reintentar»', async () => {
    window.location.hash = '#gastos'
    let failures = 1
    loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/insights/category': { body: DETAIL },
      'GET /api/v1/transactions': (call) =>
        call.url.searchParams.has('category_id') && failures-- > 0
          ? { status: 500, body: { detail: 'Error del servidor' } }
          : { body: TRANSACTIONS },
    })
    render(<App />)
    const panel = (await screen.findByRole('heading', { name: /Movimientos de/ })).parentElement!
    expect(await within(panel).findByRole('alert')).toHaveTextContent('Error del servidor')
    await userEvent.click(within(panel).getByRole('button', { name: 'Reintentar' }))
    expect(await within(panel).findByRole('table')).toBeInTheDocument()
    expect(within(panel).queryByRole('alert')).toBeNull()
  })

  it('Presupuestos se recupera al reintentar', async () => {
    window.location.hash = '#presupuestos'
    let failures = 1
    loggedIn({
      'GET /api/v1/categories': { body: CATS_WITH_SLUGS },
      'GET /api/v1/budgets': () =>
        failures-- > 0 ? { status: 500, body: { detail: 'Error del servidor' } } : { body: BUDGETS },
      'GET /api/v1/savings/overview': { body: SAVINGS },
    })
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Error del servidor')
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByLabelText('Presupuesto de Supermercado')).toBeInTheDocument()
  })
})
