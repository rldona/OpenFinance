import { describe, expect, it } from 'vitest'
import type { Me } from '../../api/client'
import { kindLabel } from './labels'

const me = { members: [] } as unknown as Me
const pocket = (amount: string) =>
  kindLabel({ kind: 'savings_transfer', member_id: null, category_id: null, amount: { amount, currency: 'EUR' } }, me)

describe('kindLabel', () => {
  it('distingue meter en la hucha de sacar de ella', () => {
    expect(pocket('-300.00').text).toBe('A la hucha')
    expect(pocket('100.00').text).toBe('De la hucha')
  })
})
