# ADR-0008: AGPL-3.0 como licencia de distribución

- Estado: Proposed
- Fecha: 2026-10-31

## Contexto

Queremos que las mejoras de OpenFinance sigan siendo abiertas, también cuando alguien lo ofrezca como servicio de red.

## Decisión propuesta

Publicar bajo **AGPL-3.0-or-later**. Los metadatos de los paquetes ya lo declaran (`pyproject.toml`, `package.json`).

## Pendiente antes de aceptar

- Auditar las licencias de las dependencias y su compatibilidad con AGPL.
- Definir la política de contribuciones (DCO o CLA).
- Revisar las implicaciones para posibles servicios comerciales y para extensiones de terceros.
- Añadir el texto completo en `LICENSE` y las cabeceras SPDX.

## Consecuencias

- Copyleft fuerte: quien modifique y ofrezca el software por red debe publicar sus cambios.
- Puede reducir la adopción por parte de empresas que evitan la AGPL.
