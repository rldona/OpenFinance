import type { Category, Me, Transaction } from '../../api/client'
import { toCents } from '../../lib/format'

type Labelled = Pick<Transaction, 'kind' | 'member_id' | 'category_id' | 'amount'>

export function kindLabel(
  t: Labelled,
  me: Me,
  categoryById: Map<string, Category> = new Map(),
): { text: string; tone: 'neutral' | 'in' | 'save' | 'warn' } {
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
    case 'expense': {
      const category = t.category_id ? categoryById.get(t.category_id) : undefined
      const refund = toCents(t.amount.amount) > 0n
      if (category) return { text: `${category.icon} ${category.name}${refund ? ' · devolución' : ''}`, tone: 'neutral' }
      if (refund) return { text: 'Devolución', tone: 'in' }
      return { text: 'Sin categoría', tone: 'warn' }
    }
  }
}
