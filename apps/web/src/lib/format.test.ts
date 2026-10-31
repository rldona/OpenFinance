import { describe, expect, it } from 'vitest'
import { centsToAmount, formatMoney, monthLabel, shiftMonth, toCents } from './format'

describe('format', () => {
  it('formatea importes exactos en euros', () => {
    expect(formatMoney({ amount: '-87.34', currency: 'EUR' })).toMatch(/-87,34\s€/)
    expect(formatMoney({ amount: '1234.50', currency: 'EUR' })).toMatch(/1234,50\s€|1\.234,50\s€/)
    expect(formatMoney({ amount: '23.99', currency: 'EUR' }, { signed: true })).toMatch(/^\+23,99/)
  })

  it('convierte a céntimos sin float', () => {
    expect(toCents('-87.3')).toBe(-8730n)
    expect(toCents('0.1')).toBe(10n)
    expect(toCents('2619.69') - toCents('3746.95')).toBe(-112726n)
    expect(centsToAmount(-112726n)).toBe('-1127.26')
    expect(() => toCents('1e3')).toThrow()
  })

  it('navega entre meses', () => {
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
    expect(monthLabel('2026-10')).toBe('octubre de 2026')
  })
})
