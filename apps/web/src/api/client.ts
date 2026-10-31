export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: 'application/json', ...init?.headers },
    credentials: 'include',
  })
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} → ${response.status}`)
  }
  return (await response.json()) as T
}

export interface Health {
  status: string
  version: string
}

export const getHealth = (signal?: AbortSignal) => apiGet<Health>('/health', { signal })
