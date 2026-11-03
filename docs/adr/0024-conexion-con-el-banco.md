# ADR-0024: Conexión con el banco mediante un agregador PSD2

- Estado: Accepted
- Fecha: 2026-11-03

## Contexto

Hasta ahora los movimientos entran por extractos (CSV, OFX, CAMT…) o a mano. Revolut y Bankinter, los bancos del hogar, publican su información por PSD2, pero un banco solo la entrega a un proveedor autorizado (AISP). Un proyecto self-hosted no puede ser AISP, así que necesita un **agregador** que lo sea. La instalación es propia: cada hogar crea su cuenta en el agregador y las claves no salen de su servidor.

## Decisión

### Agregador: Enable Banking

- Se usa [Enable Banking](https://enablebanking.com) con **la cuenta del propio hogar**. Su modo de producción restringido permite enlazar las cuentas de quien registra la aplicación, sin contrato comercial. OpenFinance no pasa por ningún servidor nuestro.
- La API se firma con un JWT RS256 (`kid` = identificador de la aplicación, `iss` = `enablebanking.com`, `aud` = `api.enablebanking.com`, caduca en una hora) con la clave privada que descarga quien registra la aplicación. Se configura con `OPENFINANCE_BANK_APP_ID`, `OPENFINANCE_BANK_PRIVATE_KEY` (el PEM) y `OPENFINANCE_BANK_REDIRECT_URL`. **Sin esas variables la conexión está apagada** y Ajustes lo dice; el resto de la app no cambia.
- El agregador va detrás de un puerto (`BankAggregator`). Otro proveedor (GoCardless, Tink…) sería un adaptador más. Los tests usan un agregador simulado: no se prueba contra bancos reales en CI.
- Sin dependencia nueva: el cliente usa `urllib` de la biblioteca estándar y `cryptography` (ya presente por `pywebpush`, que pasa a declararse como dependencia directa).

### Consentimiento (OF-1401)

- Una **conexión** la crea una persona para un banco y es **suya**: solo ella la ve, la enlaza, la sincroniza o la revoca. Otra persona del hogar, o de otro hogar, recibe 404.
- Flujo: `POST /bank/connections` (banco y país) devuelve la URL del banco y guarda un `state` aleatorio de un solo uso; el banco redirige a `OPENFINANCE_BANK_REDIRECT_URL` con `code` y `state`; la web llama a `POST /bank/connections/complete`, que exige que el `state` pertenezca a una conexión pendiente **de la persona con sesión**. La finalización es un POST (con `X-Requested-With`), no un GET con efectos, para que un enlace ajeno no pueda completar nada.
- Al completar, el agregador devuelve las cuentas autorizadas. Cada una queda **sin enlazar** hasta que la persona la asigna a una cuenta de OpenFinance que ella vea (ADR-0013) y de la misma moneda; una cuenta personal ajena no se puede elegir. Una cuenta del banco enlaza con una sola cuenta de OpenFinance y al revés.
- El identificador de sesión del agregador no se devuelve nunca por la API ni se escribe en logs. Lo que se muestra del banco es el nombre y los últimos cuatro dígitos del IBAN.
- **Revocar** pide al agregador cerrar la sesión (si falla, igualmente se marca revocada y se avisa) y detiene la sincronización. Los movimientos ya traídos no se tocan.

### Sincronización (OF-1402)

- Reutiliza **la misma tubería que la importación**: cada movimiento del banco se convierte en una fila normalizada con su huella y pasa por las mismas reglas de categorías, comercios y aportaciones. La huella es `bank:<identificador del banco>` cuando el banco lo da, y la huella habitual por fecha, importe y concepto cuando no, así que sincronizar dos veces no duplica.
- Cada sincronización crea un **lote de importación** (`banco:<nombre>`), de modo que se ve en el historial y se puede deshacer como cualquier otra importación.
- Solo entran movimientos **contabilizados** (`BOOK`); los pendientes no cuentan hasta que el banco los fije, para que un cargo retenido que luego cambia de importe no genere un duplicado.
- Ventana: la primera vez, 90 días; después, desde 7 días antes de la última sincronización correcta (los bancos corrigen fechas con retraso, y las huellas evitan repetir).
- **Nada corre dentro del servidor**: `openfinance bank sync` lo lanza cron, como las copias y los avisos. Hay también un botón «Sincronizar ahora» por conexión. Una sincronización fallida guarda el motivo y no toca nada más; no hay reintentos agresivos (los bancos limitan a unas 4 consultas diarias sin presencia de la persona).
- La sincronización actúa **con la persona titular de la conexión** y solo escribe en las cuentas enlazadas, que esa persona ve.

### Caducidad del consentimiento (OF-1403)

- PSD2 limita el consentimiento (hasta 180 días). Se guarda `valid_until`; pasada esa fecha la conexión pasa a **caducada** y deja de sincronizar.
- Un aviso nuevo (`consent_expiring`, ADR-0023) salta 14 días antes de caducar, y otro cuando ya caducó, solo para la persona titular. Renovar es crear una conexión nueva; las cuentas enlazadas se pueden reasignar sin perder el historial.

### Conciliación automática (OF-1404)

- Al sincronizar, una fila del banco que no es duplicada por huella busca un movimiento **anotado a mano o importado de un extracto** en la misma cuenta con el **mismo importe** y fecha a **≤ 3 días**, que no venga ya del banco. Si hay **exactamente uno**, ese movimiento adopta la huella del banco (queda conciliado: no se crea otro y la próxima sincronización lo reconoce); si hay varios, no se adivina: se crea el movimiento nuevo y el hogar decide.
- Tras sincronizar se compara el saldo que informa el banco con el calculado en OpenFinance y se guarda la diferencia en el enlace; si no cuadra, se ve en Ajustes. Es informativo: no se corrige nada solo.

## Consecuencias

- Se añaden `bank_connections` y `bank_links`. Los movimientos traídos entran en el registro de cambios por su lote de importación, como los de un extracto.
- Los datos bancarios pasan por el agregador elegido por el hogar. La documentación de despliegue explica cómo crear la aplicación, qué se comparte y cómo revocar.
- **No probado contra un banco real**: el adaptador sigue la documentación pública del agregador y se prueba con respuestas simuladas. La primera conexión real puede pedir ajustes (campos opcionales, límites de cada banco).
- Los pagos y las transferencias iniciadas desde OpenFinance quedan fuera: solo lectura de cuentas.
