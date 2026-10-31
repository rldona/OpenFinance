# ADR-0006: Módulos oficiales primero; SDK público después

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

Diseñar un SDK de extensiones antes de tener módulos reales suele producir contratos incompletos que luego no se pueden cambiar sin romper a terceros.

## Decisión

- Los primeros módulos (categorización, presupuestos) son oficiales y viven en `openfinance.modules`.
- Implementan un contrato interno versionado: identidad y versión, compatibilidad con el Core, capacidades, permisos solicitados, herramientas y eventos que publican o consumen, configuración, migraciones y ciclo de vida.
- Un módulo no tiene acceso global a datos: recibe solo los permisos declarados y aprobados.
- No se ejecuta código de terceros en el proceso principal.

## Consecuencias

- El SDK público se diseñará a partir de al menos dos módulos oficiales reales.
- Las extensiones de terceros, cuando lleguen, se aislarán en procesos separados o en un runtime con capacidades limitadas.
