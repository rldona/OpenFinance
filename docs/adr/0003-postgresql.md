# ADR-0003: PostgreSQL as the main storage

- Status: Accepted
- Date: 2026-10-31

## Context

We need ACID transactions, referential integrity, exact `NUMERIC` types and a single engine that behaves the same locally and on a server.

## Decision

PostgreSQL 16 as the database, SQLAlchemy 2 as the ORM and Alembic for migrations. Constraints use a fixed naming convention (`infrastructure/db/base.py`). Amounts are stored as `NUMERIC` with the currency in a separate column.

## Consequences

- The local installation uses PostgreSQL packaged in Docker Compose.
- SQLite remains a possible future adapter, not a requirement.
- CI applies the migrations on a real PostgreSQL and runs `alembic check`.
