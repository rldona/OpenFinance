import { Fragment, useEffect, useState } from 'react'
import { ApiError, api, type Account, type TagCount, type Transaction, type TransactionPage } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { useHashParam } from '../../app/router'
import { ErrorState, Loading } from '../../components/LoadState'
import { formatDate, formatMoney } from '../../lib/format'
import { notifyUndoable } from '../../lib/undo'
import { MonthPicker } from '../insights/common'
import { kindLabel } from './labels'
import { ManualForm } from './ManualForm'
import { Reconcile } from './Reconcile'
import { TransactionDetail } from './TransactionDetail'

function CategorySelect({
  t,
  disabled,
  onChange,
}: {
  t: Transaction
  disabled: boolean
  onChange: (categoryId: string | null) => void
}) {
  const { categories, categoriesReady } = useHousehold()
  const options = categories.filter((c) => !c.hidden || c.id === t.category_id)
  return (
    <select
      className={`catsel ${t.category_id ? '' : 'empty'}`}
      aria-label={`Categoría de ${t.description}`}
      value={t.category_id ?? ''}
      disabled={disabled || !categoriesReady}
      onChange={(e) => onChange(e.target.value || null)}
    >
      <option value="">🏷️ Sin categoría</option>
      {options.map((c) => (
        <option key={c.id} value={c.id}>
          {c.icon} {c.name}
        </option>
      ))}
    </select>
  )
}

export function TransactionsPage() {
  const { me, categories, categoryById, uncategorized, refreshUncategorized, notify, month } = useHousehold()
  // Los filtros viven en la URL (OF-801): una búsqueda se comparte y sobrevive a recargar.
  const [allParam, setAllParam] = useHashParam('todos')
  const [qParam, setQParam] = useHashParam('q')
  const [sinParam, setSinParam] = useHashParam('sin')
  const [accountParam, setAccountParam] = useHashParam('cuenta')
  const [tagParam, setTagParam] = useHashParam('etiqueta')
  const [pendingParam, setPendingParam] = useHashParam('sinrevisar')
  const onlyUnreviewed = pendingParam === '1'
  const tag = tagParam ?? ''
  const allMonths = allParam === '1'
  const onlyUncategorized = sinParam === '1'
  const accountId = accountParam ?? ''
  const setAllMonths = (v: boolean) => setAllParam(v ? '1' : null)
  const setOnlyUncategorized = (v: boolean) => setSinParam(v ? '1' : null)
  const setAccountId = (v: string) => setAccountParam(v || null)
  // El cuadro de texto es local para escribir sin saltos; la URL se actualiza tras una pausa.
  const [q, setQ] = useState(qParam ?? '')
  const debouncedQ = (qParam ?? '').trim()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [tagList, setTagList] = useState<TagCount[]>([])
  const selectedAccount = accounts.find((a) => a.id === accountId)
  const [version, setVersion] = useState(0)
  const [pending, setPending] = useState<string | null>(null)
  type Result = { key: string; page?: TransactionPage; rows?: Transaction[]; error?: string }
  const [result, setResult] = useState<Result | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setQParam(q.trim() || null), 250)
    return () => clearTimeout(t)
  }, [q, setQParam])

  useEffect(() => {
    const controller = new AbortController()
    api.accounts(controller.signal).then(setAccounts, () => undefined) // los nombres de cuenta son opcionales
    api.tags(controller.signal).then(setTagList, () => undefined) // el filtro por etiqueta es opcional
    return () => controller.abort()
  }, [])

  const query = {
    month: allMonths || onlyUncategorized ? undefined : month,
    q: debouncedQ || undefined,
    uncategorized: onlyUncategorized,
    account_id: accountId || undefined,
    tag: tag || undefined,
    reviewed: onlyUnreviewed ? ('false' as const) : undefined,
  }
  // La clave lleva la consulta tal cual: la búsqueda puede contener cualquier carácter.
  const key = JSON.stringify([query, version])

  useEffect(() => {
    const controller = new AbortController()
    api
      .transactionsPage((JSON.parse(key) as [typeof query, number])[0], controller.signal)
      .then((page) => setResult({ key, page, rows: page.items }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const error = err instanceof ApiError ? err.message : 'No se han podido cargar los movimientos'
        setResult({ key, error })
      })
    return () => controller.abort()
  }, [key])

  const current = result?.key === key ? result : null
  // Mientras llega la consulta nueva se siguen viendo las filas anteriores, atenuadas y sin
  // poder editarse, para evitar parpadeos sin permitir cambios sobre datos desactualizados.
  const stale = !current
  const shown = current ?? (stale && !result?.error ? result : null)
  const rows = shown?.rows ?? null
  const error = current?.error ?? null
  const nextCursor = current?.page?.next_cursor ?? null

  async function loadMore() {
    if (!current || !nextCursor) return
    setLoadingMore(true)
    try {
      const more = await api.transactionsPage({ ...query, cursor: nextCursor })
      setResult((r) => {
        if (!r || r.key !== key || !r.rows) return r
        const seen = new Set(r.rows.map((t) => t.id))
        return { ...r, page: more, rows: [...r.rows, ...more.items.filter((t) => !seen.has(t.id))] }
      })
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se han podido cargar más movimientos')
    } finally {
      setLoadingMore(false)
    }
  }

  /** Sustituye una fila con lo que devuelve la API, sin volver a pedir la lista (OF-803). */
  function replaceRow(updated: Transaction) {
    setResult((r) => (r?.rows ? { ...r, rows: r.rows.map((t) => (t.id === updated.id ? updated : t)) } : r))
  }
  const accountName = (id: string) => accounts.find((a) => a.id === id)?.name ?? ''
  const [openId, setOpenId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkCategory, setBulkCategory] = useState('')
  const [showManual, setShowManual] = useState(false)
  // Solo se pueden seleccionar varios en «Solo sin categoría» y entre los que se ven.
  const selectable = onlyUncategorized ? (rows ?? []).filter((t) => t.kind === 'expense') : []
  const chosen = selectable.filter((t) => selected.has(t.id))

  function toggle(id: string) {
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function categorizeChosen() {
    if (chosen.length === 0) return
    try {
      const r = await api.categorizeMany(
        chosen.map((t) => t.id),
        bulkCategory || null,
      )
      const name = bulkCategory ? (categoryById.get(bulkCategory)?.name ?? 'categoría') : 'Sin categoría'
      notifyUndoable(notify, me, `${r.updated} ${r.updated === 1 ? 'gasto' : 'gastos'} → ${name}`, r.operation_id, refresh)
      setSelected(new Set())
      refresh()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido clasificar')
    }
  }

  async function deleteManual(t: Transaction) {
    try {
      const r = await api.deleteManual(t.id)
      notifyUndoable(notify, me, `Borrado: ${t.description}`, r.operation_id, refresh)
      setOpenId(null)
      refresh()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido borrar')
    }
  }

  function refresh() {
    setVersion((v) => v + 1)
    refreshUncategorized()
  }

  async function changeCategory(t: Transaction, categoryId: string | null) {
    setPending(t.id)
    try {
      const r = await api.categorize(t.id, categoryId)
      const category = categoryId ? categoryById.get(categoryId) : undefined
      const message =
        r.rule && category
          ? `Regla guardada: «${r.rule.merchant}» → ${category.name}${r.also_categorized ? ` · ${r.also_categorized} más clasificados` : ''}`
          : category
            ? `Categoría: ${category.name}`
            : 'Categoría quitada'
      notifyUndoable(notify, me, message, r.operation_id, refresh)
      // Si la regla ha clasificado más movimientos, o la fila ya no cumple el filtro, hay que
      // volver a pedir; si no, basta con cambiar esta fila.
      if (r.also_categorized > 0 || onlyUncategorized) refresh()
      else {
        replaceRow(r.transaction)
        refreshUncategorized()
      }
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido cambiar la categoría')
    } finally {
      setPending(null)
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Movimientos</h1>
          <p className="lead">
            Cambia la categoría en la tabla y OpenFinance aprende la regla para ese comercio.{' '}
            <a href="#categorias">Gestionar categorías</a> · <a href="#reglas">Reglas</a> · <a href="#cambios">Mis cambios</a>
          </p>
        </div>
        <div className="page-tools">
          <button className="btn" type="button" onClick={() => setShowManual((v) => !v)} aria-expanded={showManual}>
            + Añadir a mano
          </button>
          <MonthPicker disabled={allMonths || onlyUncategorized} />
        </div>
      </div>

      {showManual && (
        <ManualForm
          accounts={accounts}
          onClose={() => setShowManual(false)}
          onSaved={(r) => {
            notifyUndoable(notify, me, `Añadido: ${r.transaction.description}`, r.operation_id, refresh)
            setShowManual(false)
            refresh()
          }}
        />
      )}

      {uncategorized > 0 && !onlyUncategorized && (
        <div className="notice warn row">
          <span>
            🏷️ <strong>{uncategorized === 1 ? '1 gasto' : `${uncategorized} gastos`} sin categoría.</strong>{' '}
            Clasificarlos hará que los gráficos sean fiables.
          </span>
          <button className="btn" type="button" onClick={() => setOnlyUncategorized(true)}>
            Clasificar
          </button>
        </div>
      )}

      <div className="card">
        <div className="toolbar">
          <input
            type="search"
            className="field"
            placeholder="Buscar concepto…"
            aria-label="Buscar"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select className="field" aria-label="Cuenta" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Todas las cuentas</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          {(tagList.length > 0 || tag) && (
            <select className="field" aria-label="Etiqueta" value={tag} onChange={(e) => setTagParam(e.target.value || null)}>
              <option value="">Todas las etiquetas</option>
              {tagList.map((x) => (
                <option key={x.tag} value={x.tag}>
                  #{x.tag} ({x.count})
                </option>
              ))}
            </select>
          )}
          <label className="small">
            <input
              type="checkbox"
              checked={onlyUncategorized}
              onChange={(e) => setOnlyUncategorized(e.target.checked)}
            />{' '}
            Solo sin categoría ({uncategorized})
          </label>
          <label className="small">
            <input type="checkbox" checked={onlyUnreviewed} onChange={(e) => setPendingParam(e.target.checked ? '1' : null)} /> Solo sin revisar
          </label>
          <label className="small">
            <input type="checkbox" checked={allMonths} onChange={(e) => setAllMonths(e.target.checked)} /> Todos los meses
          </label>
        </div>

        {selectedAccount && <Reconcile key={selectedAccount.id} account={selectedAccount} />}

        {onlyUncategorized && chosen.length > 0 && (
          <div className="toolbar bulk" role="group" aria-label="Clasificar los seleccionados">
            <strong>{chosen.length === 1 ? '1 seleccionado' : `${chosen.length} seleccionados`}</strong>
            <select
              className="field"
              aria-label="Categoría para los seleccionados"
              value={bulkCategory}
              onChange={(e) => setBulkCategory(e.target.value)}
            >
              <option value="">Elige categoría…</option>
              {categories
                .filter((c) => !c.hidden)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.icon} {c.name}
                  </option>
                ))}
            </select>
            <button className="btn primary small" type="button" disabled={!bulkCategory} onClick={() => void categorizeChosen()}>
              Poner categoría
            </button>
            <span className="small muted">No aprende reglas.</span>
          </div>
        )}
        {error && <ErrorState message={error} onRetry={() => setVersion((v) => v + 1)} />}
        {!error && rows === null && <Loading />}
        {rows && rows.length === 0 && (
          <div className="empty">
            {onlyUncategorized ? (
              <p>✓ Todos los gastos tienen categoría.</p>
            ) : (
              <>
                <p>No hay movimientos con estos filtros.</p>
                <a className="btn" href="#importar">
                  Importar un extracto
                </a>
              </>
            )}
          </div>
        )}
        {rows && rows.length > 0 && (
          <table role="table" className={`rows tx${stale ? ' stale' : ''}`} aria-busy={stale}>
            <thead role="rowgroup">
              <tr role="row">
                {onlyUncategorized && (
                  <th role="columnheader">
                    <input
                      type="checkbox"
                      aria-label="Seleccionar todos"
                      checked={selectable.length > 0 && chosen.length === selectable.length}
                      onChange={(e) => setSelected(new Set(e.target.checked ? selectable.map((t) => t.id) : []))}
                    />
                  </th>
                )}
                <th role="columnheader">Fecha</th>
                <th role="columnheader">Concepto</th>
                <th role="columnheader">Categoría</th>
                <th role="columnheader" className="num">Importe</th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {rows.map((t) => {
                const label = kindLabel(t, me, categoryById)
                const open = openId === t.id
                return (
                  <Fragment key={t.id}>
                  <tr role="row">
                    {onlyUncategorized && (
                      <td role="cell">
                        {t.kind === 'expense' && (
                          <input
                            type="checkbox"
                            aria-label={`Seleccionar ${t.description}`}
                            checked={selected.has(t.id)}
                            onChange={() => toggle(t.id)}
                          />
                        )}
                      </td>
                    )}
                    <td role="cell" className="muted small">{formatDate(t.booked_at)}</td>
                    <td role="cell">
                      <button
                        type="button"
                        className="linkish"
                        aria-expanded={open}
                        aria-label={`Detalle de ${t.description}`}
                        onClick={() => setOpenId(open ? null : t.id)}
                      >
                        {t.merchant || t.description}
                      </button>
                      <div className="small muted">
                        {t.reviewed && <span title="Revisado con el banco" aria-label="Revisado con el banco">✓ </span>}
                        {t.transfer_peer_id && <span title="Traspaso enlazado" aria-label="Traspaso enlazado">🔗 </span>}
                        {t.description} · {accountName(t.account_id)}
                        {t.note && <> · 📝 {t.note.split('\n')[0]}</>}
                        {t.tags.map((x) => (
                          <span key={x} className="tag-chip">
                            #{x}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td role="cell">
                      {t.kind === 'expense' ? (
                        <CategorySelect
                          t={t}
                          disabled={stale || pending !== null}
                          onChange={(id) => void changeCategory(t, id)}
                        />
                      ) : (
                        <span className={`tag tag-${label.tone}`}>{label.text}</span>
                      )}
                    </td>
                    <td role="cell" className={`num ${t.amount.amount.startsWith('-') ? '' : 'pos'}`}>
                      {formatMoney(t.amount, { signed: true })}
                    </td>
                  </tr>
                  {open && (
                    <tr role="row" className="detail-row">
                      <td role="cell" colSpan={onlyUncategorized ? 5 : 4}>
                        <TransactionDetail
                          key={`${t.id}|${t.kind}|${t.member_id}|${t.note}|${t.tags.join()}|${t.parts.length}|${t.transfer_peer_id}|${t.reviewed}`}
                          t={t}
                          version={version}
                          onClose={() => setOpenId(null)}
                          onDelete={t.source === 'manual' ? () => void deleteManual(t) : undefined}
                          accountName={accountName}
                          onReviewChanged={(message, op) => {
                            notifyUndoable(notify, me, message, op, refresh)
                            refresh()
                          }}
                          onLinkChanged={(message, op) => {
                            notifyUndoable(notify, me, message, op, refresh)
                            refresh()
                          }}
                          onSplitChanged={(message, op) => {
                            notifyUndoable(notify, me, message, op, refresh)
                            refresh()
                          }}
                          onTagsSaved={(op) => {
                            notifyUndoable(notify, me, 'Etiquetas guardadas', op, refresh)
                            refresh()
                            api.tags().then(setTagList, () => undefined)
                          }}
                          onSaved={(r) => {
                            notifyUndoable(notify, me, 'Movimiento corregido', r.operation_id, refresh)
                            refresh()
                          }}
                        />
                      </td>
                    </tr>
                  )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        )}
        {current?.page && rows && rows.length > 0 && (
          <>
            <p className="small muted">
              {nextCursor
                ? `Mostrando ${rows.length} de ${current.page.count} movimientos`
                : `${current.page.count} movimientos`}
            </p>
            <p className="small muted">Suma del filtro: {formatMoney(current.page.total, { signed: true })}</p>
          </>
        )}
        {nextCursor && (
          <button className="btn" type="button" disabled={loadingMore} onClick={() => void loadMore()}>
            {loadingMore ? 'Cargando…' : 'Cargar más'}
          </button>
        )}
      </div>
    </section>
  )
}
