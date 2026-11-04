import { vi } from 'vitest'

export type Call = { method: string; url: URL; headers: Headers; body: BodyInit | null | undefined }
type Handler = (call: Call) => { status?: number; body?: unknown }

/** Simula la API: `routes` asocia "MÉTODO /ruta" a una respuesta. */
export function mockApi(routes: Record<string, Handler | { status?: number; body?: unknown }>) {
  const calls: Call[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost')
    const method = (init?.method ?? 'GET').toUpperCase()
    const call: Call = { method, url, headers: new Headers(init?.headers), body: init?.body }
    calls.push(call)
    const route = routes[`${method} ${url.pathname}`]
    if (!route) return new Response(JSON.stringify({ detail: 'no mock' }), { status: 404 })
    const { status = 200, body } = typeof route === 'function' ? route(call) : route
    return new Response(status === 204 ? null : JSON.stringify(body ?? null), { status })
  })
  return calls
}

export const ME = {
  user: { id: 'u-raul', email: 'raul@example.org', display_name: 'Raúl' },
  household: { id: 'h1', name: 'Nuestra casa', currency: 'EUR' },
  members: [
    { id: 'u-elena', display_name: 'Elena' },
    { id: 'u-raul', display_name: 'Raúl' },
  ],
  role: 'owner',
}

const eur = (amount: string) => ({ amount, currency: 'EUR' })

export const ACCOUNTS = [
  { id: 'a-joint', name: 'Cuenta conjunta', institution: 'revolut', kind: 'joint', type: 'bank', owner_id: null, opening_balance: eur('100.00'), balance: eur('1227.26') },
  { id: 'a-raul', name: 'Bankinter Raúl', institution: 'bankinter', kind: 'personal', type: 'bank', owner_id: 'u-raul', opening_balance: eur('0.00'), balance: eur('500.00') },
]

export const CATEGORIES = [
  { id: 'c-super', name: 'Supermercado', icon: '🛒', color: '#16a34a', hidden: false, slug: 'super' },
  { id: 'c-rest', name: 'Restaurantes', icon: '🍽️', color: '#ea580c', hidden: false, slug: 'restaurantes' },
  { id: 'c-old', name: 'Antigua', icon: '📦', color: '#64748b', hidden: true, slug: null },
]

const tx = (id: string, description: string, amount: string, kind: string, extra: object = {}) => ({
  id,
  account_id: 'a-joint',
  booked_at: '2026-10-05T10:00:00',
  value_date: '2026-10-05',
  description,
  merchant: description,
  amount: eur(amount),
  kind,
  category_id: null,
  member_id: null,
  source: 'import:revolut.csv',
  note: '',
  tags: [],
  parts: [],
  transfer_peer_id: null,
  reviewed: false,
  attachment_count: 0,
  ...extra,
})

export const TRANSACTIONS = [
  tx('t1', 'Payment from Raul', '1600.00', 'contribution', { member_id: 'u-raul' }),
  tx('t2', 'To pocket Ahorro', '-300.00', 'savings_transfer'),
  tx('t3', 'Mercadona', '-87.34', 'expense', { category_id: 'c-super' }),
  tx('t4', 'Glovo', '-25.40', 'expense'),
  tx('t5', 'Amazon', '23.99', 'expense'),
]

export const PREVIEW = {
  id: 'imp-1',
  account_id: 'a-joint',
  filename: 'revolut.csv',
  new_count: 2,
  duplicate_count: 1,
  skipped_count: 1,
  rows: [
    { line: 2, booked_at: '2026-10-01T08:00:12', description: 'Payment from Elena', amount: eur('1400.00'), kind: 'contribution', member_id: 'u-elena', category_id: null, duplicate: false },
    { line: 3, booked_at: '2026-10-03T19:22:41', description: 'Mercadona', amount: eur('-87.34'), kind: 'expense', member_id: null, category_id: 'c-super', duplicate: true },
    { line: 4, booked_at: '2026-10-04T08:15:03', description: 'Café Central', amount: eur('-1.80'), kind: 'expense', member_id: null, category_id: null, duplicate: false },
  ],
  skipped: [{ line: 5, reason: 'pendiente: se importará cuando se complete', description: 'Glovo' }],
  balance_mismatches: [],
  members_without_recharge: [],
  bank_balance: eur('2625.46'),
  balance_after_import: eur('2625.46'),
}

/** Una página de `GET /api/v1/transactions/page` con valores por defecto razonables. */
export function page(
  items: unknown[],
  extra: { next_cursor?: string | null; count?: number; total?: string } = {},
) {
  return {
    items,
    next_cursor: extra.next_cursor ?? null,
    count: extra.count ?? items.length,
    total: { amount: extra.total ?? '-100.00', currency: 'EUR' },
    other_currencies: [] as string[],
  }
}
