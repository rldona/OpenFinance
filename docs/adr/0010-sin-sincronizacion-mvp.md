# ADR-0010: Sin sincronización bidireccional en el MVP

- Estado: Proposed
- Fecha: 2026-10-31

## Contexto

Sincronizar réplicas entre dispositivos exige resolver conflictos, identidades de dispositivo, cifrado, revocación y recuperación. Es un proyecto en sí mismo.

## Decisión propuesta

En v0.1 cada instalación tiene una única fuente de verdad. El acceso desde otros dispositivos se hace por la web autenticada del servidor.

## Consecuencias

- No se resuelven conflictos entre réplicas en el MVP.
- Se conservan desde ya identificadores estables (UUID) y procedencia de los datos para facilitar una sincronización futura.
- La exportación completa de datos cubre la portabilidad mientras tanto.
