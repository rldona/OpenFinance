export { BarChart, type Bar } from './BarChart'
export { ChartFigure } from './ChartFigure'
export { niceMax } from './scale'
export { Donut, type DonutSegment } from './Donut'
export { LineChart, type Series } from './LineChart'
export { Ring } from './Ring'
export { StackedBars, type StackPart, type StackRow } from './StackedBars'

/** Céntimos (BigInt) → número solo para geometría (ADR-0014). Nunca para mostrar importes. */
export function geometry(cents: bigint): number {
  return Number(cents) / 100
}
