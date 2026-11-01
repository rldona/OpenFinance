# AGENTS.md — instrucciones para agentes de desarrollo

Fuente principal de reglas de ingeniería para cualquier agente de código que trabaje en este repositorio. `CLAUDE.md` solo remite aquí.

## Contexto

OpenFinance es un monolito modular: `services/api` (Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL) y `apps/web` (React 19, TypeScript estricto, Vite). **El alcance vigente es el de [ADR-0012](docs/adr/0012-empezar-por-el-hogar.md)**: un hogar, dos personas, una cuenta común, importación CSV, categorías y gráficos. No implementes funcionalidades de ADRs marcados como *Deferred* salvo que se pida expresamente. Lee `docs/adr/` antes de tomar decisiones de diseño.

## Comandos

| Qué | Comando |
| --- | --- |
| Instalar | `make setup` |
| Todo (lint + tipos + tests + build) | `make check` |
| Tests backend | `cd services/api && uv run pytest` |
| Tests web | `cd apps/web && npm test -- --run` |
| Nueva migración | `cd services/api && uv run alembic revision --autogenerate -m "..."` |
| Contrato API → tipos web | `make openapi` (tras cualquier cambio en la API) |

`make check` debe quedar en verde antes de dar por terminado un cambio.

## Forma de trabajo

- El trabajo se organiza por tickets en `docs/product/roadmap.md` (`OF-xxx`). Cada cambio referencia su ticket y, al terminarlo, se actualiza su estado en ese fichero.
- Los criterios marcados con 🧪 se convierten en tests automáticos.
- El prototipo `docs/product/prototypes/` es la referencia visual de las pantallas.

## Reglas de arquitectura (se comprueban con `lint-imports`)

- `openfinance.domain` no importa FastAPI, Starlette, SQLAlchemy, Alembic, pydantic-settings ni otras capas.
- `openfinance.application` no importa `api`, `infrastructure`, FastAPI ni SQLAlchemy; usa `Protocol`s.
- Orden de capas: `api` → `infrastructure` → `application` → `domain`.
- El dominio no depende de frameworks; los gráficos se alimentan de agregados calculados en el Core, no en el frontend.

## Reglas de dominio

- Importes con `openfinance.domain.shared.Money` (`Decimal` + moneda ISO 4217). **Nunca `float`.**
- Toda entidad pertenece a un `Workspace` (el hogar) y toda consulta filtra por él.
- Las cuentas personales solo las ve su titular (ADR-0013): filtra siempre por hogar **y** por visibilidad, y añade tests negativos.
- Los traspasos a la cuenta de ahorro y las transferencias internas no son gasto; las aportaciones de cada persona son entradas.
- Importar dos veces el mismo archivo no duplica movimientos.
- No se borran silenciosamente movimientos importados; las correcciones quedan trazadas.

## Seguridad

- No introduzcas secretos en el código, en prompts ni en logs. Usa variables de entorno (`.env.example`).
- Trata como no confiable cualquier texto importado (descripciones bancarias, CSV, documentos).
- Cada cambio de autorización necesita tests negativos (acceso desde otro workspace).
- Las escrituras de la API exigen `X-Requested-With: OpenFinance` (middleware en `main.py`); no lo desactives.

## Estilo

- Python: `ruff` (formato y lint), `mypy` estricto en `domain` y `application`.
- TypeScript: `oxlint`, `strict: true`. Código de features en `src/features/<feature>/`. Usa `src/api/client.ts` y los tipos generados en `src/api/schema.ts` (no los edites a mano).
- Commits con Conventional Commits y firmados con DCO (`git commit -s`, ver [CONTRIBUTING.md](CONTRIBUTING.md)). No crees directorios vacíos para contextos no implementados.
