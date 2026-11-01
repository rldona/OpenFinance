# ADR-0017: Registro de cambios con deshacer y rehacer

- Estado: Accepted
- Fecha: 2026-11-01

## Contexto

La fase 7 (OF-701 … OF-706) permite corregir datos desde la web: tipo, persona y nota de un movimiento, categorías en bloque, reglas, movimientos de efectivo y deshacer una importación. Toda corrección tiene que quedar trazada (quién, cuándo, antes y después) y poder deshacerse sin miedo.

La auditoría proponía primero una tabla `transaction_corrections` (OF-701) y después ampliarla a un registro general (OF-706). Hacerlo en dos pasos obliga a migrar datos reales a mitad del mes de uso. Se hace el registro general desde el principio y OF-701 es su primer uso.

## Decisión

### Modelo

- **Operación** (`change_operations`): una acción de una persona, con hogar, autor, fecha, tipo (`transaction.edit`, `transactions.categorize`, `rule.delete`, `import.undo`…), un resumen legible y, si se ha deshecho, cuándo y por quién. Varias escrituras van en la misma operación (poner una categoría y que la regla clasifique otros 40).
- **Cambio** (`change_entries`): entidad (`transaction`, `rule`, `import`), su identificador, campo, valor antes y valor después (JSON). Solo se registran campos que se pueden corregir: en un movimiento `kind`, `member_id`, `category_id`, `note` y `voided`; en una regla, su categoría (`null` = sin regla); en una importación, su estado.
- **Nada se borra.** Borrar un movimiento manual o deshacer una importación pone `voided = true` (y queda en el registro). Las consultas, los totales y la exportación ignoran los movimientos anulados. El importe, la fecha, el concepto y la huella de un movimiento importado nunca cambian.
- Alta de un movimiento manual: se registra como `voided: true → false`, así deshacerla es anularlo.

### Deshacer y rehacer

- Cada persona solo deshace y rehace **sus** operaciones.
- Deshacer recorre los cambios al revés y pone el valor «antes» **solo donde el valor actual sigue siendo el «después»**. Si alguien (esa persona o la pareja) lo cambió después, ese cambio se respeta y la respuesta dice cuántos se han dejado y quién los tocó. Rehacer es lo simétrico. Nunca se pisa un cambio posterior.
- Consecuencia: deshacer todas las operaciones en orden inverso devuelve el estado inicial (test de propiedades).
- Deshacer o rehacer también queda en la operación (`undone_at`, `undone_by`).

### Privacidad (ADR-0013)

- El historial de un movimiento solo se ve si se ve el movimiento: la pareja no ve el de una cuenta personal ajena (404, como el propio movimiento).
- La lista de operaciones de una persona solo incluye las suyas. Las reglas personales y sus cambios solo los ve su titular.

## Consecuencias

- Toda escritura nueva sobre movimientos, reglas o importaciones pasa por el registro: es la base de las fusiones de comercios, el motor de reglas y las propuestas del asistente de fases posteriores.
- Las consultas de movimientos llevan siempre el filtro `voided = false`; hay tests que lo comprueban en listados, totales y exportación.
- Volver a importar un extracto deshecho reactiva sus movimientos (misma huella, mismo identificador) en lugar de duplicarlos.
- El registro crece con el uso. Con dos personas son unos cientos de filas al mes; no se purga.
