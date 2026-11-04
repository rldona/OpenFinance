# ADR-0020: Motor de reglas con condiciones y importación universal

- Estado: Accepted
- Fecha: 2026-11-02

## Contexto

Hoy hay una sola clase de regla: «comercio → categoría», que se aprende al corregir (OF-202, OF-702). Sirve para lo común, pero no para «los pagos de más de 500 € desde la conjunta son *Casa*», «lo que contenga *AMAZON PRIME* lleva la etiqueta *suscripción*» o «las comisiones del banco son *Banco* y no cuentan para revisar». Y solo se importan dos formatos de dos bancos (Revolut y Bankinter), cuando otros hogares tendrán otro banco.

Esta fase hace las reglas más potentes sin perder lo que ya funciona, y abre la importación a formatos estándar y a cualquier CSV.

## Decisión

### Reglas con condiciones, acciones y fases

- Una **regla** tiene un nombre, un ámbito (del hogar o personal, como hoy), **condiciones** (todas a la vez), **acciones** y una **fase**.
- **Condiciones**: el concepto *contiene*, *empieza por* o *es igual a* un texto (sin distinguir mayúsculas ni tildes); el comercio es uno concreto; el importe está *entre* dos valores (en valor absoluto); es un gasto o un ingreso (signo); la cuenta es una de estas; el tipo del banco es este. **No hay expresiones regulares**: una regla escrita por una persona no puede colgar el servidor (ReDoS), y lo anterior cubre lo que se pide en la práctica.
- **Acciones**: poner la categoría, poner el tipo (gasto, ingreso, traspaso…), añadir etiquetas, poner o añadir nota, asignar el comercio. Una acción nunca toca el importe, la fecha ni el concepto.
- **Fases**: `antes`, `normal` y `después`. Dentro de cada fase, por orden de prioridad (un número que se puede reordenar). Cada acción se aplica **solo si el campo todavía no lo ha fijado una regla anterior o una persona** («la primera que fija, gana»): una categoría elegida a mano nunca se pisa, como hasta ahora.
- Las reglas aprendidas «comercio → categoría» **siguen existiendo tal cual** y se evalúan en la fase `normal` con la prioridad más baja: lo que una regla explícita no decide, lo decide lo aprendido. No hay migración de datos de las reglas actuales.
- Un movimiento **revisado** (OF-1006) o **dividido** (OF-1003) no lo cambia ninguna regla.

### Vista previa y aplicar a lo existente

- Toda regla se puede **probar** antes de guardarla: la vista previa dice qué movimientos existentes (entre los que ve quien la crea) cambiarían, con el antes y el después, sin escribir nada.
- **Aplicar a lo existente** es una acción explícita, separada de guardar la regla, y deja una operación en el registro de cambios (ADR-0017) que se deshace de una vez. Las reglas nuevas se aplican solas a las importaciones futuras.
- Privacidad (ADR-0013): una regla del hogar solo ve y cambia los movimientos de las cuentas visibles para quien la aplica; una regla personal, solo los de las cuentas personales de su titular. Un recuento nunca incluye lo que no se ve.

### Importación universal

- **Formatos**: OFX y QIF (los que exportan casi todos los bancos), CAMT.053 (XML de ISO 20022, el estándar europeo) y **CSV de cualquier banco** con un **perfil**.
- Todos entran por la misma tubería de hoy: lector → filas normalizadas (`ImportedRow`) → vista previa → confirmar. Mismo `fingerprint` estable para no duplicar, mismas comprobaciones de saldo cuando el formato trae saldos, mismos límites de tamaño (5 MB) y los mismos extractos reales sin entrar nunca en el repositorio.
- XML solo con `defusedxml` (sin entidades externas ni expansión). Los importes nunca pasan por `float`.
- Un **perfil de CSV** guarda cómo leer el archivo de un banco: separador, codificación, formato de fecha y de número, columnas de fecha, concepto e importe (o debe/haber), signo y cuántas filas de cabecera saltar. Se crea desde una vista previa de las primeras filas y se reutiliza; es del hogar y se puede borrar. No ejecuta nada: es solo datos.
- Un formato nuevo no sustituye a los lectores de Revolut y Bankinter: esos siguen detectándose por su cabecera.

## Consecuencias

- Hace falta un orden de evaluación estable y testeable: el motor es una función pura (movimiento + reglas → cambios) en el dominio, con el acceso a datos fuera.
- Los tests incluyen propiedades: aplicar las mismas reglas dos veces no cambia nada la segunda vez (idempotencia) y nunca se cambia un campo fijado a mano.
- OFX, QIF y CAMT se prueban con archivos sintéticos; los extractos reales siguen fuera del repositorio.
- Las reglas con condiciones sobre la cuenta o el importe necesitan que la vista previa sea rápida: se evalúa en memoria sobre los movimientos visibles, sin una consulta por regla.
