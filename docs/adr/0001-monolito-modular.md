# ADR-0001: Monolito modular como arquitectura inicial

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

OpenFinance tiene varios contextos de dominio (identity, workspaces, ledger, categorization, budgeting, imports, manager, approvals, modules, audit) y un equipo pequeño. Microservicios multiplicarían el coste operativo y complicarían las transacciones financieras, que necesitan consistencia fuerte.

## Decisión

Una única aplicación desplegable en Python (`services/api`) con contextos separados por paquetes y capas (`domain`, `application`, `infrastructure`, `api`). Las dependencias entre capas se hacen cumplir en CI con `import-linter`. El worker del Manager será un proceso aparte que reutiliza el mismo código de aplicación.

## Consecuencias

- Menor coste de desarrollo, pruebas y operación; transacciones locales a la base de datos.
- Exige disciplina: un contexto solo usa otro a través de su interfaz de aplicación, nunca de sus tablas.
- Un contexto se podrá extraer a un servicio cuando exista una necesidad operativa medida.
