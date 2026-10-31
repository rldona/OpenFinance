import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, type Category, type Me } from '../api/client'
import { currentMonth } from '../lib/format'
import { HouseholdContext } from './household-context'

export function HouseholdProvider({
  me,
  notify,
  children,
}: {
  me: Me
  notify: (message: string) => void
  children: ReactNode
}) {
  const [categories, setCategories] = useState<Category[]>([])
  const [categoriesReady, setCategoriesReady] = useState(false)
  const [uncategorized, setUncategorized] = useState(0)
  const [categoriesVersion, setCategoriesVersion] = useState(0)
  const [countVersion, setCountVersion] = useState(0)
  const [month, setMonth] = useState(currentMonth)
  const [focusCategory, setFocusCategory] = useState<string | null | undefined>(undefined)

  useEffect(() => {
    const controller = new AbortController()
    api.categories(controller.signal).then(
      (list) => {
        setCategories(list)
        setCategoriesReady(true)
      },
      () => {
        if (!controller.signal.aborted) notify('No se han podido cargar las categorías')
      },
    )
    return () => controller.abort()
  }, [categoriesVersion, notify])

  useEffect(() => {
    const controller = new AbortController()
    // Si falla, el contador se queda como estaba: es orientativo.
    api.uncategorizedCount(controller.signal).then((r) => setUncategorized(r.count), () => undefined)
    return () => controller.abort()
  }, [countVersion])

  const reloadCategories = useCallback(() => setCategoriesVersion((v) => v + 1), [])
  const refreshUncategorized = useCallback(() => setCountVersion((v) => v + 1), [])

  const value = useMemo(
    () => ({
      me,
      categories,
      categoriesReady,
      categoryById: new Map(categories.map((c) => [c.id, c])),
      uncategorized,
      reloadCategories,
      refreshUncategorized,
      notify,
      month,
      setMonth,
      focusCategory,
      setFocusCategory,
    }),
    [
      me,
      categories,
      categoriesReady,
      uncategorized,
      reloadCategories,
      refreshUncategorized,
      notify,
      month,
      focusCategory,
    ],
  )
  return <HouseholdContext.Provider value={value}>{children}</HouseholdContext.Provider>
}
