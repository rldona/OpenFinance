import type { Me, Transaction } from '../../api/client'
import { toCents } from '../../lib/format'

export function kindLabel(t: Pick<Transaction, 'kind' | 'member_id' | 'category' | 'amount'>, me: Me): {
  text: string
  tone: 'neutral' | 'in' | 'save' | 'warn'
} {
  switch (t.kind) {
    case 'contribution': {
      const who = me.members.find((m) => m.id === t.member_id)?.display_name ?? 'alguien'
      return { text: `Aportación de ${who}`, tone: 'in' }
    }
    case 'savings_transfer':
      return { text: 'A la hucha', tone: 'save' }
    case 'income':
      return { text: 'Ingreso', tone: 'in' }
    case 'internal_transfer':
      return { text: 'Entre cuentas', tone: 'neutral' }
    case 'expense':
      if (toCents(t.amount.amount) > 0n) return { text: 'Devolución', tone: 'in' }
      return t.category ? { text: t.category, tone: 'neutral' } : { text: 'Sin categoría', tone: 'warn' }
  }
}
