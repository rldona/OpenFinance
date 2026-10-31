# Architecture Decision Records

Formato: contexto → decisión → consecuencias. Un ADR aceptado no se edita; se sustituye por otro nuevo que lo marque como *Superseded*.

**Punto de partida actual: [ADR-0012](0012-empezar-por-el-hogar.md).** Los ADRs marcados como *Deferred* siguen siendo la dirección de futuro, pero no forman parte de v0.1.

| ADR | Título | Estado |
| --- | --- | --- |
| [0001](0001-monolito-modular.md) | Monolito modular como arquitectura inicial | Accepted |
| [0002](0002-workspace-frontera-aislamiento.md) | Workspace como frontera de aislamiento | Accepted (simplificado por 0012) |
| [0003](0003-postgresql.md) | PostgreSQL como almacenamiento principal | Accepted |
| [0004](0004-separacion-core-manager.md) | Separación entre Core y Manager | Deferred (0012) |
| [0005](0005-aprobacion-humana.md) | Aprobación humana para operaciones preparadas por agentes | Deferred (0012) |
| [0006](0006-modulos-oficiales-primero.md) | Módulos oficiales primero; SDK público después | Deferred (0012) |
| [0007](0007-local-first-self-hosted.md) | Local-first y self-hosted con servicios externos opcionales | Accepted |
| [0008](0008-licencia-agpl.md) | AGPL-3.0 como licencia de distribución | Proposed |
| [0009](0009-openapi-contrato.md) | OpenAPI como contrato entre frontend y backend | Proposed |
| [0010](0010-sin-sincronizacion-mvp.md) | Sin sincronización bidireccional en el MVP | Proposed |
| [0011](0011-perfiles-compartidos-reparto.md) | Perfiles compartidos y reparto de gastos | Deferred (0012) |
| [0012](0012-empezar-por-el-hogar.md) | Empezar por el hogar | Accepted |
| [0013](0013-cuentas-personales-privadas.md) | Cuentas personales en el hogar, privadas por defecto | Accepted |
