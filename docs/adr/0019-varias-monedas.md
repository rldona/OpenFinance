# ADR-0019: Varias monedas

- Estado: Accepted
- Fecha: 2026-11-01

## Contexto

`Money` ya lleva la moneda de cada importe y las operaciones entre monedas distintas fallan, pero el hogar entero está en una sola moneda y los informes la dan por hecha. Hay quien viaja, cobra en otra moneda o tiene una cuenta en el extranjero.

## Decisión

- **Cada cuenta tiene una moneda** y sus movimientos van en ella. No hay cuentas multimoneda.
- **El hogar tiene una moneda de referencia** (la de hoy, EUR por defecto). Los informes, los presupuestos y los objetivos se calculan en ella.
- **Tipos de cambio manuales o importados, nunca consultados en línea**: una tabla `exchange_rates` (hogar, moneda, fecha, tasa `Decimal` con 8 decimales, procedencia `manual|extracto`). OpenFinance no llama a ningún servicio de cotizaciones (coherente con [ADR-0007](0007-local-first-self-hosted.md)).
- **Conversión a una fecha**: la tasa más reciente anterior o igual a la fecha del movimiento. Si no hay ninguna, el movimiento **no se convierte** y el informe lo dice («3 movimientos en USD sin tipo de cambio») en lugar de inventar un valor.
- La conversión es siempre una vista de cálculo: el importe original no se modifica y se redondea una sola vez, al final, con `ROUND_HALF_EVEN`.
- Un traspaso entre cuentas de monedas distintas guarda sus dos importes reales; el cambio implícito se enseña, no se corrige.

## Consecuencias

- Los informes del Core pasan a recibir un conversor (puerto) en vez de sumar `Money` directamente.
- Un hogar con una sola moneda no nota nada: sin tasas, todo se queda como está.
- Es el último ticket de la fase porque toca los totales de todas las pantallas.
