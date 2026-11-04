# Architecture Decision Records

Format: context → decision → consequences. An accepted ADR is not edited; it is replaced by a new one that marks it as *Superseded*.

**Current starting point: [ADR-0012](0012-empezar-por-el-hogar.md).** ADRs marked *Deferred* remain the future direction but are not part of v0.1.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-monolito-modular.md) | Modular monolith as the initial architecture | Accepted |
| [0002](0002-workspace-frontera-aislamiento.md) | Workspace as the isolation boundary | Accepted (simplified by 0012) |
| [0003](0003-postgresql.md) | PostgreSQL as the main storage | Accepted |
| [0004](0004-separacion-core-manager.md) | Separation between Core and Manager | Deferred (0012) |
| [0005](0005-aprobacion-humana.md) | Human approval for operations prepared by agents | Deferred (0012) |
| [0006](0006-modulos-oficiales-primero.md) | Official modules first; public SDK later | Deferred (0012) |
| [0007](0007-local-first-self-hosted.md) | Local-first and self-hosted with optional external services | Accepted |
| [0008](0008-licencia-agpl.md) | AGPL-3.0 as the distribution license | Accepted |
| [0009](0009-openapi-contrato.md) | OpenAPI as the contract between frontend and backend | Proposed |
| [0010](0010-sin-sincronizacion-mvp.md) | No bidirectional sync in the MVP | Proposed |
| [0011](0011-perfiles-compartidos-reparto.md) | Shared profiles and expense splitting | Deferred (0012) |
| [0012](0012-empezar-por-el-hogar.md) | Start with the household | Accepted |
| [0013](0013-cuentas-personales-privadas.md) | Personal accounts in the household, private by default | Accepted |
| [0014](0014-graficos-svg-propios.md) | Custom SVG charts in React | Accepted |
| [0015](0015-patrones-por-persona-y-xlsx.md) | Per-person contribution patterns and Excel statements | Accepted |
| [0016](0016-exposicion-y-copias.md) | Home exposure, backups and export | Accepted |
| [0017](0017-registro-de-cambios.md) | Change log with undo and redo | Accepted |
| [0018](0018-libro-contable-completo.md) | Scope of the full ledger | Accepted |
| [0019](0019-varias-monedas.md) | Multiple currencies | Accepted |
| [0020](0020-motor-de-reglas-e-importacion-universal.md) | Rules engine with conditions and universal import | Accepted |
| [0021](0021-pagos-programados-y-prevision.md) | Scheduled payments, balance forecast and "hoy podéis gastar" (you can spend today) | Accepted |
| [0022](0022-presupuestos-con-limites-o-sobres.md) | Budgets with limits or envelopes, carry-over and goals v2 | Accepted |
| [0023](0023-avisos-y-notificaciones.md) | Deterministic alerts, Web Push notifications and weekly summary | Accepted |
| [0024](0024-conexion-con-el-banco.md) | Bank connection through a PSD2 aggregator | Accepted |
| [0025](0025-informes-y-patrimonio.md) | Net worth, cash flow, custom reports and export v2 | Accepted |
| [0026](0026-hogar-ampliado.md) | Extended household: more people with roles, expense splitting and events | Accepted |
