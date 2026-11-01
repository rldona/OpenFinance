import type { Money } from '../api/client'

const formatters = new Map<string, Intl.NumberFormat>()

function formatter(currency: string, rounded = false): Intl.NumberFormat {
  const key = `${currency}:${rounded}`
  let f = formatters.get(key)
  if (!f) {
    f = new Intl.NumberFormat('es-ES', {
      style: 'currency',
      currency,
      ...(rounded ? { maximumFractionDigits: 0, minimumFractionDigits: 0 } : {}),
    })
    formatters.set(key, f)
  }
  return f
}

/** Importe redondeado a euros, para titulares y gráficos. */
export function formatMoneyRounded(money: Money): string {
  return formatter(money.currency, true).format(money.amount as Intl.StringNumericLiteral)
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

/** Variación porcentual entera de `now` frente a `before` (null si no hay base). */
export function percentChange(now: Money, before: Money): number | null {
  const b = toCents(before.amount)
  if (b === 0n) return null
  const diff = toCents(now.amount) - b
  return Math.round((Number(diff) * 100) / Number(b < 0n ? -b : b))
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

export function shortMonth(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('es-ES', { month: 'short' }).replace('.', '')
}

export function monthLabel(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('es-ES', { month: 'long', year: 'numeric' })
}

/** Texto escrito por el usuario («45,90») → decimal para la API, o null si no es válido. */
export function parseAmountInput(text: string): string | null {
  const t = text.trim().replace(/\s/g, '')
  if (!/^\d{1,9}([.,]\d{1,2})?$/.test(t)) return null
  return t.replace(',', '.')
}

/** División entera hacia arriba con BigInt. */
export function ceilDiv(a: bigint, b: bigint): bigint {
  return (a + b - 1n) / b
}
