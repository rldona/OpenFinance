# ADR-0003: PostgreSQL como almacenamiento principal

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

Necesitamos transacciones ACID, integridad referencial, tipos `NUMERIC` exactos y un único motor que funcione igual en local y en servidor.

## Decisión

PostgreSQL 16 como base de datos, SQLAlchemy 2 como ORM y Alembic para migraciones. Las restricciones usan una convención de nombres fija (`infrastructure/db/base.py`). Los importes se guardan como `NUMERIC` con la moneda en columna aparte.

## Consecuencias

- La instalación local usa PostgreSQL empaquetado en Docker Compose.
- SQLite queda como posible adaptador futuro, no como requisito.
- CI aplica las migraciones sobre PostgreSQL real y ejecuta `alembic check`.
