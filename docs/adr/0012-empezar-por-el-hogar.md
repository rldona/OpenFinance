# ADR-0012: Start with the household

- Status: Accepted
- Date: 2026-10-31

## Context

The initial design proposed a multi-user platform with roles, modules, a Manager with AI agents, approvals and shared profiles with expense splitting. That is too much to start with. The real need is more concrete: **a couple with a joint account** wants to know how much they spend, on what, and how to save better, seeing it as graphically as possible.

## Decision

v0.1 is a personal finance manager **for one household**:

- **One household** (one `Workspace`), **two people** with full access and **one joint account**. Accounts, such as the savings one, can be added later.
- Transactions come in by **importing the bank's CSV**, with deduplication.
- **Categories** with rules that are learned when a transaction is corrected.
- **Visualization**: current month, spending by category and merchant, 12-month evolution, budgets per category, savings goals and savings ideas calculated from the data itself.
- Each person's contributions to the joint account are inflows and transfers to the savings account are savings, not spending.

The foundations that add no complexity for the user are kept: framework-free domain (ADR-0001), PostgreSQL (ADR-0003), `Money` without `float`, local or own-server execution (ADR-0007), OpenAPI (ADR-0009) and a single installation (ADR-0010).

### Deferred

| ADR | What is left for later |
| --- | --- |
| 0002 | `Workspace` is kept as the data boundary, but without roles or per-account permissions: both members can do everything. |
| 0004, 0005 | Manager with AI agents, proposals and approvals. The v0.1 "savings ideas" ("ideas para ahorrar") are deterministic calculations, with no LLM. |
| 0006 | Modules and SDK. The code is organized by contexts, with no module registry. |
| 0011 | Shared profiles with expense splitting and settlements. |

None of these decisions is discarded: they will be revisited once the base is in use.

## Consequences

- The MVP can be finished much sooner and tested with the household's real data.
- The model keeps `workspace_id` on every entity so it can grow without painful migrations.
- The savings ideas must explain where each figure comes from (transactions and period).
- The prototype of the full platform is kept in `docs/product/prototypes/archive-plataforma/` as a reference.
