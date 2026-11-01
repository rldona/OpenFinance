# ADR-0018: Alcance del libro contable completo

- Estado: Proposed
- Fecha: 2026-11-01

## Contexto

Hasta la fase 9, OpenFinance trata un movimiento como entrada o gasto de un hogar con una cuenta bancaria detrás ([ADR-0012](0012-empezar-por-el-hogar.md)). Eso basta para importar extractos y ver el mes. No basta para lo que el hogar hace de verdad con el dinero: pagar una compra entre dos cuentas, dividir un ticket en varias categorías, llevar el efectivo, ver lo que se debe de la hipoteca o lo que valen unos fondos.

El roadmap dejaba «préstamos» fuera de alcance. Lo que quedó fuera es **vender o intermediar** préstamos, seguros y cuentas remuneradas (negocio de intermediación). **Llevar la cuenta de un préstamo que ya tenéis** es otra cosa: es un saldo que baja. Este ADR fija esa frontera.

## Decisión

### Dentro de alcance (fase 10)

1. **Cuentas de más tipos**, todas solo de seguimiento (nada se contrata ni se mueve desde OpenFinance): `cash` (efectivo), `card` (tarjeta de crédito: el saldo es lo que se debe), `loan` (préstamo o hipoteca que ya existe: saldo pendiente) e `investment` (valor anotado a mano o por movimientos; sin cotizaciones en directo).
2. **Comercios** como entidad: un nombre visible, con sus variantes del banco («MERCADONA 0451» → «Mercadona»), que se pueden renombrar y fusionar.
3. **Dividir un movimiento** en varias partes con su categoría; la suma de las partes es siempre el importe original.
4. **Traspasos enlazados**: los dos lados de un traspaso entre cuentas propias se enlazan entre sí, para que ninguno cuente como gasto ni como ingreso y se vea el par.
5. **Conciliación**: marcar movimientos como revisados y comprobar el saldo de una cuenta contra el del banco en una fecha.
6. **Etiquetas, notas y adjuntos** (ticket, factura) en un movimiento. Los adjuntos viven en disco bajo la misma regla de privacidad que el movimiento y entran en la copia de seguridad.
7. **Varias monedas** ([ADR-0019](0019-varias-monedas.md)).

### Fuera de alcance (se mantiene)

Contratar, comparar o recomendar préstamos, seguros o cuentas remuneradas; cotizaciones y rentabilidad de inversiones en tiempo real; asesoramiento financiero; cifrado de extremo a extremo.

### Reglas que no cambian

- Toda consulta filtra por hogar y por visibilidad de la cuenta ([ADR-0013](0013-cuentas-personales-privadas.md)). Etiquetas, partes, enlaces y adjuntos heredan la visibilidad del movimiento; un test negativo por cada una.
- Todo cambio de un dato corregible pasa por el registro de cambios ([ADR-0017](0017-registro-de-cambios.md)), con deshacer y rehacer.
- Los importes son `Decimal`; nunca `float`.
- Un movimiento importado conserva su importe, fecha, concepto y huella. Dividirlo no los toca: las partes son una capa encima.

### Efecto en los informes

- Las cuentas `loan` e `investment` no cuentan en el gasto del mes ni en los presupuestos. Las cuotas de un préstamo son un gasto (categoría) en la cuenta desde la que se pagan; el saldo del préstamo baja por el traspaso enlazado a la cuenta `loan`.
- El saldo del hogar sigue siendo la suma de las cuentas visibles; `card` y `loan` restan.

## Consecuencias

- Hace falta una migración por ticket y un cambio de la API pública con cada uno (`make openapi`).
- Los informes de fase 3 tienen que ignorar las partes de un movimiento dividido y usar las partes en su lugar; se cubre con un test de propiedades (la suma por categoría no cambia al dividir).
- Se puede implementar por tickets independientes en este orden: comercios → etiquetas y notas → dividir → traspasos enlazados → tipos de cuenta → conciliación → adjuntos → monedas. Las monedas van al final porque tocan todo el Core.
