import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ACCOUNTS, ME, PREVIEW, TRANSACTIONS, mockApi } from '../test/api'
import { App } from './App'

beforeEach(() => {
  window.location.hash = ''
})
afterEach(() => vi.restoreAllMocks())

const loggedIn = (extra: Parameters<typeof mockApi>[0] = {}) =>
  mockApi({
    'GET /api/v1/me': { body: ME },
    'GET /api/v1/accounts': { body: ACCOUNTS },
    'GET /api/v1/transactions': { body: TRANSACTIONS },
    ...extra,
  })

describe('Inicio de sesión', () => {
  it('pide credenciales sin sesión y entra con ellas', async () => {
    const calls = mockApi({
      'GET /api/v1/me': { status: 401, body: { detail: 'Inicia sesión' } },
      'POST /api/v1/auth/login': { body: ME },
      'GET /api/v1/accounts': { body: ACCOUNTS },
      'GET /api/v1/transactions': { body: [] },
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
    expect(row('Glovo')).toHaveTextContent('Sin categoría')
    expect(row('Amazon')).toHaveTextContent('Devolución')
    expect(row('Mercadona')).toHaveTextContent('Cuenta conjunta')
  })

  it('filtra por mes y por «sin categoría»', async () => {
    const calls = loggedIn()
    render(<App />)
    await screen.findByRole('table')
    const month = calls.filter((c) => c.url.pathname === '/api/v1/transactions').at(-1)!
    expect(month.url.searchParams.get('month')).toMatch(/^\d{4}-\d{2}$/)

    await userEvent.click(screen.getByLabelText(/Solo sin/))
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions').at(-1)!
      expect(last.url.searchParams.get('uncategorized')).toBe('true')
    })

    await userEvent.click(screen.getByRole('button', { name: 'Mes anterior' }))
    await waitFor(() => {
      const last = calls.filter((c) => c.url.pathname === '/api/v1/transactions').at(-1)!
      expect(last.url.searchParams.get('month')).not.toBe(month.url.searchParams.get('month'))
    })
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
    expect(within(select).getByRole('option', { name: /Bankinter Raúl \(próximamente\)/ })).toBeDisabled()

    const file = new File(['Type,Product\n'], 'revolut.csv', { type: 'text/csv' })
    await userEvent.upload(screen.getByLabelText('Extracto'), file)
    await userEvent.click(screen.getByRole('button', { name: 'Ver vista previa' }))

    expect(await screen.findByText(/coincidirá con el del banco/)).toBeInTheDocument()
    expect(screen.getByText('Aportación de Elena')).toBeInTheDocument()
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
