import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BarChart, Donut, LineChart, Ring, StackedBars, geometry, niceMax } from '.'
import { labelStep, labelWidth, showLabel } from './useChartWidth'

describe('gráficos (ADR-0014)', () => {
  it('niceMax redondea el eje', () => {
    expect(niceMax(0)).toBe(1)
    expect(niceMax(87)).toBe(100)
    expect(niceMax(2300)).toBe(2500)
    expect(niceMax(4100)).toBe(5000)
  })

  it('geometry convierte céntimos solo para dibujar', () => {
    expect(geometry(-8734n)).toBe(-87.34)
  })

  it('el donut dibuja solo segmentos positivos y es accesible', () => {
    const { container } = render(
      <Donut
        label="Gasto de octubre: 2.247 €"
        title="2.247 €"
        subtitle="3 categorías"
        segments={[
          { id: 'a', label: 'Vivienda', value: 785, valueText: '785 €', color: '#0f766e' },
          { id: 'b', label: 'Super', value: 520, valueText: '520 €', color: '#16a34a' },
          { id: 'c', label: 'Devoluciones', value: -20, valueText: '-20 €', color: '#999' },
        ]}
        active="b"
      />,
    )
    expect(screen.getByRole('img', { name: 'Gasto de octubre: 2.247 €' })).toBeInTheDocument()
    expect(container.querySelectorAll('[data-segment]')).toHaveLength(2)
    expect(container.querySelector('[data-segment="a"]')).toHaveAttribute('opacity', '0.25')
    const table = screen.getByRole('table', { name: 'Gasto de octubre: 2.247 €' })
    expect(within(table).getByText('Vivienda').closest('tr')).toHaveTextContent('785 €')
  })

  it('el donut sin datos no dibuja segmentos', () => {
    const { container } = render(<Donut label="Sin datos" title="0 €" segments={[]} />)
    expect(container.querySelectorAll('[data-segment]')).toHaveLength(0)
  })

  it('las barras admiten negativos, referencia y mes resaltado', () => {
    const { container } = render(
      <BarChart
        label="Ahorro por mes"
        data={[
          { label: 'jul', value: 681, valueText: '681 €' },
          { label: 'ago', value: -555, valueText: '-555 €' },
          { label: 'sep', value: 1057, valueText: '1.057 €' },
        ]}
        reference={{ value: 400, label: 'Media 400 €' }}
        highlight={2}
      />,
    )
    const bars = container.querySelectorAll('[data-bar] rect')
    expect(bars).toHaveLength(3)
    expect(bars[1]).toHaveAttribute('fill', '#c2410c')
    expect(container.querySelector('[data-bar="0"]')).toHaveClass('dim')
    expect(container.querySelector('[data-bar="2"]')).not.toHaveClass('dim')
    expect(container.querySelector('line.zero')).not.toBeNull()
    expect(screen.getByText('Media 400 €')).toBeInTheDocument()
    // las barras no salen del área dibujada
    for (const rect of bars) {
      expect(Number(rect.getAttribute('y'))).toBeGreaterThanOrEqual(0)
      expect(Number(rect.getAttribute('y')) + Number(rect.getAttribute('height'))).toBeLessThanOrEqual(200)
    }
  })

  it('las barras dibujan una referencia negativa por debajo de cero', () => {
    const { container } = render(
      <BarChart
        label="Ahorro"
        data={[{ label: 'ene', value: -100, valueText: '-100 €' }]}
        reference={{ value: -50, label: 'Media -50 €' }}
      />,
    )
    const zero = Number(container.querySelector('line.zero')!.getAttribute('y1'))
    const ref = Number(container.querySelector('line.ref')!.getAttribute('y1'))
    expect(ref).toBeGreaterThan(zero)
    expect(screen.getByText('Media -50 €')).toBeInTheDocument()
  })

  it('las barras apiladas ignoran partes no positivas', () => {
    const { container } = render(
      <StackedBars
        label="Gasto mensual"
        rows={[
          {
            label: 'oct',
            totalText: '300 €',
            parts: [
              { id: 'a', label: 'A', value: 200, valueText: '200 €', color: '#111' },
              { id: 'b', label: 'B', value: 100, valueText: '100 €', color: '#222' },
              { id: 'c', label: 'C', value: -5, valueText: '-5 €', color: '#333' },
            ],
          },
        ]}
      />,
    )
    expect(container.querySelectorAll('[data-stack="0"] rect')).toHaveLength(2)
    expect(screen.getByRole('table', { name: 'Gasto mensual' })).toHaveTextContent('300 €')
  })

  it('las líneas saltan los huecos sin datos', () => {
    const { container } = render(
      <LineChart
        label="Ritmo de gasto"
        series={[
          { id: 'now', label: 'Este mes', points: [10, 20, null, null], color: '#0f766e', area: true, summary: '20 €' },
          { id: 'prev', label: 'Anterior', points: [5, 15, 25, 30], color: '#94a3b8', dashed: true, summary: '30 €' },
        ]}
        xLabels={[[0, '1'], [3, '4']]}
      />,
    )
    const now = container.querySelector('[data-series="now"] polyline')!
    expect(now.getAttribute('points')!.split(' ')).toHaveLength(2)
    expect(container.querySelector('[data-series="now"] polygon')).not.toBeNull()
    expect(container.querySelector('[data-series="prev"] polyline')).toHaveAttribute('stroke-dasharray', '6 5')
  })

  it('en estrecho se escriben menos etiquetas y siempre la del último dato (OF-503)', () => {
    // 12 meses en 330 px: cada hueco mide 26 px y «sept» necesita más.
    const step = labelStep(26, labelWidth('sept'))
    expect(step).toBe(2)
    const shown = Array.from({ length: 12 }, (_, i) => showLabel(i, 12, step))
    expect(shown.filter(Boolean)).toHaveLength(6)
    expect(shown[11]).toBe(true)
    expect(labelStep(60, labelWidth('sept'))).toBe(1)
  })

  it('el anillo limita el porcentaje', () => {
    render(<Ring percent={140} label="Fondo de emergencia" />)
    expect(screen.getByRole('img', { name: 'Fondo de emergencia: 140 %' })).toBeInTheDocument()
  })
})
