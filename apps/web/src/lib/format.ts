import type { Money } from '../api/client'

const formatters = new Map<string, Intl.NumberFormat>()

function formatter(currency: string): Intl.NumberFormat {
  let f = formatters.get(currency)
  if (!f) {
    f = new Intl.NumberFormat('es-ES', { style: 'currency', currency })
    formatters.set(currency, f)
  }
  return f
}

/** Formatea el decimal exacto que envía la API sin pasar por float. */
export function formatMoney(money: Money, { signed = false } = {}): string {
  const text = formatter(money.currency).format(money.amount as Intl.StringNumericLiteral)
  return signed && !money.amount.startsWith('-') && toCents(money.amount) !== 0n ? `+${text}` : text
}

/** "-87.3" → -8730n. Solo para comparar y restar importes de 2 decimales. */
export function toCents(amount: string): bigint {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(amount.trim())
  if (!match) throw new Error(`Importe no válido: ${amount}`)
  const [, sign, whole, frac = ''] = match
  const cents = BigInt(whole) * 100n + BigInt((frac + '00').slice(0, 2))
  return sign ? -cents : cents
}

export function centsToAmount(cents: bigint): string {
  const negative = cents < 0n
  const abs = negative ? -cents : cents
  const frac = (abs % 100n).toString().padStart(2, '0')
  return `${negative ? '-' : ''}${abs / 100n}.${frac}`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
}

export function currentMonth(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return currentMonth(d)
}

export function monthLabel(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('es-ES', { month: 'long', year: 'numeric' })
}
