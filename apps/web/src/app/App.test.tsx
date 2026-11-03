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

describe('Etiquetas y notas largas (OF-1002)', () => {
  const TAGGED = TRANSACTIONS.map((t) => (t.id === 't4' ? { ...t, tags: ['Cena', 'Amigos'] } : t))

  it('enseña las etiquetas del movimiento y permite filtrar por una', async () => {
    window.location.hash = '#movimientos'
    const calls = loggedIn({
      'GET /api/v1/transactions/page': { body: page(TAGGED) },
      'GET /api/v1/tags': { body: [{ tag: 'Amigos', count: 1 }, { tag: 'Cena', count: 1 }] },
    })
    render(<App />)
    expect(await screen.findByText('#Cena')).toBeInTheDocument()
    await userEvent.selectOptions(await screen.findByLabelText('Etiqueta'), 'Cena')
    await waitFor(() =>
      expect(calls.some((c) => c.url.pathname === '/api/v1/transactions/page' && c.url.searchParams.get('tag') === 'Cena')).toBe(true),
    )
    expect(window.location.hash).toContain('etiqueta=Cena')
  })

  it('guarda las etiquetas separadas por comas y avisa con «Deshacer»', async () => {
    window.location.hash = '#movimientos'
    const calls = loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'PUT /api/v1/transactions/t4/tags': { body: { transaction: TAGGED[3], operation_id: 'op-t' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    await userEvent.type(await screen.findByLabelText(/Etiquetas \(separadas/), 'cena, #amigos ,')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar etiquetas' }))
    const put = calls.find((c) => c.method === 'PUT')!
    expect(JSON.parse(String(put.body))).toEqual({ tags: ['cena', '#amigos'] })
    expect(await screen.findByText('Etiquetas guardadas')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deshacer' })).toBeInTheDocument()
  })

  it('una etiqueta no válida se avisa junto al campo', async () => {
    window.location.hash = '#movimientos'
    loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'PUT /api/v1/transactions/t4/tags': { status: 422, body: { detail: 'Una etiqueta admite como máximo 40 caracteres' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    const input = await screen.findByLabelText(/Etiquetas \(separadas/)
    await userEvent.type(input, 'larga')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar etiquetas' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('como máximo 40 caracteres')
    expect(input).toHaveAttribute('aria-invalid', 'true')
  })

  it('la nota admite varias líneas y la lista enseña solo la primera', async () => {
    window.location.hash = '#movimientos'
    const NOTED = TRANSACTIONS.map((t) => (t.id === 't4' ? { ...t, note: 'Primera línea\nSegunda línea' } : t))
    loggedIn({
      'GET /api/v1/transactions/page': { body: page(NOTED) },
      'GET /api/v1/transactions/t4/history': { body: [] },
    })
    render(<App />)
    expect(await screen.findByText(/📝 Primera línea/)).toBeInTheDocument()
    expect(screen.queryByText(/Segunda línea/)).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Detalle de Glovo' }))
    const note = (await screen.findByLabelText('Nota')) as HTMLTextAreaElement
    expect(note.tagName).toBe('TEXTAREA')
    expect(note.value).toBe('Primera línea\nSegunda línea')
    expect(note).toHaveAttribute('maxlength', '2000')
  })
})

describe('Dividir un gasto (OF-1003)', () => {
  const open = async () => {
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Dividir en partes' }))
  }

  it('avisa de lo que falta por repartir y solo deja guardar cuando suma el total', async () => {
    window.location.hash = '#movimientos'
    loggedIn({ 'GET /api/v1/transactions/t4/history': { body: [] } })
    render(<App />)
    await open()
    expect(within(screen.getByRole('form', { name: 'Dividir el gasto' })).getByRole('status')).toHaveTextContent('Falta por repartir 25,40')
    await userEvent.type(screen.getByLabelText('Importe de la parte 1'), '20')
    await userEvent.selectOptions(screen.getByLabelText('Categoría de la parte 1'), 'c-rest')
    await userEvent.type(screen.getByLabelText('Importe de la parte 2'), '3,40')
    await userEvent.selectOptions(screen.getByLabelText('Categoría de la parte 2'), 'c-super')
    expect(within(screen.getByRole('form', { name: 'Dividir el gasto' })).getByRole('status')).toHaveTextContent('Falta por repartir 2,00')
    expect(screen.getByRole('button', { name: 'Guardar la división' })).toBeDisabled()
    await userEvent.clear(screen.getByLabelText('Importe de la parte 2'))
    await userEvent.type(screen.getByLabelText('Importe de la parte 2'), '5,40')
    expect(within(screen.getByRole('form', { name: 'Dividir el gasto' })).getByRole('status')).toHaveTextContent('Todo repartido.')
    expect(screen.getByRole('button', { name: 'Guardar la división' })).toBeEnabled()
    await userEvent.clear(screen.getByLabelText('Importe de la parte 2'))
    await userEvent.type(screen.getByLabelText('Importe de la parte 2'), '9,40')
    expect(within(screen.getByRole('form', { name: 'Dividir el gasto' })).getByRole('status')).toHaveTextContent('Te pasas 4,00')
  })

  it('envía las partes con el signo del gasto y permite deshacer', async () => {
    window.location.hash = '#movimientos'
    const calls = loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'PUT /api/v1/transactions/t4/split': { body: { transaction: TRANSACTIONS[3], operation_id: 'op-s' } },
    })
    render(<App />)
    await open()
    await userEvent.type(screen.getByLabelText('Importe de la parte 1'), '20')
    await userEvent.selectOptions(screen.getByLabelText('Categoría de la parte 1'), 'c-rest')
    await userEvent.type(screen.getByLabelText('Importe de la parte 2'), '5,40')
    await userEvent.selectOptions(screen.getByLabelText('Categoría de la parte 2'), 'c-super')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar la división' }))
    const put = calls.find((c) => c.method === 'PUT')!
    expect(JSON.parse(String(put.body))).toEqual({
      parts: [
        { amount: '-20', category_id: 'c-rest' },
        { amount: '-5.40', category_id: 'c-super' },
      ],
    })
    expect(await screen.findByText('Gasto dividido')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deshacer' })).toBeInTheDocument()
  })

  it('un gasto ya dividido enseña sus partes y se puede deshacer la división', async () => {
    window.location.hash = '#movimientos'
    const SPLIT = TRANSACTIONS.map((t) =>
      t.id === 't4'
        ? {
            ...t,
            parts: [
              { amount: { amount: '-20.00', currency: 'EUR' }, category_id: 'c-rest' },
              { amount: { amount: '-5.40', currency: 'EUR' }, category_id: 'c-super' },
            ],
          }
        : t,
    )
    const calls = loggedIn({
      'GET /api/v1/transactions/page': { body: page(SPLIT) },
      'GET /api/v1/transactions/t4/history': { body: [] },
      'DELETE /api/v1/transactions/t4/split': { body: { transaction: TRANSACTIONS[3], operation_id: 'op-u' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    const list = await screen.findByRole('list', { name: 'Partes del gasto' })
    expect(list).toHaveTextContent('🍽️ Restaurantes · -20,00')
    expect(list).toHaveTextContent('🛒 Supermercado · -5,40')
    await userEvent.click(screen.getByRole('button', { name: 'Deshacer la división' }))
    expect(calls.some((c) => c.method === 'DELETE' && c.url.pathname === '/api/v1/transactions/t4/split')).toBe(true)
    expect(await screen.findByText('División deshecha')).toBeInTheDocument()
  })

  it('un ingreso no se puede dividir', async () => {
    window.location.hash = '#movimientos'
    loggedIn({ 'GET /api/v1/transactions/t1/history': { body: [] } })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Payment from Raul' }))
    await screen.findByText('Sin correcciones.')
    expect(screen.queryByRole('button', { name: 'Dividir en partes' })).toBeNull()
  })
})

describe('Traspasos enlazados (OF-1004)', () => {
  const OTHER = { ...TRANSACTIONS[3], id: 't9', description: 'Entrada de Glovo', account_id: 'a-raul', amount: { amount: '25.40', currency: 'EUR' } }

  it('busca el otro lado, lo enlaza y avisa con «Deshacer»', async () => {
    window.location.hash = '#movimientos'
    const calls = loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'GET /api/v1/transactions/t4/transfer-candidates': { body: [OTHER] },
      'PUT /api/v1/transactions/t4/link': { body: { transaction: TRANSACTIONS[3], peer: OTHER, operation_id: 'op-l' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Enlazar como traspaso' }))
    const list = await screen.findByRole('list', { name: 'Posibles otros lados' })
    expect(list).toHaveTextContent('Entrada de Glovo · Bankinter Raúl · +25,40')
    await userEvent.click(screen.getByRole('button', { name: 'Enlazar con Entrada de Glovo' }))
    expect(JSON.parse(String(calls.find((c) => c.method === 'PUT' && c.url.pathname.endsWith('/link'))!.body))).toEqual({ peer_id: 't9' })
    expect(await screen.findByText('Traspaso enlazado')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deshacer' })).toBeInTheDocument()
  })

  it('dice cuando no hay otro lado posible', async () => {
    window.location.hash = '#movimientos'
    loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'GET /api/v1/transactions/t4/transfer-candidates': { body: [] },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Enlazar como traspaso' }))
    expect(await screen.findByText(/No hay un movimiento de otra cuenta tuya/)).toBeInTheDocument()
  })

  it('un traspaso enlazado lleva 🔗 y se puede desenlazar', async () => {
    window.location.hash = '#movimientos'
    const LINKED = TRANSACTIONS.map((t) => (t.id === 't4' ? { ...t, transfer_peer_id: 't9' } : t))
    const calls = loggedIn({
      'GET /api/v1/transactions/page': { body: page(LINKED) },
      'GET /api/v1/transactions/t4/history': { body: [] },
      'DELETE /api/v1/transactions/t4/link': { body: { transaction: TRANSACTIONS[3], peer: OTHER, operation_id: 'op-d' } },
    })
    render(<App />)
    expect(await screen.findByLabelText('Traspaso enlazado')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Detalle de Glovo' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Desenlazar' }))
    expect(calls.some((c) => c.method === 'DELETE' && c.url.pathname === '/api/v1/transactions/t4/link')).toBe(true)
    expect(await screen.findByText('Traspaso desenlazado')).toBeInTheDocument()
  })
})

describe('Tipos de cuenta (OF-1005)', () => {
  const CARD = { id: 'a-visa', name: 'Visa', institution: 'other', kind: 'personal', type: 'card', owner_id: 'u-raul', opening_balance: { amount: '0.00', currency: 'EUR' }, balance: { amount: '-120.50', currency: 'EUR' } }

  it('lista las cuentas con su tipo y enseña lo que se debe', async () => {
    window.location.hash = '#ajustes'
    loggedIn({ 'GET /api/v1/accounts': { body: [...ACCOUNTS, CARD] }, 'GET /api/v1/me/patterns': { body: [] } })
    render(<App />)
    const list = await screen.findByRole('list', { name: 'Tus cuentas' })
    expect(list).toHaveTextContent('Cuenta conjunta · Banco')
    expect(list).toHaveTextContent('Visa · Tarjeta de crédito · solo tuya · Debes 120,50')
  })

  it('añade una cuenta de efectivo', async () => {
    window.location.hash = '#ajustes'
    const calls = loggedIn({
      'GET /api/v1/accounts': { body: ACCOUNTS },
      'GET /api/v1/me/patterns': { body: [] },
      'POST /api/v1/accounts': { status: 201, body: { ...CARD, type: 'cash', name: 'Cartera' } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Nombre'), 'Cartera')
    await userEvent.clear(screen.getByLabelText('Saldo de partida'))
    await userEvent.type(screen.getByLabelText('Saldo de partida'), '40,50')
    await userEvent.click(screen.getByRole('button', { name: 'Añadir cuenta' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/accounts')!
    expect(JSON.parse(String(post.body))).toEqual({ name: 'Cartera', type: 'cash', shared: true, opening_balance: '40.50' })
    expect(await screen.findByText('Cuenta «Cartera» añadida')).toBeInTheDocument()
  })

  it('un saldo mal escrito se avisa junto al campo', async () => {
    window.location.hash = '#ajustes'
    loggedIn({ 'GET /api/v1/accounts': { body: ACCOUNTS }, 'GET /api/v1/me/patterns': { body: [] } })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Nombre'), 'X')
    await userEvent.clear(screen.getByLabelText('Saldo de partida'))
    await userEvent.type(screen.getByLabelText('Saldo de partida'), 'mucho')
    await userEvent.click(screen.getByRole('button', { name: 'Añadir cuenta' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Escribe un saldo')
    expect(screen.getByLabelText('Saldo de partida')).toHaveAttribute('aria-invalid', 'true')
  })
})

describe('Revisado y conciliación (OF-1006)', () => {
  it('marca un movimiento como revisado y avisa con «Deshacer»', async () => {
    window.location.hash = '#movimientos'
    const calls = loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'POST /api/v1/transactions/review': { body: { changed: 1, operation_id: 'op-r' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    await userEvent.click(await screen.findByLabelText('Revisado con el banco'))
    const post = calls.find((c) => c.url.pathname === '/api/v1/transactions/review')!
    expect(JSON.parse(String(post.body))).toEqual({ ids: ['t4'], reviewed: true })
    expect(await screen.findByText('Marcado como revisado')).toBeInTheDocument()
  })

  it('filtra los movimientos sin revisar', async () => {
    window.location.hash = '#movimientos'
    const calls = loggedIn()
    render(<App />)
    await userEvent.click(await screen.findByLabelText('Solo sin revisar'))
    await waitFor(() =>
      expect(calls.some((c) => c.url.pathname === '/api/v1/transactions/page' && c.url.searchParams.get('reviewed') === 'false')).toBe(true),
    )
  })

  const RECON = (matches: boolean, diff: string) => ({
    id: 'r1',
    account_id: 'a-joint',
    as_of: '2026-10-31',
    bank_balance: { amount: '1300.00', currency: 'EUR' },
    computed_balance: { amount: '1227.26', currency: 'EUR' },
    difference: { amount: diff, currency: 'EUR' },
    matches,
    created_by: 'u-raul',
    created_at: '2026-11-02T10:00:00Z',
  })

  it('comprueba el saldo de una cuenta y dice lo que falta', async () => {
    window.location.hash = '#movimientos?cuenta=a-joint'
    const calls = loggedIn({
      'GET /api/v1/accounts/a-joint/reconciliations': { body: [] },
      'POST /api/v1/accounts/a-joint/reconciliations': { status: 201, body: RECON(false, '72.74') },
    })
    render(<App />)
    await userEvent.click(await screen.findByText(/Comprobar el saldo de «Cuenta conjunta»/))
    await userEvent.type(screen.getByLabelText('Saldo según el banco'), '1300')
    await userEvent.click(screen.getByRole('button', { name: 'Comprobar' }))
    const post = calls.find((c) => c.method === 'POST')!
    expect(JSON.parse(String(post.body))).toMatchObject({ bank_balance: '1300' })
    expect(await screen.findByText(/Faltan 72,74/)).toBeInTheDocument()
  })

  it('un saldo mal escrito se avisa junto al campo', async () => {
    window.location.hash = '#movimientos?cuenta=a-joint'
    loggedIn({ 'GET /api/v1/accounts/a-joint/reconciliations': { body: [] } })
    render(<App />)
    await userEvent.click(await screen.findByText(/Comprobar el saldo de «Cuenta conjunta»/))
    await userEvent.type(screen.getByLabelText('Saldo según el banco'), 'mucho')
    await userEvent.click(screen.getByRole('button', { name: 'Comprobar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Escribe el saldo del banco')
  })
})

describe('Adjuntos (OF-1007)', () => {
  const ATT = { id: 'att-1', transaction_id: 't4', filename: 'ticket.png', content_type: 'image/png', size: 2048, created_by: 'u-raul', created_at: '2026-11-02T10:00:00Z' }

  it('lista los adjuntos con enlace de descarga y permite borrar con «Deshacer»', async () => {
    window.location.hash = '#movimientos'
    const calls = loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'GET /api/v1/transactions/t4/attachments': { body: [ATT] },
      'DELETE /api/v1/attachments/att-1': { body: { operation_id: 'op-a' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    const link = await screen.findByRole('link', { name: /ticket.png/ })
    expect(link).toHaveAttribute('href', '/api/v1/attachments/att-1')
    expect(link).toHaveAttribute('download', 'ticket.png')
    await userEvent.click(screen.getByRole('button', { name: 'Borrar el adjunto ticket.png' }))
    expect(calls.some((c) => c.method === 'DELETE' && c.url.pathname === '/api/v1/attachments/att-1')).toBe(true)
    expect(await screen.findByText('Adjunto «ticket.png» borrado')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deshacer' })).toBeInTheDocument()
  })

  it('sube un archivo y avisa', async () => {
    window.location.hash = '#movimientos'
    const calls = loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'GET /api/v1/transactions/t4/attachments': { body: [] },
      'POST /api/v1/transactions/t4/attachments': { status: 201, body: { attachment: ATT, operation_id: 'op-u' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    const file = new File([new Uint8Array([137, 80, 78, 71])], 'ticket.png', { type: 'image/png' })
    await userEvent.upload(await screen.findByLabelText(/Adjuntar ticket o factura/), file)
    expect(calls.some((c) => c.method === 'POST' && c.url.pathname === '/api/v1/transactions/t4/attachments')).toBe(true)
    expect(await screen.findByText('Adjuntado «ticket.png»')).toBeInTheDocument()
  })

  it('un archivo de más de 5 MB se rechaza antes de subirlo', async () => {
    window.location.hash = '#movimientos'
    const calls = loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'GET /api/v1/transactions/t4/attachments': { body: [] },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'enorme.pdf', { type: 'application/pdf' })
    await userEvent.upload(await screen.findByLabelText(/Adjuntar ticket o factura/), big)
    expect(await screen.findByRole('alert')).toHaveTextContent('pesa más de 5 MB')
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('el servidor puede rechazar el tipo y se avisa', async () => {
    window.location.hash = '#movimientos'
    loggedIn({
      'GET /api/v1/transactions/t4/history': { body: [] },
      'GET /api/v1/transactions/t4/attachments': { body: [] },
      'POST /api/v1/transactions/t4/attachments': { status: 422, body: { detail: 'Solo se admiten PDF e imágenes PNG, JPEG o WebP' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Detalle de Glovo' }))
    await userEvent.upload(await screen.findByLabelText(/Adjuntar ticket o factura/), new File(['x'], 'a.png', { type: 'image/png' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Solo se admiten PDF')
  })
})

describe('Varias monedas (OF-1008)', () => {
  const USD = { currency: 'USD', on: '2026-10-01', rate: '0.90000000', source: 'manual' }

  it('lista los tipos de cambio y avisa de los movimientos sin tipo', async () => {
    window.location.hash = '#ajustes'
    loggedIn({
      'GET /api/v1/me/patterns': { body: [] },
      'GET /api/v1/exchange-rates': { body: [USD] },
      'GET /api/v1/exchange-rates/missing': { body: [{ currency: 'GBP', count: 3, first: '2026-10-05' }] },
    })
    render(<App />)
    const list = await screen.findByRole('list', { name: 'Tipos de cambio' })
    expect(list).toHaveTextContent('1 USD = 0.9 EUR')
    expect(await screen.findByText(/3 movimientos en GBP sin tipo de cambio/)).toBeInTheDocument()
  })

  it('guarda un tipo de cambio y avisa con «Deshacer»', async () => {
    window.location.hash = '#ajustes'
    const calls = loggedIn({
      'GET /api/v1/me/patterns': { body: [] },
      'GET /api/v1/exchange-rates': { body: [] },
      'GET /api/v1/exchange-rates/missing': { body: [] },
      'PUT /api/v1/exchange-rates': { body: { rate: USD, operation_id: 'op-x' } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Moneda'), 'usd')
    await userEvent.type(screen.getByLabelText(/Vale en EUR/), '0,9')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar tipo' }))
    const put = calls.find((c) => c.method === 'PUT')!
    expect(JSON.parse(String(put.body))).toMatchObject({ currency: 'USD', rate: '0,9' })
    expect(await screen.findByText('Tipo de cambio USD guardado')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deshacer' })).toBeInTheDocument()
  })

  it('un tipo no válido se avisa junto al campo', async () => {
    window.location.hash = '#ajustes'
    loggedIn({
      'GET /api/v1/me/patterns': { body: [] },
      'GET /api/v1/exchange-rates': { body: [] },
      'GET /api/v1/exchange-rates/missing': { body: [] },
      'PUT /api/v1/exchange-rates': { status: 422, body: { detail: 'EUR ya es la moneda del hogar: no necesita tipo de cambio' } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Moneda'), 'EUR')
    await userEvent.type(screen.getByLabelText(/Vale en EUR/), '1')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar tipo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('ya es la moneda del hogar')
    expect(screen.getByLabelText(/Vale en EUR/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('una cuenta puede ir en otra moneda', async () => {
    window.location.hash = '#ajustes'
    const calls = loggedIn({
      'GET /api/v1/me/patterns': { body: [] },
      'GET /api/v1/exchange-rates': { body: [] },
      'GET /api/v1/exchange-rates/missing': { body: [] },
      'POST /api/v1/accounts': { status: 201, body: { ...ACCOUNTS[0], name: 'Viajes', type: 'cash' } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Nombre'), 'Viajes')
    await userEvent.type(screen.getByLabelText(/Moneda \(vacío/), 'usd')
    await userEvent.click(screen.getByRole('button', { name: 'Añadir cuenta' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/accounts')!
    expect(JSON.parse(String(post.body))).toMatchObject({ name: 'Viajes', currency: 'USD' })
  })

  it('la suma del filtro dice qué monedas no cuenta', async () => {
    window.location.hash = '#movimientos'
    loggedIn({ 'GET /api/v1/transactions/page': { body: { ...page(TRANSACTIONS), other_currencies: ['USD'] } } })
    render(<App />)
    expect(await screen.findByText(/sin contar USD/)).toBeInTheDocument()
  })
})

describe('Reglas con condiciones (OF-1101, OF-1102)', () => {
  const RULE = {
    id: 'ar-1',
    name: 'Suscripciones',
    personal: false,
    phase: 'normal',
    priority: 10,
    enabled: true,
    conditions: [{ field: 'description', op: 'contains', value: 'amazon' }],
    actions: [
      { type: 'set_category', value: 'c-rest' },
      { type: 'add_tags', value: ['suscripción'] },
    ],
  }
  const PREVIEW = {
    count: 3,
    items: [
      {
        transaction: { ...TRANSACTIONS[4], tags: [], parts: [] },
        changes: [
          { field: 'category_id', before: null, after: 'c-rest' },
          { field: 'tags', before: null, after: 'suscripción' },
        ],
      },
    ],
  }

  it('lista las reglas con lo que hacen', async () => {
    window.location.hash = '#reglas'
    loggedIn({ 'GET /api/v1/rules': { body: [] }, 'GET /api/v1/automation-rules': { body: [{ ...RULE, personal: true }] } })
    render(<App />)
    const list = await screen.findByRole('list', { name: 'Tus reglas con condiciones' })
    expect(list).toHaveTextContent('Suscripciones')
    expect(list).toHaveTextContent('El concepto contiene «amazon» → categoría Restaurantes, etiquetas #suscripción')
    expect(list).toHaveTextContent('Personal, solo la ves tú')
  })

  it('prueba una regla guardada y la aplica a lo existente con «Deshacer»', async () => {
    window.location.hash = '#reglas'
    const calls = loggedIn({
      'GET /api/v1/rules': { body: [] },
      'GET /api/v1/automation-rules': { body: [RULE] },
      'POST /api/v1/automation-rules/ar-1/preview': { body: PREVIEW },
      'POST /api/v1/automation-rules/ar-1/apply': { body: { changed: 3, operation_id: 'op-ap' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Probar la regla Suscripciones' }))
    const region = await screen.findByRole('region', { name: 'Vista previa de la regla' })
    expect(within(region).getByRole('status')).toHaveTextContent('Cambiaría 3 movimientos (se enseñan 1)')
    expect(region).toHaveTextContent('Categoría: — → 🍽️ Restaurantes')
    expect(calls.some((c) => c.method === 'POST' && c.url.pathname.endsWith('/apply'))).toBe(false)  // probar no escribe
    await userEvent.click(within(region).getByRole('button', { name: 'Aplicar a lo existente' }))
    expect(await screen.findByText('«Suscripciones»: 3 movimientos cambiados')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deshacer' })).toBeInTheDocument()
  })

  it('crea una regla desde el formulario', async () => {
    window.location.hash = '#reglas'
    const calls = loggedIn({
      'GET /api/v1/rules': { body: [] },
      'GET /api/v1/automation-rules': { body: [] },
      'POST /api/v1/automation-rules': { status: 201, body: { rule: RULE, operation_id: 'op-c' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Nueva regla' }))
    await userEvent.type(screen.getByLabelText('Nombre'), 'Suscripciones')
    await userEvent.type(screen.getByLabelText('Valor de la condición 1'), 'amazon')
    await userEvent.selectOptions(screen.getByLabelText('Valor de la acción 1'), 'c-rest')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar la regla' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/automation-rules')!
    expect(JSON.parse(String(post.body))).toEqual({
      name: 'Suscripciones',
      personal: false,
      phase: 'normal',
      priority: null,
      enabled: true,
      conditions: [{ field: 'description', op: 'contains', value: 'amazon' }],
      actions: [{ type: 'set_category', value: 'c-rest' }],
    })
    expect(await screen.findByText('Regla «Suscripciones» guardada')).toBeInTheDocument()
  })

  it('una regla no válida se avisa en el formulario y conserva lo escrito', async () => {
    window.location.hash = '#reglas'
    loggedIn({
      'GET /api/v1/rules': { body: [] },
      'GET /api/v1/automation-rules': { body: [] },
      'POST /api/v1/automation-rules': { status: 422, body: { detail: 'El importe mínimo no puede ser mayor que el máximo' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Nueva regla' }))
    await userEvent.type(screen.getByLabelText('Nombre'), 'Rara')
    await userEvent.type(screen.getByLabelText('Valor de la condición 1'), 'x')
    await userEvent.selectOptions(screen.getByLabelText('Valor de la acción 1'), 'c-rest')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar la regla' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('importe mínimo')
    expect(screen.getByLabelText('Nombre')).toHaveValue('Rara')
  })

  it('desactiva una regla', async () => {
    window.location.hash = '#reglas'
    const calls = loggedIn({
      'GET /api/v1/rules': { body: [] },
      'GET /api/v1/automation-rules': { body: [RULE] },
      'PUT /api/v1/automation-rules/ar-1': { body: { rule: { ...RULE, enabled: false }, operation_id: 'op-t' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Desactivar la regla Suscripciones' }))
    const put = calls.find((c) => c.method === 'PUT')!
    expect(JSON.parse(String(put.body))).toMatchObject({ enabled: false, name: 'Suscripciones' })
  })
})

describe('Importar formatos estándar (OF-1103)', () => {
  it('una cuenta sin banco propio ya se puede elegir y acepta OFX, QIF y CAMT', async () => {
    window.location.hash = '#importar'
    const CASH = { id: 'a-cash', name: 'Efectivo', institution: 'other', kind: 'joint', type: 'cash', owner_id: null, opening_balance: { amount: '0.00', currency: 'EUR' }, balance: { amount: '0.00', currency: 'EUR' } }
    loggedIn({ 'GET /api/v1/accounts': { body: [CASH] } })
    render(<App />)
    const option = await screen.findByRole('option', { name: 'Efectivo' })
    expect(option).not.toBeDisabled()
    expect(await screen.findByText(/Elige el extracto \(OFX, QIF, CAMT.053 o CSV\)/)).toBeInTheDocument()
    expect(document.querySelector('input[type=file]')).toHaveAttribute('accept', '.ofx,.qfx,.qif,.xml,.csv,.txt')
  })
})

describe('Perfiles de CSV (OF-1105)', () => {
  const CASH = { id: 'a-cash', name: 'Otro banco', institution: 'other', kind: 'joint', type: 'cash', owner_id: null, opening_balance: { amount: '0.00', currency: 'EUR' }, balance: { amount: '0.00', currency: 'EUR' } }
  const PROFILE = { id: 'p-1', name: 'Mi banco', delimiter: ';', encoding: 'cp1252', skip_rows: 0, has_header: true, date_column: 0, date_format: '%d/%m/%Y', description_columns: [1], amount_mode: 'single', amount_column: 2, debit_column: null, credit_column: null, decimal_separator: ',', invert_sign: false, balance_column: null }
  const SAMPLE = { delimiter: ';', encoding: 'cp1252', rows: [['Fecha', 'Concepto', 'Importe'], ['03/10/2026', 'CAFE', '-1,80'], ['04/10/2026', 'SUELDO', '1.600,00']] }
  const TEST = {
    rows: [
      { line: 2, booked_at: '2026-10-03T00:00:00', description: 'CAFE', amount: { amount: '-1.80', currency: 'EUR' }, balance: null },
      { line: 3, booked_at: '2026-10-04T00:00:00', description: 'SUELDO', amount: { amount: '1600.00', currency: 'EUR' }, balance: null },
    ],
    total: 2,
    skipped: [{ line: 4, reason: 'fila no válida: fecha no válida', description: 'ROTA' }],
    skipped_total: 1,
  }
  const mocks = (extra = {}) =>
    loggedIn({ 'GET /api/v1/accounts': { body: [CASH] }, 'GET /api/v1/csv-profiles': { body: [PROFILE] }, ...extra })

  it('ofrece los perfiles guardados al importar en una cuenta sin banco propio', async () => {
    window.location.hash = '#importar'
    mocks()
    render(<App />)
    const select = await screen.findByLabelText(/Si es un CSV, perfil/)
    expect(within(select).getByRole('option', { name: 'Mi banco' })).toBeInTheDocument()
  })

  it('crea un perfil desde un archivo de ejemplo: muestra las filas, prueba y guarda', async () => {
    window.location.hash = '#importar'
    const calls = mocks({
      'POST /api/v1/csv-profiles/sample': { body: SAMPLE },
      'POST /api/v1/csv-profiles/test': { body: TEST },
      'POST /api/v1/csv-profiles': { status: 201, body: { profile: PROFILE, operation_id: 'op-p' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Crear un perfil de CSV' }))
    const wizard = await screen.findByRole('form', { name: 'Nuevo perfil de CSV' })
    await userEvent.upload(within(wizard).getByLabelText('Extracto de ejemplo'), new File(['x'], 'banco.csv', { type: 'text/csv' }))
    const region = await screen.findByRole('region', { name: 'Primeras filas del archivo' })
    expect(region).toHaveTextContent('03/10/2026')
    expect(within(wizard).getByRole('button', { name: 'Guardar el perfil' })).toBeDisabled()
    await userEvent.type(within(wizard).getByLabelText('Nombre del perfil'), 'Mi banco')
    await userEvent.click(within(wizard).getByRole('button', { name: 'Probar con el archivo' }))
    const result = await screen.findByRole('region', { name: 'Resultado de la prueba' })
    expect(within(result).getByRole('status')).toHaveTextContent('2 filas se leen bien y 1 se descartan')
    expect(result).toHaveTextContent('Línea 4: fila no válida: fecha no válida')
    await userEvent.click(within(wizard).getByRole('button', { name: 'Guardar el perfil' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/csv-profiles')!
    expect(JSON.parse(String(post.body))).toMatchObject({ name: 'Mi banco', delimiter: ';', encoding: 'cp1252', date_format: '%d/%m/%Y' })
    expect(await screen.findByText('Perfil «Mi banco» guardado')).toBeInTheDocument()
  })

  it('no deja guardar un perfil que no lee ninguna fila', async () => {
    window.location.hash = '#importar'
    mocks({
      'POST /api/v1/csv-profiles/sample': { body: SAMPLE },
      'POST /api/v1/csv-profiles/test': { body: { ...TEST, rows: [], total: 0 } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Crear un perfil de CSV' }))
    const wizard = await screen.findByRole('form', { name: 'Nuevo perfil de CSV' })
    await userEvent.upload(within(wizard).getByLabelText('Extracto de ejemplo'), new File(['x'], 'banco.csv'))
    await userEvent.type(await within(wizard).findByLabelText('Nombre del perfil'), 'Vacío')
    await userEvent.click(within(wizard).getByRole('button', { name: 'Probar con el archivo' }))
    await screen.findByRole('region', { name: 'Resultado de la prueba' })
    expect(within(wizard).getByRole('button', { name: 'Guardar el perfil' })).toBeDisabled()
  })

  it('el servidor puede rechazar el archivo y se avisa', async () => {
    window.location.hash = '#importar'
    mocks({ 'POST /api/v1/csv-profiles/sample': { status: 422, body: { detail: 'El archivo está vacío' } } })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Crear un perfil de CSV' }))
    const wizard = await screen.findByRole('form', { name: 'Nuevo perfil de CSV' })
    await userEvent.upload(within(wizard).getByLabelText('Extracto de ejemplo'), new File(['x'], 'vacio.csv'))
    expect(await screen.findByRole('alert')).toHaveTextContent('El archivo está vacío')
  })

  it('envía el perfil elegido al subir el extracto', async () => {
    window.location.hash = '#importar'
    const calls = mocks({ 'POST /api/v1/imports': { status: 201, body: PREVIEW } })
    render(<App />)
    await userEvent.selectOptions(await screen.findByLabelText(/Si es un CSV, perfil/), 'p-1')
    await userEvent.upload(screen.getByLabelText('Extracto'), new File(['x'], 'banco.csv', { type: 'text/csv' }))
    await userEvent.click(screen.getByRole('button', { name: 'Ver vista previa' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/imports')!
    expect((post.body as FormData).get('profile_id')).toBe('p-1')
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

  it('crea un movimiento desde una plantilla con la fecha elegida', async () => {
    const template = {
      id: 'tpl1',
      name: 'Café de la oficina',
      kind: 'expense',
      amount: { amount: '1.80', currency: 'EUR' },
      description: 'Café',
      account_id: 'a-joint',
      personal: false,
      category_id: null,
      tags: [],
      note: '',
    }
    const calls = loggedIn({
      'GET /api/v1/templates': { body: [template] },
      'POST /api/v1/templates/tpl1/use': {
        status: 201,
        body: { transaction: { ...TRANSACTIONS[3], id: 't9', description: 'Café', source: 'manual' }, operation_id: 'op-1' },
      },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: '+ Añadir a mano' }))
    const form = screen.getByRole('form', { name: 'Añadir a mano' })
    fireEvent.change(within(form).getByLabelText('Fecha'), { target: { value: '2026-10-12' } })
    await userEvent.click(await within(form).findByRole('button', { name: /Café de la oficina · 1,80/ }))
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/templates/tpl1/use')!
    expect(JSON.parse(String(post.body))).toEqual({ booked_on: '2026-10-12' })
    expect(await screen.findByText('Añadido: Café')).toBeInTheDocument()
  })

  it('guarda el formulario como plantilla y la borra con «Deshacer»', async () => {
    const saved = {
      id: 'tpl2',
      name: 'Churros',
      kind: 'expense',
      amount: { amount: '7.50', currency: 'EUR' },
      description: 'Churrería',
      account_id: 'a-joint',
      personal: false,
      category_id: null,
      tags: [],
      note: '',
    }
    let current = [] as unknown[]
    const calls = loggedIn({
      'GET /api/v1/templates': () => ({ body: current }),
      'POST /api/v1/templates': () => {
        current = [saved]
        return { status: 201, body: { template: saved, operation_id: 'op-5' } }
      },
      'DELETE /api/v1/templates/tpl2': () => {
        current = []
        return { body: { operation_id: 'op-6' } }
      },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: '+ Añadir a mano' }))
    const form = screen.getByRole('form', { name: 'Añadir a mano' })
    await userEvent.type(within(form).getByLabelText('Concepto'), 'Churrería')
    await userEvent.type(within(form).getByLabelText('Importe'), '7,50')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar como plantilla' }))
    const name = within(form).getByLabelText('Nombre de la plantilla')
    await userEvent.clear(name)
    await userEvent.type(name, 'Churros')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar plantilla' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/templates')!
    expect(JSON.parse(String(post.body))).toMatchObject({
      name: 'Churros',
      kind: 'expense',
      amount: '7.50',
      description: 'Churrería',
      account_id: 'a-joint',
      personal: false,
    })
    await userEvent.click(await within(form).findByRole('button', { name: 'Borrar la plantilla Churros' }))
    expect(await screen.findByText(/Plantilla «Churros» borrada/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'DELETE' && c.url.pathname === '/api/v1/templates/tpl2')).toBe(true)
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

const BUDGET_DEFAULTS = { mode: 'limit', has_override: false, carried: eur('0.00'), started: null }

const BUDGETS = {
  month: '2026-10',
  items: [
    { ...BUDGET_DEFAULTS, category_id: 'c-super', amount: eur('550.00'), base_amount: eur('550.00'), available: eur('-50.00'), spent: eur('600.00'), percent: 109, status: 'over', fixed: eur('0.00') },
    { ...BUDGET_DEFAULTS, category_id: 'c-rest', amount: eur('350.00'), base_amount: eur('350.00'), available: eur('50.00'), spent: eur('300.00'), percent: 86, status: 'warning', fixed: eur('0.00') },
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
  priority: 50,
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

  it('Este mes cuenta el arrastre de un sobre dentro de lo que se puede gastar', async () => {
    window.location.hash = '#mes'
    const envelope = { ...BUDGETS.items[1], mode: 'envelope', started: '2026-08', carried: eur('-40.00'), available: eur('90.00'), status: 'ok', percent: 80 }
    loggedIn({
      'GET /api/v1/categories': { body: CATS_WITH_SLUGS },
      'GET /api/v1/budgets': { body: { ...BUDGETS, items: [envelope] } },
      'GET /api/v1/insights/month': { body: OVERVIEW },
    })
    render(<App />)
    expect(await screen.findByText('300 € de 310 €')).toBeInTheDocument()
    expect(screen.getByText(/Sobre: arrastra un exceso de 40 € del mes anterior/)).toBeInTheDocument()
  })

  it('Presupuestos muestra el arrastre de un sobre y cambia de tipo', async () => {
    window.location.hash = '#presupuestos'
    const envelope = { ...BUDGETS.items[0], mode: 'envelope', started: '2026-08', carried: eur('120.00'), available: eur('70.00') }
    const calls = loggedIn({
      'GET /api/v1/categories': { body: CATS_WITH_SLUGS },
      'GET /api/v1/budgets': { body: { ...BUDGETS, items: [envelope, BUDGETS.items[1]] } },
      'GET /api/v1/savings/overview': { body: SAVINGS },
      'PUT /api/v1/budgets/c-rest': { body: BUDGETS.items[1] },
    })
    render(<App />)
    expect(await screen.findByText(/Sobre desde agosto de 2026 · arrastra 120,00 € · disponible 70,00 €/)).toBeInTheDocument()
    expect(screen.getByLabelText('Tipo de presupuesto de Supermercado')).toHaveValue('envelope')
    expect(screen.getByLabelText('Tipo de presupuesto de Restaurantes')).toHaveValue('limit')
    await userEvent.selectOptions(screen.getByLabelText('Tipo de presupuesto de Restaurantes'), 'envelope')
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    const put = calls.find((c) => c.method === 'PUT')!
    expect(put.url.pathname).toBe('/api/v1/budgets/c-rest')
    expect(JSON.parse(String(put.body))).toEqual({ amount: '350.00', mode: 'envelope' })
  })

  it('Presupuestos pone y quita un importe solo para el mes elegido', async () => {
    window.location.hash = '#presupuestos'
    const withMonth = { ...BUDGETS.items[0], has_override: true, amount: eur('900.00') }
    const calls = loggedIn({
      'GET /api/v1/categories': { body: CATS_WITH_SLUGS },
      'GET /api/v1/budgets': { body: { ...BUDGETS, items: [withMonth, BUDGETS.items[1]] } },
      'GET /api/v1/savings/overview': { body: SAVINGS },
      'PUT /api/v1/budgets/c-rest/months/2026-10': { body: BUDGETS.items[1] },
      'DELETE /api/v1/budgets/c-super/months/2026-10': { status: 204 },
    })
    render(<App />)
    const sup = await screen.findByLabelText('Importe de Supermercado solo en octubre de 2026')
    expect(sup).toHaveValue('900.00')
    // el presupuesto de siempre sigue siendo el base, no el del mes
    expect(screen.getByLabelText('Presupuesto de Supermercado')).toHaveValue('550.00')
    await userEvent.type(screen.getByLabelText('Importe de Restaurantes solo en octubre de 2026'), '500{Enter}')
    await userEvent.clear(sup)
    sup.blur()
    await waitFor(() => expect(calls.filter((c) => c.method !== 'GET')).toHaveLength(2))
    const writes = calls.filter((c) => c.method !== 'GET').map((c) => [c.method, c.url.pathname, c.body ? JSON.parse(String(c.body)) : null])
    expect(writes).toContainEqual(['PUT', '/api/v1/budgets/c-rest/months/2026-10', { amount: '500' }])
    expect(writes).toContainEqual(['DELETE', '/api/v1/budgets/c-super/months/2026-10', null])
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

  it('anota una aportación a un objetivo, la lista y la borra con «Deshacer»', async () => {
    window.location.hash = '#ahorrar'
    const contribution = { id: 'k1', goal_id: 'g1', made_on: '2026-10-12', amount: eur('150.00'), note: 'Paga extra' }
    let current = [] as unknown[]
    const calls = loggedIn({
      'GET /api/v1/savings/overview': { body: SAVINGS },
      'GET /api/v1/goals/g1/contributions': () => ({ body: current }),
      'POST /api/v1/goals/g1/contributions': () => {
        current = [contribution]
        return { status: 201, body: { contribution, operation_id: 'op-7' } }
      },
      'DELETE /api/v1/goals/g1/contributions/k1': () => {
        current = []
        return { body: { operation_id: 'op-8' } }
      },
    })
    render(<App />)
    const fund = await screen.findByRole('article', { name: 'Fondo de emergencia' })
    await userEvent.type(within(fund).getByLabelText('Cantidad para Fondo de emergencia'), '150')
    await userEvent.type(within(fund).getByLabelText('Nota para Fondo de emergencia'), 'Paga extra')
    await userEvent.click(within(fund).getByRole('button', { name: 'Aportar a Fondo de emergencia' }))
    const post = calls.find((c) => c.method === 'POST')!
    expect(JSON.parse(String(post.body))).toEqual({ amount: '150', note: 'Paga extra' })
    expect(await screen.findByText('Aportación anotada')).toBeInTheDocument()

    await userEvent.click(within(fund).getByRole('button', { name: 'Ver aportaciones' }))
    const list = await within(fund).findByRole('list', { name: 'Aportaciones a Fondo de emergencia' })
    expect(list).toHaveTextContent('+150,00 €')
    expect(list).toHaveTextContent('Paga extra')
    await userEvent.click(within(list).getByRole('button', { name: /Borrar la aportación de 150,00/ }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
    expect(await screen.findByText('Aportación borrada')).toBeInTheDocument()
  })

  it('una retirada se manda en negativo', async () => {
    window.location.hash = '#ahorrar'
    const calls = loggedIn({
      'GET /api/v1/savings/overview': { body: SAVINGS },
      'POST /api/v1/goals/g1/contributions': {
        status: 201,
        body: { contribution: { id: 'k2', goal_id: 'g1', made_on: '2026-10-12', amount: eur('-40.00'), note: '' }, operation_id: null },
      },
    })
    render(<App />)
    const fund = await screen.findByRole('article', { name: 'Fondo de emergencia' })
    await userEvent.type(within(fund).getByLabelText('Cantidad para Fondo de emergencia'), '40')
    await userEvent.click(within(fund).getByRole('button', { name: 'Retirar de Fondo de emergencia' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(JSON.parse(String(calls.find((c) => c.method === 'POST')!.body))).toMatchObject({ amount: '-40' })
  })

  it('un objetivo con hucha no deja anotar aportaciones', async () => {
    window.location.hash = '#ahorrar'
    loggedIn({ 'GET /api/v1/savings/overview': { body: { ...SAVINGS, goals: [{ ...GOAL, account_id: 'a-pocket' }] } } })
    render(<App />)
    const fund = await screen.findByRole('article', { name: 'Fondo de emergencia' })
    expect(within(fund).queryByRole('button', { name: /Aportar a/ })).toBeNull()
  })

  it('propone repartir una cantidad por prioridad y enlaza el recordatorio mensual', async () => {
    window.location.hash = '#ahorrar'
    const calls = loggedIn({
      'GET /api/v1/savings/overview': { body: SAVINGS },
      'GET /api/v1/goals/split': {
        body: [
          { goal_id: 'g1', name: 'Fondo de emergencia', amount: eur('200.00'), remaining: eur('200.00') },
          { goal_id: 'g2', name: 'Vacaciones', amount: eur('100.00'), remaining: eur('800.00') },
        ],
      },
    })
    render(<App />)
    const fund = await screen.findByRole('article', { name: 'Fondo de emergencia' })
    const reminder = within(fund).getByRole('link', { name: 'Programar la aportación mensual a Fondo de emergencia' })
    const href = new URLSearchParams(reminder.getAttribute('href')!.split('?')[1])
    expect(href.get('nombre')).toBe('Aportación a Fondo de emergencia')
    expect(href.get('importe')).toBe('-200.00')
    expect(href.get('fecha')).toBe('2026-11-01')

    await userEvent.type(screen.getByLabelText('Cantidad a repartir'), '300')
    await userEvent.click(screen.getByRole('button', { name: 'Sugerir reparto' }))
    const shares = await screen.findByRole('list', { name: 'Reparto sugerido' })
    expect(shares).toHaveTextContent('Fondo de emergencia: 200,00 €')
    expect(shares).toHaveTextContent('Vacaciones: 100,00 €')
    expect(calls.find((c) => c.url.pathname === '/api/v1/goals/split')!.url.searchParams.get('amount')).toBe('300')
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
      ['POST', { name: 'Coche', icon: '🎯', target: '12000', monthly: '250.50', saved: '0', deadline: null, priority: 50 }],
      ['PATCH', { clear_account: false, monthly: '300', saved: '6120.00', priority: 50 }],
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
    'GET /api/v1/csv-profiles': { body: [] },
    'GET /api/v1/insights/month': { body: OVERVIEW },
    'GET /api/v1/insights/category': { body: DETAIL },
    'GET /api/v1/insights/trends': { body: TRENDS },
    'GET /api/v1/budgets': { body: BUDGETS },
    'GET /api/v1/savings/overview': { body: SAVINGS },
    'GET /api/v1/rules': { body: RULES },
    'GET /api/v1/merchants': { body: MERCHANTS },
    'GET /api/v1/automation-rules': { body: [] },
    'GET /api/v1/exchange-rates': { body: [] },
    'GET /api/v1/exchange-rates/missing': { body: [] },
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

describe('Pagos programados', () => {
  const PAYMENT = {
    id: 's1',
    name: 'Alquiler',
    amount: { amount: '-900.00', currency: 'EUR' },
    account_id: 'a-joint',
    frequency: 'monthly',
    interval: 1,
    first_due: '2026-10-01',
    ends_on: null,
    category_id: null,
    merchant: '',
    variable: false,
    active: true,
  }
  const ITEM = {
    payment: PAYMENT,
    occurrences: [
      { due: '2026-10-01', amount: PAYMENT.amount, status: 'paid', transaction_id: 't9' },
      { due: '2026-11-01', amount: PAYMENT.amount, status: 'pending', transaction_id: null },
      { due: '2026-09-28', amount: PAYMENT.amount, status: 'late', transaction_id: null },
    ],
  }

  it('enseña los pagos con sus próximas fechas y marca el atraso', async () => {
    window.location.hash = '#pagos'
    loggedIn({ 'GET /api/v1/schedule': { body: [ITEM] } })
    render(<App />)
    const list = await screen.findByRole('list', { name: 'Tus pagos programados' })
    expect(list).toHaveTextContent('Alquiler')
    expect(list).toHaveTextContent('Cuenta conjunta')
    const dates = screen.getByRole('list', { name: 'Próximas fechas de Alquiler' })
    expect(dates).toHaveTextContent('Atrasado')
    expect(dates).toHaveTextContent('Pendiente')
    expect(dates).not.toHaveTextContent('Cobrado')
  })

  it('crea un pago con el importe en negativo y avisa de que se puede deshacer', async () => {
    window.location.hash = '#pagos'
    const calls = loggedIn({
      'GET /api/v1/schedule': { body: [] },
      'POST /api/v1/schedule': { status: 201, body: { payment: PAYMENT, operation_id: 'op1' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo pago programado' }))
    await userEvent.type(screen.getByLabelText('Nombre'), 'Alquiler')
    await userEvent.type(screen.getByLabelText('Importe'), '900')
    fireEvent.change(screen.getByLabelText(/Primera fecha/), { target: { value: '2026-11-01' } })
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.pathname === '/api/v1/schedule')).toBe(true))
    const sent = JSON.parse(String(calls.find((c) => c.method === 'POST' && c.url.pathname === '/api/v1/schedule')!.body))
    expect(sent).toMatchObject({
      name: 'Alquiler',
      amount: '-900',
      account_id: 'a-joint',
      frequency: 'monthly',
      interval: 1,
      first_due: '2026-11-01',
      ends_on: null,
    })
  })

  it('un ingreso se manda en positivo y borrar avisa con deshacer', async () => {
    window.location.hash = '#pagos'
    const calls = loggedIn({
      'GET /api/v1/schedule': { body: [ITEM] },
      'PUT /api/v1/schedule/s1': { body: { payment: PAYMENT, operation_id: 'op2' } },
      'DELETE /api/v1/schedule/s1': { body: { operation_id: 'op3' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Editar el pago Alquiler' }))
    await userEvent.selectOptions(screen.getByLabelText('Tipo'), 'in')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(JSON.parse(String(calls.find((c) => c.method === 'PUT')!.body))).toMatchObject({ amount: '900.00' })

    await userEvent.click(await screen.findByRole('button', { name: 'Borrar el pago Alquiler' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
    expect(await screen.findByText(/Pago «Alquiler» borrado/)).toBeInTheDocument()
  })

  it('enseña la previsión de saldo y avisa del primer día en negativo', async () => {
    window.location.hash = '#pagos'
    const eur = (amount: string) => ({ amount, currency: 'EUR' })
    const joint = {
      account_id: 'a-joint',
      name: 'Cuenta conjunta',
      currency: 'EUR',
      start: eur('100.00'),
      end: eur('-800.00'),
      lowest: { day: '2026-11-01', balance: eur('-800.00') },
      first_negative: '2026-11-01',
      points: [
        { day: '2026-10-15', balance: eur('100.00') },
        { day: '2026-11-01', balance: eur('-800.00') },
      ],
    }
    loggedIn({
      'GET /api/v1/schedule': { body: [ITEM] },
      'GET /api/v1/forecast': { body: { until: '2027-01-13', accounts: [joint], totals: [{ ...joint, account_id: null, name: null }] } },
    })
    render(<App />)
    const box = await screen.findByRole('region', { name: 'Previsión de saldo' })
    expect(box).toHaveTextContent('Total en EUR')
    const alerts = within(screen.getByRole('list', { name: 'Avisos de saldo negativo' }))
    expect(alerts.getByRole('alert')).toHaveTextContent('Cuenta conjunta: el saldo queda en negativo')
    expect(within(screen.getByRole('list', { name: 'Previsión por cuenta' })).getByText(/Cuenta conjunta/)).toBeInTheDocument()
  })

  it('sin pagos programados la previsión no inventa nada', async () => {
    window.location.hash = '#pagos'
    const eur = (amount: string) => ({ amount, currency: 'EUR' })
    const flat = { account_id: 'a-joint', name: 'Cuenta conjunta', currency: 'EUR', start: eur('100.00'), end: eur('100.00'), lowest: { day: '2026-10-15', balance: eur('100.00') }, first_negative: null, points: [{ day: '2026-10-15', balance: eur('100.00') }] }
    loggedIn({
      'GET /api/v1/schedule': { body: [] },
      'GET /api/v1/forecast': { body: { until: '2027-01-13', accounts: [flat], totals: [{ ...flat, account_id: null, name: null }] } },
    })
    render(<App />)
    const box = await screen.findByRole('region', { name: 'Previsión de saldo' })
    expect(box).toHaveTextContent('Sin pagos programados')
    expect(screen.queryByRole('list', { name: 'Avisos de saldo negativo' })).toBeNull()
  })

  const eurm = (amount: string) => ({ amount, currency: 'EUR' })
  const ALLOWANCE = {
    status: 'ok',
    balance: eurm('1227.26'),
    committed: eurm('900.00'),
    available: eurm('327.26'),
    per_day: eurm('18.18'),
    days: 18,
    until: '2026-10-28',
    horizon: 'income',
    short: false,
    pending: [{ name: 'Alquiler', due: '2026-10-20', amount: eurm('-900.00') }],
    next_income: { name: 'Nómina', due: '2026-10-28', amount: eurm('1600.00') },
    envelopes: [{ category_id: 'c-super', available: eurm('52.66'), status: 'ok' }],
  }

  it('Este mes enseña cuánto se puede gastar hoy, con su cuenta y los sobres', async () => {
    window.location.hash = '#mes'
    loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/allowance': { body: ALLOWANCE },
    })
    render(<App />)
    const card = await screen.findByRole('region', { name: 'Hoy podéis gastar' })
    expect(card).toHaveTextContent('18,18 € al día')
    expect(card).toHaveTextContent('cuando llega Nómina (18 días)')
    expect(card).toHaveTextContent('1227,26 € menos 900,00 € de pagos pendientes')
    expect(within(card).getByRole('list', { name: 'Pagos que se descuentan' })).toHaveTextContent('Alquiler')
    expect(within(card).getByRole('list', { name: 'Sobres' })).toHaveTextContent('quedan 52,66 € en el sobre')
  })

  const ALERT = {
    kind: 'fee',
    key: 'fee:t1',
    severity: 'info',
    title: 'Comisión: Mantenimiento',
    detail: '2.00 EUR cobrados por el banco.',
    on: '2026-10-20',
    amount: eurm('2.00'),
    account_id: 'a-joint',
  }

  it('Este mes enseña los avisos y deja descartarlos', async () => {
    window.location.hash = '#mes'
    const calls = loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/alerts': { body: [{ ...ALERT, kind: 'low_balance', key: 'low:1', severity: 'critical', title: 'Cuenta conjunta se queda en negativo' }, ALERT] },
      'POST /api/v1/alerts/dismiss': { status: 204 },
    })
    render(<App />)
    const card = await screen.findByRole('region', { name: 'Avisos' })
    const items = within(card).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Cuenta conjunta se queda en negativo')
    await userEvent.click(within(card).getByRole('button', { name: 'Descartar: Comisión: Mantenimiento' }))
    await waitFor(() => expect(within(card).queryByText('Comisión: Mantenimiento')).toBeNull())
    const sent = calls.find((c) => c.url.pathname === '/api/v1/alerts/dismiss')
    expect(JSON.parse(String(sent?.body))).toEqual({ key: 'fee:t1' })
  })

  it('sin avisos no hay tarjeta, y si no se pueden pedir Este mes sigue funcionando', async () => {
    window.location.hash = '#mes'
    loggedIn({ 'GET /api/v1/insights/month': { body: OVERVIEW }, 'GET /api/v1/alerts': { body: [] } })
    render(<App />)
    await screen.findByRole('heading', { name: '¿En qué se ha ido?' })
    expect(screen.queryByRole('region', { name: 'Avisos' })).toBeNull()
  })

  it('si no llega, la tarjeta lo dice en lugar de repartir', async () => {
    window.location.hash = '#mes'
    loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/allowance': {
        body: { ...ALLOWANCE, short: true, available: eurm('-400.00'), per_day: eurm('0.00'), committed: eurm('1627.26') },
      },
    })
    render(<App />)
    const card = await screen.findByRole('region', { name: 'Hoy podéis gastar' })
    expect(within(card).getByRole('alert')).toHaveTextContent('no llega hasta el')
    expect(card).not.toHaveTextContent(/€ al día/)
  })

  it('sin pagos programados no se inventa ninguna cifra', async () => {
    window.location.hash = '#mes'
    loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/allowance': {
        body: { ...ALLOWANCE, status: 'no_schedule', balance: null, committed: null, available: null, per_day: null, days: null, until: null, horizon: null, pending: [], next_income: null, envelopes: [] },
      },
    })
    render(<App />)
    const card = await screen.findByRole('region', { name: 'Hoy podéis gastar' })
    expect(card).toHaveTextContent('Programad el alquiler')
    expect(card).not.toHaveTextContent(/€ al día/)
    expect(within(card).getByRole('link', { name: /Programad el alquiler/ })).toHaveAttribute('href', '#pagos')
  })

  it('sin cuenta conjunta la tarjeta no aparece', async () => {
    window.location.hash = '#mes'
    loggedIn({
      'GET /api/v1/insights/month': { body: OVERVIEW },
      'GET /api/v1/allowance': { body: { ...ALLOWANCE, status: 'no_balance' } },
    })
    render(<App />)
    await screen.findByRole('heading', { name: 'Este mes' })
    expect(screen.queryByRole('region', { name: 'Hoy podéis gastar' })).toBeNull()
  })

  it('un cargo detectado llega con su nombre, importe y fecha ya puestos', async () => {
    window.location.hash = '#pagos?nombre=Netflix&importe=-17.99&fecha=2026-11-02'
    loggedIn({ 'GET /api/v1/schedule': { body: [] } })
    render(<App />)
    expect(await screen.findByLabelText('Nombre')).toHaveValue('Netflix')
    expect(screen.getByLabelText('Importe')).toHaveValue('17.99')
    expect(screen.getByLabelText('Tipo')).toHaveValue('out')
    expect(screen.getByLabelText(/Primera fecha/)).toHaveValue('2026-11-02')
    await waitFor(() => expect(window.location.hash).toBe('#pagos'))
  })

  it('muestra el error de la API al guardar', async () => {
    window.location.hash = '#pagos'
    loggedIn({
      'GET /api/v1/schedule': { body: [] },
      'POST /api/v1/schedule': { status: 409, body: { detail: 'Ya hay un pago con ese nombre' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo pago programado' }))
    await userEvent.type(screen.getByLabelText('Nombre'), 'Alquiler')
    await userEvent.type(screen.getByLabelText('Importe'), '900')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Ya hay un pago con ese nombre')
  })
})
