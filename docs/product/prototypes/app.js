(() => {
  'use strict'

  const D = window.OF
  const C = window.Charts
  const CAT = Object.fromEntries(D.categories.map((c) => [c.id, c]))
  const LAST = D.months.length - 1

  const state = {
    month: LAST,
    txns: D.txns.map((t) => ({ ...t })),
    cat: null,
    q: '',
    onlyUncat: false,
    sim: { super: 10, restaurantes: 25, suscripciones: 0, transporte: 0, ocio: 0, ropa: 0 },
    importStep: 1,
    rules: [],
  }

  /* ---------- utilidades ---------- */
  const eur = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' })
  const eur0 = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
  const fmt = (c) => eur.format(c / 100)
  const fmt0 = (c) => eur0.format(Math.round(c / 100))
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
  const $ = (s) => document.querySelector(s)
  const sum = (xs) => xs.reduce((a, b) => a + b, 0)
  const pct = (a, b) => (b ? Math.round(((a - b) / b) * 100) : 0)
  const day = (iso) => Number(iso.slice(8, 10))
  const dateLabel = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
  const monthName = (i) => new Date(D.months[i].y, D.months[i].m, 1).toLocaleDateString('es-ES', { month: 'long', year: 'numeric' })

  function toast(msg) {
    const el = $('#toast')
    el.textContent = msg
    el.classList.add('show')
    clearTimeout(toast.t)
    toast.t = setTimeout(() => el.classList.remove('show'), 2600)
  }

  function merchant(desc) {
    const clean = desc
      .replace(/^(COMPRA TARJETA \d+|RECIBO|TRANSFERENCIA DE|BIZUM A)\s+/i, '')
      .replace(/[^A-ZÁÉÍÓÚÑ .]/gi, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    const ws = clean.split(' ').filter((w) => w.length > 1)
    const words = ws.slice(0, ws[1] && ws[1].length <= 3 ? 3 : 2).join(' ')
    return words.charAt(0) + words.slice(1).toLowerCase()
  }

  /* ---------- cálculos (en la app real los hace el Core) ---------- */
  const isExpense = (t) => t.amount < 0 && !t.savings
  const inMonth = (i) => state.txns.filter((t) => t.date.startsWith(D.months[i].key))
  const spent = (i) => -sum(inMonth(i).filter(isExpense).map((t) => t.amount))
  const income = (i) => sum(inMonth(i).filter((t) => t.income).map((t) => t.amount))
  const saved = (i) => income(i) - spent(i)

  function byCat(i) {
    const out = {}
    for (const t of inMonth(i).filter(isExpense)) out[t.category || 'sin'] = (out[t.category || 'sin'] || 0) - t.amount
    return out
  }

  /** Media mensual de los 12 meses anteriores al mes i (o de los que haya). */
  function avgCat(cat, i = state.month) {
    const prev = D.months.map((_, k) => k).filter((k) => k < i)
    const ks = prev.length ? prev : [i]
    return Math.round(sum(ks.map((k) => byCat(k)[cat] || 0)) / ks.length)
  }
  const avgSpent = (i = state.month) => {
    const ks = D.months.map((_, k) => k).filter((k) => k < i)
    return ks.length ? Math.round(sum(ks.map(spent)) / ks.length) : spent(i)
  }

  function cumulative(i) {
    const days = D.months[i].days
    const per = Array(days).fill(0)
    for (const t of inMonth(i).filter(isExpense)) per[day(t.date) - 1] -= t.amount
    let acc = 0
    return per.map((v) => (acc += v))
  }

  const totalBudget = () => sum(Object.values(D.budgets))
  const uncategorized = () => state.txns.filter((t) => !t.category && !t.income && !t.savings)

  function segments(i) {
    return Object.entries(byCat(i))
      .sort((a, b) => b[1] - a[1])
      .map(([id, value]) => ({ id, value, color: CAT[id]?.color || '#cbd5e1', label: `${CAT[id]?.name || 'Sin categoría'}: ${fmt(value)}` }))
  }

  function delta(a, b, { invert = false, suffix = 'que el mes anterior' } = {}) {
    const p = pct(a, b)
    if (!b || p === 0) return `<span class="pill neutral">= ${suffix}</span>`
    const good = invert ? p > 0 : p < 0
    return `<span class="pill ${good ? 'down' : 'up'}">${p > 0 ? '▲' : '▼'} ${Math.abs(p)} % ${suffix}</span>`
  }

  /* ---------- cabecera ---------- */
  const TABS = [
    ['mes', 'Este mes'],
    ['gastos', '¿En qué gastamos?'],
    ['evolucion', 'Evolución'],
    ['ahorrar', 'Ahorrar'],
    ['movimientos', 'Movimientos'],
    ['importar', 'Importar'],
  ]
  const route = () => (TABS.some(([id]) => id === location.hash.slice(1)) ? location.hash.slice(1) : 'mes')

  function renderTop() {
    $('#hh-name').textContent = `${D.household.name} · ${D.household.account}`
    const n = uncategorized().length
    $('#tabs').innerHTML = TABS.map(([id, label]) => `<a href="#${id}" class="${route() === id ? 'active' : ''}">${label}${id === 'movimientos' && n ? `<span class="badge">${n}</span>` : ''}</a>`).join('')
    const showPicker = ['mes', 'gastos', 'movimientos'].includes(route())
    $('#month-picker').innerHTML = showPicker
      ? `<button data-month="-1" ${state.month === 0 ? 'disabled' : ''} aria-label="Mes anterior">‹</button><strong>${monthName(state.month)}</strong><button data-month="1" ${state.month === LAST ? 'disabled' : ''} aria-label="Mes siguiente">›</button>`
      : ''
    $('#people').innerHTML = D.household.members.map((m, i) => `<span style="background:${['#0f766e', '#db2777'][i % 2]}" title="${esc(m)}">${esc(m[0])}</span>`).join('')
  }

  /* ---------- Este mes ---------- */
  function viewMes() {
    const i = state.month
    const s = spent(i), prev = i > 0 ? spent(i - 1) : 0, avg = avgSpent(i)
    const inc = income(i), sv = saved(i)
    const rate = inc ? Math.round((sv / inc) * 100) : 0
    const segs = segments(i)
    const top = segs[0]
    const cur = cumulative(i)
    const last = i > 0 ? cumulative(i - 1) : []
    const n = Math.max(cur.length, last.length)
    const changes = D.categories
      .map((c) => ({ c, now: byCat(i)[c.id] || 0, avg: avgCat(c.id, i) }))
      .filter((x) => x.avg > 2000 || x.now > 2000)
      .map((x) => ({ ...x, diff: x.now - x.avg }))
      .sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff))
      .slice(0, 4)
    const uc = uncategorized().filter((t) => t.date.startsWith(D.months[i].key))

    return `
      ${uc.length ? `<div class="alert">🏷️ <span><strong>${uc.length} movimientos sin categoría</strong> este mes. Clasificarlos mejora los gráficos.</span><span class="spacer"></span><a class="btn" href="#movimientos" data-uncat="1">Clasificar</a></div>` : ''}
      <div class="grid g3">
        <div class="card hero kpi"><div class="label">Habéis gastado en ${D.months[i].short}</div><div class="value">${fmt0(s)}</div><div class="delta">${i > 0 ? delta(s, prev) : ''}</div><div class="small muted" style="margin-top:6px">Vuestra media: ${fmt0(avg)}/mes</div></div>
        <div class="card kpi"><div class="label">Habéis ahorrado</div><div class="value ${sv < 0 ? 'neg' : 'pos'}">${fmt0(sv)}</div><div class="delta"><span class="pill ${rate >= 20 ? 'down' : rate >= 0 ? 'neutral' : 'up'}">${rate} % de lo que entra</span></div><div class="small muted" style="margin-top:6px">Entró ${fmt0(inc)} · ${D.household.members.join(' y ')}</div></div>
        <div class="card kpi"><div class="label">Donde más se va</div><div class="value">${top ? `${CAT[top.id]?.icon || '❔'} ${fmt0(top.value)}` : '—'}</div><div class="delta muted">${top ? `${esc(CAT[top.id]?.name || 'Sin categoría')} · ${Math.round((top.value / s) * 100)} % del gasto` : ''}</div></div>
      </div>

      <div class="grid g12" style="margin-top:16px">
        <div class="card"><h2>¿En qué se ha ido?</h2>${C.donut(segs, { title: fmt0(s), subtitle: `${segs.length} categorías` })}
          <div class="catlist" style="margin-top:14px">${segs.slice(0, 5).map((g) => catRow(g.id, g.value, s)).join('')}</div>
          <p style="margin:10px 0 0"><a href="#gastos">Ver todas las categorías →</a></p></div>
        <div class="card"><h2>Ritmo de gasto del mes</h2>
          ${C.lines([
            { points: last.concat(Array(Math.max(0, n - last.length)).fill(null)), color: '#94a3b8', label: `Mes anterior: ${fmt(prev)}`, dashed: true },
            { points: cur.concat(Array(Math.max(0, n - cur.length)).fill(null)), color: '#0f766e', label: `Este mes: ${fmt(s)}`, area: true },
          ], { xLabels: [[0, '1'], [9, '10'], [19, '20'], [n - 1, String(n)]], fmt: fmt0, budget: totalBudget() })}
          <div class="legend"><span><i style="background:#0f766e"></i>Este mes</span><span><i class="dash" style="border-color:#94a3b8"></i>Mes anterior</span><span><i class="dash" style="border-color:#94a3b8"></i>Presupuesto total</span></div>
          <h2 style="margin-top:20px">Lo que más ha cambiado frente a vuestra media</h2>
          <div class="catlist">${changes.map((x) => `<div class="cat" data-cat="${x.c.id}"><span class="ic">${x.c.icon}</span><div><div class="name"><span>${esc(x.c.name)}</span><span class="${x.diff > 0 ? 'neg' : 'pos'}">${x.diff > 0 ? '+' : '−'}${fmt0(Math.abs(x.diff))}</span></div><div class="small muted">${fmt0(x.now)} este mes · media ${fmt0(x.avg)}</div></div><span></span></div>`).join('')}</div>
        </div>
      </div>

      <div class="card" style="margin-top:16px"><h2>Presupuestos del mes</h2>
        <div class="grid g2">${Object.entries(D.budgets).map(([id, lim]) => budgetRow(id, byCat(i)[id] || 0, lim)).join('')}</div>
      </div>`
  }

  function catRow(id, value, total) {
    const c = CAT[id] || { icon: '❔', name: 'Sin categoría', color: '#cbd5e1' }
    return `<div class="cat ${state.cat === id ? 'active' : ''}" data-cat="${id}"><span class="ic">${c.icon}</span><div><div class="name"><span>${esc(c.name)}</span><strong class="num">${fmt(value)}</strong></div><div class="track"><i style="width:${Math.max(2, (value / total) * 100)}%;background:${c.color}"></i></div></div><span class="small muted num">${Math.round((value / total) * 100)} %</span></div>`
  }

  function budgetRow(id, value, lim) {
    const c = CAT[id]
    const p = Math.round((value / lim) * 100)
    const color = p > 100 ? '#c2410c' : p > 85 ? '#d97706' : c.color
    return `<div class="cat" data-cat="${id}"><span class="ic">${c.icon}</span><div><div class="name"><span>${esc(c.name)}</span><span class="small ${p > 100 ? 'neg' : 'muted'}">${fmt0(value)} de ${fmt0(lim)}</span></div><div class="track"><i style="width:${Math.min(p, 100)}%;background:${color}"></i></div></div><span class="small num ${p > 100 ? 'neg' : 'muted'}">${p} %</span></div>`
  }

  /* ---------- ¿En qué gastamos? ---------- */
  function viewGastos() {
    const i = state.month
    const s = spent(i)
    const segs = segments(i)
    const sel = state.cat && (byCat(i)[state.cat] || avgCat(state.cat, i)) ? state.cat : segs[0]?.id
    const c = CAT[sel] || { name: 'Sin categoría', icon: '❔', color: '#94a3b8' }
    const series = D.months.map((m, k) => ({ label: m.short, value: byCat(k)[sel] || 0, color: c.color }))
    const avg = avgCat(sel, i)
    const tx = inMonth(i).filter((t) => isExpense(t) && (t.category || 'sin') === sel)
    const merchants = {}
    for (const t of state.txns.filter((t) => isExpense(t) && (t.category || 'sin') === sel && D.months.slice(Math.max(0, i - 2), i + 1).some((m) => t.date.startsWith(m.key)))) {
      const m = merchant(t.desc)
      merchants[m] = (merchants[m] || 0) - t.amount
    }
    const topM = Object.entries(merchants).sort((a, b) => b[1] - a[1]).slice(0, 5)
    const maxM = topM[0]?.[1] || 1

    return `<h1>¿En qué gastamos?</h1><p class="lead">Pulsa una categoría para ver su detalle.</p>
      <div class="grid g12">
        <div class="card">${C.donut(segs, { title: fmt0(s), subtitle: monthName(i), active: sel })}
          <div class="catlist" style="margin-top:14px">${segs.map((g) => catRow(g.id, g.value, s)).join('')}</div></div>
        <div class="grid" style="align-content:start">
          <div class="card"><h2>${c.icon} ${esc(c.name)} · últimos 12 meses</h2>
            ${C.bars(series, { fmt: fmt0, ref: avg, refLabel: `Media ${fmt0(avg)}`, highlight: i })}
            <p class="small muted" style="margin:8px 0 0">Este mes: <strong>${fmt(byCat(i)[sel] || 0)}</strong> · ${delta(byCat(i)[sel] || 0, avg, { suffix: 'que la media' })}</p></div>
          <div class="card"><h2>Dónde (últimos 3 meses)</h2>
            ${topM.map(([m, v]) => `<div style="margin-bottom:8px"><div class="name" style="display:flex;justify-content:space-between"><span>${esc(m)}</span><span class="num">${fmt(v)}</span></div><div class="track"><i style="width:${(v / maxM) * 100}%;background:${c.color}"></i></div></div>`).join('') || '<p class="muted">Sin datos.</p>'}</div>
          <div class="card"><h2>Movimientos de ${D.months[i].short}</h2>${txTable(tx, true)}</div>
        </div>
      </div>`
  }

  /* ---------- Evolución ---------- */
  function viewEvolucion() {
    const totals = D.categories.map((c) => ({ c, v: sum(D.months.map((_, k) => byCat(k)[c.id] || 0)) })).sort((a, b) => b.v - a.v)
    const main = totals.slice(0, 6).map((x) => x.c.id)
    const rows = D.months.map((m, k) => {
      const bc = byCat(k)
      const rest = sum(Object.entries(bc).filter(([id]) => !main.includes(id)).map(([, v]) => v))
      return { label: m.short, parts: main.map((id) => ({ value: bc[id] || 0, color: CAT[id].color, label: CAT[id].name })).concat([{ value: rest, color: '#cbd5e1', label: 'Resto' }]) }
    })
    const savings = D.months.map((m, k) => ({ label: m.short, value: saved(k), color: '#16a34a' }))
    const totalSaved = sum(savings.map((x) => x.value))
    const totalInc = sum(D.months.map((_, k) => income(k)))
    const best = savings.reduce((a, b) => (b.value > a.value ? b : a))
    const worst = savings.reduce((a, b) => (b.value < a.value ? b : a))
    const spentY = sum(D.months.map((_, k) => spent(k)))

    return `<h1>Evolución</h1><p class="lead">Los últimos 12 meses de un vistazo.</p>
      <div class="grid g3">
        <div class="card hero kpi"><div class="label">Ahorrado en 12 meses</div><div class="value">${fmt0(totalSaved)}</div><div class="small muted">${Math.round((totalSaved / totalInc) * 100)} % de todo lo que entró</div></div>
        <div class="card kpi"><div class="label">Gasto medio al mes</div><div class="value">${fmt0(spentY / 12)}</div><div class="small muted">${fmt0(spentY)} en el año</div></div>
        <div class="card kpi"><div class="label">Mejor y peor mes</div><div class="value" style="font-size:22px"><span class="pos">${best.label} ${fmt0(best.value)}</span></div><div class="small"><span class="neg">${worst.label} ${fmt0(worst.value)}</span> <span class="muted">(${worst.value < 0 ? 'gastasteis más de lo que entró' : 'el que menos'})</span></div></div>
      </div>
      <div class="card" style="margin-top:16px"><h2>Gasto mensual por categoría</h2>${C.stacked(rows, { fmt: fmt0 })}
        <div class="legend">${main.map((id) => `<span><i style="background:${CAT[id].color}"></i>${esc(CAT[id].name)}</span>`).join('')}<span><i style="background:#cbd5e1"></i>Resto</span></div></div>
      <div class="card" style="margin-top:16px"><h2>Ahorro de cada mes</h2>${C.bars(savings, { fmt: fmt0, ref: Math.round(totalSaved / 12), refLabel: `Media ${fmt0(totalSaved / 12)}` })}
        <p class="small muted" style="margin:8px 0 0">Ahorro = lo que entra en la cuenta común − lo que se gasta. El traspaso a la cuenta de ahorro cuenta como ahorro, no como gasto.</p></div>`
  }

  /* ---------- Ahorrar ---------- */
  function addMonths(n) {
    const d = new Date(D.months[LAST].y, D.months[LAST].m + n, 1)
    return d.toLocaleDateString('es-ES', { month: 'long', year: 'numeric' })
  }

  function insights() {
    const out = []
    const subs = {}
    for (const t of state.txns.filter((t) => t.recurring)) (subs[t.recurring] ||= []).push(t)
    const subNow = Object.entries(subs).map(([name, ts]) => {
      const sorted = ts.slice().sort((a, b) => a.date.localeCompare(b.date))
      return { name, first: -sorted[0].amount, now: -sorted[sorted.length - 1].amount, since: sorted[0].date }
    })
    const subTotal = sum(subNow.map((s) => s.now))
    const raised = subNow.filter((s) => s.now > s.first)
    out.push({ ic: '📺', title: `Pagáis ${fmt(subTotal)} al mes en cuotas fijas`, text: `${subNow.map((s) => s.name).join(', ')}. ${raised.length ? `Han subido: ${raised.map((s) => `${s.name} (${fmt(s.first)} → ${fmt(s.now)})`).join(', ')}.` : ''} Quitar una plataforma de vídeo ahorraría:`, save: Math.min(...subNow.filter((s) => ['Netflix', 'Disney+'].includes(s.name)).map((s) => s.now)) * 12 })

    const rAvg = avgCat('restaurantes', LAST + 1)
    out.push({ ic: '🍽️', title: `Restaurantes y comida a domicilio: ${fmt0(rAvg)} al mes de media`, text: 'Cambiar una cena fuera a la semana por cocinar en casa (≈ −25 %) supone:', save: Math.round(rAvg * 0.25) * 12 })

    const sAvg = avgCat('super', LAST + 1)
    const tickets = Math.round(state.txns.filter((t) => t.category === 'super').length / 12)
    out.push({ ic: '🛒', title: `${tickets} compras de supermercado al mes (${fmt0(sAvg)})`, text: 'Planificar una compra semanal con lista suele recortar en torno a un 10 %:', save: Math.round(sAvg * 0.1) * 12 })

    const luz = state.txns.filter((t) => /IBERDROLA/.test(t.desc))
    const luzMax = Math.max(...luz.map((t) => -t.amount)), luzMin = Math.min(...luz.map((t) => -t.amount))
    out.push({ ic: '💡', title: `La luz va de ${fmt0(luzMin)} a ${fmt0(luzMax)} según la época`, text: 'Revisar la potencia contratada y la tarifa por tramos puede rebajar ≈ 15 %:', save: Math.round((sum(luz.map((t) => -t.amount)) / luz.length) * 0.15) * 12 })
    return out
  }

  function viewAhorrar() {
    const avgSaved = Math.round(sum(D.months.map((_, k) => saved(k))) / 12)
    const ins = insights()
    const simCats = Object.keys(state.sim)
    const extra = sum(simCats.map((id) => Math.round((avgCat(id, LAST + 1) * state.sim[id]) / 100)))
    const g = D.goals[0]
    const etaNow = Math.ceil((g.target - g.saved) / g.monthly)
    const etaSim = Math.ceil((g.target - g.saved) / (g.monthly + extra))

    return `<h1>Ahorrar</h1><p class="lead">Ahorráis de media <strong>${fmt0(avgSaved)}</strong> al mes. Aquí tenéis vuestros objetivos e ideas calculadas con vuestros propios gastos.</p>
      <div class="grid g2">${D.goals.map((goal) => {
        const p = (goal.saved / goal.target) * 100
        const eta = Math.ceil((goal.target - goal.saved) / goal.monthly)
        return `<div class="card goal">${C.ring(p, { label: goal.name })}<div><h2 style="margin:0">${goal.icon} ${esc(goal.name)}</h2><div><strong>${fmt0(goal.saved)}</strong> <span class="muted">de ${fmt0(goal.target)}</span></div><div class="small muted">Apartando ${fmt0(goal.monthly)}/mes lo alcanzáis en <strong>${addMonths(eta)}</strong>${goal.deadline ? ` · objetivo ${goal.deadline}` : ''}</div></div></div>`
      }).join('')}</div>

      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h2>Ideas para ahorrar</h2>
          ${ins.map((x) => `<div class="insight"><span class="ic">${x.ic}</span><div><strong>${esc(x.title)}</strong><span class="small muted">${esc(x.text)}</span></div><span class="save">${fmt0(x.save)}/año</span></div>`).join('')}
          <p class="small muted">Las cifras salen de vuestros movimientos; los porcentajes de mejora son estimaciones orientativas.</p></div>
        <div class="card"><h2>Simulador: ¿y si recortamos…?</h2>
          ${simCats.map((id) => `<div class="sim-row"><span>${CAT[id].icon}</span><span>${esc(CAT[id].name)}<div class="small muted">media ${fmt0(avgCat(id, LAST + 1))}/mes</div></span><input type="range" min="0" max="50" step="5" value="${state.sim[id]}" data-sim="${id}" aria-label="Recorte en ${esc(CAT[id].name)}" /><span class="num"><strong>${state.sim[id]} %</strong></span><span class="num pos">+${fmt0((avgCat(id, LAST + 1) * state.sim[id]) / 100)}/mes</span></div>`).join('')}
          <div class="sim-total"><div><div class="small muted">Ahorro extra</div><strong>${fmt0(extra)}/mes · ${fmt0(extra * 12)}/año</strong></div>
            <div class="small">${g.icon} ${esc(g.name)}: <strong>${addMonths(etaSim)}</strong><br><span class="muted">en vez de ${addMonths(etaNow)}${etaNow - etaSim > 0 ? ` (${etaNow - etaSim} meses antes)` : ''}</span></div></div>
        </div>
      </div>`
  }

  /* ---------- Movimientos ---------- */
  function catSelect(t) {
    return `<select class="catsel ${t.category ? '' : 'empty'}" data-tx="${t.id}" aria-label="Categoría"><option value="">🏷️ Sin categoría</option>${D.categories.map((c) => `<option value="${c.id}" ${t.category === c.id ? 'selected' : ''}>${c.icon} ${esc(c.name)}</option>`).join('')}</select>`
  }

  function txTable(list, compact) {
    if (!list.length) return '<p class="muted">No hay movimientos.</p>'
    return `<table><thead><tr><th>Fecha</th><th>Concepto</th>${compact ? '' : '<th>Categoría</th>'}<th class="num">Importe</th></tr></thead><tbody>
      ${list.map((t) => `<tr><td class="muted small">${dateLabel(t.date)}</td><td>${esc(merchant(t.desc))}<div class="small muted">${esc(t.desc)}</div></td>${compact ? '' : `<td>${t.income ? `<span class="tag">Aportación de ${esc(t.who)}</span>` : t.savings ? '<span class="tag">Traspaso a ahorro</span>' : catSelect(t)}</td>`}<td class="num ${t.amount < 0 ? '' : 'pos'}">${t.amount > 0 ? '+' : ''}${fmt(t.amount)}</td></tr>`).join('')}
    </tbody></table>`
  }

  function viewMovimientos() {
    let list = inMonth(state.month)
    if (state.onlyUncat) list = uncategorized()
    if (state.q) list = list.filter((t) => t.desc.toLowerCase().includes(state.q.toLowerCase()))
    const n = uncategorized().length
    return `<h1>Movimientos</h1><p class="lead">Cambia la categoría directamente en la tabla; OpenFinance aprende la regla para los siguientes.</p>
      <div class="card"><div class="toolbar">
        <input type="search" id="q" class="field" placeholder="Buscar…" value="${esc(state.q)}" style="width:260px" />
        <label class="small"><input type="checkbox" id="only-uncat" ${state.onlyUncat ? 'checked' : ''}/> Solo sin categoría (${n})</label>
        <span style="flex:1"></span>${state.rules.length ? `<span class="small muted">${state.rules.length} regla${state.rules.length > 1 ? 's' : ''} aprendida${state.rules.length > 1 ? 's' : ''}</span>` : ''}
      </div>${txTable(list, false)}</div>`
  }

  function setCategory(id, cat) {
    const t = state.txns.find((x) => x.id === id)
    t.category = cat || null
    const m = merchant(t.desc)
    const same = state.txns.filter((x) => x.id !== id && !x.category && !x.income && !x.savings && merchant(x.desc) === m)
    if (cat) {
      state.rules.push({ merchant: m, category: cat })
      same.forEach((x) => (x.category = cat))
      toast(`Regla guardada: «${m}» → ${CAT[cat].name}${same.length ? ` · ${same.length} más clasificados` : ''}`)
    }
    render()
  }

  /* ---------- Importar ---------- */
  function viewImportar() {
    const s = state.importStep
    const steps = ['Subir CSV', 'Revisar', 'Listo'].map((l, k) => `<div class="step ${k + 1 === s ? 'on' : k + 1 < s ? 'done' : ''}">${k + 1 < s ? '✓' : k + 1}. ${l}</div>`).join('')
    let body
    if (s === 1) {
      body = `<div class="dropzone"><p style="font-size:34px;margin:0">📄</p><p>Descarga los movimientos de la web de ${esc(D.household.bank)} en CSV y arrástralos aquí</p><button class="btn primary" data-import="2">Usar «movimientos-noviembre.csv» de ejemplo</button><p class="small muted">El archivo se procesa en vuestro equipo; no sale a ningún servicio externo.</p></div>`
    } else if (s === 2) {
      const rows = [
        ['2026-11-01', 'RECIBO HIPOTECA PRESTAMO 0042', -72000, 'vivienda', 'nuevo'],
        ['2026-11-02', 'MERCADONA 1234', -6420, 'super', 'nuevo'],
        ['2026-11-02', 'NETFLIX.COM', -1799, 'suscripciones', 'nuevo'],
        ['2026-11-03', 'FERRETERIA PEPE', -1850, null, 'nuevo'],
        ['2026-10-29', 'BIZUM A LUCIA CENA', -2250, null, 'duplicado'],
      ]
      body = `<div class="card"><h2>5 filas · 4 nuevas · 1 ya estaba</h2><table><thead><tr><th>Fecha</th><th>Concepto</th><th>Categoría propuesta</th><th class="num">Importe</th><th></th></tr></thead><tbody>
        ${rows.map(([d, desc, a, c, st]) => `<tr style="${st === 'duplicado' ? 'opacity:.5' : ''}"><td class="small muted">${dateLabel(d)}</td><td>${esc(desc)}</td><td>${c ? `${CAT[c].icon} ${esc(CAT[c].name)} <span class="tag">regla</span>` : '<span class="tag">sin categoría</span>'}</td><td class="num">${fmt(a)}</td><td>${st === 'duplicado' ? '<span class="tag">ya importado · se omite</span>' : ''}</td></tr>`).join('')}
        </tbody></table><div class="toolbar" style="margin-top:12px"><button class="btn" data-import="1">Atrás</button><span style="flex:1"></span><button class="btn primary" data-import="3">Importar 4 movimientos</button></div></div>`
    } else {
      body = `<div class="card"><h2>✓ Importados 4 movimientos</h2><p>3 se han clasificado solos con vuestras reglas; 1 queda sin categoría. Volver a importar el mismo archivo no crea duplicados.</p><a class="btn" href="#movimientos">Ver movimientos</a> <button class="btn" data-import="1">Importar otro</button></div>`
    }
    return `<h1>Importar movimientos</h1><p class="lead">De momento, a mano: un CSV del banco cuando queráis. La conexión automática con el banco llegará más adelante.</p><div class="steps">${steps}</div>${body}`
  }

  /* ---------- render y eventos ---------- */
  const VIEWS = { mes: viewMes, gastos: viewGastos, evolucion: viewEvolucion, ahorrar: viewAhorrar, movimientos: viewMovimientos, importar: viewImportar }

  function render() {
    renderTop()
    $('#view').innerHTML = VIEWS[route()]()
  }

  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-month],[data-cat],[data-import],[data-uncat]')
    if (!el) return
    if (el.dataset.month) {
      state.month = Math.min(LAST, Math.max(0, state.month + Number(el.dataset.month)))
      return render()
    }
    if (el.dataset.cat) {
      state.cat = el.dataset.cat
      if (route() !== 'gastos') location.hash = 'gastos'
      else render()
      return
    }
    if (el.dataset.import) {
      state.importStep = Number(el.dataset.import)
      if (state.importStep === 3) toast('Importación registrada')
      return render()
    }
    if (el.dataset.uncat) state.onlyUncat = true
  })

  document.addEventListener('change', (e) => {
    const t = e.target
    if (t.dataset.tx) return setCategory(t.dataset.tx, t.value)
    if (t.id === 'only-uncat') { state.onlyUncat = t.checked; render() }
  })

  document.addEventListener('input', (e) => {
    const t = e.target
    if (t.dataset.sim) {
      state.sim[t.dataset.sim] = Number(t.value)
      render()
      document.querySelector(`[data-sim="${t.dataset.sim}"]`)?.focus()
    }
    if (t.id === 'q') {
      state.q = t.value
      const pos = t.selectionStart
      render()
      const q = $('#q')
      q.focus()
      q.setSelectionRange(pos, pos)
    }
  })

  window.addEventListener('hashchange', () => { render(); window.scrollTo(0, 0) })
  render()
})()
