import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ACCOUNTS, CATEGORIES, ME, PREVIEW, TRANSACTIONS, mockApi, page } from '../test/api'
import axe from 'axe-core'
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
    'GET /api/v1/transactions/page': { body: page(TRANSACTIONS) },
    'GET /api/v1/categories': { body: CATEGORIES },
    'GET /api/v1/transactions/uncategorized-count': { body: { count: 1 } },
    'GET /api/v1/imports': { body: [] },
    ...extra,
  })

describe('Inicio de sesión', () => {
  it('pide credenciales sin sesión y entra con ellas', async () => {
    const calls = mockApi({
      'GET /api/v1/me': { status: 401, body: { detail: 'Inicia sesión' } },
      'POST /api/v1/auth/login': { body: ME },
      'GET /api/v1/accounts': { body: ACCOUNTS },
      'GET /api/v1/transactions/page': { body: page([]) },
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
    const month = calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').at(-1)!
    expect(month.url.searchParams.get('month')).toMatch(/^\d{4}-\d{2}$/)

    await userEvent.click(screen.getByLabelText(/Solo sin categoría/))
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').at(-1)!
      expect(last.url.searchParams.get('uncategorized')).toBe('true')
    })

    await userEvent.click(screen.getByLabelText(/Solo sin categoría/))
    await userEvent.click(screen.getByRole('button', { name: 'Mes anterior' }))
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').at(-1)!
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

describe('Varios a la vez y efectivo (OF-705)', () => {
  it('pone la misma categoría a los seleccionados sin aprender reglas y se puede deshacer', async () => {
    const calls = loggedIn({
      'POST /api/v1/transactions/categorize': { body: { updated: 2, operation_id: 'op-9' } },
      'POST /api/v1/changes/op-9/undo': {
        body: { operation: { id: 'op-9', actor_id: 'u-raul', created_at: '2026-11-01T10:00:00Z', action: 'x', summary: 'x', undone: true, changes: [] }, applied: 2, kept: 0, kept_by: [] },
      },
    })
    render(<App />)
    await userEvent.click(await screen.findByLabelText(/Solo sin categoría/))
    await userEvent.click(await screen.findByLabelText('Seleccionar Glovo'))
    await userEvent.click(screen.getByLabelText('Seleccionar Amazon'))
    expect(screen.getByText('2 seleccionados')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Categoría para los seleccionados'), 'c-rest')
    await userEvent.click(screen.getByRole('button', { name: 'Poner categoría' }))
    const bulk = calls.find((c) => c.url.pathname === '/api/v1/transactions/categorize')!
    expect(JSON.parse(String(bulk.body))).toEqual({ ids: ['t4', 't5'], category_id: 'c-rest' })
    expect(await screen.findByText('2 gastos → Restaurantes')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Deshacer' }))
    expect(await screen.findByText('Deshecho')).toBeInTheDocument()
  })

  it('añade un gasto en efectivo y avisa si la cuenta es del banco', async () => {
    const calls = loggedIn({
      'POST /api/v1/transactions': {
        status: 201,
        body: { transaction: { ...TRANSACTIONS[3], id: 't9', description: 'Churrería', source: 'manual' }, operation_id: 'op-1' },
      },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: '+ Añadir a mano' }))
    const form = screen.getByRole('form', { name: 'Añadir a mano' })
    expect(within(form).getByText(/su saldo dejará de cuadrar/)).toBeInTheDocument()
    await userEvent.type(within(form).getByLabelText('Concepto'), 'Churrería')
    await userEvent.type(within(form).getByLabelText('Importe'), '7,50')
    await userEvent.click(within(form).getByRole('button', { name: 'Añadir' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/transactions')!
    expect(JSON.parse(String(post.body))).toMatchObject({ description: 'Churrería', amount: '7.50', kind: 'expense', account_id: 'a-joint' })
    expect(await screen.findByText('Añadido: Churrería')).toBeInTheDocument()
  })

  it('solo los movimientos añadidos a mano se pueden borrar', async () => {
    const manual = { ...TRANSACTIONS[3], source: 'manual' }
    const calls = loggedIn({
      'GET /api/v1/transactions/page': { body: page([TRANSACTIONS[2], manual]) },
      'GET /api/v1/transactions/t3/history': { body: [] },
      'GET /api/v1/transactions/t4/history': { body: [] },
      'DELETE /api/v1/transactions/t4': { body: { operation_id: 'op-3' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Mercadona' }))
    expect(await screen.findByText('Sin correcciones.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Borrar' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Detalle de Glovo' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Borrar' }))
    expect(calls.some((c) => c.method === 'DELETE' && c.url.pathname === '/api/v1/transactions/t4')).toBe(true)
    expect(await screen.findByText('Borrado: Glovo')).toBeInTheDocument()
  })
})

describe('Reglas (OF-702)', () => {
  it('lista las reglas con sus movimientos y borra una con «Deshacer»', async () => {
    window.location.hash = '#reglas'
    const calls = loggedIn({
      'GET /api/v1/rules': {
        body: [
          { key: 'MERCADONA', merchant: 'Mercadona', category_id: 'c-super', scope: 'household', matches: 12 },
          { key: 'PELUQUERIA', merchant: 'Peluqueria', category_id: 'c-rest', scope: 'personal', matches: 1 },
        ],
      },
      'DELETE /api/v1/rules/household/MERCADONA': { body: { operation_id: 'op-r' } },
    })
    render(<App />)
    const row = (await screen.findByText('Mercadona')).closest('tr')!
    expect(row).toHaveTextContent('🛒 Supermercado')
    expect(row).toHaveTextContent('12')
    expect(screen.getByText('Personal · solo la ves tú')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Borrar la regla de Mercadona' }))
    expect(calls.some((c) => c.method === 'DELETE' && c.url.pathname === '/api/v1/rules/household/MERCADONA')).toBe(true)
    expect(await screen.findByText('Regla borrada: Mercadona')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deshacer' })).toBeInTheDocument()
  })
})

describe('Comercios (OF-1001)', () => {
  const GROUPS = [
    { id: null, name: 'Mercadona', keys: ['MERCADONA'], count: 5, total: { amount: '-147.34', currency: 'EUR' } },
    { id: null, name: 'Mercadona Valencia', keys: ['MERCADONA VALENCIA'], count: 2, total: { amount: '-20.00', currency: 'EUR' } },
    { id: 'm-1', name: 'Super', keys: ['A', 'B'], count: 3, total: { amount: '-9.00', currency: 'EUR' } },
  ]

  it('lista los comercios con sus variantes y totales', async () => {
    window.location.hash = '#comercios'
    loggedIn({ 'GET /api/v1/merchants': { body: GROUPS } })
    render(<App />)
    const row = (await screen.findByRole('cell', { name: 'Mercadona Valencia' })).closest('tr')!
    expect(row).toHaveTextContent('2')
    expect(screen.getByText(/2 variantes del banco: A, B/)).toBeInTheDocument()
  })

  it('renombra un comercio y se puede deshacer', async () => {
    window.location.hash = '#comercios'
    const calls = loggedIn({
      'GET /api/v1/merchants': { body: GROUPS },
      'POST /api/v1/merchants/rename': {
        body: { merchant: { ...GROUPS[0], name: 'El Mercadona' }, reclassified: 0, operation_id: 'op-m' },
      },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Renombrar Mercadona' }))
    const input = screen.getByLabelText('Nombre')
    await userEvent.clear(input)
    await userEvent.type(input, 'El Mercadona')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    const call = calls.find((c) => c.url.pathname === '/api/v1/merchants/rename')!
    expect(JSON.parse(String(call.body))).toEqual({ key: 'MERCADONA', name: 'El Mercadona' })
    expect(await screen.findByText('«Mercadona» ahora es «El Mercadona»')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deshacer' })).toBeInTheDocument()
  })

  it('un nombre repetido se avisa junto al campo', async () => {
    window.location.hash = '#comercios'
    loggedIn({
      'GET /api/v1/merchants': { body: GROUPS },
      'POST /api/v1/merchants/rename': { status: 409, body: { detail: 'Ya hay un comercio con ese nombre: fusiónalos si son el mismo' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Renombrar Mercadona' }))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Ya hay un comercio con ese nombre')
    expect(screen.getByLabelText('Nombre')).toHaveAttribute('aria-invalid', 'true')
  })

  it('fusiona otro comercio en este y cuenta los gastos clasificados', async () => {
    window.location.hash = '#comercios'
    const calls = loggedIn({
      'GET /api/v1/merchants': { body: GROUPS },
      'POST /api/v1/merchants/merge': { body: { merchant: GROUPS[0], reclassified: 2, operation_id: 'op-f' } },
    })
    render(<App />)
    await userEvent.selectOptions(await screen.findByLabelText('Fusionar otro comercio en Mercadona'), 'MERCADONA VALENCIA')
    const call = calls.find((c) => c.url.pathname === '/api/v1/merchants/merge')!
    expect(JSON.parse(String(call.body))).toEqual({ target_key: 'MERCADONA', source_key: 'MERCADONA VALENCIA' })
    expect(await screen.findByText(/«Mercadona Valencia» fusionado en «Mercadona» · 2 gastos clasificados/)).toBeInTheDocument()
  })
})

describe('Historial de importaciones (OF-703)', () => {
  const ITEM = {
    id: 'imp-9',
    account_id: 'a-joint',
    filename: 'octubre.xlsx',
    created_by: 'u-elena',
    committed_at: '2026-11-01T09:00:00Z',
    status: 'committed',
    created: 42,
    duplicates: 3,
    skipped: 1,
    can_undo: true,
  }

  it('lista quién importó qué y deshace la última tras confirmar en la pantalla', async () => {
    window.location.hash = '#importar'
    const calls = loggedIn({
      'GET /api/v1/imports': { body: [ITEM, { ...ITEM, id: 'imp-8', filename: 'septiembre.xlsx', can_undo: false }] },
      'POST /api/v1/imports/imp-9/undo': { body: { voided: 42, operation_id: 'op-i' } },
    })
    render(<App />)
    const list = await screen.findByRole('list', { name: 'Importaciones' })
    expect(within(list).getByText('octubre.xlsx').closest('li')).toHaveTextContent('Elena · 42 nuevos · 3 ya estaban · 1 descartados')
    expect(within(list).getAllByRole('button', { name: 'Deshacer' })).toHaveLength(1)
    await userEvent.click(within(list).getByRole('button', { name: 'Deshacer' }))
    expect(within(list).getByText(/Se anularán sus 42 movimientos/)).toBeInTheDocument()
    expect(calls.some((c) => c.url.pathname.endsWith('/undo'))).toBe(false)
    await userEvent.click(within(list).getByRole('button', { name: 'Sí, deshacer' }))
    expect(await screen.findByText('Importación deshecha: 42 movimientos anulados')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.url.pathname === '/api/v1/imports/imp-9/undo')).toBe(true)
  })
})

describe('Ajustes (OF-704)', () => {
  it('cambia la contraseña pidiendo la actual', async () => {
    window.location.hash = '#ajustes'
    const calls = loggedIn({ 'GET /api/v1/me/patterns': { body: [] }, 'POST /api/v1/me/password': { body: { revoked: 2 } } })
    render(<App />)
    const form = await screen.findByRole('form', { name: 'Cambiar la contraseña' })
    await userEvent.type(within(form).getByLabelText('Contraseña actual'), 'clave-actual-larga')
    await userEvent.type(within(form).getByLabelText(/Nueva contraseña/), 'clave-nueva-larga')
    await userEvent.type(within(form).getByLabelText('Repite la nueva'), 'clave-nueva-larg')
    expect(within(form).getByText('No coinciden.')).toBeInTheDocument()
    expect(within(form).getByRole('button', { name: 'Cambiar la contraseña' })).toBeDisabled()
    await userEvent.type(within(form).getByLabelText('Repite la nueva'), 'a')
    await userEvent.click(within(form).getByRole('button', { name: 'Cambiar la contraseña' }))
    const post = calls.find((c) => c.url.pathname === '/api/v1/me/password')!
    expect(JSON.parse(String(post.body))).toEqual({ current_password: 'clave-actual-larga', new_password: 'clave-nueva-larga' })
    expect(await screen.findByText('Contraseña cambiada · 2 sesiones cerradas en otros dispositivos')).toBeInTheDocument()
  })

  it('guarda la tarjeta de recarga propia', async () => {
    window.location.hash = '#ajustes'
    let saved: { pattern: string; direction: string }[] = []
    const calls = loggedIn({
      'GET /api/v1/me/patterns': () => ({ body: saved }),
      'POST /api/v1/me/patterns': () => {
        saved = [{ pattern: '*1234', direction: 'inflow' }]
        return { status: 201, body: saved[0] }
      },
    })
    render(<App />)
    expect(await screen.findByText('Aún no has guardado ninguna.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Últimos dígitos'), '1234')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/me/patterns')!
    expect(JSON.parse(String(post.body))).toEqual({ pattern: '*1234', direction: 'inflow' })
    const list = await screen.findByRole('list', { name: 'Tus tarjetas de recarga' })
    expect(await within(list).findByText('*1234')).toBeInTheDocument()
  })

  it('importar en la conjunta pide confirmación si alguien no tiene tarjeta de recarga', async () => {
    window.location.hash = '#importar'
    loggedIn({ 'POST /api/v1/imports': { status: 201, body: { ...PREVIEW, members_without_recharge: ['u-elena'] } } })
    render(<App />)
    await waitFor(() => expect(screen.getByLabelText('Cuenta')).toHaveValue('a-joint'))
    await userEvent.upload(screen.getByLabelText('Extracto'), new File(['x'], 'r.csv', { type: 'text/csv' }))
    await userEvent.click(screen.getByRole('button', { name: 'Ver vista previa' }))
    expect(await screen.findByText(/Elena no tiene guardada la tarjeta/)).toBeInTheDocument()
    const confirm = screen.getByRole('button', { name: /Importar 2 movimientos/ })
    expect(confirm).toBeDisabled()
    await userEvent.click(screen.getByLabelText(/Importar igualmente/))
    expect(confirm).toBeEnabled()
  })
})

describe('Mis cambios (OF-706)', () => {
  const OP = { id: 'op-a', actor_id: 'u-raul', created_at: '2026-11-01T10:00:00Z', action: 'transaction.edit', changes: [] }

  it('deshace y rehace las operaciones propias', async () => {
    window.location.hash = '#cambios'
    let undone = false
    const calls = loggedIn({
      'GET /api/v1/changes': () => ({ body: [{ ...OP, summary: 'Glovo: Sin categoría → Restaurantes', undone }] }),
      'POST /api/v1/changes/op-a/undo': () => {
        undone = true
        return { body: { operation: { ...OP, summary: 'x', undone: true }, applied: 1, kept: 0, kept_by: [] } }
      },
      'POST /api/v1/changes/op-a/redo': () => {
        undone = false
        return { body: { operation: { ...OP, summary: 'x', undone: false }, applied: 1, kept: 0, kept_by: [] } }
      },
    })
    render(<App />)
    const list = await screen.findByRole('list', { name: 'Mis cambios' })
    expect(within(list).getByText('Glovo: Sin categoría → Restaurantes')).toBeInTheDocument()
    await userEvent.click(within(list).getByRole('button', { name: 'Deshacer' }))
    expect(await screen.findByText('Deshecho')).toBeInTheDocument()
    await userEvent.click(await within(list).findByRole('button', { name: 'Rehacer' }))
    expect(await screen.findByText('Rehecho')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.url.pathname)).toEqual([
      '/api/v1/changes/op-a/undo',
      '/api/v1/changes/op-a/redo',
    ])
  })
})

describe('Búsqueda', () => {
  it.each(['#1', '%', '"comillas"', "l'oreal"])('busca «%s» sin romper la pantalla', async (text) => {
    const calls = loggedIn()
    render(<App />)
    await screen.findByRole('table')
    await userEvent.type(screen.getByRole('searchbox'), text)
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').at(-1)!
      expect(last.url.searchParams.get('q')).toBe(text)
    })
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })
})

describe('Error inesperado', () => {
  it('muestra un aviso con «Recargar» en vez de dejar la pantalla congelada', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined) // React registra el error capturado
    loggedIn({ 'GET /api/v1/transactions/page': { body: page([{ roto: true }]) } })
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

    const upload = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/imports')!
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
      'GET /api/v1/transactions/page': { status: 401, body: { detail: 'Inicia sesión' } },
    })
    render(<App />)
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
  })

  it('con más movimientos que una página ofrece «Cargar más» y enseña el total del filtro', async () => {
    const first = Array.from({ length: 50 }, (_, i) => ({ ...TRANSACTIONS[3], id: `t${i}` }))
    const second = Array.from({ length: 20 }, (_, i) => ({ ...TRANSACTIONS[3], id: `u${i}` }))
    const calls = loggedIn({
      'GET /api/v1/transactions/page': (call) =>
        call.url.searchParams.get('cursor') === 'c1'
          ? { body: page(second, { count: 70, total: '-700.00' }) }
          : { body: page(first, { next_cursor: 'c1', count: 70, total: '-700.00' }) },
    })
    render(<App />)
    expect(await screen.findByText(/Mostrando 50 de 70 movimientos/)).toBeInTheDocument()
    expect(screen.getByText(/Suma del filtro/)).toHaveTextContent('-700,00')
    await userEvent.click(screen.getByRole('button', { name: 'Cargar más' }))
    expect(await screen.findByText(/70 movimientos/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cargar más' })).toBeNull()
    const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').at(-1)!
    expect(last.url.searchParams.get('cursor')).toBe('c1')
    expect(screen.getAllByRole('row')).toHaveLength(71)
  })

  it('al cambiar un filtro vuelve a la primera página', async () => {
    const calls = loggedIn({
      'GET /api/v1/transactions/page': { body: page(TRANSACTIONS, { next_cursor: 'c1' }) },
    })
    render(<App />)
    await screen.findByRole('button', { name: 'Cargar más' })
    await userEvent.type(screen.getByRole('searchbox'), 'luz')
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').at(-1)!
      expect(last.url.searchParams.get('q')).toBe('luz')
      expect(last.url.searchParams.has('cursor')).toBe(false)
    })
  })

  it('corregir una categoría actualiza solo esa fila, sin volver a pedir la lista', async () => {
    const calls = loggedIn({
      'PATCH /api/v1/transactions/t4': {
        body: {
          transaction: { ...TRANSACTIONS[3], category_id: 'c-rest' },
          rule: null,
          also_categorized: 0,
          operation_id: 'op-1',
        },
      },
    })
    render(<App />)
    const select = await screen.findByLabelText(`Categoría de ${TRANSACTIONS[3].description}`)
    const before = calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').length
    await userEvent.selectOptions(select, 'c-rest')
    await waitFor(() => expect(select).toHaveValue('c-rest'))
    expect(calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').length).toBe(before)
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
  forecast: null,
  pending_charges: [],
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
    { category_id: 'c-super', amount: eur('550.00'), spent: eur('600.00'), percent: 109, status: 'over', fixed: eur('0.00') },
    { category_id: 'c-rest', amount: eur('350.00'), spent: eur('300.00'), percent: 86, status: 'warning', fixed: eur('0.00') },
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
      dismissed: false,
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

describe('Estado en la URL y menú (OF-801)', () => {
  it('los filtros de Movimientos se leen de la URL y se escriben en ella', async () => {
    window.location.hash = '#movimientos?q=luz&sin=1&mes=2026-08'
    const calls = loggedIn()
    render(<App />)
    await screen.findByRole('table')
    const first = calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').at(-1)!
    expect(first.url.searchParams.get('q')).toBe('luz')
    expect(first.url.searchParams.get('uncategorized')).toBe('true')
    expect(screen.getByRole('searchbox')).toHaveValue('luz')

    await userEvent.click(screen.getByLabelText(/Solo sin categoría/))
    await waitFor(() => expect(window.location.hash).not.toContain('sin=1'))
    expect(window.location.hash).toContain('q=luz')
  })

  it('el mes elegido va en la URL y el menú lo conserva al cambiar de pantalla', async () => {
    window.location.hash = '#mes'
    loggedIn({ 'GET /api/v1/insights/month': { body: OVERVIEW } })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Mes anterior' }))
    await waitFor(() => expect(window.location.hash).toBe('#mes?mes=2026-09'))
    const nav = screen.getByRole('navigation', { name: 'Secciones' })
    expect(within(nav).getByRole('link', { name: /Movimientos/ })).toHaveAttribute('href', '#movimientos?mes=2026-09')
  })

  it('un mes inválido en la URL se ignora', async () => {
    window.location.hash = '#movimientos?mes=basura'
    const calls = loggedIn()
    render(<App />)
    await screen.findByRole('table')
    const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions/page').at(-1)!
    expect(last.url.searchParams.get('month')).toBe('2026-10')
  })

  it('el menú marca la pantalla actual', async () => {
    loggedIn()
    render(<App />)
    const nav = await screen.findByRole('navigation', { name: 'Secciones' })
    expect(within(nav).getByRole('link', { name: /Movimientos/ })).toHaveAttribute('aria-current', 'page')
  })
})

describe('Este mes honesto (OF-802)', () => {
  const PARTIAL = {
    ...OVERVIEW,
    is_partial: true,
    days_elapsed: 20,
    forecast: eur('1400.00'),
    pending_charges: [
      { merchant: 'Gimnasio', category_id: null, amount: eur('30.00'), expected_day: 25, late: false },
      { merchant: 'Seguro hogar', category_id: null, amount: eur('45.00'), expected_day: 10, late: true },
    ],
  }

  it('enseña la previsión de cierre y los cargos pendientes del mes en curso', async () => {
    window.location.hash = '#mes'
    loggedIn({ 'GET /api/v1/insights/month': { body: PARTIAL } })
    render(<App />)
    expect(await screen.findByText(/Al ritmo actual cerraríais el mes en torno a/)).toHaveTextContent('1400 €')
    const list = screen.getByRole('list', { name: 'Cargos pendientes' })
    expect(within(list).getByText('Gimnasio')).toBeInTheDocument()
    expect(within(list).getByText(/día 25/)).toBeInTheDocument()
    expect(within(list).getByText(/Seguro hogar/).closest('li')).toHaveTextContent('aún no ha llegado')
  })

  it('un mes cerrado no hace previsión ni lista cargos', async () => {
    window.location.hash = '#mes'
    loggedIn({ 'GET /api/v1/insights/month': { body: OVERVIEW } })
    render(<App />)
    await screen.findByRole('heading', { name: 'Este mes' })
    expect(screen.queryByText(/Al ritmo actual/)).toBeNull()
    expect(screen.queryByRole('list', { name: 'Cargos pendientes' })).toBeNull()
  })

  it('explica que parte de un presupuesto son cuotas fijas', async () => {
    window.location.hash = '#mes'
    loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/budgets': {
        body: {
          ...BUDGETS,
          items: [{ ...BUDGETS.items[1], status: 'ok', fixed: eur('120.00') }],
        },
      },
    })
    render(<App />)
    expect(await screen.findByText(/120 € son cuotas fijas/)).toBeInTheDocument()
    expect(screen.queryByText(/cerca/)).toBeNull()
  })
})

describe('Accesibilidad (OF-804)', () => {
  const MERCHANTS = [
    { id: null, name: 'Mercadona', keys: ['MERCADONA'], count: 5, total: { amount: '-147.34', currency: 'EUR' } },
    { id: null, name: 'Mercadona Valencia', keys: ['MERCADONA VALENCIA'], count: 2, total: { amount: '-20.00', currency: 'EUR' } },
  ]
  const RULES = [{ key: 'MERCADONA', merchant: 'Mercadona', category_id: 'c-super', scope: 'household', matches: 12 }]
  const OP = { id: 'op-a', actor_id: 'u-raul', created_at: '2026-11-01T10:00:00Z', action: 'transaction.edit', changes: [], summary: 'Glovo → Restaurantes', undone: false }
  const mocks = () => ({
    'GET /api/v1/version': { body: { current: '0.2.0', enabled: false, latest: null, url: null, update_available: false } },
    'GET /api/v1/insights/month': { body: OVERVIEW },
    'GET /api/v1/insights/category': { body: DETAIL },
    'GET /api/v1/insights/trends': { body: TRENDS },
    'GET /api/v1/budgets': { body: BUDGETS },
    'GET /api/v1/savings/overview': { body: SAVINGS },
    'GET /api/v1/rules': { body: RULES },
    'GET /api/v1/merchants': { body: MERCHANTS },
    'GET /api/v1/changes': { body: [OP] },
    'GET /api/v1/me/patterns': { body: [] },
  })

  /** Reglas de WCAG 2.1 A/AA. El contraste se comprueba aparte: jsdom no calcula estilos de CSS. */
  async function violations(): Promise<string[]> {
    const result = await axe.run(document.body, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
      rules: { 'color-contrast': { enabled: false } },
    })
    return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)
  }

  const SCREENS: Array<[string, string, string]> = [
    ['mes', 'Este mes', 'heading'],
    ['gastos', '¿En qué gastamos?', 'heading'],
    ['evolucion', 'Evolución', 'heading'],
    ['ahorrar', 'Ahorrar', 'heading'],
    ['movimientos', 'Movimientos', 'heading'],
    ['importar', 'Importar extracto', 'heading'],
    ['categorias', 'Categorías', 'heading'],
    ['presupuestos', 'Presupuestos', 'heading'],
    ['reglas', 'Reglas', 'heading'],
    ['comercios', 'Comercios', 'heading'],
    ['ajustes', 'Ajustes', 'heading'],
    ['cambios', 'Mis cambios', 'heading'],
  ]

  it.each(SCREENS)('%s no tiene violaciones de axe', async (hash, title) => {
    window.location.hash = `#${hash}`
    loggedIn(mocks())
    render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('Cargando…')).toBeNull())
    expect(await violations()).toEqual([])
    expect(document.title).toBe(`${title} · OpenFinance`)
  })

  it('el detector funciona: encuentra una imagen sin texto alternativo', async () => {
    render(<img src="x.png" />)
    expect(await violations()).toEqual([expect.stringContaining('image-alt')])
  })

  it('el acceso (sin sesión) no tiene violaciones y el error va junto al campo', async () => {
    mockApi({
      'GET /api/v1/me': { status: 401 },
      'POST /api/v1/auth/login': { status: 401, body: { detail: 'Email o contraseña incorrectos' } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Email'), 'raul@example.org')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'mala-clave')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    const alert = await screen.findByRole('alert')
    const password = screen.getByLabelText('Contraseña')
    expect(password).toHaveAttribute('aria-invalid', 'true')
    expect(password).toHaveAttribute('aria-describedby', alert.id)
    expect(password).toHaveFocus()
    expect(await violations()).toEqual([])
  })

  it('al cambiar de pantalla el foco pasa al contenido y hay un enlace para saltar el menú', async () => {
    loggedIn(mocks())
    render(<App />)
    await screen.findByRole('table')
    expect(screen.getByRole('link', { name: 'Saltar al contenido' })).toHaveAttribute('href', '#contenido')
    const nav = screen.getByRole('navigation', { name: 'Secciones' })
    await userEvent.click(within(nav).getByRole('link', { name: /Importar/ }))
    await screen.findByRole('heading', { level: 1, name: 'Importar extracto' })
    expect(screen.getByRole('main')).toHaveFocus()
  })

  it('un importe mal escrito se avisa junto al campo y le devuelve el foco', async () => {
    loggedIn(mocks())
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: '+ Añadir a mano' }))
    await userEvent.type(screen.getByLabelText(/Concepto/), 'Pan')
    await userEvent.type(screen.getByLabelText(/Importe/), 'abc')
    await userEvent.click(screen.getByRole('button', { name: 'Añadir' }))
    const amount = screen.getByLabelText(/Importe/)
    expect(amount).toHaveAttribute('aria-invalid', 'true')
    expect(amount).toHaveFocus()
    expect(screen.getByRole('alert')).toHaveTextContent('Escribe un importe mayor que cero')
  })

  it('Ajustes dice qué versión hay y cómo activar el aviso de versiones nuevas', async () => {
    window.location.hash = '#ajustes'
    loggedIn(mocks())
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Versión' })).toBeInTheDocument()
    expect(await screen.findByText('0.2.0')).toBeInTheDocument()
    expect(screen.getByText('OPENFINANCE_UPDATE_CHECK=true')).toBeInTheDocument()
  })

  it('una contraseña actual incorrecta se señala en su campo, sin cerrar la sesión', async () => {
    window.location.hash = '#ajustes'
    loggedIn({
      ...mocks(),
      'POST /api/v1/me/password': { status: 422, body: { detail: 'La contraseña actual no es correcta' } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Contraseña actual'), 'mala-clave-1')
    await userEvent.type(screen.getByLabelText(/Nueva contraseña/), 'nueva-clave-larga')
    await userEvent.type(screen.getByLabelText('Repite la nueva'), 'nueva-clave-larga')
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar la contraseña' }))
    const current = screen.getByLabelText('Contraseña actual')
    await waitFor(() => expect(current).toHaveAttribute('aria-invalid', 'true'))
    expect(current).toHaveFocus()
    expect(screen.getByRole('alert')).toHaveTextContent('La contraseña actual no es correcta')
  })

  it('un presupuesto no válido se avisa junto a su campo y conserva lo escrito', async () => {
    window.location.hash = '#presupuestos'
    loggedIn(mocks())
    render(<App />)
    const input = await screen.findByLabelText('Presupuesto de Restaurantes')
    await userEvent.clear(input)
    await userEvent.type(input, 'mucho')
    await userEvent.tab()
    expect(await screen.findByRole('alert')).toHaveTextContent('Escribe un importe mayor que cero')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveValue('mucho')
  })
})

describe('Apariencia y app instalable (OF-805)', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('data-theme')
    window.localStorage.clear()
  })

  it('el tema oscuro se elige en Ajustes, se aplica y se recuerda', async () => {
    window.location.hash = '#ajustes'
    loggedIn({ 'GET /api/v1/me/patterns': { body: [] } })
    render(<App />)
    const group = await screen.findByRole('radiogroup', { name: 'Apariencia' })
    expect(within(group).getByLabelText('Como el sistema')).toBeChecked()
    await userEvent.click(within(group).getByLabelText('Oscuro'))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(window.localStorage.getItem('openfinance-theme')).toBe('dark')
    await userEvent.click(within(group).getByLabelText('Como el sistema'))
    expect(document.documentElement).not.toHaveAttribute('data-theme')
    expect(window.localStorage.getItem('openfinance-theme')).toBeNull()
  })

  it('si el navegador no deja guardar, el tema vale para esta visita', async () => {
    window.location.hash = '#ajustes'
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    loggedIn({ 'GET /api/v1/me/patterns': { body: [] } })
    render(<App />)
    await userEvent.click(await screen.findByLabelText('Claro'))
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })
})

describe('Simulador e ideas (OF-806)', () => {
  const MANY = Array.from({ length: 9 }, (_, i) => ({
    id: `c-${i}`,
    name: `Categoría ${i}`,
    icon: '🏷️',
    color: '#000000',
    hidden: false,
    slug: `cat-${i}`,
  }))
  const WITH_ALL = {
    ...SAVINGS,
    averages: MANY.map((c, i) => ({ category_id: c.id, average: eur(`${(90 - i * 10).toFixed(2)}`) })),
  }

  it('el simulador ofrece todas las categorías con gasto, de mayor a menor media', async () => {
    window.location.hash = '#ahorrar'
    loggedIn({ 'GET /api/v1/categories': { body: MANY }, 'GET /api/v1/savings/overview': { body: WITH_ALL } })
    render(<App />)
    await screen.findByText(/Ahorro extra/)
    // Seis a la vista y el resto plegado, pero todas cuentan en el total.
    const sliders = screen.getAllByRole('slider')
    expect(sliders.map((s) => s.getAttribute('aria-label'))).toEqual(
      [0, 1, 2, 3, 4, 5].map((i) => `Recorte en Categoría ${i}`),
    )
    fireEvent.change(sliders[0], { target: { value: '50' } })
    const box = screen.getByText(/Ahorro extra/).closest('.sim-total')!
    expect(box).toHaveTextContent('45 €/mes') // 50 % de 90 €
    await userEvent.click(screen.getByRole('button', { name: 'Mostrar las 3 categorías restantes' }))
    expect(screen.getAllByRole('slider')).toHaveLength(9)
    fireEvent.change(screen.getByLabelText('Recorte en Categoría 8'), { target: { value: '50' } })
    expect(box).toHaveTextContent('50 €/mes') // + 50 % de 10 €
  })

  it('descarta una idea, la esconde y se puede recuperar', async () => {
    window.location.hash = '#ahorrar'
    let dismissed = false
    const calls = loggedIn({
      'GET /api/v1/savings/overview': () => ({
        body: { ...SAVINGS, ideas: SAVINGS.ideas.map((i) => ({ ...i, dismissed })) },
      }),
      'PUT /api/v1/savings/ideas/cut-restaurantes/dismissed': () => {
        dismissed = true
        return { status: 204 }
      },
      'DELETE /api/v1/savings/ideas/cut-restaurantes/dismissed': () => {
        dismissed = false
        return { status: 204 }
      },
    })
    render(<App />)
    const ideas = await screen.findByRole('list', { name: 'Ideas' })
    await userEvent.click(within(ideas).getByRole('button', { name: /Descartar: Restaurantes/ }))
    expect(await screen.findByText('Has descartado todas las ideas.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT' && c.url.pathname.endsWith('/cut-restaurantes/dismissed'))).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: /1 idea descartada/ }))
    const old = screen.getByRole('list', { name: 'Ideas descartadas' })
    await userEvent.click(within(old).getByRole('button', { name: /Recuperar: Restaurantes/ }))
    expect(await screen.findByRole('button', { name: /Descartar: Restaurantes/ })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Ideas descartadas' })).toBeNull()
  })
})
