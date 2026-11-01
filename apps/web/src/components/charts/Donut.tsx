import { ChartFigure } from './ChartFigure'

export type DonutSegment = { id: string; label: string; value: number; valueText: string; color: string }

export function Donut({
  segments,
  title,
  subtitle,
  label,
  active,
  size = 220,
  thickness = 34,
}: {
  segments: DonutSegment[]
  title: string
  subtitle?: string
  label: string
  active?: string | null
  size?: number
  thickness?: number
}) {
  const visible = segments.filter((s) => s.value > 0)
  const total = visible.reduce((s, x) => s + x.value, 0)
  const r = (size - thickness) / 2
  const c = size / 2
  const circ = 2 * Math.PI * r
  let offset = 0
  return (
    <ChartFigure label={label} rows={segments.map((s) => [s.label, s.valueText])} className="donut">
      <svg viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle r={r} cx={c} cy={c} fill="none" style={{ stroke: 'var(--track)' }} strokeWidth={thickness} />
        <g transform={`rotate(-90 ${c} ${c})`}>
          {total > 0 &&
            visible.map((s) => {
              const len = (s.value / total) * circ
              const el = (
                <circle
                  key={s.id}
                  data-segment={s.id}
                  r={r}
                  cx={c}
                  cy={c}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={thickness}
                  strokeDasharray={`${len} ${circ - len}`}
                  strokeDashoffset={-offset}
                  opacity={active && active !== s.id ? 0.25 : 1}
                >
                  <title>{`${s.label}: ${s.valueText}`}</title>
                </circle>
              )
              offset += len
              return el
            })}
        </g>
        <text x={c} y={c - 4} textAnchor="middle" className="donut-title">
          {title}
        </text>
        {subtitle && (
          <text x={c} y={c + 18} textAnchor="middle" className="donut-sub">
            {subtitle}
          </text>
        )}
      </svg>
    </ChartFigure>
  )
}
