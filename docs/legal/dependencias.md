# Licencias de las dependencias

Auditoría de OF-504 para la release v0.1 ([ADR-0008](../adr/0008-licencia-agpl.md)). OpenFinance se distribuye bajo **AGPL-3.0-or-later**; aquí se comprueba que todo lo que se distribuye junto a él tiene una licencia compatible.

- Fecha: 2026-11-01, sobre `services/api/uv.lock` y `apps/web/package-lock.json` de ese día.
- Cómo repetirla: `make licenses` (tablas) y `make licenses CHECK=1` (falla si una dependencia de producción tiene una licencia fuera de la lista permitida). El script es [`deploy/scripts/licenses.sh`](../../deploy/scripts/licenses.sh) y usa [`pip-licenses`](https://pypi.org/project/pip-licenses/) 5.5.5 y [`license-checker-rseidelsohn`](https://www.npmjs.com/package/license-checker-rseidelsohn) 5.0.1.
- CI: el job `licenses` ejecuta `deploy/scripts/licenses.sh --check` en cada push y pull request.
- Las licencias se leen de los metadatos de cada paquete (`--from=mixed` en Python: la expresión SPDX si existe y, si no, los clasificadores). Esto **no** es asesoramiento jurídico: es una revisión de buena fe para un proyecto self-hosted.

## Conclusión

**No hay ninguna licencia incompatible con AGPL-3.0.** Todas las dependencias de producción son permisivas (MIT, BSD, Apache-2.0, ISC, PSF-2.0, Unlicense, MIT-0) o copyleft débil compatible con la familia GPLv3 (psycopg, LGPL-3.0-only). Las de desarrollo no se distribuyen y tampoco plantean problemas. Ninguna dependencia es GPL-2.0-only, SSPL, BUSL, Commons Clause, CC-BY-NC ni propietaria.

Puntos a vigilar, ninguno bloqueante:

| Punto | Por qué es compatible | Qué vigilar |
| --- | --- | --- |
| **psycopg / psycopg-binary** (LGPL-3.0-only) | La LGPL-3.0 es la GPL-3.0 con permisos adicionales, así que se puede combinar con código AGPL-3.0 (AGPL-3.0 §13 permite combinar con GPL-3.0). Se usa sin modificar y como biblioteca. | Si algún día se modifica psycopg, esos cambios se publican bajo LGPL. La wheel `psycopg-binary` incluye `libpq` (PostgreSQL License) y sus bibliotecas C (entre ellas OpenSSL 3, Apache-2.0). |
| **Apache-2.0** (python-multipart, opentelemetry-api, uvloop en doble licencia…) | Compatible con GPLv3/AGPLv3 en un sentido: código Apache-2.0 puede formar parte de una obra AGPL-3.0. | Conservar sus avisos `NOTICE` si se redistribuyen (los conserva la propia instalación de paquetes). |
| **PSF-2.0** (typing_extensions, defusedxml) | La FSF la considera compatible con la GPL. | — |
| **MPL-2.0** (solo en desarrollo: lightningcss, axe-core, certifi y pathspec) | MPL-2.0 §3.3 permite combinarla con GPL/AGPL salvo que el fichero diga «Incompatible With Secondary Licenses», y no lo dice. Además no acaban en lo que se distribuye. | Si alguna pasara a producción, revisar que no lleve esa marca. |
| **Imágenes Docker** (sistema base con componentes GPL) | Desde OF-907 el proyecto publica sus imágenes (`openfinance-api` y `openfinance-web`) en ghcr.io, firmadas; también se pueden construir en local. Junto a los paquetes del sistema (BusyBox, glibc…) son una «agregación» (AGPL-3.0 §5), no una obra derivada. | Al publicar imágenes hay que ofrecer también el código fuente de los componentes GPL de la imagen base: las imágenes base van fijadas por digest (`FROM imagen@sha256:…`), así que ese digest identifica exactamente qué paquetes lleva y su fuente está en los repositorios de Alpine y Debian. Las imágenes llevan las etiquetas OCI `licenses` y `source`, y lista de materiales (SBOM) adjunta. |

La lista permitida de `licenses.sh --check` solo contiene estas licencias. Una dependencia nueva con otra licencia hace fallar CI y obliga a revisarla y a actualizar este documento.

## Python · producción (`services/api`)

Dependencias de runtime de `uv.lock` (`uv export --no-dev`): las que acaban en la imagen de la API. No incluye el grupo `dev`.

| Paquete | Versión | Licencia | Notas |
| --- | --- | --- | --- |
| alembic | 1.20.1 | MIT | |
| annotated-doc | 0.0.5 | MIT | |
| annotated-types | 0.8.0 | MIT | |
| anyio | 4.15.1 | MIT | |
| argon2-cffi | 25.1.0 | MIT | |
| argon2-cffi-bindings | 26.1.0 | MIT | |
| cffi | 2.1.1 | MIT-0 | |
| click | 8.5.0 | BSD-3-Clause | |
| defusedxml | 0.7.1 | PSF-2.0 | |
| dnspython | 2.9.1 | ISC | |
| email-validator | 2.3.0 | Unlicense | |
| et_xmlfile | 2.0.0 | MIT | |
| fastapi | 0.162.0 | MIT | |
| h11 | 0.16.0 | MIT | |
| httptools | 0.9.0 | MIT | |
| idna | 3.20 | BSD-3-Clause | |
| Mako | 1.4.3 | MIT | |
| MarkupSafe | 3.0.4 | BSD-3-Clause | |
| openpyxl | 3.1.5 | MIT | |
| opentelemetry-api | 1.45.2 | Apache-2.0 | dependencia de fastapi |
| psycopg | 3.3.6 | **LGPL-3.0-only** | ver «Puntos a vigilar» |
| psycopg-binary | 3.3.6 | **LGPL-3.0-only** | incluye libpq y sus bibliotecas C |
| pycparser | 3.12 | BSD-3-Clause | |
| pydantic | 2.14.2 | MIT | |
| pydantic_core | 2.50.2 | MIT | |
| pydantic-settings | 2.16.2 | MIT | |
| python-dotenv | 1.2.4 | BSD-3-Clause | |
| python-multipart | 0.0.33 | Apache-2.0 | |
| PyYAML | 6.0.3 | MIT | |
| SQLAlchemy | 2.1.6 | MIT | |
| starlette | 1.10.0 | BSD-3-Clause | |
| typing_extensions | 4.16.0 | PSF-2.0 | |
| typing-inspection | 0.4.4 | MIT | |
| tzdata | 2026.6 | Apache-2.0 | solo en Windows; no entra en la imagen |
| uvicorn | 0.54.0 | BSD-3-Clause | |
| uvloop | 0.23.0 | MIT o Apache-2.0 | doble licencia, a elegir |
| watchfiles | 1.3.0 | MIT | |
| websockets | 17.4 | BSD-3-Clause | |

## npm · producción (`apps/web`)

Lo único que acaba en el JavaScript que se sirve al navegador (`npm ls --omit=dev`):

| Paquete | Versión | Licencia |
| --- | --- | --- |
| react | 19.3.1 | MIT |
| react-dom | 19.3.1 | MIT |
| scheduler | 0.28.0 | MIT |

La web no incluye fuentes, iconos ni imágenes de terceros: usa las fuentes del sistema y el favicon es propio.

## Desarrollo y build (no se distribuyen)

Herramientas que se usan para comprobar y construir, pero que no forman parte de lo que se instala en casa.

**npm (`devDependencies` y sus dependencias, 108 paquetes en macOS arm64).** El número exacto depende de la plataforma, porque algunos binarios son opcionales por sistema.

| Licencia | Paquetes | Ejemplos |
| --- | --- | --- |
| MIT | 87 | vite, vitest, @vitejs/plugin-react, jsdom, oxlint, @testing-library/* |
| Apache-2.0 | 9 | typescript, @playwright/test, playwright, aria-query |
| MIT-0 | 2 | @csstools/color-helpers |
| BSD-2-Clause | 2 | entities, webidl-conversions |
| BSD-3-Clause | 2 | source-map-js, tough-cookie |
| ISC | 2 | picocolors, saxes |
| MPL-2.0 | 3 | lightningcss, axe-core |
| BlueOak-1.0.0 | 1 | lru-cache |
| CC0-1.0 | 1 | mdn-data |

`npm run gen:api` descarga además `openapi-typescript` (MIT). Los navegadores que instala Playwright solo se usan en CI.

**Python (grupo `dev`).** pytest, pytest-cov, mypy, ruff, httpx y sus dependencias: MIT, BSD, Apache-2.0 y MPL-2.0 (certifi, pathspec); import-linter y grimp, BSD; `types-openpyxl`, Apache-2.0.

## Imágenes Docker

| Imagen | Uso | Licencia del software principal | Sistema base |
| --- | --- | --- | --- |
| `postgres:16-alpine` | base de datos (`compose.yaml`, CI) | PostgreSQL License (permisiva, tipo BSD/MIT) | Alpine |
| `nginx:1.30-alpine` | sirve la web y hace de proxy (`web.Dockerfile`) | BSD-2-Clause | Alpine |
| `python:3.12-slim` | API (`api.Dockerfile`) | PSF-2.0 | Debian |
| `ghcr.io/astral-sh/uv:0.8` | solo se copia el binario `uv` en la imagen de la API | MIT o Apache-2.0 | — |
| `node:24-alpine` | solo la etapa de build de la web; no está en la imagen final | MIT (con componentes de terceros bajo licencias permisivas) | Alpine |
| `caddy:2.10-alpine` | HTTPS opcional (`compose.https.yaml`) | Apache-2.0 | Alpine |

Las imágenes Alpine y Debian contienen paquetes del sistema con sus propias licencias (BusyBox y Bash son GPL; musl es MIT; glibc es LGPL…). Van como programas separados dentro del contenedor, sin enlazarse con OpenFinance.
