import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExportMenu } from './ExportMenu'

describe('Exportación', () => {
  it('enlaza a la descarga JSON y CSV de la API', () => {
    render(<ExportMenu />)
    expect(screen.getByRole('link', { name: 'JSON', hidden: true })).toHaveAttribute(
      'href',
      '/api/v1/export?format=json',
    )
    expect(screen.getByRole('link', { name: 'CSV (ZIP)', hidden: true })).toHaveAttribute(
      'href',
      '/api/v1/export?format=csv',
    )
  })

  it('aclara que la cuenta personal de la pareja no se incluye', () => {
    render(<ExportMenu />)
    expect(screen.getByText(/cuenta personal de la otra persona no se incluye/)).toBeInTheDocument()
  })
})
