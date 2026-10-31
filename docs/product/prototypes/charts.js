/* Gráficos SVG mínimos para el prototipo. Sin dependencias. */
window.Charts = (() => {
  'use strict'
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
  const niceMax = (v) => {
    if (v <= 0) return 1
    const p = 10 ** Math.floor(Math.log10(v))
    return [1, 2, 2.5, 5, 10].map((k) => k * p).find((x) => x >= v)
  }

  /** Donut: segments = [{ value, color, label, id }] */
  function donut(segments, { size = 220, thickness = 34, title = '', subtitle = '', active = null } = {}) {
    const total = segments.reduce((s, x) => s + x.value, 0) || 1
    const r = (size - thickness) / 2
    const c = size / 2
    const circ = 2 * Math.PI * r
    let offset = 0
    const arcs = segments.map((s) => {
      const len = (s.value / total) * circ
      const dim = active && active !== s.id ? 0.25 : 1
      const el = `<circle r="${r}" cx="${c}" cy="${c}" fill="none" stroke="${s.color}" stroke-width="${thickness}" stroke-dasharray="${len} ${circ - len}" stroke-dashoffset="${-offset}" opacity="${dim}" data-cat="${s.id || ''}" style="cursor:pointer"><title>${esc(s.label)}</title></circle>`
      offset += len
      return el
    })
    return `<svg viewBox="0 0 ${size} ${size}" class="chart-svg donut" role="img" aria-label="${esc(title)}">
      <g transform="rotate(-90 ${c} ${c})">${arcs.join('')}</g>
      <text x="${c}" y="${c - 4}" text-anchor="middle" class="donut-title">${esc(title)}</text>
      <text x="${c}" y="${c + 18}" text-anchor="middle" class="donut-sub">${esc(subtitle)}</text>
    </svg>`
  }

  /** Barras verticales: data = [{ label, value, color, title }]; ref = línea de referencia */
  function bars(data, { height = 200, ref = null, refLabel = '', fmt = String, highlight = -1, negativeColor = '#dc2626' } = {}) {
    const W = 640, H = height, pad = { l: 8, r: 8, t: 16, b: 26 }
    const maxV = niceMax(Math.max(...data.map((d) => Math.abs(d.value)), ref || 0))
    const hasNeg = data.some((d) => d.value < 0)
    const zeroY = hasNeg ? pad.t + (H - pad.t - pad.b) * 0.8 : H - pad.b
    const scale = (zeroY - pad.t) / maxV
    const bw = (W - pad.l - pad.r) / data.length
    const out = data.map((d, i) => {
      const h = Math.abs(d.value) * scale
      const y = d.value >= 0 ? zeroY - h : zeroY
      const x = pad.l + i * bw + bw * 0.18
      const color = d.value < 0 ? negativeColor : d.color || '#0f766e'
      return `<g><rect x="${x}" y="${y}" width="${bw * 0.64}" height="${Math.max(h, 1)}" rx="4" fill="${color}" opacity="${highlight === -1 || highlight === i ? 1 : 0.45}"><title>${esc(d.title || `${d.label}: ${fmt(d.value)}`)}</title></rect>
        <text x="${x + bw * 0.32}" y="${H - 8}" text-anchor="middle" class="axis">${esc(d.label)}</text></g>`
    })
    const refLine = ref ? `<line x1="${pad.l}" x2="${W - pad.r}" y1="${zeroY - ref * scale}" y2="${zeroY - ref * scale}" class="ref"/><text x="${W - pad.r}" y="${zeroY - ref * scale - 5}" text-anchor="end" class="ref-label">${esc(refLabel)}</text>` : ''
    const zero = hasNeg ? `<line x1="${pad.l}" x2="${W - pad.r}" y1="${zeroY}" y2="${zeroY}" class="zero"/>` : ''
    return `<svg viewBox="0 0 ${W} ${H}" class="chart-svg" role="img">${zero}${out.join('')}${refLine}</svg>`
  }

  /** Barras apiladas: rows = [{ label, parts: [{ value, color, label }] }] */
  function stacked(rows, { height = 240, fmt = String } = {}) {
    const W = 640, H = height, pad = { l: 8, r: 8, t: 10, b: 26 }
    const maxV = niceMax(Math.max(...rows.map((r) => r.parts.reduce((s, p) => s + p.value, 0))))
    const scale = (H - pad.t - pad.b) / maxV
    const bw = (W - pad.l - pad.r) / rows.length
    const out = rows.map((r, i) => {
      let y = H - pad.b
      const x = pad.l + i * bw + bw * 0.15
      const total = r.parts.reduce((s, p) => s + p.value, 0)
      const segs = r.parts.map((p) => {
        const h = p.value * scale
        y -= h
        return `<rect x="${x}" y="${y}" width="${bw * 0.7}" height="${h}" fill="${p.color}"><title>${esc(`${r.label} · ${p.label}: ${fmt(p.value)}`)}</title></rect>`
      })
      return `<g>${segs.join('')}<text x="${x + bw * 0.35}" y="${H - 8}" text-anchor="middle" class="axis">${esc(r.label)}</text><text x="${x + bw * 0.35}" y="${H - pad.b - total * scale - 4}" text-anchor="middle" class="axis small-axis">${esc(fmt(total).replace(/,\d+\s/, ' '))}</text></g>`
    })
    return `<svg viewBox="0 0 ${W} ${H}" class="chart-svg" role="img">${out.join('')}</svg>`
  }

  /** Líneas: series = [{ points: [number|null], color, label, dashed }]; xLabels opcional */
  function lines(series, { height = 220, xLabels = [], fmt = String, budget = null } = {}) {
    const W = 640, H = height, pad = { l: 8, r: 8, t: 14, b: 24 }
    const n = Math.max(...series.map((s) => s.points.length))
    const maxV = niceMax(Math.max(...series.flatMap((s) => s.points.filter((v) => v !== null)), budget || 0))
    const X = (i) => pad.l + (i / (n - 1)) * (W - pad.l - pad.r)
    const Y = (v) => H - pad.b - (v / maxV) * (H - pad.t - pad.b)
    const paths = series.map((s) => {
      const pts = s.points.map((v, i) => (v === null ? null : `${X(i)},${Y(v)}`)).filter(Boolean)
      const last = s.points.map((v, i) => [v, i]).filter(([v]) => v !== null).pop()
      const area = s.area ? `<polygon points="${X(0)},${H - pad.b} ${pts.join(' ')} ${X(last[1])},${H - pad.b}" fill="${s.color}" opacity=".10"/>` : ''
      return `${area}<polyline points="${pts.join(' ')}" fill="none" stroke="${s.color}" stroke-width="${s.dashed ? 2 : 3}" ${s.dashed ? 'stroke-dasharray="6 5"' : ''} stroke-linejoin="round" stroke-linecap="round"><title>${esc(s.label)}</title></polyline>
        ${last ? `<circle cx="${X(last[1])}" cy="${Y(last[0])}" r="4.5" fill="${s.color}"><title>${esc(`${s.label}: ${fmt(last[0])}`)}</title></circle>` : ''}`
    })
    const b = budget ? `<line x1="${pad.l}" x2="${W - pad.r}" y1="${Y(budget)}" y2="${Y(budget)}" class="ref"/><text x="${W - pad.r}" y="${Y(budget) - 5}" text-anchor="end" class="ref-label">Presupuesto ${esc(fmt(budget))}</text>` : ''
    const xl = xLabels.map(([i, l]) => `<text x="${X(i)}" y="${H - 6}" text-anchor="middle" class="axis">${esc(l)}</text>`).join('')
    return `<svg viewBox="0 0 ${W} ${H}" class="chart-svg" role="img">${b}${paths.join('')}${xl}</svg>`
  }

  /** Sparkline pequeña */
  function spark(values, { color = '#0f766e', w = 110, h = 30 } = {}) {
    const max = Math.max(...values, 1)
    const pts = values.map((v, i) => `${(i / (values.length - 1)) * (w - 4) + 2},${h - 2 - (v / max) * (h - 4)}`).join(' ')
    return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/></svg>`
  }

  /** Anillo de progreso */
  function ring(pct, { size = 84, color = '#0f766e', label = '' } = {}) {
    const r = size / 2 - 7, c = size / 2, circ = 2 * Math.PI * r, p = Math.max(0, Math.min(pct, 100))
    return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="${esc(label)} ${Math.round(pct)} %">
      <circle r="${r}" cx="${c}" cy="${c}" fill="none" stroke="#e7eaee" stroke-width="9"/>
      <circle r="${r}" cx="${c}" cy="${c}" fill="none" stroke="${color}" stroke-width="9" stroke-linecap="round" stroke-dasharray="${(p / 100) * circ} ${circ}" transform="rotate(-90 ${c} ${c})"/>
      <text x="${c}" y="${c + 5}" text-anchor="middle" class="ring-text">${Math.round(pct)}%</text></svg>`
  }

  return { donut, bars, stacked, lines, spark, ring }
})()
