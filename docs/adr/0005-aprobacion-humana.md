# ADR-0005: Aprobación humana para operaciones preparadas por agentes

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

Los agentes pueden preparar operaciones, pero la autoridad para ejecutarlas es del usuario. Una aprobación no debe poder reutilizarse para algo distinto de lo que se revisó.

## Decisión

- Toda escritura del Manager se materializa como `ActionProposal`: operación, argumentos tipados, alcance y una **huella** (hash canónico de todo lo anterior). La propuesta es inmutable.
- `Approval` referencia la propuesta y su huella, con aprobador, decisión y fecha.
- Estados: `draft → pending_approval → approved → executing → succeeded`, con ramas `rejected`, `expired`, `cancelled` y `failed`.
- Al pasar de `approved` a `executing` se revalidan permisos, estado actual de los recursos y condiciones de negocio.
- `ActionExecution` registra cada intento con clave de idempotencia; reintentar no duplica efectos.
- Las aprobaciones caducan y nunca autorizan operaciones futuras.

## Consecuencias

- Se necesita un motor de estados y auditoría desde la fase 3.
- En el MVP solo se proponen operaciones internas (categorizaciones, reglas); nada de pagos o transferencias reales.
