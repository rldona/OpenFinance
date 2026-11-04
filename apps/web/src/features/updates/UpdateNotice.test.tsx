import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mockApi } from '../../test/api'
import { safeUrl } from '../../lib/safeUrl'
import { UpdateNotice } from './UpdateNotice'

const NEW = {
  current: '0.2.0',
  enabled: true,
  latest: '0.3.0',
  url: 'https://github.com/rldona/OpenFinance/releases/tag/v0.3.0',
  update_available: true,
}

describe('UpdateNotice', () => {
  beforeEach(() => window.localStorage.clear())
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('avisa de una versión nueva con enlace a las novedades', async () => {
    mockApi({ 'GET /api/v1/version': { body: NEW } })
    render(<UpdateNotice />)
    expect(await screen.findByRole('status')).toHaveTextContent('0.3.0')
    const link = screen.getByRole('link', { name: 'Ver novedades' })
    expect(link).toHaveAttribute('href', NEW.url)
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('se puede descartar y no vuelve para esa versión', async () => {
    mockApi({ 'GET /api/v1/version': { body: NEW } })
    const { unmount } = render(<UpdateNotice />)
    await userEvent.click(await screen.findByRole('button', { name: 'Ahora no' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    unmount()
    render(<UpdateNotice />)
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('vuelve a avisar cuando sale otra versión distinta de la descartada', async () => {
    window.localStorage.setItem('of-update-dismissed', '0.2.5')
    mockApi({ 'GET /api/v1/version': { body: NEW } })
    render(<UpdateNotice />)
    expect(await screen.findByRole('status')).toBeInTheDocument()
  })

  it.each([
    ['sin versión nueva', { ...NEW, update_available: false }],
    ['con la consulta apagada', { ...NEW, enabled: false, latest: null, url: null, update_available: false }],
  ])('no pinta nada %s', async (_name, body) => {
    mockApi({ 'GET /api/v1/version': { body } })
    render(<UpdateNotice />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('si la consulta falla, no molesta', async () => {
    mockApi({ 'GET /api/v1/version': { status: 500, body: { detail: 'x' } } })
    render(<UpdateNotice />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('un enlace que no es https no se pinta como enlace', async () => {
    mockApi({ 'GET /api/v1/version': { body: { ...NEW, url: 'javascript:alert(1)' } } })
    render(<UpdateNotice />)
    expect(await screen.findByRole('status')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(safeUrl('http://github.com/x')).toBeNull()
    expect(safeUrl('https://github.com/x')).toBe('https://github.com/x')
  })
})
