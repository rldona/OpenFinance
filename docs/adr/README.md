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
| [0008](0008-licencia-agpl.md) | AGPL-3.0 como licencia de distribución | Accepted |
| [0009](0009-openapi-contrato.md) | OpenAPI como contrato entre frontend y backend | Proposed |
| [0010](0010-sin-sincronizacion-mvp.md) | Sin sincronización bidireccional en el MVP | Proposed |
| [0011](0011-perfiles-compartidos-reparto.md) | Perfiles compartidos y reparto de gastos | Deferred (0012) |
| [0012](0012-empezar-por-el-hogar.md) | Empezar por el hogar | Accepted |
| [0013](0013-cuentas-personales-privadas.md) | Cuentas personales en el hogar, privadas por defecto | Accepted |
| [0014](0014-graficos-svg-propios.md) | Gráficos SVG propios en React | Accepted |
| [0015](0015-patrones-por-persona-y-xlsx.md) | Patrones de aportación por persona y extractos en Excel | Accepted |
| [0016](0016-exposicion-y-copias.md) | Exposición en casa, copias de seguridad y exportación | Accepted |
| [0017](0017-registro-de-cambios.md) | Registro de cambios con deshacer y rehacer | Accepted |
| [0018](0018-libro-contable-completo.md) | Alcance del libro contable completo | Accepted |
| [0019](0019-varias-monedas.md) | Varias monedas | Accepted |
| [0020](0020-motor-de-reglas-e-importacion-universal.md) | Motor de reglas con condiciones e importación universal | Accepted |
| [0021](0021-pagos-programados-y-prevision.md) | Pagos programados, previsión de saldo y «hoy podéis gastar» | Accepted |
| [0022](0022-presupuestos-con-limites-o-sobres.md) | Presupuestos con límites o sobres, arrastre y objetivos v2 | Accepted |
| [0023](0023-avisos-y-notificaciones.md) | Avisos deterministas, notificaciones Web Push y resumen semanal | Accepted |
| [0024](0024-conexion-con-el-banco.md) | Conexión con el banco mediante un agregador PSD2 | Accepted |
| [0025](0025-informes-y-patrimonio.md) | Patrimonio neto, flujo de caja, informes a medida y exportación v2 | Accepted |
| [0026](0026-hogar-ampliado.md) | Hogar ampliado: más personas con roles, reparto de gastos y eventos | Accepted |
