import { ChartFigure } from './ChartFigure'
import { niceMax } from './scale'
import { labelStep, labelWidth, showLabel, useChartWidth } from './useChartWidth'

export type Bar = { label: string; value: number; valueText: string; color?: string }

export function BarChart({
  data,
  label,
  height = 200,
  reference,
  highlight,
  color = '#0f766e',
  negativeColor = '#c2410c',
}: {
  data: Bar[]
  label: string
  height?: number
  reference?: { value: number; label: string }
  highlight?: number
  color?: string
  negativeColor?: string
}) {
  const [figure, W] = useChartWidth<HTMLElement>()
  const pad = { l: 8, r: 8, t: 18, b: 26 }
  const ref = reference?.value ?? 0
  const hasNeg = data.some((d) => d.value < 0) || ref < 0
  const maxPos = niceMax(Math.max(0, ...data.map((d) => d.value), ref))
  const maxNeg = hasNeg ? niceMax(Math.max(0, ...data.map((d) => -d.value), -ref)) : 0
  const plot = height - pad.t - pad.b
  const scale = plot / (maxPos + maxNeg)
  const zeroY = pad.t + maxPos * scale
  const bw = (W - pad.l - pad.r) / Math.max(data.length, 1)
  const step = labelStep(bw, Math.max(0, ...data.map((d) => labelWidth(d.label))))
  return (
    <ChartFigure label={label} rows={data.map((d) => [d.label, d.valueText])} measureRef={figure}>
      <svg viewBox={`0 0 ${W} ${height}`} aria-hidden="true">
        {hasNeg && <line x1={pad.l} x2={W - pad.r} y1={zeroY} y2={zeroY} className="zero" />}
        {data.map((d, i) => {
          const h = Math.max(Math.abs(d.value) * scale, d.value === 0 ? 0 : 1)
          const x = pad.l + i * bw + bw * 0.18
          const y = d.value >= 0 ? zeroY - h : zeroY
          const dim = highlight !== undefined && highlight !== i
          return (
            <g key={`${d.label}-${i}`} data-bar={i} className={dim ? 'dim' : ''}>
              <rect
                x={x}
                y={y}
                width={bw * 0.64}
                height={h}
                rx={4}
                fill={d.value < 0 ? negativeColor : (d.color ?? color)}
                opacity={dim ? 0.45 : 1}
              >
                <title>{`${d.label}: ${d.valueText}`}</title>
              </rect>
              {showLabel(i, data.length, step) && (
                <text x={x + bw * 0.32} y={height - 8} textAnchor="middle" className="axis">
                  {d.label}
                </text>
              )}
            </g>
          )
        })}
        {reference && reference.value !== 0 && (
          <g className="reference">
            <line
              x1={pad.l}
              x2={W - pad.r}
              y1={zeroY - reference.value * scale}
              y2={zeroY - reference.value * scale}
              className="ref"
            />
            <text x={W - pad.r} y={zeroY - reference.value * scale - 5} textAnchor="end" className="ref-label">
              {reference.label}
            </text>
          </g>
        )}
      </svg>
    </ChartFigure>
  )
}
