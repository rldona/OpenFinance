# Arquitectura

Alcance actual: [ADR-0012 · Empezar por el hogar](../adr/0012-empezar-por-el-hogar.md).

## Vista lógica (v0.1)

```
┌───────────────────────────────────────────────────────────┐
│ apps/web — React + TypeScript                             │
│ Este mes · ¿En qué gastamos? · Evolución · Ahorrar · …    │
└───────────────────────────┬───────────────────────────────┘
                            │ REST /api/v1 (OpenAPI)
┌───────────────────────────▼───────────────────────────────┐
│ services/api — OpenFinance Core (monolito modular)        │
│  api/            HTTP → casos de uso                      │
│  application/    casos de uso, puertos (Protocols)        │
│  domain/         hogar, movimientos, categorías…  (puro)  │
│  infrastructure/ SQLAlchemy, config, lector de CSV        │
└───────────────────────────┬───────────────────────────────┘
                     ┌──────▼──────┐
                     │ PostgreSQL  │
                     └─────────────┘
```

Un solo proceso para la API y un solo frontend. Sin workers, colas ni IA en v0.1.

## Contextos de dominio (v0.1)

| Contexto | Responsabilidad |
| --- | --- |
| identity | Las dos personas del hogar e inicio de sesión |
| workspaces | El hogar: frontera de datos (`workspace_id` en todo) |
| ledger | Cuentas y movimientos: aportaciones, gastos y traspasos a ahorro |
| categorization | Categorías por hogar y reglas aprendidas por comercio (del hogar o personales) |
| budgeting | Presupuestos mensuales por categoría |
| imports | Lectura de CSV del banco, normalización y deduplicación |
| insights | Agregados para gráficos, objetivos de ahorro, ideas y simulador |

La lista vive en `openfinance.domain.BOUNDED_CONTEXTS` y se expone en `GET /api/v1/meta`.

Aplazados (ADR-0012): `manager`, `approvals`, `modules`, `sharing` y `audit` avanzada.

## Reglas de dependencia

Se hacen cumplir con `import-linter` (`services/api/pyproject.toml`):

- `api → infrastructure → application → domain` (solo hacia abajo).
- `domain` sin frameworks; `application` sin HTTP ni ORM.

## Reglas del dinero

- `Money` = `Decimal` + `Currency` ISO 4217, cuantizado a céntimos; rechaza `float`.
- Tipos de movimiento: **aportación** (entra a la cuenta común), **gasto** (con categoría), **traspaso a ahorro** (no es gasto).
- Cuentas: conjunta (Revolut) y huchas visibles para el hogar; personales (Bankinter) visibles solo para su titular ([ADR-0013](../adr/0013-cuentas-personales-privadas.md)).
- Cada movimiento guarda su comercio normalizado (`merchant`) para aplicar reglas sin recalcularlo.
- Sesiones en servidor: cookie `HttpOnly` con un token aleatorio del que solo se guarda el hash; contraseñas con Argon2id.
- Fecha efectiva ≠ fecha de importación; cada movimiento importado conserva su archivo de origen.
- Deduplicación por identificador externo cuando el banco lo da; si no, por huella de fecha, importe y concepto normalizado.
- Los gráficos se calculan en el Core con consultas agregadas por mes y categoría; el frontend solo pinta.
