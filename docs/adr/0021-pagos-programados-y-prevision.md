# ADR-0021: Pagos programados, previsión de saldo y «hoy podéis gastar»

- Estado: Accepted
- Fecha: 2026-11-02

## Contexto

Hoy solo se mira hacia atrás: los cargos recurrentes se **detectan** a partir de lo cobrado (OF-403) y «Este mes» estima el cierre con lo que ya ha pasado (OF-802). Un hogar necesita lo contrario: declarar «el alquiler son 900 € el día 1», «el seguro anual de 380 € vence el 14 de marzo» o «la nómina de Elena llega el 28», y saber qué saldo habrá dentro de 30 días y cuánto se puede gastar hoy sin quedarse corto.

## Decisión

### Pagos programados

- Un **pago programado** es del hogar y tiene: nombre, importe (positivo si es un ingreso, negativo si es un pago), cuenta, categoría y comercio opcionales, **frecuencia** (`semanal`, `cada N meses`, `anual`, `una vez`), **próxima fecha**, fecha de fin opcional y un interruptor de activo.
- Una **ocurrencia** es una fecha esperada de un pago. **No es un movimiento**: nada se escribe en el libro por sí solo. Lo cobrado de verdad sigue entrando por la importación o a mano, y la previsión nunca cambia un saldo real.
- **Emparejado**: al importar o crear un movimiento, una ocurrencia pendiente del mismo pago se da por cumplida si la cuenta coincide, el importe difiere como mucho un 5 % (o el pago es de importe variable) y la fecha cae a ±7 días de la esperada. Si hay más de un candidato, no se empareja a ciegas: queda para elegir. El emparejado se deshace.
- Si pasa la fecha y no llega nada, la ocurrencia queda **atrasada**: se avisa y no se suma a la previsión.
- Los meses cortos se resuelven con el último día del mes (un pago del día 31 cae el 28/29 en febrero). Todo el calendario es función pura de la fecha; no hay tareas programadas ni reloj en el servidor.
- Los cargos recurrentes **detectados** pueden convertirse en un pago programado con un clic (se rellena con comercio, importe y día habituales). Mientras no se convierta, siguen valiendo para la previsión como hasta ahora; si existe el pago programado del mismo comercio, el detectado no se cuenta dos veces.

### Previsión de saldo

- `previsión(cuenta, hasta)` = saldo actual + suma de las ocurrencias pendientes y no atrasadas hasta esa fecha, día a día. Es una función pura en el dominio; la capa de aplicación solo reúne saldos y pagos visibles.
- Solo cuentan las cuentas que ve quien consulta (ADR-0013). El total del hogar suma las cuentas visibles; una cuenta personal ajena no entra ni en el total ni en los avisos.
- Se avisa del **día del primer saldo negativo** y del **saldo mínimo** del periodo. Varias monedas (ADR-0019): se calcula por moneda; si falta una tasa, esa moneda no se mezcla en el total y se dice.
- Las cuentas de tipo `card` y `loan` no entran en la previsión de efectivo (como no entran en gasto).

### «Hoy podéis gastar»

- Es un cálculo honesto, no una promesa: `(saldo de cuentas corrientes y efectivo − pagos pendientes hasta la próxima entrada de dinero esperada, o hasta fin de mes si no hay ninguna) ÷ días restantes`, con piso en cero.
- Si hay presupuestos con sobres (ADR-0022), se muestra además lo que queda en cada sobre. Si no hay datos suficientes (sin saldo o sin pagos programados), la tarjeta lo dice en lugar de inventar una cifra.

### Plantillas

- Una **plantilla** es un movimiento manual guardado (nombre, importe, tipo, cuenta, categoría, comercio, etiquetas) para crearlo con un clic. Es del hogar o personal. Crear desde una plantilla usa el flujo normal de OF-701, con registro de cambios y deshacer.

## Consecuencias

- El calendario de ocurrencias es una función pura y se prueba con propiedades: ninguna ocurrencia cae fuera del rango pedido, el orden es estable, y generar dos veces da lo mismo.
- No se crean movimientos automáticos: se evita el peor fallo posible (un gasto fantasma que descuadra el saldo).
- Se añaden las tablas `scheduled_payments`, `scheduled_occurrences` (solo las emparejadas o descartadas; las futuras se calculan) y `transaction_templates`.
- Tests de privacidad negativos: un pago de una cuenta personal ajena no aparece en listados, previsión ni «hoy podéis gastar».
