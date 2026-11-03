# ADR-0026: Hogar ampliado: más personas con roles, reparto de gastos y eventos

- Estado: Accepted
- Fecha: 2026-11-03

## Contexto

El hogar nació para dos personas ([ADR-0012](0012-empezar-por-el-hogar.md)) y las altas se hacen desde el servidor. El modelo ya admite más de dos miembros, pero no hay forma de invitarlos, todos pueden escribirlo todo y no existe el reparto de gastos que preveía [ADR-0011](0011-perfiles-compartidos-reparto.md). Un piso compartido o un viaje en grupo necesitan tres cosas: más personas con permisos distintos, repartir lo que paga uno en nombre de todos y agrupar gastos por evento.

Se reutiliza el **hogar** como frontera ([ADR-0002](0002-workspace-frontera-aislamiento.md)) en vez de crear un workspace compartido aparte: un hogar de cuatro personas es el «piso compartido». Quedan fuera, y se documentan como pendientes, los gastos pagados con la cuenta común repartidos por persona (el «saldo del fondo» de ADR-0011) y el enlace entre un movimiento personal y un gasto compartido.

## Decisión

### Personas y roles (OF-1601)

- Cada pertenencia al hogar tiene un **rol**: `owner`, `editor` o `viewer` (ADR-0002). Las personas que ya estaban son `owner`. Como mucho **10 personas** por hogar.
  - `owner`: todo, y además invita, cambia roles y quita personas.
  - `editor`: escribe en el hogar (movimientos, importaciones, reglas, presupuestos…), pero no gestiona personas.
  - `viewer`: solo lee. Puede cambiar su contraseña, cerrar sesión, descartar avisos, elegir sus notificaciones y ejecutar informes (no escriben datos del hogar).
- El rol **no abre cuentas personales**: un `owner` tampoco ve la cuenta personal de otra persona (ADR-0013). Es un permiso de escritura y de gestión, no de visibilidad.
- La comprobación es **central**: toda petición que no sea de lectura la rechaza (403) un `viewer` salvo la lista anterior, sin depender de que cada ruta se acuerde. La gestión de personas exige `owner` en cada ruta.
- **Invitaciones**: un `owner` crea una invitación con el rol elegido; recibe un enlace **una sola vez** (256 bits al azar; en la base de datos solo se guarda su hash SHA-256). Caduca a los 7 días, vale una vez y se puede revocar. Quien la abre elige su nombre, email y contraseña (mínimo 10 caracteres) y entra con sesión abierta. No hay registro público: sin invitación vigente no se crea nada. Aceptar está limitado por intentos y por IP como el inicio de sesión. Un email que ya tiene cuenta se rechaza (una persona pertenece a un hogar).
- **Quitar a alguien** (`owner`): se cierran sus sesiones y deja de pertenecer al hogar. No se puede quitar a una persona con **cuentas personales** (habría que decidir qué pasa con sus movimientos), ni a uno mismo, ni al último `owner`. Cambiar el rol de alguien no puede dejar el hogar sin `owner`.

### Reparto de gastos (OF-1602)

- **Participantes**: las personas del hogar y **invitados sin usuario** (un nombre, sin acceso a nada; quien tiene rol de escritura anota por ellos). Un invitado solo se archiva con saldo cero.
- **Gasto compartido**: fecha, concepto, importe (en la moneda del hogar), **quién pagó** (una o varias personas; la suma pagada es exactamente el importe) y **cómo se reparte**: `equal`, `percentage`, `exact` o `shares`, entre todo el grupo o un subconjunto. Los cálculos son en céntimos enteros y lo que sobra se asigna por **mayor resto** con desempate por el orden dado; la suma de las partes es **siempre** el importe y, si no cuadra, se rechaza. Se guarda el resultado de cada parte, no solo la regla. Un gasto se puede corregir (se recalcula) y se anula sin borrarse.
- **Saldo entre personas** = pagado − su parte + liquidaciones enviadas − liquidaciones recibidas (solo las confirmadas). La suma de todos los saldos es exactamente **cero**. Las sugerencias «quién paga a quién» salen de esos saldos con el mínimo de transferencias, emparejando mayores deudores con mayores acreedores.
- **Liquidaciones**: quien paga la registra y queda **pendiente** hasta que el receptor la confirma (o un `owner` o `editor` si el receptor es un invitado). Solo entonces cambia los saldos. Registrar la misma liquidación dos veces con la misma referencia no la duplica. Se puede cancelar mientras está pendiente.
- **Visibilidad**: los gastos compartidos son del hogar y los ven todas las personas. No están enlazados a movimientos de cuentas personales, así que no filtran nada de ellas.

### Eventos y viajes (OF-1603)

- Un **evento** (viaje, cumpleaños, obra) tiene nombre, icono y fechas opcionales. Los gastos compartidos pueden pertenecer a uno. Su resumen enseña el total, lo pagado y la parte de cada participante, los saldos **solo con los gastos del evento** y el gasto por categoría.
- Un evento se puede **cerrar**: no admite gastos nuevos hasta reabrirlo. Un evento con gastos no se borra, se cierra.

## Consecuencias

- Se añaden `memberships.role`, `invitations`, `guests`, `shared_expenses` (con sus pagadores y partes), `settlements` y `events`.
- `Actor` lleva el rol; los casos de uso existentes siguen funcionando porque el valor por defecto es `owner` y la restricción de `viewer` se aplica en la API.
- Pruebas obligatorias: las partes suman el importe del gasto, los saldos suman cero, repetir una liquidación no cambia nada, un `viewer` no escribe en ninguna ruta de escritura (se recorren todas), una invitación vale una vez y caduca, y nada de otro hogar es visible ni modificable.
- Pendiente (sin ticket): gastos pagados con la cuenta común repartidos por persona, y enlazar un movimiento personal con un gasto compartido («Gasto compartido · Casa»).
