import type { components, operations } from './schema'

type Schemas = components['schemas']
export type Me = Schemas['MeOut']
export type CsvProfile = Schemas['CsvProfileOut']
export type CsvProfileInput = Schemas['CsvProfileIn']
export type CsvSample = Schemas['CsvSampleOut']
export type CsvTest = Schemas['CsvTestOut']
export type AutomationRule = Schemas['AutomationRuleOut']
export type AutomationRuleInput = Schemas['AutomationRuleIn']
export type RulePreview = Schemas['RulePreviewOut']
export type ScheduleItem = Schemas['ScheduleItemOut']
export type ForecastView = Schemas['ForecastViewOut']
export type Template = Schemas['TemplateOut']
export type Allowance = Schemas['AllowanceOut']
export type Alert = Schemas['AlertOut']
export type WeeklySummary = Schemas['WeeklySummaryOut']
export type Notifications = Schemas['NotificationsOut']
export type AlertKind = Alert['kind']
export type TemplateInput = Schemas['TemplateIn']
export type AccountForecast = Schemas['ForecastOut']
export type ScheduledPayment = Schemas['ScheduledPaymentOut']
export type ScheduledPaymentInput = Schemas['ScheduledPaymentIn']
export type ExchangeRate = Schemas['RateOut']
export type MissingRate = Schemas['MissingRateOut']
export type Attachment = Schemas['AttachmentOut']
export type Reconciliation = Schemas['ReconciliationOut']
export type AccountType = Schemas['AccountType']
export type LinkResult = Schemas['LinkOut']
export type SplitResult = Schemas['SplitOut']
export type TagCount = Schemas['TagOut']
export type TagsResult = Schemas['TagsOut']
export type MerchantGroup = Schemas['MerchantGroupOut']
export type MerchantChange = Schemas['MerchantChangeOut']
export type VersionInfo = Schemas['VersionOut']
export type Account = Schemas['AccountOut']
export type Transaction = Schemas['TransactionOut']
export type TransactionPage = Schemas['TransactionPageOut']
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
export type ImportItem = Schemas['ImportListItemOut']
export type MemberPattern = Schemas['PatternOut']
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
export type Contribution = Schemas['ContributionOut']
export type GoalShare = Schemas['ShareOut']
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

export const api = {
  me: (signal?: AbortSignal) => request<Me>('GET', '/api/v1/me', { signal }),
  login: (email: string, password: string) =>
    request<Me>('POST', '/api/v1/auth/login', { json: { email, password } }),
  logout: () => request<void>('POST', '/api/v1/auth/logout'),
  /** Versión instalada y, si está activada la consulta, si hay una nueva (OF-907). */
  version: (signal?: AbortSignal) => request<VersionInfo>('GET', '/api/v1/version', { signal }),
  /** Añade una cuenta de efectivo, tarjeta, préstamo o inversión (OF-1005). */
  createAccount: (body: { name: string; type: AccountType; shared: boolean; opening_balance: string; currency?: string }) =>
    request<Account>('POST', '/api/v1/accounts', { json: body }),
  accounts: (signal?: AbortSignal) => request<Account[]>('GET', '/api/v1/accounts', { signal }),
  transactions: (
    query: { month?: string; q?: string; uncategorized?: boolean; account_id?: string; category_id?: string; tag?: string; reviewed?: 'true' | 'false'; shared_only?: boolean; mine_only?: boolean },
    signal?: AbortSignal,
  ) => request<Transaction[]>('GET', '/api/v1/transactions', { query, signal }),
  /** Movimientos de 50 en 50 con el total del filtro (OF-803). */
  transactionsPage: (
    query: { month?: string; q?: string; uncategorized?: boolean; account_id?: string; tag?: string; reviewed?: 'true' | 'false'; cursor?: string },
    signal?: AbortSignal,
  ) => request<TransactionPage>('GET', '/api/v1/transactions/page', { query, signal }),
  previewImport: (accountId: string, file: File, profileId?: string) => {
    const form = new FormData()
    form.set('account_id', accountId)
    if (profileId) form.set('profile_id', profileId)
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
  imports: (signal?: AbortSignal) => request<ImportItem[]>('GET', '/api/v1/imports', { signal }),
  undoImport: (importId: string) =>
    request<{ voided: number; operation_id: string | null; kept_reviewed?: number }>('POST', `/api/v1/imports/${encodeURIComponent(importId)}/undo`),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ revoked: number }>('POST', '/api/v1/me/password', {
      json: { current_password: currentPassword, new_password: newPassword },
    }),
  revokeOtherSessions: () => request<{ revoked: number }>('POST', '/api/v1/me/sessions/revoke-others'),
  myPatterns: (signal?: AbortSignal) => request<MemberPattern[]>('GET', '/api/v1/me/patterns', { signal }),
  addPattern: (pattern: string, direction: MemberPattern['direction'] = 'inflow') =>
    request<MemberPattern>('POST', '/api/v1/me/patterns', { json: { pattern, direction } }),
  removePattern: (p: MemberPattern) =>
    request<void>('DELETE', `/api/v1/me/patterns/${p.direction}/${encodeURIComponent(p.pattern)}`),
  /** Perfiles de CSV de cualquier banco (OF-1105). */
  csvProfiles: (signal?: AbortSignal) => request<CsvProfile[]>('GET', '/api/v1/csv-profiles', { signal }),
  createCsvProfile: (profile: CsvProfileInput) =>
    request<{ profile: CsvProfile; operation_id: string | null }>('POST', '/api/v1/csv-profiles', { json: profile }),
  deleteCsvProfile: (id: string) =>
    request<{ operation_id: string | null }>('DELETE', `/api/v1/csv-profiles/${encodeURIComponent(id)}`),
  csvSample: (file: File) => {
    const form = new FormData()
    form.set('file', file)
    return request<CsvSample>('POST', '/api/v1/csv-profiles/sample', { form })
  },
  testCsvProfile: (file: File, profile: CsvProfileInput) => {
    const form = new FormData()
    form.set('file', file)
    form.set('profile', JSON.stringify(profile))
    return request<CsvTest>('POST', '/api/v1/csv-profiles/test', { form })
  },
  /** «Hoy podéis gastar» con el dinero de la conjunta (OF-1205). */
  allowance: (signal?: AbortSignal) => request<Allowance>('GET', '/api/v1/allowance', { signal }),
  /** Avisos deterministas de hoy y descartarlos (OF-1301). */
  alerts: (signal?: AbortSignal) => request<Alert[]>('GET', '/api/v1/alerts', { signal }),
  dismissAlert: (key: string) => request<void>('POST', '/api/v1/alerts/dismiss', { json: { key } }),
  /** Resumen de la última semana completa (OF-1303). */
  weeklySummary: (signal?: AbortSignal) => request<WeeklySummary>('GET', '/api/v1/summary/weekly', { signal }),
  /** Notificaciones push de esta persona (OF-1302). */
  notifications: (signal?: AbortSignal) => request<Notifications>('GET', '/api/v1/notifications', { signal }),
  saveNotificationPrefs: (kinds: AlertKind[], weekly: boolean) =>
    request<Notifications>('PUT', '/api/v1/notifications/preferences', { json: { kinds, weekly } }),
  subscribePush: (endpoint: string, keys: { p256dh: string; auth: string }) =>
    request<void>('POST', '/api/v1/notifications/subscriptions', { json: { endpoint, keys } }),
  unsubscribePush: (endpoint: string) =>
    request<void>('POST', '/api/v1/notifications/subscriptions/remove', { json: { endpoint } }),
  /** Plantillas de movimientos manuales (OF-1204). */
  templates: (signal?: AbortSignal) => request<Template[]>('GET', '/api/v1/templates', { signal }),
  createTemplate: (template: TemplateInput) =>
    request<{ template: Template; operation_id: string | null }>('POST', '/api/v1/templates', { json: template }),
  deleteTemplate: (id: string) =>
    request<{ operation_id: string | null }>('DELETE', `/api/v1/templates/${encodeURIComponent(id)}`),
  useTemplate: (id: string, bookedOn: string) =>
    request<ManualTransactionResult>('POST', `/api/v1/templates/${encodeURIComponent(id)}/use`, { json: { booked_on: bookedOn } }),
  /** Pagos programados y sus próximas fechas (OF-1201). */
  schedule: (days: number, signal?: AbortSignal) =>
    request<ScheduleItem[]>('GET', `/api/v1/schedule?days=${days}`, { signal }),
  forecast: (days: number, signal?: AbortSignal) =>
    request<ForecastView>('GET', `/api/v1/forecast?days=${days}`, { signal }),
  createScheduledPayment: (payment: ScheduledPaymentInput) =>
    request<{ payment: ScheduledPayment; operation_id: string | null }>('POST', '/api/v1/schedule', { json: payment }),
  updateScheduledPayment: (id: string, payment: ScheduledPaymentInput) =>
    request<{ payment: ScheduledPayment; operation_id: string | null }>('PUT', `/api/v1/schedule/${encodeURIComponent(id)}`, { json: payment }),
  deleteScheduledPayment: (id: string) =>
    request<{ operation_id: string | null }>('DELETE', `/api/v1/schedule/${encodeURIComponent(id)}`),
  /** Reglas con condiciones, acciones y fases (OF-1101, OF-1102). */
  automationRules: (signal?: AbortSignal) => request<AutomationRule[]>('GET', '/api/v1/automation-rules', { signal }),
  createAutomationRule: (rule: AutomationRuleInput) =>
    request<{ rule: AutomationRule; operation_id: string | null }>('POST', '/api/v1/automation-rules', { json: rule }),
  updateAutomationRule: (id: string, rule: AutomationRuleInput) =>
    request<{ rule: AutomationRule; operation_id: string | null }>('PUT', `/api/v1/automation-rules/${encodeURIComponent(id)}`, { json: rule }),
  deleteAutomationRule: (id: string) =>
    request<{ operation_id: string | null }>('DELETE', `/api/v1/automation-rules/${encodeURIComponent(id)}`),
  previewAutomationDraft: (rule: AutomationRuleInput) =>
    request<RulePreview>('POST', '/api/v1/automation-rules/preview', { json: rule }),
  previewAutomationRule: (id: string) =>
    request<RulePreview>('POST', `/api/v1/automation-rules/${encodeURIComponent(id)}/preview`),
  applyAutomationRule: (id: string) =>
    request<{ changed: number; operation_id: string | null }>('POST', `/api/v1/automation-rules/${encodeURIComponent(id)}/apply`),
  /** Tipos de cambio manuales: 1 unidad de la moneda = tanto de la del hogar (OF-1008). */
  exchangeRates: (signal?: AbortSignal) => request<ExchangeRate[]>('GET', '/api/v1/exchange-rates', { signal }),
  setExchangeRate: (currency: string, on: string, rate: string) =>
    request<{ rate: ExchangeRate; operation_id: string | null }>('PUT', '/api/v1/exchange-rates', { json: { currency, on, rate } }),
  deleteExchangeRate: (currency: string, on: string) =>
    request<{ operation_id: string | null }>('DELETE', `/api/v1/exchange-rates/${encodeURIComponent(currency)}/${encodeURIComponent(on)}`),
  missingRates: (signal?: AbortSignal) => request<MissingRate[]>('GET', '/api/v1/exchange-rates/missing', { signal }),
  /** Tickets y facturas adjuntos a un movimiento (OF-1007). */
  attachments: (transactionId: string, signal?: AbortSignal) =>
    request<Attachment[]>('GET', `/api/v1/transactions/${encodeURIComponent(transactionId)}/attachments`, { signal }),
  addAttachment: (transactionId: string, file: File) => {
    const form = new FormData()
    form.set('file', file)
    return request<{ attachment: Attachment; operation_id: string | null }>(
      'POST',
      `/api/v1/transactions/${encodeURIComponent(transactionId)}/attachments`,
      { form },
    )
  },
  deleteAttachment: (attachmentId: string) =>
    request<{ operation_id: string | null }>('DELETE', `/api/v1/attachments/${encodeURIComponent(attachmentId)}`),
  /** Revisar movimientos y comprobar el saldo contra el banco (OF-1006). */
  reviewTransactions: (ids: string[], reviewed: boolean) =>
    request<{ changed: number; operation_id: string | null }>('POST', '/api/v1/transactions/review', { json: { ids, reviewed } }),
  reconcileAccount: (accountId: string, asOf: string, bankBalance: string) =>
    request<Reconciliation>('POST', `/api/v1/accounts/${encodeURIComponent(accountId)}/reconciliations`, {
      json: { as_of: asOf, bank_balance: bankBalance },
    }),
  reconciliations: (accountId: string, signal?: AbortSignal) =>
    request<Reconciliation[]>('GET', `/api/v1/accounts/${encodeURIComponent(accountId)}/reconciliations`, { signal }),
  /** Traspasos entre cuentas propias: candidatos, enlazar y desenlazar (OF-1004). */
  transferCandidates: (transactionId: string, signal?: AbortSignal) =>
    request<Transaction[]>('GET', `/api/v1/transactions/${encodeURIComponent(transactionId)}/transfer-candidates`, { signal }),
  linkTransfer: (transactionId: string, peerId: string) =>
    request<LinkResult>('PUT', `/api/v1/transactions/${encodeURIComponent(transactionId)}/link`, { json: { peer_id: peerId } }),
  unlinkTransfer: (transactionId: string) =>
    request<LinkResult>('DELETE', `/api/v1/transactions/${encodeURIComponent(transactionId)}/link`),
  /** Divide un gasto en partes con categoría que suman su importe (OF-1003). */
  splitTransaction: (transactionId: string, parts: { amount: string; category_id: string }[]) =>
    request<SplitResult>('PUT', `/api/v1/transactions/${encodeURIComponent(transactionId)}/split`, { json: { parts } }),
  unsplitTransaction: (transactionId: string) =>
    request<SplitResult>('DELETE', `/api/v1/transactions/${encodeURIComponent(transactionId)}/split`),
  /** Etiquetas de los movimientos que ves, con cuántos las llevan (OF-1002). */
  tags: (signal?: AbortSignal) => request<TagCount[]>('GET', '/api/v1/tags', { signal }),
  setTags: (transactionId: string, tags: string[]) =>
    request<TagsResult>('PUT', `/api/v1/transactions/${encodeURIComponent(transactionId)}/tags`, { json: { tags } }),
  /** Comercios con sus variantes del banco (OF-1001). */
  merchants: (signal?: AbortSignal) => request<MerchantGroup[]>('GET', '/api/v1/merchants', { signal }),
  renameMerchant: (key: string, name: string) =>
    request<MerchantChange>('POST', '/api/v1/merchants/rename', { json: { key, name } }),
  mergeMerchants: (targetKey: string, sourceKey: string) =>
    request<MerchantChange>('POST', '/api/v1/merchants/merge', { json: { target_key: targetKey, source_key: sourceKey } }),
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
  /** `mode` solo viaja si es un sobre: un límite es lo de siempre (OF-1203). */
  setBudget: (categoryId: string, amount: string, mode: 'limit' | 'envelope' = 'limit') =>
    request<Budget>('PUT', `/api/v1/budgets/${encodeURIComponent(categoryId)}`, {
      json: mode === 'envelope' ? { amount, mode } : { amount },
    }),
  setBudgetMonth: (categoryId: string, month: string, amount: string) =>
    request<Budget>('PUT', `/api/v1/budgets/${encodeURIComponent(categoryId)}/months/${encodeURIComponent(month)}`, { json: { amount } }),
  clearBudgetMonth: (categoryId: string, month: string) =>
    request<void>('DELETE', `/api/v1/budgets/${encodeURIComponent(categoryId)}/months/${encodeURIComponent(month)}`),
  deleteBudget: (categoryId: string) => request<void>('DELETE', `/api/v1/budgets/${encodeURIComponent(categoryId)}`),
  createGoal: (input: GoalInput) => request<Goal>('POST', '/api/v1/goals', { json: input }),
  updateGoal: (id: string, patch: Partial<GoalPatch>) =>
    request<Goal>('PATCH', `/api/v1/goals/${encodeURIComponent(id)}`, {
      json: { clear_account: false, ...patch },
    }),
  deleteGoal: (id: string) => request<void>('DELETE', `/api/v1/goals/${encodeURIComponent(id)}`),
  /** Aportaciones a un objetivo y reparto por prioridad (OF-1206). */
  goalContributions: (id: string, signal?: AbortSignal) =>
    request<Contribution[]>('GET', `/api/v1/goals/${encodeURIComponent(id)}/contributions`, { signal }),
  addContribution: (id: string, amount: string, note: string) =>
    request<{ contribution: Contribution; operation_id: string | null }>('POST', `/api/v1/goals/${encodeURIComponent(id)}/contributions`, {
      json: { amount, note },
    }),
  deleteContribution: (goalId: string, contributionId: string) =>
    request<{ operation_id: string | null }>(
      'DELETE',
      `/api/v1/goals/${encodeURIComponent(goalId)}/contributions/${encodeURIComponent(contributionId)}`,
    ),
  goalSplit: (amount: string) => request<GoalShare[]>('GET', '/api/v1/goals/split', { query: { amount } }),
  dismissIdea: (id: string) => request<void>('PUT', `/api/v1/savings/ideas/${encodeURIComponent(id)}/dismissed`),
  restoreIdea: (id: string) => request<void>('DELETE', `/api/v1/savings/ideas/${encodeURIComponent(id)}/dismissed`),
  savingsOverview: (signal?: AbortSignal) => request<SavingsOverview>('GET', '/api/v1/savings/overview', { signal }),
  uncategorizedCount: (signal?: AbortSignal) =>
    request<{ count: number }>('GET', '/api/v1/transactions/uncategorized-count', { signal }),
}
