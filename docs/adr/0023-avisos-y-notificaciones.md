# ADR-0023: Avisos deterministas, notificaciones Web Push y resumen semanal

- Estado: Accepted
- Fecha: 2026-11-03

## Contexto

Con pagos programados, previsión y presupuestos (ADR-0021, ADR-0022) hay datos para avisar de lo que importa: un cargo duplicado, una comisión, un recibo que sube, un pago que no ha llegado, un saldo que se queda en negativo. Hoy hay que abrir la app para enterarse. El hogar son dos personas y la instalación es propia (HTTPS con dominio propio).

## Decisión

### Avisos (OF-1301)

- Un **aviso** es una función pura de los datos de hoy. **No se guarda**: se recalcula en cada consulta, como el emparejado de pagos. Lo único que se guarda es que una persona lo **descartó**, por su clave (`alert_dismissals`, por persona, no por hogar).
- Detectores, cada uno con su umbral explícito y sin aprendizaje:
  - `duplicate`: mismo gasto (cuenta, comercio, importe) a ≤ 2 días; solo los últimos 14 días.
  - `fee`: gasto cuyo concepto o tipo de banco dice «comisión»/«fee», últimos 30 días.
  - `price_rise`: cuota recurrente cuyo último cambio fue este mes o el anterior y subió ≥ 5 %.
  - `late_payment`: ocurrencia atrasada de un pago programado.
  - `low_balance`: una cuenta de efectivo queda en negativo en los próximos 30 días según la previsión.
  - `budget_over`: presupuesto superado este mes.
- La **clave** de cada aviso es estable y nombra lo que lo causa (`duplicate:<movimiento>`, `price_rise:<comercio>:<mes>`…): un cambio de precio nuevo avisa de nuevo; descartar uno no apaga el siguiente.
- **Privacidad (ADR-0013)**: cada detector solo ve las cuentas visibles para quien consulta. Un aviso de una cuenta personal solo lo ve su titular, no se puede descartar desde otra cuenta (404) y no aparece en ninguna notificación ajena. Los avisos de presupuestos y cuotas recurrentes usan solo la conjunta, como el resto de informes del hogar.
- Descartar solo acepta claves de avisos que existen hoy para esa persona: una clave inventada o ajena da 404.

### Notificaciones (OF-1302): Web Push

- Canal único en esta fase: **Web Push** (estándar W3C con claves VAPID). La app ya es una PWA y la instalación usa HTTPS, así que no hay servidor ni app extra, y el contenido viaja cifrado de extremo a extremo hasta el dispositivo. Se descarta ntfy por ahora (otro servicio que mantener y, en el servidor público, el texto lo ve un tercero); el envío va detrás de un puerto (`PushSender`), así que ntfy puede ser un segundo adaptador más adelante sin tocar el motor.
- Cada persona se suscribe desde su móvil (una suscripción por navegador) y elige qué tipos de aviso quiere. Una suscripción caducada (HTTP 404/410 del servicio push) se borra sola.
- **El servidor solo envía a servicios push conocidos** (`fcm.googleapis.com`, `push.services.mozilla.com`, `push.apple.com`, `notify.windows.com`, solo https y sin puerto ni credenciales): el endpoint lo aporta el cliente y, sin esa lista, cualquier persona con sesión podría hacer que el servidor pidiera cualquier URL (SSRF).
- **Nada corre dentro del servidor**: igual que las copias, el envío lo lanza `openfinance alerts notify` desde cron. Es idempotente: `alert_deliveries` guarda (persona, clave) de lo ya enviado, así que ejecutarlo cada hora no repite nada.
- El texto de una notificación **no lleva importes ni nombres de comercio**: solo el tipo de aviso y cuántos hay («Tienes 2 avisos nuevos en OpenFinance»); el detalle se ve dentro, con sesión iniciada. Los servicios push (Google, Apple, Mozilla) ven metadatos pero nunca el contenido financiero.
- Sin claves VAPID configuradas (`OPENFINANCE_VAPID_PRIVATE_KEY`, `OPENFINANCE_VAPID_SUBJECT`), la función está apagada y la web lo dice; los avisos siguen viéndose en la app.
- Solo funciona en HTTPS; en modo `direct` (HTTP) no se ofrece. En iPhone exige iOS 16.4+ y la PWA añadida a inicio.

### Resumen semanal (OF-1303)

- Una vista calculada, no un informe guardado: gasto de la última semana completa frente a la anterior a esa, las tres categorías que más pesan, los pagos de los próximos 7 días y los avisos abiertos. Se calcula sobre la conjunta y las cuentas visibles de quien lo pide.
- Se envía como una notificación más (solo el aviso de que está listo; el contenido se abre en la app), una vez por semana ISO y persona: la primera vez que corre `alerts notify` cada semana, así que si cron falla un lunes llega al día siguiente. La semana resumida es la última completa (de lunes a domingo). Cada persona puede apagarlo.

## Consecuencias

- Los detectores son funciones puras y se prueban uno a uno; cualquier cambio de umbral es una constante visible.
- Se añaden `alert_dismissals`, `push_subscriptions`, `notification_preferences` y `alert_deliveries`. Ninguna toca el libro ni entra en el registro de cambios (son estado de interfaz, no datos contables).
- Dependencia nueva: `pywebpush` (licencia MPL-2.0, ya permitida por `make licenses`).
- Pendiente de probar en un móvil real; en CI solo se prueba con un servicio push simulado.
