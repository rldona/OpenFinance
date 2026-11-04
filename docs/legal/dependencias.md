# Dependency licenses

OF-504 audit for the v0.1 release ([ADR-0008](../adr/0008-licencia-agpl.md)). OpenFinance is distributed under **AGPL-3.0-or-later**; this document checks that everything distributed alongside it has a compatible license.

- Date: 2026-11-01, based on that day's `services/api/uv.lock` and `apps/web/package-lock.json`.
- How to repeat it: `make licenses` (tables) and `make licenses CHECK=1` (fails if a production dependency has a license outside the allowed list). The script is [`deploy/scripts/licenses.sh`](../../deploy/scripts/licenses.sh) and uses [`pip-licenses`](https://pypi.org/project/pip-licenses/) 5.5.5 and [`license-checker-rseidelsohn`](https://www.npmjs.com/package/license-checker-rseidelsohn) 5.0.1.
- CI: the `licenses` job runs `deploy/scripts/licenses.sh --check` on every push and pull request.
- Licenses are read from each package's metadata (`--from=mixed` in Python: the SPDX expression if present, otherwise the classifiers). This is **not** legal advice: it is a good-faith review for a self-hosted project.

## Conclusion

**No license is incompatible with AGPL-3.0.** All production dependencies are permissive (MIT, BSD, Apache-2.0, ISC, PSF-2.0, Unlicense, MIT-0) or weak copyleft compatible with the GPLv3 family (psycopg, LGPL-3.0-only; pywebpush, py-vapid and certifi, MPL-2.0). Development ones are not distributed and raise no issues either. No dependency is GPL-2.0-only, SSPL, BUSL, Commons Clause, CC-BY-NC or proprietary.

Points to watch, none blocking:

| Point | Why it is compatible | What to watch |
| --- | --- | --- |
| **psycopg / psycopg-binary** (LGPL-3.0-only) | LGPL-3.0 is GPL-3.0 with additional permissions, so it can be combined with AGPL-3.0 code (AGPL-3.0 §13 allows combining with GPL-3.0). It is used unmodified and as a library. | If psycopg is ever modified, those changes are published under LGPL. The `psycopg-binary` wheel includes `libpq` (PostgreSQL License) and its C libraries (among them OpenSSL 3, Apache-2.0). |
| **Apache-2.0** (python-multipart, opentelemetry-api, uvloop under dual license…) | Compatible with GPLv3/AGPLv3 in one direction: Apache-2.0 code can be part of an AGPL-3.0 work. | Keep their `NOTICE` notices if redistributed (the package installation itself keeps them). |
| **PSF-2.0** (typing_extensions, defusedxml) | The FSF considers it compatible with the GPL. | — |
| **MPL-2.0** (production: pywebpush, py-vapid and certifi; development: lightningcss, axe-core and pathspec) | MPL-2.0 §3.3 allows combining it with GPL/AGPL unless the file says "Incompatible With Secondary Licenses", and it does not. It is file-level copyleft: they are used unmodified, as libraries. | If any of those packages is modified, the changes to their files are published under MPL-2.0. |
| **Docker images** (base system with GPL components) | Since OF-907 the project publishes its images (`openfinance-api` and `openfinance-web`) on ghcr.io, signed; they can also be built locally. Together with the system packages (BusyBox, glibc…) they are an "aggregate" (AGPL-3.0 §5), not a derivative work. | When publishing images, the source code of the GPL components in the base image must also be offered: base images are pinned by digest (`FROM image@sha256:…`), so that digest identifies exactly which packages it contains and their source is in the Alpine and Debian repositories. The images carry the OCI labels `licenses` and `source`, and an attached bill of materials (SBOM). |

The allowed list of `licenses.sh --check` contains only these licenses. A new dependency with any other license makes CI fail and requires reviewing it and updating this document.

## Python · production (`services/api`)

Runtime dependencies from `uv.lock` (`uv export --no-dev`): those that end up in the API image. It does not include the `dev` group.

| Package | Version | License | Notes |
| --- | --- | --- | --- |
| aiohappyeyeballs | 2.7.1 | PSF-2.0 | |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT | |
| aiosignal | 1.4.0 | Apache-2.0 | |
| alembic | 1.20.1 | MIT | |
| annotated-doc | 0.0.5 | MIT | |
| annotated-types | 0.8.0 | MIT | |
| anyio | 4.15.1 | MIT | |
| argon2-cffi | 25.1.0 | MIT | |
| argon2-cffi-bindings | 26.1.0 | MIT | |
| attrs | 26.1.0 | MIT | |
| certifi | 2026.10.23 | MPL-2.0 | see "Points to watch" |
| cffi | 2.1.1 | MIT-0 | |
| charset-normalizer | 3.5.2 | MIT | |
| click | 8.5.0 | BSD-3-Clause | |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | |
| defusedxml | 0.7.1 | PSF-2.0 | |
| dnspython | 2.9.1 | ISC | |
| email-validator | 2.3.0 | Unlicense | |
| et_xmlfile | 2.0.0 | MIT | |
| fastapi | 0.162.0 | MIT | |
| frozenlist | 1.8.0 | Apache-2.0 | |
| h11 | 0.16.0 | MIT | |
| http_ece | 1.2.1 | MIT | |
| httptools | 0.9.0 | MIT | |
| idna | 3.20 | BSD-3-Clause | |
| Mako | 1.4.3 | MIT | |
| MarkupSafe | 3.0.4 | BSD-3-Clause | |
| multidict | 7.2.1 | Apache-2.0 | |
| openpyxl | 3.1.5 | MIT | |
| opentelemetry-api | 1.45.2 | Apache-2.0 | dependency of fastapi |
| propcache | 0.5.4 | Apache-2.0 | |
| psycopg | 3.3.6 | **LGPL-3.0-only** | see "Points to watch" |
| psycopg-binary | 3.3.6 | **LGPL-3.0-only** | includes libpq and its C libraries |
| py-vapid | 1.9.6 | MPL-2.0 | see "Points to watch" |
| pycparser | 3.12 | BSD-3-Clause | |
| pydantic | 2.14.2 | MIT | |
| pydantic_core | 2.50.2 | MIT | |
| pydantic-settings | 2.16.2 | MIT | |
| python-dotenv | 1.2.4 | BSD-3-Clause | |
| python-multipart | 0.0.33 | Apache-2.0 | |
| pywebpush | 2.5.0 | MPL-2.0 | see "Points to watch" |
| PyYAML | 6.0.3 | MIT | |
| requests | 2.34.2 | Apache-2.0 | |
| SQLAlchemy | 2.1.6 | MIT | |
| starlette | 1.10.0 | BSD-3-Clause | |
| typing_extensions | 4.16.0 | PSF-2.0 | |
| typing-inspection | 0.4.4 | MIT | |
| tzdata | 2026.6 | Apache-2.0 | Windows only; not in the image |
| urllib3 | 2.8.0 | MIT | |
| uvicorn | 0.54.0 | BSD-3-Clause | |
| uvloop | 0.23.0 | MIT or Apache-2.0 | dual license, your choice |
| watchfiles | 1.3.0 | MIT | |
| websockets | 17.4 | BSD-3-Clause | |
| yarl | 1.25.1 | Apache-2.0 | |

## npm · production (`apps/web`)

The only things that end up in the JavaScript served to the browser (`npm ls --omit=dev`):

| Package | Version | License |
| --- | --- | --- |
| react | 19.3.1 | MIT |
| react-dom | 19.3.1 | MIT |
| scheduler | 0.28.0 | MIT |

The web app includes no third-party fonts, icons or images: it uses system fonts and the favicon is our own.

## Development and build (not distributed)

Tools used to check and build, but not part of what is installed at home.

**npm (`devDependencies` and their dependencies, 108 packages on macOS arm64).** The exact number depends on the platform, because some binaries are optional per system.

| License | Packages | Examples |
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

`npm run gen:api` also downloads `openapi-typescript` (MIT). The browsers Playwright installs are only used in CI.

**Python (`dev` group).** pytest, pytest-cov, mypy, ruff, httpx and their dependencies: MIT, BSD, Apache-2.0 and MPL-2.0 (pathspec); import-linter and grimp, BSD; `types-openpyxl`, Apache-2.0.

## Docker images

| Image | Use | License of the main software | Base system |
| --- | --- | --- | --- |
| `postgres:16-alpine` | database (`compose.yaml`, CI) | PostgreSQL License (permissive, BSD/MIT-like) | Alpine |
| `nginx:1.30-alpine` | serves the web app and acts as proxy (`web.Dockerfile`) | BSD-2-Clause | Alpine |
| `python:3.12-slim` | API (`api.Dockerfile`) | PSF-2.0 | Debian |
| `ghcr.io/astral-sh/uv:0.8` | only the `uv` binary is copied into the API image | MIT or Apache-2.0 | — |
| `node:24-alpine` | only the web build stage; not in the final image | MIT (with third-party components under permissive licenses) | Alpine |
| `caddy:2.10-alpine` | optional HTTPS (`compose.https.yaml`) | Apache-2.0 | Alpine |

The Alpine and Debian images contain system packages with their own licenses (BusyBox and Bash are GPL; musl is MIT; glibc is LGPL…). They run as separate programs inside the container, not linked with OpenFinance.
