# ADR-0001: Modular monolith as the initial architecture

- Status: Accepted
- Date: 2026-10-31

## Context

OpenFinance has several domain contexts (identity, workspaces, ledger, categorization, budgeting, imports, manager, approvals, modules, audit) and a small team. Microservices would multiply operational cost and complicate financial transactions, which need strong consistency.

## Decision

A single deployable Python application (`services/api`) with contexts separated by packages and layers (`domain`, `application`, `infrastructure`, `api`). Dependencies between layers are enforced in CI with `import-linter`. The Manager worker will be a separate process that reuses the same application code.

## Consequences

- Lower development, testing and operating cost; transactions local to the database.
- Requires discipline: a context only uses another through its application interface, never through its tables.
- A context can be extracted into a service when a measured operational need exists.
