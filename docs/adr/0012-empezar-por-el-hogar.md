# ADR-0012: Empezar por el hogar

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

El diseño inicial planteaba una plataforma multiusuario con roles, módulos, un Manager con agentes de IA, aprobaciones y perfiles compartidos con reparto de gastos. Es demasiado para empezar. La necesidad real es más concreta: **una pareja con una cuenta común** quiere saber cuánto gasta, en qué y cómo ahorrar mejor, viéndolo de la forma más gráfica posible.

## Decisión

v0.1 es un gestor económico **para un hogar**:

- **Un hogar** (un `Workspace`), **dos personas** con acceso completo y **una cuenta común**. Más adelante se pueden añadir cuentas, como la de ahorro.
- Los movimientos entran **importando el CSV del banco**, con deduplicación.
- **Categorías** con reglas que se aprenden al corregir un movimiento.
- **Visualización**: mes actual, gasto por categoría y comercio, evolución de 12 meses, presupuestos por categoría, objetivos de ahorro e ideas de ahorro calculadas a partir de los propios datos.
- Las aportaciones de cada persona a la cuenta común son entradas y los traspasos a la cuenta de ahorro son ahorro, no gasto.

Se mantienen las bases que no añaden complejidad al usuario: dominio sin frameworks (ADR-0001), PostgreSQL (ADR-0003), `Money` sin `float`, ejecución local o en servidor propio (ADR-0007), OpenAPI (ADR-0009) y una sola instalación (ADR-0010).

### Aplazado

| ADR | Qué queda para más adelante |
| --- | --- |
| 0002 | Se mantiene `Workspace` como frontera de datos, pero sin roles ni permisos por cuenta: los dos miembros pueden hacer todo. |
| 0004, 0005 | Manager con agentes de IA, propuestas y aprobaciones. Las «ideas para ahorrar» de v0.1 son cálculos deterministas, sin LLM. |
| 0006 | Módulos y SDK. El código se organiza por contextos, sin registro de módulos. |
| 0011 | Perfiles compartidos con reparto de gastos y liquidaciones. |

Ninguna de estas decisiones se descarta: se retomarán cuando la base esté en uso.

## Consecuencias

- El MVP se puede terminar mucho antes y probar con datos reales del hogar.
- El modelo conserva `workspace_id` en cada entidad para poder crecer sin migraciones dolorosas.
- Las ideas de ahorro deben explicar de dónde sale cada cifra (movimientos y periodo).
- El prototipo de la plataforma completa se conserva en `docs/product/prototypes/archive-plataforma/` como referencia.
