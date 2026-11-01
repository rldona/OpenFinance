import { ChartFigure } from './ChartFigure'
import { niceMax } from './scale'
import { labelWidth, useChartWidth } from './useChartWidth'

export type Series = {
  id: string
  label: string
  points: (number | null)[]
  color: string
  dashed?: boolean
  area?: boolean
  summary: string
}

export function LineChart({
  series,
  label,
  xLabels = [],
  height = 220,
  reference,
}: {
  series: Series[]
  label: string
  xLabels?: [number, string][]
  height?: number
  reference?: { value: number; label: string }
}) {
  const [figure, W] = useChartWidth<HTMLElement>()
  const pad = { l: 8, r: 8, t: 16, b: 24 }
  const n = Math.max(2, ...series.map((s) => s.points.length))
  const values = series.flatMap((s) => s.points.filter((v): v is number => v !== null))
  const max = niceMax(Math.max(0, ...values, reference?.value ?? 0))
  const X = (i: number) => pad.l + (i / (n - 1)) * (W - pad.l - pad.r)
  const Y = (v: number) => height - pad.b - (Math.max(v, 0) / max) * (height - pad.t - pad.b)
  // Sin solapes: se descarta la etiqueta que pisaría a la anterior escrita.
  const ticks = xLabels.reduce<[number, string][]>((shown, tick) => {
    const prev = shown.at(-1)
    const gap = prev ? X(tick[0]) - X(prev[0]) : Infinity
    return prev && gap < (labelWidth(prev[1]) + labelWidth(tick[1])) / 2 ? shown : [...shown, tick]
  }, [])
  return (
    <ChartFigure label={label} rows={series.map((s) => [s.label, s.summary])} measureRef={figure}>
      <svg viewBox={`0 0 ${W} ${height}`} aria-hidden="true">
        {reference && reference.value > 0 && (
          <g className="reference">
            <line x1={pad.l} x2={W - pad.r} y1={Y(reference.value)} y2={Y(reference.value)} className="ref" />
            <text x={W - pad.r} y={Y(reference.value) - 5} textAnchor="end" className="ref-label">
              {reference.label}
            </text>
          </g>
        )}
        {series.map((s) => {
          const pts = s.points.flatMap((v, i) => (v === null ? [] : [[i, v] as const]))
          if (pts.length === 0) return null
          const path = pts.map(([i, v]) => `${X(i)},${Y(v)}`).join(' ')
          const [lastI, lastV] = pts[pts.length - 1]
          return (
            <g key={s.id} data-series={s.id}>
              {s.area && (
                <polygon
                  points={`${X(pts[0][0])},${height - pad.b} ${path} ${X(lastI)},${height - pad.b}`}
                  fill={s.color}
                  opacity={0.1}
                />
              )}
              <polyline
                points={path}
                fill="none"
                stroke={s.color}
                strokeWidth={s.dashed ? 2 : 3}
                strokeDasharray={s.dashed ? '6 5' : undefined}
                strokeLinejoin="round"
                strokeLinecap="round"
              >
                <title>{`${s.label}: ${s.summary}`}</title>
              </polyline>
              <circle cx={X(lastI)} cy={Y(lastV)} r={4.5} fill={s.color}>
                <title>{`${s.label}: ${s.summary}`}</title>
              </circle>
            </g>
          )
        })}
        {ticks.map(([i, l]) => (
          <text key={`${i}-${l}`} x={X(i)} y={height - 6} textAnchor="middle" className="axis">
            {l}
          </text>
        ))}
      </svg>
    </ChartFigure>
  )
}
