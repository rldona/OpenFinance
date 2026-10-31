export function Ring({ percent, label, size = 84, color = '#0f766e' }: { percent: number; label: string; size?: number; color?: string }) {
  const r = size / 2 - 7
  const c = size / 2
  const circ = 2 * Math.PI * r
  const p = Math.max(0, Math.min(percent, 100))
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label={`${label}: ${Math.round(percent)} %`}>
      <circle r={r} cx={c} cy={c} fill="none" stroke="#e7eaee" strokeWidth={9} />
      <circle
        r={r}
        cx={c}
        cy={c}
        fill="none"
        stroke={color}
        strokeWidth={9}
        strokeLinecap="round"
        strokeDasharray={`${(p / 100) * circ} ${circ}`}
        transform={`rotate(-90 ${c} ${c})`}
      />
      <text x={c} y={c + 5} textAnchor="middle" className="ring-text">
        {Math.round(percent)}%
      </text>
    </svg>
  )
}
