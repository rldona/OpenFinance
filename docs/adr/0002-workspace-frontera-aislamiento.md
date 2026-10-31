# ADR-0002: Workspace como frontera de aislamiento

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

OpenFinance es multiusuario desde el inicio: una persona puede tener finanzas propias y compartir otras con su familia. La fuga de datos entre usuarios es el riesgo prioritario del producto.

## Decisión

- `User` es la identidad global; `Workspace` es el contexto financiero y la frontera de acceso; `Membership` une ambos con un rol (`owner`, `editor`, `viewer`).
- Toda entidad financiera tiene `workspace_id` no nulo.
- La autorización se decide en el servidor combinando membresía, rol, recurso y acción. El rol es el punto de partida, no la única regla: `AccountAccess` permite restringir cuentas concretas.
- Una cuenta compartida debe serlo de forma explícita.
- Las mismas comprobaciones aplican a la API, a las tareas asíncronas, a las exportaciones y a las herramientas del Manager.

## Consecuencias

- Todos los casos de uso reciben un contexto de autorización (actor + workspace).
- Los repositorios filtran siempre por workspace; se añaden tests negativos que manipulan identificadores entre workspaces.
- Se valorará Row-Level Security de PostgreSQL como defensa en profundidad, no como sustituto.
