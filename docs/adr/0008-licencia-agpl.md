# ADR-0008: AGPL-3.0 como licencia de distribución

- Estado: Accepted
- Fecha: 2026-10-31 (propuesto) · 2026-11-01 (aceptado, OF-504)

## Contexto

Queremos que las mejoras de OpenFinance sigan siendo abiertas, también cuando alguien lo ofrezca como servicio de red.

Antes de aceptarlo quedaban pendientes cuatro cosas: auditar las licencias de las dependencias, elegir la política de contribuciones (DCO o CLA), valorar las implicaciones para servicios comerciales y extensiones, y decidir sobre el texto de la licencia y las cabeceras SPDX.

## Decisión

1. **Licencia: AGPL-3.0-or-later.** El texto literal de la GNU Affero General Public License v3, descargado de <https://www.gnu.org/licenses/agpl-3.0.txt>, está en [`LICENSE`](../../LICENSE). Los metadatos lo declaran con su identificador SPDX: `license = "AGPL-3.0-or-later"` en `services/api/pyproject.toml` y `"license": "AGPL-3.0-or-later"` en `apps/web/package.json`.
2. **Dependencias compatibles.** La auditoría de OF-504 ([docs/legal/dependencias.md](../legal/dependencias.md)) no encontró ninguna licencia incompatible. Solo hay licencias permisivas y psycopg (LGPL-3.0-only, compatible con la familia GPLv3). CI comprueba en cada cambio que las dependencias de producción siguen dentro de esa lista (`make licenses CHECK=1`).
3. **Contribuciones con DCO, sin CLA.** Cada commit lleva `Signed-off-by:` (`git commit -s`) y con ello quien contribuye certifica el [Developer Certificate of Origin 1.1](https://developercertificate.org/). No se pide ceder derechos ni firmar un CLA: cada contribución entra bajo la misma AGPL-3.0-or-later. Detalles en [CONTRIBUTING.md](../../CONTRIBUTING.md).
4. **Sin cabeceras SPDX por fichero.** La licencia se declara una sola vez, en `LICENSE` y en los metadatos de los paquetes. Esto vale para todo el repositorio salvo que un fichero diga otra cosa.

## Consecuencias

- Copyleft fuerte: quien modifique OpenFinance y lo ofrezca por red debe ofrecer el código de sus cambios a quienes lo usan (AGPL-3.0 §13).
- Un hogar que lo instala en casa sin modificarlo no tiene ninguna obligación adicional.
- El uso comercial está permitido en las mismas condiciones. Puede reducir la adopción por parte de empresas que evitan la AGPL.
- Sin CLA, el proyecto no puede relicenciar ni ofrecer licencias comerciales sin el permiso de cada autor. Es una decisión consciente: nadie concentra derechos que el resto no tenga.
- «or-later» permite usar el código bajo versiones futuras de la AGPL que publique la FSF.
- Las extensiones de terceros (ADR-0006, aplazado) se decidirán cuando haya SDK. Mientras tanto, un módulo que se integre en el proceso de la API o en el bundle de la web forma parte de la obra y queda bajo AGPL.
- Si en el futuro se publican imágenes Docker, hay que ofrecer también el código fuente de los componentes GPL de su sistema base (ver la auditoría).
