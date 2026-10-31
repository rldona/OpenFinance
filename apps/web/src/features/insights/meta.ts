import type { Category } from '../../api/client'
import { useHousehold } from '../../app/household-context'

export const UNCATEGORIZED = { id: null, name: 'Sin categoría', icon: '❔', color: '#cbd5e1' }

export type CategoryMeta = Pick<Category, 'name' | 'icon' | 'color'> & { id: string | null }

export function useCategoryMeta(): (id: string | null | undefined) => CategoryMeta {
  const { categoryById } = useHousehold()
  return (id) => {
    const c = id ? categoryById.get(id) : undefined
    return c ? { id: c.id, name: c.name, icon: c.icon, color: c.color } : UNCATEGORIZED
  }
}

/** Porcentaje entero de `amount` sobre `base` (céntimos), redondeado. Solo para mostrar. */
export function sharePercent(amount: bigint, base: bigint): number {
  if (base <= 0n || amount <= 0n) return 0
  return Math.round((Number(amount) * 100) / Number(base))
}
