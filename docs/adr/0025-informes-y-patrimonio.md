# ADR-0025: Patrimonio neto, flujo de caja, informes a medida y exportación v2

- Estado: Accepted
- Fecha: 2026-11-03

## Contexto

Con cuentas de varios tipos (ADR-0018), varias monedas (ADR-0019), pagos programados (ADR-0021) y datos que ya llegan solos del banco (ADR-0024), las pantallas del mes y la evolución se quedan cortas para dos preguntas: «¿cuánto tenemos de verdad?» y «¿de dónde sale y adónde va el dinero?». Además la exportación v1 no lleva lo que se ha añadido desde la fase 10 y nadie puede pedir un informe distinto de los fijos.

Todo son **vistas calculadas** sobre los movimientos, sin tablas nuevas salvo los informes guardados.

## Decisión

### Patrimonio neto (OF-1501)

- **Patrimonio = activos − deudas**, en la moneda del hogar y con las cuentas que ve quien pregunta (ADR-0013): una cuenta personal ajena no suma, ni en el total ni en el historial. Los **activos** son la suma de los saldos positivos y las **deudas** la de los negativos (en valor absoluto), sea cual sea el tipo de cuenta: una tarjeta o un préstamo con saldo negativo es lo que se debe, y un descubierto en una cuenta bancaria también. Una tarjeta con saldo positivo (se pagó de más) es un activo: no se oculta. El desglose por tipo (banco, efectivo, inversión, tarjeta, préstamo) enseña el neto de cada uno.
- Se enseña el total, el desglose por tipo y por cuenta y la **evolución de los últimos 12 fines de mes** más el de hoy. El saldo de cada fecha es el inicial más los movimientos hasta ese día (los anulados no cuentan).
- **Otras monedas** se convierten con el tipo de cambio más reciente anterior o igual a cada fecha (ADR-0019). Una cuenta sin tipo para una fecha **no entra** en esa fecha y se lista aparte, para decir «falta el tipo de USD» en vez de inventar un valor.
- El patrimonio incluye las cuentas personales de quien mira. Quien mira la vista del hogar ve el suyo; no hay un «patrimonio de la pareja» que sume cuentas ajenas.

### Flujo de caja (OF-1502)

- Por mes, sobre el **dinero líquido** que ve quien pregunta (cuentas bancarias y efectivo) **en la moneda del hogar**: **ingresos**, **aportaciones** (netas: lo que entra a la conjunta menos lo que sale de una personal, así que se compensan cuando se ven las dos), **gasto** (neto de devoluciones), **al ahorro** (neto de lo que se saca de la hucha), **traspasos propios** (netos, normalmente cero) y el **saldo al final del mes**. Ingresos + aportaciones − gasto − ahorro + traspasos = variación del mes = diferencia entre los saldos de fin de mes: la identidad se comprueba en tests.
- Las cuentas líquidas en **otra moneda quedan fuera** (se cuentan en el resultado y la pantalla lo dice): convertir movimientos y saldos con tipos distintos haría que la identidad no cuadrase al céntimo, y es preferible no enseñar una cifra que parece exacta y no lo es.
- Los últimos 12 meses por defecto (de 1 a 36). El mes en curso se marca como parcial.
- Las tarjetas, los préstamos y las inversiones no son líquidos y quedan fuera: sus compras ya son gasto de la tarjeta (ADR-0018) y mezclarlas contaría dos veces.

### Informes a medida (OF-1503)

- Un informe es una **definición** (no un resultado): periodo (de mes a mes, máximo 36 meses), qué medir (gasto, ingreso, ahorro o neto), por qué agrupar (categoría, comercio, cuenta, mes o persona) y filtros opcionales (cuentas, categorías, etiquetas, importe mínimo). Se ejecuta siempre con los **permisos de quien lo ejecuta**: la misma definición da resultados distintos a cada persona porque cada una ve cuentas distintas, y nunca se guarda un resultado.
- Se pueden **guardar** (`saved_reports`): personales o compartidos con el hogar. Compartir comparte la definición, no los datos. Máximo 30 por persona. Solo su dueño los cambia o borra; un informe personal ajeno es 404. Filtrar por una cuenta que no se ve es 404, no un resultado vacío.
- El resultado se puede descargar en **CSV** con la misma protección frente a fórmulas que la exportación (OF-501).
- No hay lenguaje de consulta ni expresiones: solo campos cerrados, validados.

### Exportación v2 (OF-1504)

- `format_version: 2` añade lo que v1 no llevaba: importes de presupuesto por mes y modo (límite o sobre), aportaciones a objetivos, pagos programados, plantillas, reglas de automatización, comercios con nombre propio, etiquetas, informes guardados propios y compartidos, conexiones bancarias (banco, estado, caducidad y últimos cuatro dígitos del IBAN) y tipos de cambio.
- **Nunca** se exporta el identificador de sesión del agregador, el `state` de una conexión, las claves VAPID, las suscripciones push, las huellas de movimientos, las sesiones ni los hashes de contraseña. Lo de otra persona del hogar (cuentas personales, informes personales, conexiones, sus reglas personales) tampoco, como en v1.
- v1 sigue disponible con `?version=1` para quien lo use; sin parámetro se entrega v2. El CSV de movimientos no cambia.

## Consecuencias

- Una tabla nueva, `saved_reports`; el resto no toca el esquema.
- El patrimonio y el flujo de caja tienen sus cifras cruzadas en tests (variación del mes = diferencia de saldos; la suma por tipo = el total).
- Los informes a medida son otra superficie de lectura de movimientos: cada consulta pasa por las cuentas visibles y tiene tests negativos entre personas y entre hogares.
- La exportación v2 es mayor que v1 y se prueba con una lista explícita de campos que **no** debe contener.
