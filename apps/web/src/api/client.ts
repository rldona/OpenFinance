import type { components, operations } from './schema'

type Schemas = components['schemas']
export type Me = Schemas['MeOut']
export type Account = Schemas['AccountOut']
export type Transaction = Schemas['TransactionOut']
export type TransactionKind = Schemas['TransactionKind']
export type Money = Schemas['MoneyOut']
export type ImportPreview = Schemas['ImportPreviewOut']
export type ImportResult = Schemas['ImportResultOut']
export type Category = Schemas['CategoryOut']
export type CategoryInput = Schemas['CategoryIn']
export type CategoryPatch = Schemas['CategoryPatch']
export type CategorizeResult = Schemas['CategorizeOut']
export type TransactionPatch = Schemas['CategorizeIn']
export type Operation = Schemas['OperationOut']
export type RevertResult = Schemas['RevertOut']
export type ManualTransactionInput = Schemas['ManualTransactionIn']
export type ManualTransactionResult = Schemas['ManualTransactionOut']
export type BulkCategorizeResult = Schemas['BulkCategorizeOut']
export type RuleView = Schemas['RuleViewOut']
export type MonthOverview = Schemas['MonthOverviewOut']
export type CategoryDetail = Schemas['CategoryDetailOut']
export type Trends = Schemas['TrendsOut']
/** «Hogar» (conjunta y huchas) o «Mío» (tus cuentas personales). */
export type InsightsView = Schemas['View']
export type Budgets = Schemas['BudgetsOut']
export type Budget = Schemas['BudgetOut']
export type Goal = Schemas['GoalOut']
export type GoalInput = Schemas['GoalIn']
export type GoalPatch = Schemas['GoalPatch']
export type SavingsOverview = Schemas['SavingsOverviewOut']

export type ExportFormat = NonNullable<
  NonNullable<operations['export_api_v1_export_get']['parameters']['query']>['format']
>

/** Descarga directa (GET con la cookie de sesión): no pasa por fetch. */
export const exportUrl = (format: ExportFormat) => `/api/v1/export?format=${format}`

export const CSRF_HEADER = { 'X-Requested-With': 'OpenFinance' } as const

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function detailOf(body: unknown, status: number): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return 'Revisa los datos enviados'
  }
  if (status === 429) return 'Demasiados intentos. Espera unos minutos.'
  return `Error ${status}`
}

let onUnauthorized: (() => void) | null = null

/** La app se suscribe para volver al login si la sesión caduca. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

type Query = Record<string, string | number | boolean | undefined | null>

async function request<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE',
  path: string,
  options: { query?: Query; json?: unknown; form?: FormData; signal?: AbortSignal } = {},
): Promise<T> {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(options.query ?? {})) {
    if (v !== undefined && v !== null && v !== '' && v !== false) params.set(k, String(v))
  }
  const url = params.size ? `${path}?${params}` : path
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (method !== 'GET') Object.assign(headers, CSRF_HEADER)
  let body: BodyInit | undefined
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.json)
  } else if (options.form) {
    body = options.form
  }
  const response = await fetch(url, { method, headers, body, credentials: 'include', signal: options.signal })
  if (response.status === 204) return undefined as T
  const data: unknown = await response.json().catch(() => null)
  if (response.status === 401 && path !== '/api/v1/auth/login' && path !== '/api/v1/me') onUnauthorized?.()
  if (!response.ok) throw new ApiError(response.status, detailOf(data, response.status))
  return data as T
}

export const TRANSACTIONS_LIMIT = 1000

export const api = {
  me: (signal?: AbortSignal) => request<Me>('GET', '/api/v1/me', { signal }),
  login: (email: string, password: string) =>
    request<Me>('POST', '/api/v1/auth/login', { json: { email, password } }),
  logout: () => request<void>('POST', '/api/v1/auth/logout'),
  accounts: (signal?: AbortSignal) => request<Account[]>('GET', '/api/v1/accounts', { signal }),
  transactions: (
    query: { month?: string; q?: string; uncategorized?: boolean; account_id?: string; category_id?: string; shared_only?: boolean; mine_only?: boolean },
    signal?: AbortSignal,
  ) => request<Transaction[]>('GET', '/api/v1/transactions', { query, signal }),
  previewImport: (accountId: string, file: File) => {
    const form = new FormData()
    form.set('account_id', accountId)
    form.set('file', file)
    return request<ImportPreview>('POST', '/api/v1/imports', { form })
  },
  commitImport: (importId: string) =>
    request<ImportResult>('POST', `/api/v1/imports/${encodeURIComponent(importId)}/commit`),
  categories: (signal?: AbortSignal) => request<Category[]>('GET', '/api/v1/categories', { signal }),
  createCategory: (input: CategoryInput) => request<Category>('POST', '/api/v1/categories', { json: input }),
  updateCategory: (id: string, patch: CategoryPatch) =>
    request<Category>('PATCH', `/api/v1/categories/${encodeURIComponent(id)}`, { json: patch }),
  categorize: (transactionId: string, categoryId: string | null, learn = true) =>
    request<CategorizeResult>('PATCH', `/api/v1/transactions/${encodeURIComponent(transactionId)}`, {
      json: { category_id: categoryId, learn },
    }),
  editTransaction: (transactionId: string, patch: Partial<TransactionPatch>) =>
    request<CategorizeResult>('PATCH', `/api/v1/transactions/${encodeURIComponent(transactionId)}`, { json: patch }),
  transactionHistory: (transactionId: string, signal?: AbortSignal) =>
    request<Operation[]>('GET', `/api/v1/transactions/${encodeURIComponent(transactionId)}/history`, { signal }),
  categorizeMany: (ids: string[], categoryId: string | null) =>
    request<BulkCategorizeResult>('POST', '/api/v1/transactions/categorize', { json: { ids, category_id: categoryId } }),
  addManual: (input: ManualTransactionInput) =>
    request<ManualTransactionResult>('POST', '/api/v1/transactions', { json: input }),
  deleteManual: (transactionId: string) =>
    request<{ operation_id: string | null }>('DELETE', `/api/v1/transactions/${encodeURIComponent(transactionId)}`),
  rules: (signal?: AbortSignal) => request<RuleView[]>('GET', '/api/v1/rules', { signal }),
  deleteRule: (scope: RuleView['scope'], key: string) =>
    request<{ operation_id: string | null }>('DELETE', `/api/v1/rules/${scope}/${encodeURIComponent(key)}`),
  changes: (signal?: AbortSignal) => request<Operation[]>('GET', '/api/v1/changes', { signal }),
  undo: (operationId: string) => request<RevertResult>('POST', `/api/v1/changes/${encodeURIComponent(operationId)}/undo`),
  redo: (operationId: string) => request<RevertResult>('POST', `/api/v1/changes/${encodeURIComponent(operationId)}/redo`),
  insightsMonth: (month: string, view: InsightsView, signal?: AbortSignal) =>
    request<MonthOverview>('GET', '/api/v1/insights/month', { query: { month, view }, signal }),
  insightsCategory: (month: string, categoryId: string | null, view: InsightsView, signal?: AbortSignal) =>
    request<CategoryDetail>('GET', '/api/v1/insights/category', {
      query: { month, category_id: categoryId ?? undefined, view },
      signal,
    }),
  insightsTrends: (month: string, signal?: AbortSignal) =>
    request<Trends>('GET', '/api/v1/insights/trends', { query: { month, months: 12 }, signal }),
  budgets: (month: string, signal?: AbortSignal) =>
    request<Budgets>('GET', '/api/v1/budgets', { query: { month }, signal }),
  setBudget: (categoryId: string, amount: string) =>
    request<Budget>('PUT', `/api/v1/budgets/${encodeURIComponent(categoryId)}`, { json: { amount } }),
  deleteBudget: (categoryId: string) => request<void>('DELETE', `/api/v1/budgets/${encodeURIComponent(categoryId)}`),
  createGoal: (input: GoalInput) => request<Goal>('POST', '/api/v1/goals', { json: input }),
  updateGoal: (id: string, patch: Partial<GoalPatch>) =>
    request<Goal>('PATCH', `/api/v1/goals/${encodeURIComponent(id)}`, {
      json: { clear_account: false, ...patch },
    }),
  deleteGoal: (id: string) => request<void>('DELETE', `/api/v1/goals/${encodeURIComponent(id)}`),
  savingsOverview: (signal?: AbortSignal) => request<SavingsOverview>('GET', '/api/v1/savings/overview', { signal }),
  uncategorizedCount: (signal?: AbortSignal) =>
    request<{ count: number }>('GET', '/api/v1/transactions/uncategorized-count', { signal }),
}
