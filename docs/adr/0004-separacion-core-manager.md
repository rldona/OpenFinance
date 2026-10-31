# ADR-0004: Separación entre Core y Manager

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

El Manager usa LLMs, que pueden equivocarse o ser manipulados mediante inyección de instrucciones (por ejemplo, desde la descripción de un movimiento bancario importado). Las reglas financieras deben seguir siendo correctas pase lo que pase en esa capa.

## Decisión

- El Core (dominio + aplicación) no depende de ningún proveedor de IA y funciona sin él.
- El Manager solo actúa a través de un **Tool Gateway** con herramientas tipadas (`transactions.search`, `budgets.get_status`, `transactions.propose_category`…), cada una con esquema de argumentos, permiso requerido y límite de alcance.
- El Manager nunca tiene credenciales de base de datos ni ejecuta SQL.
- Los permisos se evalúan en el gateway con la identidad del usuario que inició la tarea; el modelo no puede ampliarlos.
- Las cifras de las respuestas proceden de resultados de herramientas, que se guardan con la ejecución (`AgentRun`).

## Consecuencias

- Cada capacidad nueva del Manager exige definir antes su herramienta en el Core.
- El proveedor de LLM es intercambiable mediante un adaptador.
- Los datos externos se pasan al modelo como contenido marcado, nunca como instrucciones.
