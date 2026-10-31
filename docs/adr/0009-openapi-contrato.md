# ADR-0009: OpenAPI como contrato entre frontend y backend

- Estado: Proposed
- Fecha: 2026-10-31

## Contexto

La web y la API evolucionan en paralelo y podrán existir otros clientes (CLI, móvil).

## Decisión propuesta

- FastAPI publica el esquema en `/openapi.json`, bajo el prefijo versionado `/api/v1`.
- El esquema se exporta al repositorio y el cliente TypeScript de `apps/web/src/api` se genera o se comprueba a partir de él en CI.
- Los cambios incompatibles requieren una nueva versión de la API.

## Consecuencias

- Las roturas de contrato se detectan antes de integrar.
- Hay que elegir el generador de cliente (pendiente; hoy el cliente es manual y mínimo).
