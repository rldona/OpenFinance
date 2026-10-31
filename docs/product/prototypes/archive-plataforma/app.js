(() => {
  'use strict'

  const D = window.OF_DATA
  const clone = (x) => JSON.parse(JSON.stringify(x))

  const state = {
    role: 'owner',
    ws: 'familia',
    proposals: clone(D.proposals),
    transactions: clone(D.transactions),
    modules: clone(D.modules),
    audit: clone(D.audit),
    sharing: clone(D.sharing),
    shareForm: null,
    importStep: 1,
    chat: [],
    runSeq: 41,
    lastRun: null,
  }

  /* ---------- utilidades ---------- */
  const eur = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' })
  const fmt = (cents) => eur.format(cents / 100)
  const signed = (cents) => `<span class="num ${cents < 0 ? 'neg' : 'pos'}">${cents > 0 ? '+' : ''}${fmt(cents)}</span>`
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
  const $ = (sel) => document.querySelector(sel)
  const fmtDate = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
  const now = () => new Date().toISOString().slice(0, 16).replace('T', ' ')

  const user = () => D.users[state.role]
  const canWrite = () => state.role !== 'viewer'
  const canApprove = () => state.role !== 'viewer'
  const isOwner = () => state.role === 'owner'

  const accounts = () => D.accounts[state.ws].filter((a) => !a.restrictedTo || a.restrictedTo.includes(user().id))
  const accountIds = () => new Set(accounts().map((a) => a.id))
  const txns = () => state.transactions[state.ws].filter((t) => accountIds().has(t.account))
  const accountName = (id) => (D.accounts[state.ws].find((a) => a.id === id) || {}).name || '—'
  const pending = () => state.proposals.filter((p) => p.ws === state.ws && p.status === 'pending_approval')
  const curWs = () => D.workspaces.find((w) => w.id === state.ws)

  function toast(msg) {
    const el = $('#toast')
    el.textContent = msg
    el.classList.add('show')
    clearTimeout(toast.t)
    toast.t = setTimeout(() => el.classList.remove('show'), 2600)
  }

  function audit(action, target, actor = user().name) {
    state.audit.unshift({ at: now(), actor, action, target })
  }

  /* ---------- navegación ---------- */
  const NAV = [
    { group: 'Finanzas', items: [['dashboard', 'Resumen'], ['sharing', 'Reparto'], ['transactions', 'Movimientos'], ['import', 'Importar'], ['budgets', 'Presupuestos']] },
    { group: 'Manager', items: [['manager', 'Asistente'], ['approvals', 'Aprobaciones']] },
    { group: 'Plataforma', items: [['workspace', 'Workspace y miembros'], ['modules', 'Módulos y proveedores'], ['audit', 'Auditoría']] },
  ]
  const route = () => (location.hash.slice(1) || 'dashboard')

  function renderChrome() {
    const ws = $('#ws-switch')
    ws.innerHTML = D.workspaces
      .filter((w) => !w.onlyFor || w.onlyFor.includes(user().id))
      .map((w) => `<option value="${w.id}" ${w.id === state.ws ? 'selected' : ''}>${esc(w.name)} · ${w.kind}</option>`)
      .join('')

    const n = pending().length
    $('#nav').innerHTML = NAV.map(
      (g) => `<div class="nav-group"><h4>${g.group}</h4>${g.items
        .filter(([id]) => id !== 'sharing' || curWs().sharing)
        .map(([id, label]) => `<a href="#${id}" class="${route() === id ? 'active' : ''}">${label}${id === 'approvals' && n ? `<span class="badge">${n}</span>` : ''}</a>`)
        .join('')}</div>`,
    ).join('')

    const u = user()
    $('#me').innerHTML = `<div class="avatar" style="background:${u.color}">${u.initials}</div><div><div>${esc(u.name)}</div><div class="small muted">${u.role}</div></div>`
  }

  const head = (title, sub, actions = '') =>
    `<div class="page-head"><div><h1>${title}</h1>${sub ? `<p>${sub}</p>` : ''}</div><div class="row">${actions}</div></div>`

  /* ---------- vistas ---------- */
  const views = {}

  views.dashboard = () => {
    const ts = txns()
    const real = ts.filter((t) => !t.transfer && !t.contribution)
    const income = real.filter((t) => t.amount > 0).reduce((s, t) => s + t.amount, 0)
    const spend = real.filter((t) => t.amount < 0).reduce((s, t) => s + (t.expense ? -myShareOf(t.shared, t.expense) : t.amount), 0)
    const worth = accounts().reduce((s, a) => s + a.balance, 0)
    const saving = income ? Math.round(((income + spend) / income) * 100) : 0
    const max = Math.max(...D.monthly.flatMap((m) => [m.in, m.out]))
    const p = pending()

    return `${head('Resumen', `${esc(D.workspaces.find((w) => w.id === state.ws).name)} · octubre 2026`, `<a class="btn" href="#import">Importar movimientos</a><a class="btn primary" href="#manager">Preguntar al Manager</a>`)}
      <div class="grid g4">
        <div class="card kpi"><div class="label">Patrimonio neto</div><div class="value">${fmt(worth)}</div><div class="delta muted">${accounts().length} cuentas visibles para ti</div></div>
        <div class="card kpi"><div class="label">Ingresos del mes</div><div class="value pos">${fmt(income)}</div><div class="delta muted">Sin transferencias internas</div></div>
        <div class="card kpi"><div class="label">Gastos del mes</div><div class="value neg">${fmt(-spend)}</div><div class="delta muted">${state.ws === 'personal' ? 'Solo tu parte de los gastos compartidos' : 'Sin transferencias internas'}</div></div>
        <div class="card kpi"><div class="label">Tasa de ahorro</div><div class="value">${saving} %</div><div class="delta muted">Calculada por el Core</div></div>
      </div>
      ${p.length ? `<div class="card" style="margin-top:16px;border-color:#ddd0fb;background:var(--ai-soft)"><div class="row"><span class="chip ai">Manager</span><strong>${p.length} propuesta${p.length > 1 ? 's' : ''} esperando tu revisión</strong><span class="spacer"></span><a class="btn" href="#approvals">Revisar</a></div></div>` : ''}
      ${sharedProfilesCard()}
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h3>Ingresos y gastos · 6 meses</h3>
          <div class="chart">${D.monthly.map((m) => `<div class="col"><div class="pair"><i class="in" style="height:${(m.in / max) * 100}%" title="Ingresos ${fmt(m.in)}"></i><i class="out" style="height:${(m.out / max) * 100}%" title="Gastos ${fmt(m.out)}"></i></div><span class="small muted">${m.m}</span></div>`).join('')}</div>
          <div class="row small muted" style="margin-top:8px"><span class="chip" style="background:#86c9bf;border:0">&nbsp;</span>Ingresos <span class="chip" style="background:#e4a39b;border:0">&nbsp;</span>Gastos</div>
        </div>
        <div class="card"><h3>Cuentas</h3><table>${accounts().map((a) => `<tr><td>${esc(a.name)}<div class="small muted">${esc(a.bank)} · ${a.type}${a.restrictedTo ? ' · 🔒 acceso restringido' : ''}</div></td><td class="num">${fmt(a.balance)}</td></tr>`).join('')}</table>
          ${state.ws === 'familia' && state.role !== 'editor' ? '<p class="small muted">Hay cuentas del workspace que no se comparten contigo.</p>' : ''}
        </div>
      </div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h3>Últimos movimientos</h3>${txTable(ts.slice(0, 6), true)}<p><a href="#transactions">Ver todos →</a></p></div>
        <div class="card"><h3>Presupuestos</h3>${budgetBars()}</div>
      </div>`
  }

  function catChip(t) {
    if (t.transfer) return `<span class="chip transfer">⇄ Transferencia · ${esc(accountName(t.transfer))}</span>`
    if (t.contribution && t.shared) return `<span class="chip transfer">🤝 Aportación a ${esc(wsShort(t.shared))}</span>`
    if (t.contribution) return `<span class="chip transfer">🤝 ${esc(t.category)}</span>`
    if (t.expense) return `<span class="chip ai">🤝 ${esc(wsShort(t.shared))} · tu parte ${fmt(myShareOf(t.shared, t.expense))}</span>`
    if (!t.category) return '<span class="chip warn">Sin categoría</span>'
    return `<span class="chip">${esc(t.category)}</span>`
  }

  function txTable(list, compact) {
    if (!list.length) return '<p class="muted">Sin resultados.</p>'
    return `<table><thead><tr><th>Fecha</th><th>Descripción</th>${compact ? '' : '<th>Cuenta</th>'}<th>Categoría</th>${compact ? '' : '<th>Origen</th>'}<th class="num">Importe</th></tr></thead><tbody>
      ${list.map((t) => `<tr><td class="muted">${fmtDate(t.date)}</td><td>${esc(t.desc)}${compact ? '' : `<div class="small muted">${esc(t.merchant)}</div>`}</td>${compact ? '' : `<td class="small">${esc(accountName(t.account))}</td>`}<td>${catChip(t)}</td>${compact ? '' : `<td class="small muted">${t.source}</td>`}<td>${signed(t.amount)}</td></tr>`).join('')}
    </tbody></table>`
  }

  function spentBy(category) {
    if (curWs().sharing) return state.sharing[state.ws].expenses.filter((e) => e.category === category).reduce((s, e) => s + e.amount, 0)
    return -txns().filter((t) => t.category === category && t.amount < 0).reduce((s, t) => s + t.amount, 0)
  }

  function budgetBars() {
    return D.budgets[state.ws].map((b) => {
      const spent = spentBy(b.category)
      const pct = Math.round((spent / b.limit) * 100)
      return `<div class="budget"><div class="row"><span>${esc(b.category)}</span><span class="spacer"></span><span class="small ${pct > 100 ? 'neg' : 'muted'}">${fmt(spent)} de ${fmt(b.limit)} · ${pct} %</span></div><div class="bar ${pct > 100 ? 'over' : ''}"><i style="width:${Math.min(pct, 100)}%"></i></div></div>`
    }).join('')
  }

  views.transactions = () => {
    const q = (state.q || '').toLowerCase()
    const f = state.filter || 'all'
    let list = txns()
    if (q) list = list.filter((t) => (t.desc + t.merchant + (t.category || '')).toLowerCase().includes(q))
    if (f === 'uncat') list = list.filter((t) => !t.category && !t.transfer)
    if (f === 'transfer') list = list.filter((t) => t.transfer)
    const uncat = txns().filter((t) => !t.category && !t.transfer).length
    return `${head('Movimientos', 'Las transferencias internas se enlazan entre cuentas y no cuentan como ingreso ni gasto.', canWrite() ? '<button class="btn" disabled title="Fuera del prototipo">Nuevo movimiento</button>' : '')}
      <div class="card">
        <div class="row" style="margin-bottom:12px">
          <input type="search" id="q" placeholder="Buscar descripción, comercio o categoría" value="${esc(state.q || '')}" style="width:320px" />
          <select class="field" id="filter">
            <option value="all" ${f === 'all' ? 'selected' : ''}>Todos</option>
            <option value="uncat" ${f === 'uncat' ? 'selected' : ''}>Sin categoría (${uncat})</option>
            <option value="transfer" ${f === 'transfer' ? 'selected' : ''}>Transferencias internas</option>
          </select>
          <span class="spacer"></span>
          ${uncat ? `<button class="btn" data-ask="Categoriza los movimientos sin categoría">✨ Pedir al Manager que categorice ${uncat}</button>` : ''}
        </div>
        ${txTable(list, false)}
      </div>`
  }

  views.import = () => {
    const s = state.importStep
    const steps = ['Archivo', 'Columnas', 'Vista previa', 'Confirmado']
      .map((l, i) => `<div class="step ${i + 1 === s ? 'on' : i + 1 < s ? 'done' : ''}">${i + 1 < s ? '✓' : i + 1}. ${l}</div>`)
      .join('')
    if (!canWrite()) {
      return `${head('Importar movimientos', '')}<div class="guard">Tu rol (viewer) no permite importar. Pide a un owner o editor del workspace que lo haga.</div>`
    }
    let body = ''
    if (s === 1) {
      body = `<div class="dropzone"><p style="font-size:28px;margin:0">📄</p><p>Arrastra un CSV de tu banco o</p><button class="btn primary" data-import="2">Usar «octubre-banco-norte.csv» de ejemplo</button><p class="small">El archivo se procesa en tu instalación. Nada sale a servicios externos.</p></div>`
    } else if (s === 2) {
      const cols = [['Fecha operación', 'Fecha efectiva'], ['Concepto', 'Descripción'], ['Importe', 'Importe (signo = sentido)'], ['Divisa', 'Moneda'], ['Referencia', 'ID externo (deduplicación)']]
      body = `<div class="card"><h3>Mapeo de columnas · destino: Tarjeta familiar</h3><table><thead><tr><th>Columna del CSV</th><th>Campo de OpenFinance</th><th>Ejemplo</th></tr></thead><tbody>
        ${cols.map(([c, f], i) => `<tr><td class="mono">${c}</td><td><select class="field"><option>${f}</option><option>Ignorar</option></select></td><td class="small muted">${['31/10/2026', 'AMAZON EU SARL', '-23,99', 'EUR', 'BN-88213'][i]}</td></tr>`).join('')}
        </tbody></table><p class="small muted">Formato decimal detectado: coma. Los importes se leen como texto y se convierten a decimal exacto, nunca a float.</p>
        <div class="row"><button class="btn" data-import="1">Atrás</button><span class="spacer"></span><button class="btn primary" data-import="3">Ver vista previa</button></div></div>`
    } else if (s === 3) {
      const rows = D.importPreview
      const nNew = rows.filter((r) => r.status !== 'dup').length
      body = `<div class="card"><h3>Vista previa · ${rows.length} filas</h3><table><thead><tr><th>Fecha</th><th>Descripción</th><th class="num">Importe</th><th>Resultado</th></tr></thead><tbody>
        ${rows.map((r) => `<tr class="${r.status === 'dup' ? 'dup' : ''}"><td class="muted">${fmtDate(r.date)}</td><td>${esc(r.desc)}</td><td>${signed(r.amount)}</td><td>${r.status === 'dup' ? `<span class="chip warn">Duplicado · se omite</span>` : r.status === 'warn' ? '<span class="chip bad">Nuevo · texto sospechoso</span>' : '<span class="chip ok">Nuevo</span>'}${r.note ? `<div class="small muted">${esc(r.note)}</div>` : ''}</td></tr>`).join('')}
        </tbody></table>
        <div class="row" style="margin-top:12px"><button class="btn" data-import="2">Atrás</button><span class="spacer"></span><span class="muted">${nNew} nuevos · ${rows.length - nNew} duplicados omitidos</span><button class="btn primary" data-import="4">Confirmar importación</button></div></div>`
    } else {
      body = `<div class="card"><h3>✓ Importación confirmada</h3><p>4 movimientos nuevos registrados con procedencia <span class="mono">import:octubre-banco-norte.csv</span>. 2 duplicados omitidos. Repetir esta importación no creará duplicados.</p><div class="row"><a class="btn" href="#transactions">Ver movimientos</a><button class="btn" data-import="1">Importar otro archivo</button></div></div>`
    }
    return `${head('Importar movimientos', 'CSV con mapeo de columnas, vista previa, deduplicación y registro de procedencia.')}<div class="steps">${steps}</div>${body}`
  }

  views.budgets = () =>
    `${head('Presupuestos', 'Módulo oficial «Presupuestos» · octubre 2026', canWrite() ? '<button class="btn" disabled title="Fuera del prototipo">Nuevo presupuesto</button>' : '')}<div class="card">${budgetBars()}<p class="small muted">El gasto se calcula a partir de movimientos categorizados; las transferencias internas no cuentan.</p></div>`

  /* ---------- Manager ---------- */
  const SUGGESTIONS = [
    'Analiza mis suscripciones de los últimos 3 meses',
    '¿Cuánto llevamos gastado en supermercado este mes?',
    'Categoriza los movimientos sin categoría',
  ]

  function answer(q) {
    const s = q.toLowerCase()
    const run = { id: `run-00${++state.runSeq}`, tools: [], writes: 0, tokens: 0 }
    let html = ''

    if (s.includes('suscrip')) {
      run.tools.push(['transactions.search', 'merchant_kind=subscription, from=2026-08-01, to=2026-10-31'], ['analysis.recurrence', 'group_by=merchant'])
      const rows = D.subscriptions.map((x) => ({ ...x, first: x.months[0], last: x.months[2], diff: x.months[2] - x.months[0] }))
      const up = rows.filter((r) => r.diff > 0)
      const total = rows.reduce((a, r) => a + r.last, 0)
      const inc = up.reduce((a, r) => a + r.diff, 0)
      html = `He encontrado <strong>${rows.length} cargos recurrentes</strong> que suman <strong>${fmt(total)}/mes</strong>. ${up.length} han subido de precio en 3 meses (+${fmt(inc)}/mes):
        <table style="margin-top:8px"><thead><tr><th>Comercio</th><th class="num">Agosto</th><th class="num">Octubre</th><th class="num">Variación</th></tr></thead><tbody>
        ${rows.map((r) => `<tr><td>${r.merchant}</td><td class="num">${fmt(r.first)}</td><td class="num">${fmt(r.last)}</td><td class="num ${r.diff > 0 ? 'neg' : 'muted'}">${r.diff > 0 ? '+' + fmt(r.diff) : '='}</td></tr>`).join('')}
        </tbody></table>
        <p>Si prescindierais de las que han subido, el ahorro sería de <strong>${fmt(up.reduce((a, r) => a + r.last, 0) * 12)}/año</strong>. No puedo cancelar suscripciones externas; puedo crear un recordatorio.</p>`
    } else if (s.includes('supermercado')) {
      run.tools.push(['budgets.get_status', 'category=Supermercado, period=2026-10'])
      const spent = spentBy('Supermercado')
      const lim = D.budgets[state.ws].find((b) => b.category === 'Supermercado')
      const n = txns().filter((t) => t.category === 'Supermercado').length
      html = `Este mes lleváis <strong>${fmt(spent)}</strong> en supermercado en ${n} compras${lim ? `, el ${Math.round((spent / lim.limit) * 100)} % del presupuesto de ${fmt(lim.limit)}` : ''}.`
    } else if (s.includes('categoriz')) {
      run.tools.push(['transactions.search', 'category=null, exclude=transfers'], ['transactions.suggest_category', 'ids=t5,t7'])
      const open = state.proposals.find((p) => p.id === 'prop-0007' && p.status === 'pending_approval')
      if (open) {
        run.tools.push(['approvals.create_proposal', 'tool=transactions.apply_category → prop-0007'])
        run.writes = 0
        html = `He preparado una propuesta para categorizar <strong>2 movimientos</strong> (Spotify → Suscripciones, Fit Life → Deporte). <strong>No he cambiado nada todavía.</strong>
          <p><a class="btn primary" href="#approvals">Revisar propuesta prop-0007</a></p>`
      } else {
        html = 'No quedan movimientos sin categoría en este workspace.'
      }
    } else {
      html = 'En este prototipo puedo responder a las preguntas sugeridas. La versión real interpreta la petición, elige herramientas autorizadas y muestra las consultas que respaldan cada cifra.'
    }
    run.tokens = 900 + run.tools.length * 650
    state.lastRun = run
    const tools = run.tools.map(([t, a]) => `<div class="tool"><b>${t}</b>(${esc(a)}) → ok</div>`).join('')
    return `${tools}${html}${run.tools.length ? `<div class="evidence muted">Cifras calculadas por el Core a partir de ${run.tools.length} consulta${run.tools.length > 1 ? 's' : ''} · ejecución ${run.id}</div>` : ''}`
  }

  views.manager = () => {
    const thread = state.chat.length
      ? state.chat.map((m) => (m.role === 'user' ? `<div class="msg user">${esc(m.text)}</div>` : `<div class="msg ai"><div class="who">✨ OpenFinance Manager</div>${m.html}</div>`)).join('')
      : `<div class="msg ai"><div class="who">✨ OpenFinance Manager</div>Hola, ${esc(user().name.split(' ')[0])}. Puedo analizar las finanzas del workspace <strong>${esc(D.workspaces.find((w) => w.id === state.ws).name)}</strong> y preparar cambios para que los apruebes. Nunca ejecuto escrituras por mi cuenta.</div>`
    const r = state.lastRun
    return `${head('Manager', 'Agentes con herramientas tipadas, permisos de solo lectura y propuestas que aprueba una persona.')}
      <div class="chat">
        <div class="card"><div class="thread" id="thread">${thread}</div>
          <form class="composer" id="composer"><input type="text" id="prompt" placeholder="Pregunta sobre tus finanzas…" autocomplete="off" /><button class="btn primary">Enviar</button></form>
          <div class="suggest">${SUGGESTIONS.map((s) => `<button type="button" data-ask="${esc(s)}">${esc(s)}</button>`).join('')}</div>
        </div>
        <div class="grid" style="align-content:start">
          <div class="card"><h3>Esta ejecución</h3>${r ? `<div class="mono">${r.id}</div><p class="small muted">Actor: Manager en nombre de ${esc(user().name)}</p><p class="small">Herramientas: ${r.tools.length}<br/>Escrituras directas: <strong>0</strong><br/>Tokens aprox.: ${r.tokens.toLocaleString('es-ES')}</p>` : '<p class="small muted">Aún no hay ejecuciones en esta sesión.</p>'}</div>
          <div class="card"><h3>Permisos del Manager</h3>
            <div><span class="perm">transactions:read</span><span class="perm">budgets:read</span><span class="perm">analysis:run</span><span class="perm">proposals:create</span></div>
            <p class="small muted">Hereda como máximo los permisos de ${esc(user().name)} (${user().role}) en este workspace y nunca puede ampliarlos.</p>
            <div class="guard small">Las descripciones de movimientos son datos, no instrucciones. Ver la fila sospechosa en <a href="#import">Importar</a>.</div>
          </div>
        </div>
      </div>`
  }

  function ask(text) {
    location.hash = 'manager'
    state.chat.push({ role: 'user', text })
    state.chat.push({ role: 'ai', html: '<span class="typing">Consultando datos…</span>' })
    render()
    setTimeout(() => {
      state.chat[state.chat.length - 1] = { role: 'ai', html: answer(text) }
      render()
      const th = $('#thread')
      if (th) th.lastElementChild?.scrollIntoView?.({ block: 'nearest' })
    }, 700)
  }

  /* ---------- Aprobaciones ---------- */
  const LIFECYCLE = ['draft', 'pending_approval', 'approved', 'executing', 'succeeded']
  const STATUS_CHIP = {
    pending_approval: '<span class="chip warn">Pendiente</span>',
    approved: '<span class="chip ok">Aprobada</span>',
    executing: '<span class="chip">Ejecutando…</span>',
    succeeded: '<span class="chip ok">Aplicada</span>',
    rejected: '<span class="chip bad">Rechazada</span>',
  }

  function lifecycle(status) {
    if (status === 'rejected') return '<div class="lifecycle"><span class="past">draft</span>→<span class="past">pending_approval</span>→<span class="cur">rejected</span></div>'
    const i = LIFECYCLE.indexOf(status)
    return `<div class="lifecycle">${LIFECYCLE.map((s, j) => `<span class="${j < i ? 'past' : j === i ? 'cur' : ''}">${s}</span>`).join('→')}</div>`
  }

  function proposalCard(p) {
    const open = p.status === 'pending_approval'
    return `<article class="proposal" id="${p.id}">
      <header><span class="chip ai">${esc(p.origin)}</span><h3>${esc(p.title)}</h3><span class="spacer"></span>${STATUS_CHIP[p.status]}</header>
      <div class="body">
        ${lifecycle(p.status)}
        <div><strong>Por qué:</strong> ${esc(p.reason)}</div>
        <table class="diff"><thead><tr><th>Elemento</th><th>Campo</th><th>Antes</th><th>Después</th></tr></thead><tbody>
          ${p.changes.map((c) => `<tr><td>${esc(c.label)}</td><td class="muted">${c.field}</td><td class="old">${esc(c.from)}</td><td class="new">${esc(c.to)}</td></tr>`).join('')}
        </tbody></table>
        <div class="small muted">Herramienta <span class="mono">${p.tool}</span> · solicitada por ${esc(p.requestedBy)} · ${p.created}${p.expires && open ? ` · caduca ${p.expires}` : ''}<br/>Huella <span class="mono">${p.fingerprint}</span>: si cambia cualquier argumento, la aprobación deja de ser válida.</div>
        ${p.decidedBy ? `<div class="small">Decidida por <strong>${esc(p.decidedBy)}</strong> el ${p.decidedAt}</div>` : ''}
      </div>
      ${open ? `<footer>${canApprove() ? `<button class="btn primary" data-approve="${p.id}">Aprobar y aplicar</button><button class="btn danger" data-reject="${p.id}">Rechazar</button>` : '<span class="guard small">Tu rol (viewer) no permite aprobar operaciones.</span>'}<span class="spacer"></span><span class="small muted">Antes de ejecutar se revalidan permisos y estado actual.</span></footer>` : ''}
    </article>`
  }

  views.approvals = () => {
    const mine = state.proposals.filter((p) => p.ws === state.ws)
    const open = mine.filter((p) => p.status === 'pending_approval')
    const done = mine.filter((p) => p.status !== 'pending_approval')
    return `${head('Aprobaciones', 'Nada de lo que prepara el Manager se aplica sin la aprobación de un miembro autorizado.')}
      <h3>Pendientes (${open.length})</h3>${open.map(proposalCard).join('') || '<p class="muted">No hay propuestas pendientes.</p>'}
      <h3 style="margin-top:24px">Historial</h3>${done.map(proposalCard).join('') || '<p class="muted">Sin historial.</p>'}`
  }

  function decide(id, approve) {
    const p = state.proposals.find((x) => x.id === id)
    if (!p || p.status !== 'pending_approval' || !canApprove()) return
    p.decidedBy = user().name
    p.decidedAt = now()
    if (!approve) {
      p.status = 'rejected'
      audit('proposal.rejected', p.id)
      toast(`Propuesta ${p.id} rechazada`)
      return render()
    }
    p.status = 'approved'
    audit('proposal.approved', p.id)
    render()
    setTimeout(() => { p.status = 'executing'; render() }, 600)
    setTimeout(() => {
      p.status = 'succeeded'
      for (const c of p.changes) {
        const t = c.txn && state.transactions[p.ws].find((x) => x.id === c.txn)
        if (t) t.category = c.to
      }
      audit('execution.succeeded', `${p.id} · idem-key ${Math.random().toString(16).slice(2, 5)}…`, 'Sistema')
      toast(`${p.id} aplicada y registrada en auditoría`)
      render()
    }, 1400)
  }

  /* ---------- Reparto de gastos (ADR-0011) ---------- */
  const METHOD = { equal: 'Partes iguales', percentage: 'Porcentaje', exact: 'Importes', shares: 'Pesos' }
  const wsShort = (id) => (D.workspaces.find((w) => w.id === id)?.name || id).replace(/^\S+\s/, '').split(' · ')[0]

  /** Reparto exacto en céntimos: mayor resto con desempate por orden de participantes. */
  function split(amount, among, method, weights = {}) {
    if (method === 'exact') return Object.fromEntries(among.map((p) => [p, weights[p] || 0]))
    const w = among.map((p) => (method === 'equal' ? 1 : Number(weights[p]) || 0))
    const total = w.reduce((a, b) => a + b, 0)
    if (!total) return Object.fromEntries(among.map((p) => [p, 0]))
    const base = w.map((x) => Math.floor((amount * x) / total))
    const rem = w.map((x, i) => ({ i, r: (amount * x) % total }))
    let left = amount - base.reduce((a, b) => a + b, 0)
    rem.sort((a, b) => b.r - a.r || a.i - b.i)
    for (let k = 0; left > 0; k++, left--) base[rem[k % rem.length].i]++
    return Object.fromEntries(among.map((p, i) => [p, base[i]]))
  }

  const sharesOf = (e) => split(e.amount, e.among, e.method, e.weights)
  const myParticipant = (wsId) => state.sharing[wsId]?.participants.find((p) => p.user === user().id)

  function myShareOf(wsId, expenseId) {
    const e = state.sharing[wsId]?.expenses.find((x) => x.id === expenseId)
    const me = myParticipant(wsId)
    return e && me ? sharesOf(e)[me.id] || 0 : 0
  }

  function balances(wsId) {
    const S = state.sharing[wsId]
    const b = Object.fromEntries(S.participants.map((p) => [p.id, { ...p, contributed: 0, poolShare: 0, paid: 0, share: 0, sent: 0, received: 0 }]))
    for (const c of S.contributions) b[c.participant].contributed += c.amount
    for (const e of S.expenses) {
      const sh = sharesOf(e)
      for (const [pid, v] of Object.entries(sh)) b[pid][e.paidBy === 'pool' ? 'poolShare' : 'share'] += v
      if (e.paidBy !== 'pool') b[e.paidBy].paid += e.amount
    }
    for (const s of S.settlements.filter((x) => x.status === 'confirmed')) {
      b[s.from].sent += s.amount
      b[s.to].received += s.amount
    }
    for (const p of Object.values(b)) {
      p.equity = p.contributed - p.poolShare
      p.net = p.paid - p.share + p.sent - p.received
    }
    return b
  }

  /** Mínimo de transferencias: empareja al mayor deudor con el mayor acreedor. */
  function suggestions(b) {
    const debt = Object.values(b).filter((p) => p.net < 0).map((p) => ({ id: p.id, v: -p.net }))
    const cred = Object.values(b).filter((p) => p.net > 0).map((p) => ({ id: p.id, v: p.net }))
    const out = []
    while (debt.length && cred.length) {
      debt.sort((x, y) => y.v - x.v)
      cred.sort((x, y) => y.v - x.v)
      const d = debt[0], c = cred[0], v = Math.min(d.v, c.v)
      out.push({ from: d.id, to: c.id, amount: v })
      d.v -= v
      c.v -= v
      if (!d.v) debt.shift()
      if (!c.v) cred.shift()
    }
    return out
  }

  function sharedProfilesCard() {
    if (curWs().sharing) return ''
    const rows = Object.keys(state.sharing)
      .filter((id) => myParticipant(id))
      .map((id) => {
        const me = balances(id)[myParticipant(id).id]
        return `<tr><td>${esc(D.workspaces.find((w) => w.id === id).name)}</td><td class="num">${fmt(me.share + me.poolShare)}</td><td>${signed(me.net)}</td><td class="num">${fmt(me.equity)}</td><td><a href="#sharing" data-ws="${id}">Abrir →</a></td></tr>`
      })
    if (!rows.length) return ''
    return `<div class="card" style="margin-top:16px"><h3>Perfiles compartidos</h3><table><thead><tr><th>Perfil</th><th class="num">Tu parte del mes</th><th class="num">Te deben (+) / debes (−)</th><th class="num">Tuyo en la cuenta común</th><th></th></tr></thead><tbody>${rows.join('')}</tbody></table>
      <p class="small muted">En tu perfil personal solo cuenta como gasto tu parte; las aportaciones a la cuenta común no son gasto.</p></div>`
  }

  function parseCents(s) {
    const m = String(s).trim().match(/^(\d{1,7})(?:[.,](\d{1,2}))?$/)
    return m ? Number(m[1]) * 100 + Number((m[2] || '0').padEnd(2, '0')) : null
  }

  function newForm() {
    const ids = state.sharing[state.ws].participants.map((p) => p.id)
    return { concept: '', amount: '', paidBy: myParticipant(state.ws)?.id || 'pool', method: 'equal', among: ids, weights: {} }
  }

  function formPreview(f) {
    const amount = parseCents(f.amount)
    if (amount === null || amount === 0) return { ok: false, msg: 'Introduce un importe válido, por ejemplo 45,90' }
    if (!f.among.length) return { ok: false, msg: 'Elige al menos un participante' }
    if (!f.concept.trim()) return { ok: false, msg: 'Falta el concepto' }
    let weights = {}
    if (f.method === 'exact') {
      for (const p of f.among) {
        const c = parseCents(f.weights[p] || '')
        if (c === null) return { ok: false, msg: 'Importe de cada participante no válido' }
        weights[p] = c
      }
      const sum = Object.values(weights).reduce((a, b) => a + b, 0)
      if (sum !== amount) return { ok: false, msg: `Los importes suman ${fmt(sum)} y el gasto es de ${fmt(amount)}` }
    } else if (f.method !== 'equal') {
      for (const p of f.among) {
        const v = f.weights[p] ?? ''
        if (!/^\d{1,3}$/.test(String(v))) return { ok: false, msg: 'Cada participante necesita un número entero' }
        weights[p] = Number(v)
      }
      const sum = Object.values(weights).reduce((a, b) => a + b, 0)
      if (f.method === 'percentage' && sum !== 100) return { ok: false, msg: `Los porcentajes suman ${sum} %, deben sumar 100 %` }
      if (!sum) return { ok: false, msg: 'Los pesos no pueden ser todos 0' }
    }
    return { ok: true, amount, weights, shares: split(amount, f.among, f.method, weights) }
  }

  function shareForm() {
    const f = state.shareForm
    const S = state.sharing[state.ws]
    const name = (id) => S.participants.find((p) => p.id === id).name
    const pv = formPreview(f)
    const needsWeights = f.method !== 'equal'
    return `<div class="card" style="margin-bottom:16px;border-color:var(--accent)"><h3>Nuevo gasto compartido</h3>
      <div class="row" style="margin-bottom:10px">
        <input type="text" id="sf-concept" data-f="concept" placeholder="Concepto (p. ej. Compra semanal)" value="${esc(f.concept)}" style="flex:2" />
        <input type="text" id="sf-amount" data-f="amount" placeholder="Importe €" value="${esc(f.amount)}" inputmode="decimal" style="width:120px" />
        <label class="small">Pagado por <select class="field" id="sf-paid" data-f="paidBy"><option value="pool" ${f.paidBy === 'pool' ? 'selected' : ''}>Cuenta común</option>${S.participants.map((p) => `<option value="${p.id}" ${f.paidBy === p.id ? 'selected' : ''}>${esc(p.name)} (de su bolsillo)</option>`).join('')}</select></label>
        <label class="small">Reparto <select class="field" id="sf-method" data-f="method">${Object.entries(METHOD).map(([k, v]) => `<option value="${k}" ${f.method === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
      </div>
      <table><thead><tr><th>Participa</th><th>Persona</th>${needsWeights ? `<th>${f.method === 'percentage' ? '%' : f.method === 'exact' ? 'Importe €' : 'Peso'}</th>` : ''}<th class="num">Le corresponde</th></tr></thead><tbody>
        ${S.participants.map((p) => {
          const on = f.among.includes(p.id)
          return `<tr><td><input type="checkbox" data-among="${p.id}" ${on ? 'checked' : ''} aria-label="Incluir a ${esc(p.name)}" /></td><td>${esc(p.name)}${p.user ? '' : ' <span class="chip small">sin usuario</span>'}</td>${needsWeights ? `<td>${on ? `<input type="text" id="sf-w-${p.id}" data-w="${p.id}" value="${esc(f.weights[p.id] ?? '')}" style="width:90px" />` : ''}</td>` : ''}<td class="num">${on && pv.ok ? fmt(pv.shares[p.id]) : '—'}</td></tr>`
        }).join('')}
      </tbody></table>
      <div class="row" style="margin-top:10px">${pv.ok ? `<span class="chip ok">✓ Suma ${fmt(Object.values(pv.shares).reduce((a, b) => a + b, 0))} = ${fmt(pv.amount)}</span><span class="small muted">Los céntimos sobrantes se asignan de forma determinista.</span>` : `<span class="chip warn">${esc(pv.msg)}</span>`}
        <span class="spacer"></span><button class="btn" data-sf="cancel">Cancelar</button><button class="btn primary" data-sf="save" ${pv.ok ? '' : 'disabled'}>Guardar gasto</button></div>
      <p class="small muted">Para un reparto 1 a 1, deja marcadas solo dos personas.</p></div>`
  }

  views.sharing = () => {
    const ws = curWs()
    if (!ws.sharing) return `${head('Reparto', '')}<p class="muted">Este workspace no tiene activado el reparto de gastos.</p>`
    const S = state.sharing[state.ws]
    const b = balances(state.ws)
    const name = (id) => (id === 'pool' ? 'Cuenta común' : b[id].name)
    const me = myParticipant(state.ws)
    const pool = Object.values(b).reduce((a, p) => a + p.equity, 0)
    const account = D.accounts[state.ws][0]
    const total = S.expenses.reduce((a, e) => a + e.amount, 0)
    const pendingS = S.settlements.filter((s) => s.status === 'pending_confirmation')
    const sug = suggestions(b)

    const canConfirm = (s) => {
      const to = S.participants.find((p) => p.id === s.to)
      return to.user ? to.user === user().id : canWrite()
    }

    return `${head('Reparto de gastos', `${esc(ws.name)} · ${S.participants.length} participantes · cuenta común y gastos pagados de su bolsillo`, canWrite() && !state.shareForm ? '<button class="btn primary" data-sf="open">Nuevo gasto compartido</button>' : '')}
      ${state.shareForm ? shareForm() : ''}
      <div class="grid g4">
        <div class="card kpi"><div class="label">Cuenta común</div><div class="value">${fmt(pool)}</div><div class="delta ${pool === account.balance ? 'pos' : 'neg'}">${pool === account.balance ? '✓ Cuadra con' : '✗ No cuadra con'} ${esc(account.name)}</div></div>
        <div class="card kpi"><div class="label">Gastos compartidos del mes</div><div class="value">${fmt(total)}</div><div class="delta muted">${S.expenses.length} gastos</div></div>
        <div class="card kpi"><div class="label">Tu parte</div><div class="value">${me ? fmt(b[me.id].share + b[me.id].poolShare) : '—'}</div><div class="delta muted">Lo que cuenta como gasto en tu perfil</div></div>
        <div class="card kpi"><div class="label">Tu saldo entre personas</div><div class="value ${me && b[me.id].net < 0 ? 'neg' : 'pos'}">${me ? (b[me.id].net > 0 ? '+' : '') + fmt(b[me.id].net) : '—'}</div><div class="delta muted">${me && b[me.id].net < 0 ? 'Debes' : 'Te deben'}</div></div>
      </div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h3>Participantes</h3><table><thead><tr><th>Persona</th><th class="num">Aportado</th><th class="num">Suyo en la cuenta</th><th class="num">Pagado de su bolsillo</th><th class="num">Su parte</th><th class="num">Saldo</th></tr></thead><tbody>
          ${Object.values(b).map((p) => `<tr><td>${esc(p.name)}${p.user ? '' : ' <span class="chip small">sin usuario</span>'}</td><td class="num">${fmt(p.contributed)}</td><td class="num">${fmt(p.equity)}</td><td class="num">${fmt(p.paid)}</td><td class="num">${fmt(p.share + p.poolShare)}</td><td>${signed(p.net)}</td></tr>`).join('')}
        </tbody></table>
        <p class="small muted">«Suyo en la cuenta» = aportado − su parte de lo pagado con la cuenta común. «Saldo» = lo que le deben (+) o debe (−) a otras personas; la suma de todos es siempre 0.</p></div>
        <div class="card"><h3>Para quedar en paz</h3>
          ${sug.length ? `<table>${sug.map((s) => {
            const p = pendingS.find((x) => x.from === s.from && x.to === s.to)
            return `<tr><td><strong>${esc(name(s.from))}</strong> paga a <strong>${esc(name(s.to))}</strong></td><td class="num">${fmt(s.amount)}</td><td>${p ? '<span class="chip warn">Pendiente de confirmar</span>' : canWrite() ? `<button class="btn" data-settle="${s.from}|${s.to}|${s.amount}">Registrar pago</button>` : ''}</td></tr>`
          }).join('')}</table>` : '<p class="pos">✓ Todos están en paz.</p>'}
          ${pendingS.length ? `<h3 style="margin-top:14px">Liquidaciones por confirmar</h3><table>${pendingS.map((s) => `<tr><td>${esc(name(s.from))} → ${esc(name(s.to))}<div class="small muted">Registrada por ${esc(s.registeredBy)}</div></td><td class="num">${fmt(s.amount)}</td><td>${canConfirm(s) ? `<button class="btn primary" data-confirm="${s.id}">Confirmar recibido</button>` : `<span class="small muted">Debe confirmarlo ${esc(name(s.to))}</span>`}</td></tr>`).join('')}</table>` : ''}
          <p class="small muted">El dinero de la cuenta común no entra en estas sugerencias: se queda en la cuenta salvo que decidáis repartirlo. Un pago solo cuenta cuando quien lo recibe lo confirma.</p>
        </div>
      </div>
      <div class="card" style="margin-top:16px"><h3>Gastos compartidos</h3><table><thead><tr><th>Fecha</th><th>Concepto</th><th>Pagado por</th><th>Reparto</th><th class="num">Importe</th></tr></thead><tbody>
        ${S.expenses.slice().sort((x, y) => y.date.localeCompare(x.date)).map((e) => {
          const sh = sharesOf(e)
          return `<tr><td class="muted">${fmtDate(e.date)}</td><td>${esc(e.concept)}<div class="small muted">${esc(e.category)}</div></td><td>${e.paidBy === 'pool' ? '<span class="chip transfer">Cuenta común</span>' : `<span class="chip">${esc(name(e.paidBy))}</span>`}</td><td><span class="chip">${METHOD[e.method]}${e.among.length < S.participants.length ? ` · ${e.among.length} de ${S.participants.length}` : ''}</span><div class="small muted">${e.among.map((p) => `${esc(name(p))} ${fmt(sh[p])}`).join(' · ')}</div></td><td class="num">${fmt(e.amount)}</td></tr>`
        }).join('')}
      </tbody></table><p class="small muted">Los demás ven «pagado por Ana», nunca su cuenta personal ni el movimiento de origen.</p></div>`
  }

  function onShareClick(el) {
    const S = state.sharing[state.ws]
    if (el.dataset.sf === 'open') state.shareForm = newForm()
    else if (el.dataset.sf === 'cancel') state.shareForm = null
    else if (el.dataset.sf === 'save') {
      const f = state.shareForm
      const pv = formPreview(f)
      if (!pv.ok) return
      const id = `e${S.expenses.length + 1}`
      S.expenses.push({ id, date: '2026-10-31', concept: f.concept.trim(), category: 'Otros', amount: pv.amount, paidBy: f.paidBy, method: f.method, among: f.among.slice(), weights: pv.weights })
      audit('sharing.expense_created', `${id} · ${f.concept.trim()} · ${fmt(pv.amount)}`)
      state.shareForm = null
      toast('Gasto compartido guardado')
    } else if (el.dataset.settle) {
      const [from, to, amount] = el.dataset.settle.split('|')
      const id = `s${S.settlements.length + 1}`
      S.settlements.push({ id, from, to, amount: Number(amount), date: '2026-10-31', status: 'pending_confirmation', registeredBy: user().name })
      audit('sharing.settlement_registered', `${id} · ${fmt(Number(amount))}`)
      toast('Pago registrado: falta que lo confirme quien lo recibe')
    } else if (el.dataset.confirm) {
      const s = S.settlements.find((x) => x.id === el.dataset.confirm)
      s.status = 'confirmed'
      s.confirmedBy = user().name
      audit('sharing.settlement_confirmed', s.id)
      toast('Pago confirmado: saldos actualizados')
    }
    render()
  }

  /* ---------- Plataforma ---------- */
  const ROLE_TEXT = {
    owner: 'Administración completa y gestión de miembros',
    editor: 'Gestión financiera, importación y aprobación de propuestas',
    viewer: 'Consulta de los datos que se le comparten',
  }

  views.workspace = () => {
    const ws = D.workspaces.find((w) => w.id === state.ws)
    const all = D.accounts[state.ws]
    return `${head(esc(ws.name), `Workspace ${ws.kind.toLowerCase()} · moneda base ${ws.currency}`, isOwner() ? '<button class="btn primary" id="invite">Invitar miembro</button>' : '')}
      <div class="grid g2">
        <div class="card"><h3>Miembros</h3><table><thead><tr><th>Persona</th><th>Rol</th><th>Estado</th></tr></thead><tbody>
          ${D.members[state.ws].map((m) => `<tr><td>${esc(m.name)}<div class="small muted">${esc(m.email)}</div></td><td><span class="chip">${m.role}</span></td><td class="small ${m.status === 'Activo' ? '' : 'muted'}">${m.status}</td></tr>`).join('')}
        </tbody></table></div>
        <div class="card"><h3>Roles</h3>${Object.entries(ROLE_TEXT).map(([r, t]) => `<p><span class="chip">${r}</span> ${t}</p>`).join('')}<p class="small muted">El rol es el punto de partida. El acceso a cada cuenta se comprueba además por recurso.</p></div>
      </div>
      <div class="card" style="margin-top:16px"><h3>Acceso a cuentas</h3><table><thead><tr><th>Cuenta</th><th>Quién la ve</th></tr></thead><tbody>
        ${all.map((a) => `<tr><td>${a.restrictedTo && !a.restrictedTo.includes(user().id) ? '🔒 Cuenta no compartida contigo' : esc(a.name)}</td><td class="small">${a.restrictedTo ? `Solo ${a.restrictedTo.map((u) => Object.values(D.users).find((x) => x.id === u).name).join(', ')}` : 'Todos los miembros'}</td></tr>`).join('')}
      </tbody></table><p class="small muted">Prueba a cambiar «Ver como» en la barra superior: Marta (viewer) no ve la nómina de Luis ni puede aprobar.</p></div>`
  }

  views.modules = () =>
    `${head('Módulos y proveedores', 'Módulos oficiales con permisos declarados. El SDK para terceros llegará después (ADR-0006).')}
      <div class="grid" style="grid-template-columns:1fr 1fr">
        ${state.modules.map((m) => `<div class="card module"><div class="icon">${m.icon}</div><div><strong>${esc(m.name)}</strong> <span class="small muted">${m.version}</span> ${m.core ? '<span class="chip">Core</span>' : m.soon ? '<span class="chip">Próximamente</span>' : '<span class="chip ok">Oficial</span>'}<p class="small muted" style="margin:4px 0">${esc(m.desc)}</p>${m.perms.map((p) => `<span class="perm">${p}</span>`).join('')}</div>
          <button class="toggle ${m.enabled ? 'on' : ''}" data-module="${m.id}" aria-label="Activar ${esc(m.name)}" ${m.core || m.soon || !isOwner() ? 'disabled' : ''}></button></div>`).join('')}
      </div>
      <div class="card" style="margin-top:16px"><h3>Servicios externos · qué sale de tu instalación</h3><table>
        ${D.providers.map((p) => `<tr><td>${p.name}</td><td class="small">${esc(p.value)}</td><td>${p.on ? '<span class="chip warn">Activo</span>' : '<span class="chip">Inactivo</span>'}</td></tr>`).join('')}
      </table><p class="small muted">Las credenciales bancarias y claves de proveedores nunca se incluyen en prompts.</p></div>`

  views.audit = () =>
    `${head('Auditoría', 'Quién hizo qué, cuándo y con qué aprobación.')}<div class="card"><table><thead><tr><th>Fecha</th><th>Actor</th><th>Acción</th><th>Objeto</th></tr></thead><tbody>
      ${state.audit.map((e) => `<tr><td class="small muted">${e.at}</td><td>${esc(e.actor)}</td><td class="mono">${e.action}</td><td class="small">${esc(e.target)}</td></tr>`).join('')}
    </tbody></table></div>`

  /* ---------- render y eventos ---------- */
  function render() {
    renderChrome()
    const v = views[route()] || views.dashboard
    $('#view').innerHTML = v()
  }

  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-ask],[data-import],[data-approve],[data-reject],[data-module],[data-sf],[data-settle],[data-confirm],[data-ws],#invite')
    if (!el) return
    if (el.dataset.ws) { state.ws = el.dataset.ws; state.shareForm = null; return render() }
    if (el.dataset.sf || el.dataset.settle || el.dataset.confirm) return onShareClick(el)
    if (el.dataset.ask) return ask(el.dataset.ask)
    if (el.dataset.import) {
      state.importStep = Number(el.dataset.import)
      if (state.importStep === 4) audit('import.committed', 'octubre-banco-norte.csv · 4 nuevos · 2 duplicados omitidos')
      return render()
    }
    if (el.dataset.approve) return decide(el.dataset.approve, true)
    if (el.dataset.reject) return decide(el.dataset.reject, false)
    if (el.dataset.module) {
      const m = state.modules.find((x) => x.id === el.dataset.module)
      m.enabled = !m.enabled
      audit(m.enabled ? 'module.enabled' : 'module.disabled', m.id)
      toast(`${m.name} ${m.enabled ? 'activado' : 'desactivado'}`)
      return render()
    }
    if (el.id === 'invite') toast('Prototipo: aquí se enviaría una invitación con rol y cuentas compartidas')
  })

  document.addEventListener('submit', (e) => {
    if (e.target.id !== 'composer') return
    e.preventDefault()
    const v = $('#prompt').value.trim()
    if (v) ask(v)
  })

  function rerenderKeepingFocus(target) {
    const id = target.id
    const pos = target.selectionStart
    render()
    const again = id && document.getElementById(id)
    if (again) {
      again.focus()
      if (typeof pos === 'number' && again.setSelectionRange) again.setSelectionRange(pos, pos)
    }
  }

  document.addEventListener('input', (e) => {
    const t = e.target
    if (t.id === 'q') {
      state.q = t.value
      return rerenderKeepingFocus(t)
    }
    const f = state.shareForm
    if (!f) return
    if (t.dataset.f && t.tagName === 'INPUT') { f[t.dataset.f] = t.value; return rerenderKeepingFocus(t) }
    if (t.dataset.w) { f.weights[t.dataset.w] = t.value; return rerenderKeepingFocus(t) }
  })

  document.addEventListener('change', (e) => {
    const f = state.shareForm
    if (f && e.target.tagName === 'SELECT' && e.target.dataset.f) {
      f[e.target.dataset.f] = e.target.value
      if (e.target.dataset.f === 'method') f.weights = {}
      return render()
    }
    if (f && e.target.dataset.among) {
      const id = e.target.dataset.among
      const order = state.sharing[state.ws].participants.map((p) => p.id)
      f.among = e.target.checked ? order.filter((p) => p === id || f.among.includes(p)) : f.among.filter((p) => p !== id)
      return render()
    }
    if (e.target.id === 'filter') { state.filter = e.target.value; render() }
    if (e.target.id === 'ws-switch') { state.ws = e.target.value; state.chat = []; state.lastRun = null; state.shareForm = null; render() }
    if (e.target.id === 'role-switch') {
      state.role = e.target.value
      const ws = D.workspaces.find((w) => w.id === state.ws)
      if (ws.onlyFor && !ws.onlyFor.includes(user().id)) state.ws = 'familia'
      state.shareForm = null
      toast(`Viendo como ${user().name} (${user().role})`)
      render()
    }
  })

  window.addEventListener('hashchange', () => { render(); $('#view').focus() })
  render()
})()
