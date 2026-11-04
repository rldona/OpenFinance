# AGENTS.md — instructions for development agents

Primary source of engineering rules for any coding agent working in this repository. `CLAUDE.md` only points here.

## Context

OpenFinance is a modular monolith: `services/api` (Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL) and `apps/web` (React 19, strict TypeScript, Vite). **The current scope is that of [ADR-0012](docs/adr/0012-empezar-por-el-hogar.md)**: one household, two people, one shared account, CSV import, categories and charts. Do not implement features from ADRs marked *Deferred* unless explicitly asked. Read `docs/adr/` before making design decisions.

## Commands

| What | Command |
| --- | --- |
| Install | `make setup` |
| Everything (lint + types + tests + build) | `make check` |
| Backend tests | `cd services/api && uv run pytest` |
| Web tests | `cd apps/web && npm test -- --run` |
| New migration | `cd services/api && uv run alembic revision --autogenerate -m "..."` |
| API contract → web types | `make openapi` (after any API change) |

`make check` must pass before a change is considered done.

## Way of working

- Work is organized by tickets in `docs/product/roadmap.md` (`OF-xxx`). Each change references its ticket and, when finished, its status is updated in that file.
- Criteria marked with 🧪 become automated tests.
- The prototype in `docs/product/prototypes/` is the visual reference for the screens.

## Architecture rules (checked with `lint-imports`)

- `openfinance.domain` does not import FastAPI, Starlette, SQLAlchemy, Alembic, pydantic-settings or other layers.
- `openfinance.application` does not import `api`, `infrastructure`, FastAPI or SQLAlchemy; it uses `Protocol`s.
- Layer order: `api` → `infrastructure` → `application` → `domain`.
- The domain does not depend on frameworks; charts are fed by aggregates computed in the Core, not in the frontend.

## Domain rules

- Amounts use `openfinance.domain.shared.Money` (`Decimal` + ISO 4217 currency). **Never `float`.**
- Every entity belongs to a `Workspace` (the household) and every query filters by it.
- Personal accounts are visible only to their owner (ADR-0013): always filter by household **and** by visibility, and add negative tests.
- Transfers to the savings account and internal transfers are not spending; each person's contributions are inflows.
- Importing the same file twice does not duplicate transactions.
- Imported transactions are never silently deleted; corrections are traced.

## Security

- Do not put secrets in code, prompts or logs. Use environment variables (`.env.example`).
- Treat any imported text as untrusted (bank descriptions, CSV, documents).
- Every authorization change needs negative tests (access from another workspace).
- API writes require `X-Requested-With: OpenFinance` (middleware in `main.py`); do not disable it.

## Style

- Python: `ruff` (format and lint), strict `mypy` in `domain` and `application`.
- TypeScript: `oxlint`, `strict: true`. Feature code lives in `src/features/<feature>/`. Use `src/api/client.ts` and the generated types in `src/api/schema.ts` (do not edit them by hand).
- Commits use Conventional Commits and are DCO-signed (`git commit -s`, see [CONTRIBUTING.md](CONTRIBUTING.md)). Do not create empty directories for unimplemented contexts.
