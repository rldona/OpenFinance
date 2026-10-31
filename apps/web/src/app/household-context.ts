import { createContext, useContext } from 'react'
import type { Category, Me } from '../api/client'

export type HouseholdState = {
  me: Me
  categories: Category[]
  /** Las categorías han cargado; mientras tanto no se puede categorizar. */
  categoriesReady: boolean
  categoryById: Map<string, Category>
  uncategorized: number
  reloadCategories: () => void
  refreshUncategorized: () => void
  notify: (message: string) => void
}

export const HouseholdContext = createContext<HouseholdState | null>(null)

export function useHousehold(): HouseholdState {
  const ctx = useContext(HouseholdContext)
  if (!ctx) throw new Error('useHousehold fuera de HouseholdProvider')
  return ctx
}
