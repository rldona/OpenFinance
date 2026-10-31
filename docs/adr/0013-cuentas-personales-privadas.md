# ADR-0013: Cuentas personales en el hogar, privadas por defecto

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

La cuenta conjunta está en Revolut y cada persona tiene además su cuenta personal en Bankinter, desde la que aporta a la conjunta. Queremos poder incorporar esas cuentas personales sin perder la sencillez de ADR-0012 ni exponer las finanzas de cada persona a la otra sin decidirlo.

## Decisión

- Cada `Account` tiene un **tipo** (`joint`, `savings`, `personal`) y una **entidad** (`revolut`, `bankinter`, `other`).
- Una cuenta `personal` tiene obligatoriamente un **titular** (`owner_id`); las demás no tienen titular. La base de datos lo garantiza con una restricción `CHECK`.
- **Visibilidad:** la cuenta conjunta y las huchas las ven todos los miembros del hogar. Una cuenta personal **solo la ve su titular**, y sus movimientos tampoco aparecen a nadie más, ni en listados ni consultando su id (404).
- Las aportaciones se registran como `contribution` con la persona que aporta: en la conjunta son **entrada**; en la cuenta personal, si se importa, son una **salida** que no cuenta como gasto.
- Los totales del hogar (gasto, ahorro y gráficos) se calculan sobre la cuenta conjunta y las huchas. Las cuentas personales tendrán su propia vista cuando se importen (OF-107).

## Consecuencias

- Toda consulta de cuentas y movimientos filtra por hogar **y** por visibilidad; hay tests negativos para ambos casos.
- Si en el futuro queréis compartir una cuenta personal, bastará con añadir un permiso explícito («compartir con…») sin cambiar el modelo.
- Esta decisión amplía ADR-0012 en un único punto (las cuentas personales); el resto del alcance de v0.1 no cambia.
