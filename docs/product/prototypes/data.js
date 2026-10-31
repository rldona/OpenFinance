/* Datos ficticios del prototipo: 12 meses de la cuenta común de un hogar.
   Importes en céntimos (enteros). Generación determinista con semilla fija. */
(() => {
  'use strict'

  let seed = 20261031
  const rnd = () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  const between = (a, b) => Math.round(a + rnd() * (b - a))
  const pick = (xs) => xs[Math.floor(rnd() * xs.length)]
  const times = (a, b) => between(a, b)

  const household = {
    name: 'Nuestra casa',
    members: ['Raúl', 'Elena'],
    account: 'Cuenta conjunta Revolut',
    bank: 'Revolut',
    savingsAccount: 'Hucha Ahorro (Revolut)',
  }

  const categories = [
    { id: 'vivienda', name: 'Vivienda', icon: '🏠', color: '#0f766e' },
    { id: 'super', name: 'Supermercado', icon: '🛒', color: '#16a34a' },
    { id: 'suministros', name: 'Luz, agua, gas e internet', icon: '💡', color: '#ca8a04' },
    { id: 'restaurantes', name: 'Restaurantes', icon: '🍽️', color: '#ea580c' },
    { id: 'transporte', name: 'Transporte', icon: '🚗', color: '#2563eb' },
    { id: 'suscripciones', name: 'Suscripciones', icon: '📺', color: '#7c3aed' },
    { id: 'salud', name: 'Salud y deporte', icon: '💪', color: '#db2777' },
    { id: 'ocio', name: 'Ocio', icon: '🎟️', color: '#0891b2' },
    { id: 'ropa', name: 'Ropa', icon: '👕', color: '#9333ea' },
    { id: 'hogar', name: 'Hogar', icon: '🛋️', color: '#65a30d' },
    { id: 'viajes', name: 'Viajes', icon: '✈️', color: '#0284c7' },
    { id: 'regalos', name: 'Regalos', icon: '🎁', color: '#e11d48' },
    { id: 'otros', name: 'Otros', icon: '📦', color: '#64748b' },
  ]

  // Últimos 12 meses: noviembre 2025 → octubre 2026
  const MONTH_NAMES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
  const months = []
  for (let i = 0; i < 12; i++) {
    const y = 2025 + Math.floor((10 + i) / 12)
    const m = (10 + i) % 12
    months.push({ key: `${y}-${String(m + 1).padStart(2, '0')}`, y, m, label: `${MONTH_NAMES[m]} ${String(y).slice(2)}`, short: MONTH_NAMES[m], days: new Date(y, m + 1, 0).getDate() })
  }

  const txns = []
  let seq = 0
  const add = (mo, day, desc, category, amount, extra = {}) =>
    txns.push({ id: `t${++seq}`, date: `${mo.key}-${String(Math.min(day, mo.days)).padStart(2, '0')}`, desc, category, amount, ...extra })

  for (const mo of months) {
    const winter = [10, 11, 0, 1, 2].includes(mo.m)
    const summer = [5, 6, 7].includes(mo.m)

    // Aportaciones de cada uno a la cuenta común (no son gasto ni ingreso «real» del hogar, pero sí entradas)
    add(mo, 1, 'Payment from Raul Lopez (Bankinter)', null, 160000, { income: true, who: 'Raúl' })
    add(mo, 1, 'Payment from Elena Martin (Bankinter)', null, 140000, { income: true, who: 'Elena' })
    // Traspaso al ahorro: es ahorro, no gasto
    add(mo, 2, 'To pocket EUR Ahorro', null, -30000, { savings: true })

    add(mo, 1, 'RECIBO HIPOTECA PRESTAMO 0042', 'vivienda', -72000)
    add(mo, 5, 'COMUNIDAD PROPIETARIOS C/ MAYOR 12', 'vivienda', -6500)

    for (let k = 0; k < times(6, 9); k++) add(mo, between(1, 30), pick(['MERCADONA 1234', 'LIDL VALENCIA', 'CARREFOUR MARKET', 'CONSUM 0087']), 'super', -between(2800, 11500))

    add(mo, between(10, 16), 'IBERDROLA CLIENTES', 'suministros', -(winter ? between(8500, 11800) : summer ? between(7000, 9500) : between(5200, 6800)))
    add(mo, 8, 'DIGI SPAIN TELECOM FIBRA', 'suministros', -3990)
    if (mo.m % 2 === 0) add(mo, 20, 'AGUAS DE VALENCIA', 'suministros', -between(2800, 3600))
    if (winter) add(mo, between(18, 25), 'NATURGY GAS', 'suministros', -between(4200, 8800))

    const rest = summer || mo.m === 11 ? times(5, 8) : times(3, 5)
    for (let k = 0; k < rest; k++) add(mo, between(1, 30), pick(['RESTAURANTE LA PEPICA', 'BAR CENTRAL', 'GLOVO', 'JUST EAT', 'PIZZERIA NAPOLI', 'CAFETERIA SOL']), 'restaurantes', -between(1800, 7500))

    for (let k = 0; k < times(2, 4); k++) add(mo, between(1, 30), pick(['REPSOL ESTACION 22', 'CEPSA AV. FRANCIA', 'BP OIL']), 'transporte', -between(4500, 7000))
    if (rnd() < 0.4) add(mo, between(1, 30), 'PARKING CENTRO', 'transporte', -between(600, 1800))

    // Suscripciones: Netflix subió en julio; Disney+ se añadió en abril
    add(mo, 12, 'NETFLIX.COM', 'suscripciones', mo.key >= '2026-07' ? -1799 : -1399, { recurring: 'Netflix' })
    add(mo, 14, 'SPOTIFY DUO', 'suscripciones', mo.key >= '2026-09' ? -1699 : -1499, { recurring: 'Spotify' })
    add(mo, 3, 'APPLE.COM/BILL ICLOUD', 'suscripciones', -299, { recurring: 'iCloud' })
    if (mo.key >= '2026-04') add(mo, 23, 'DISNEY PLUS', 'suscripciones', -1199, { recurring: 'Disney+' })

    add(mo, 2, 'GIMNASIO FIT LIFE CUOTA x2', 'salud', -7980, { recurring: 'Gimnasio' })
    for (let k = 0; k < times(0, 2); k++) add(mo, between(1, 30), 'FARMACIA LDO. GARCIA', 'salud', -between(600, 3800))

    for (let k = 0; k < times(1, 3); k++) add(mo, between(1, 30), pick(['CINES YELMO', 'TICKETMASTER', 'FNAC', 'BOLERA OCIO']), 'ocio', -between(1500, 6500))

    const ropa = [0, 6].includes(mo.m) ? times(2, 4) : times(0, 2)
    for (let k = 0; k < ropa; k++) add(mo, between(1, 30), pick(['ZARA', 'DECATHLON', 'PRIMARK', 'EL CORTE INGLES']), 'ropa', -between(2500, 9000))

    for (let k = 0; k < times(0, 2); k++) add(mo, between(1, 30), pick(['IKEA VALENCIA', 'LEROY MERLIN', 'AMAZON EU HOGAR']), 'hogar', -between(1500, 14000))

    if (mo.m === 7) { add(mo, 4, 'VUELING AIRLINES', 'viajes', -38400); add(mo, 6, 'BOOKING.COM HOTEL', 'viajes', -61500) }
    if (mo.m === 3) add(mo, 10, 'RENFE + HOTEL SEMANA SANTA', 'viajes', -34500)
    if (mo.m === 11) { add(mo, 15, 'EL CORTE INGLES REGALOS', 'regalos', -18500); add(mo, 22, 'AMAZON EU REGALOS', 'regalos', -9600) }
    if (mo.m === 0) add(mo, 5, 'JUGUETERIA REYES', 'regalos', -7400)
    if (rnd() < 0.25) add(mo, between(1, 30), 'REGALO CUMPLEAÑOS', 'regalos', -between(2500, 6000))

    if (rnd() < 0.5) add(mo, between(1, 30), pick(['BIZUM A JAVI', 'COMPRA TARJETA 4821 AMAZON', 'CORREOS ENVIO']), mo.key === '2026-10' ? null : 'otros', -between(800, 4500))
  }

  // Octubre: un par de movimientos aún sin categorizar
  const oct = months[11]
  add(oct, 27, 'COMPRA TARJETA 4821 AMZN MKTP', null, -2399)
  add(oct, 29, 'BIZUM A LUCIA CENA', null, -2250)

  txns.sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id))

  window.OF = {
    household,
    categories,
    months,
    txns,
    budgets: { vivienda: 78500, super: 55000, suministros: 18000, restaurantes: 18000, transporte: 20000, suscripciones: 6000, salud: 11000, ocio: 10000, ropa: 12000, hogar: 10000 },
    goals: [
      { id: 'g1', name: 'Fondo de emergencia', icon: '🛟', target: 900000, saved: 612000, monthly: 20000 },
      { id: 'g2', name: 'Vacaciones verano 2027', icon: '🏖️', target: 250000, saved: 88000, monthly: 10000, deadline: '2027-07' },
    ],
  }
})()
