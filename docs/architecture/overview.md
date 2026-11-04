# Architecture

Current scope: [ADR-0012 · Start with the household](../adr/0012-empezar-por-el-hogar.md).

## Logical view (v0.1)

```
┌───────────────────────────────────────────────────────────┐
│ apps/web — React + TypeScript                             │
│ Este mes · ¿En qué gastamos? · Evolución · Ahorrar · …    │
└───────────────────────────┬───────────────────────────────┘
                            │ REST /api/v1 (OpenAPI)
┌───────────────────────────▼───────────────────────────────┐
│ services/api — OpenFinance Core (modular monolith)        │
│  api/            HTTP → use cases                         │
│  application/    use cases, ports (Protocols)             │
│  domain/         household, ledger, categories… (pure)    │
│  infrastructure/ SQLAlchemy, config, CSV reader           │
└───────────────────────────┬───────────────────────────────┘
                     ┌──────▼──────┐
                     │ PostgreSQL  │
                     └─────────────┘
```

A single process for the API and a single frontend. No workers, queues or AI in v0.1.

UI screens in the diagram (the app UI is in Spanish): "Este mes" (This month), "¿En qué gastamos?" (What do we spend on?), "Evolución" (Trends), "Ahorrar" (Save).

## Domain contexts (v0.1)

| Context | Responsibility |
| --- | --- |
| identity | The household's two people and sign-in |
| workspaces | The household: data boundary (`workspace_id` everywhere) |
| ledger | Accounts and transactions: contributions, expenses and transfers to savings |
| categorization | Categories per household and rules learned per merchant (household or personal) |
| budgeting | Monthly budgets per category |
| imports | Reading bank CSVs, normalization and deduplication |
| insights | Aggregates for charts, savings goals, ideas and simulator |

The list lives in `openfinance.domain.BOUNDED_CONTEXTS` and is exposed at `GET /api/v1/meta`.

Deferred (ADR-0012): `manager`, `approvals`, `modules`, `sharing` and advanced `audit`.

## Dependency rules

Enforced with `import-linter` (`services/api/pyproject.toml`):

- `api → infrastructure → application → domain` (downward only).
- `domain` has no frameworks; `application` has no HTTP or ORM.

## Money rules

- `Money` = `Decimal` + `Currency` ISO 4217, quantized to cents; rejects `float`.
- Transaction types: **contribution** (goes into the shared account), **expense** (with a category), **transfer to savings** (not an expense).
- Accounts: joint (Revolut) and savings pots visible to the household; personal (Bankinter) visible only to their owner ([ADR-0013](../adr/0013-cuentas-personales-privadas.md)).
- Each transaction stores its normalized merchant (`merchant`) so rules can be applied without recomputing it.
- Server-side sessions: `HttpOnly` cookie with a random token of which only the hash is stored; passwords use Argon2id.
- Effective date ≠ import date; each imported transaction keeps its source file.
- Deduplication by external identifier when the bank provides one; otherwise by a fingerprint of date, amount and normalized description.
- Charts are computed in the Core (`domain/insights.py`) using only the joint account and savings pots; the frontend only renders, with its own SVG components ([ADR-0014](../adr/0014-graficos-svg-propios.md)).
