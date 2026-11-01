import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, type Category, type InsightsView, type Me } from '../api/client'
import type { Notify } from '../components/useToast'
import { currentMonth } from '../lib/format'
import { HouseholdContext } from './household-context'
import { useHashParam } from './router'

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/

export function HouseholdProvider({
  me,
  notify,
  children,
}: {
  me: Me
  notify: Notify
  children: ReactNode
}) {
  const [categories, setCategories] = useState<Category[]>([])
  const [categoriesReady, setCategoriesReady] = useState(false)
  const [uncategorized, setUncategorized] = useState(0)
  const [categoriesVersion, setCategoriesVersion] = useState(0)
  const [countVersion, setCountVersion] = useState(0)
  // Mes, vista y categoría viven en la URL (OF-801): se pueden compartir y sobreviven a recargar.
  const [monthParam, setMonthParam] = useHashParam('mes')
  const [viewParam, setViewParam] = useHashParam('vista')
  const [catParam, setCatParam] = useHashParam('cat')
  const month = monthParam && MONTH.test(monthParam) ? monthParam : currentMonth()
  const view: InsightsView = viewParam === 'mine' ? 'mine' : 'household'
  const focusCategory = catParam === null ? undefined : catParam === 'none' ? null : catParam
  const setMonth = useCallback((m: string) => setMonthParam(m === currentMonth() ? null : m), [setMonthParam])
  const setView = useCallback((v: InsightsView) => setViewParam(v === 'mine' ? 'mine' : null), [setViewParam])
  const setFocusCategory = useCallback(
    (id: string | null | undefined) => setCatParam(id === undefined ? null : id === null ? 'none' : id),
    [setCatParam],
  )

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
      view,
      setView,
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
      setMonth,
      view,
      setView,
      focusCategory,
      setFocusCategory,
    ],
  )
  return <HouseholdContext.Provider value={value}>{children}</HouseholdContext.Provider>
}
