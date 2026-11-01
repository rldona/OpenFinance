import { ChartFigure } from './ChartFigure'
import { niceMax } from './scale'
import { labelStep, labelWidth, showLabel, useChartWidth } from './useChartWidth'

export type StackPart = { id: string; label: string; value: number; valueText: string; color: string }
export type StackRow = { label: string; totalText: string; parts: StackPart[] }

export function StackedBars({ rows, label, height = 240 }: { rows: StackRow[]; label: string; height?: number }) {
  const [figure, W] = useChartWidth<HTMLElement>()
  const pad = { l: 8, r: 8, t: 22, b: 26 }
  const totals = rows.map((r) => r.parts.reduce((s, p) => s + Math.max(p.value, 0), 0))
  const max = niceMax(Math.max(0, ...totals))
  const scale = (height - pad.t - pad.b) / max
  const bw = (W - pad.l - pad.r) / Math.max(rows.length, 1)
  const labelEvery = labelStep(bw, Math.max(0, ...rows.map((r) => labelWidth(r.label))))
  // Los totales van sobre cada barra a distinta altura: solo se escriben si caben todos.
  const showTotals = labelStep(bw, Math.max(0, ...rows.map((r) => labelWidth(r.totalText, 11)))) === 1
  return (
    <ChartFigure label={label} rows={rows.map((r) => [r.label, r.totalText])} measureRef={figure}>
      <svg viewBox={`0 0 ${W} ${height}`} aria-hidden="true">
        {rows.map((r, i) => {
          let y = height - pad.b
          const x = pad.l + i * bw + bw * 0.15
          return (
            <g key={`${r.label}-${i}`} data-stack={i}>
              {r.parts
                .filter((p) => p.value > 0)
                .map((p) => {
                  const h = p.value * scale
                  y -= h
                  return (
                    <rect key={p.id} x={x} y={y} width={bw * 0.7} height={h} fill={p.color}>
                      <title>{`${r.label} · ${p.label}: ${p.valueText}`}</title>
                    </rect>
                  )
                })}
              {showLabel(i, rows.length, labelEvery) && (
                <text x={x + bw * 0.35} y={height - 8} textAnchor="middle" className="axis">
                  {r.label}
                </text>
              )}
              {totals[i] > 0 && showTotals && (
                <text x={x + bw * 0.35} y={y - 5} textAnchor="middle" className="axis small-axis">
                  {r.totalText}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </ChartFigure>
  )
}
