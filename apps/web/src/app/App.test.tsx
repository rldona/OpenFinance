import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

afterEach(() => vi.restoreAllMocks())

describe('App', () => {
  it('muestra la versión de la API cuando /health responde', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), { status: 200 }),
    )
    render(<App />)
    expect(await screen.findByText('API 0.1.0')).toBeInTheDocument()
  })

  it('indica que la API no está disponible si falla', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('network'))
    render(<App />)
    expect(await screen.findByText('API no disponible')).toBeInTheDocument()
  })

  it('navega entre secciones', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('network'))
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Ahorrar' }))
    expect(screen.getByRole('heading', { name: 'Ahorrar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ahorrar' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})
