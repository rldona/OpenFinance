# Preparar una release

Checklist para publicar una versión de OpenFinance. La primera es **v0.1.0** (OF-504). Su etiqueta se crea cuando se cumplan dos condiciones: un mes de uso real con vuestros datos y OF-108 terminado (ya lo está).

Nunca se despliega un *preview* de Vercel: todo pasa por GitHub y el flujo normal de merge.

## 1. Condiciones previas

- [ ] Todos los tickets de la versión cerrados en [roadmap.md](../product/roadmap.md). Para v0.1.0, también **OF-108** (vista «mi gasto»).
- [ ] Para v0.1.0: **al menos un mes de uso real** con vuestros datos, sin incidencias abiertas que afecten a los importes o a la privacidad.
- [ ] Rama `main` al día y sin cambios locales (`git status` limpio).

## 2. Licencias

- [ ] `make licenses CHECK=1` en verde.
- [ ] Si han cambiado las dependencias desde la última auditoría, regenerar las tablas con `make licenses` y actualizar [docs/legal/dependencias.md](../legal/dependencias.md) (fecha incluida).
- [ ] [`LICENSE`](../../LICENSE) sin cambios: es el texto literal de la AGPL-3.0 ([ADR-0008](../adr/0008-licencia-agpl.md)).

## 3. Versión

Sustituir la versión de desarrollo (`0.1.0.dev0` en Python, `0.1.0-dev` en npm) por la de la release, en todos los sitios:

- [ ] `services/api/pyproject.toml` → `version = "0.1.0"`, y después `cd services/api && uv lock` para que `uv.lock` recoja la versión.
- [ ] `apps/web/package.json` → `"version": "0.1.0"`, y después `cd apps/web && npm install --package-lock-only` para actualizar `package-lock.json` (dos entradas).
- [ ] `make openapi`: el `info.version` de `apps/web/openapi.json` sale de la versión del paquete, y CI falla si no está al día.
- [ ] Comprobar que no queda ninguna versión de desarrollo: `git grep -nE '0\.1\.0[.-]dev' -- ':!docs/development/release.md'` no devuelve nada.

## 4. CHANGELOG

- [ ] En [CHANGELOG.md](../../CHANGELOG.md), renombrar `## [Unreleased]` a `## [0.1.0] - AAAA-MM-DD` con la fecha de la etiqueta, quitar «Pendiente antes de 0.1.0» y abrir un `## [Unreleased]` vacío encima.
- [ ] Revisar que cada punto se entiende sin conocer el código.

## 5. Comprobaciones

- [ ] `make check` en verde en local (lint, tipos, tests y build).
- [ ] Pull request con los cambios de los pasos 2 a 4, commits firmados (`git commit -s`, ver [CONTRIBUTING.md](../../CONTRIBUTING.md)) y **CI verde**: `backend`, `frontend`, `licenses` y `compose-e2e` en sus dos modos (`direct` y `https`).
- [ ] Merge a `main` y CI verde también en `main`.
- [ ] Instalación limpia siguiendo [Instalar en casa](../deployment/home.md) desde `main`. Restaurar una copia real (`make restore`) y comprobar que los saldos coinciden con los del banco.

## 6. Etiqueta y release en GitHub

Solo cuando todo lo anterior esté marcado:

```bash
git switch main && git pull --ff-only
git tag -a v0.1.0 -m "OpenFinance v0.1.0"
git push origin v0.1.0
awk '/^## \[0\.1\.0\]/{f=1;next} /^## \[/{f=0} f' CHANGELOG.md > release-notes.md
gh release create v0.1.0 --verify-tag --title "OpenFinance v0.1.0" --notes-file release-notes.md
rm release-notes.md
```

- [ ] Etiqueta **anotada** `v0.1.0` sobre el commit de `main` con CI verde.
- [ ] Release en GitHub con las notas de la sección 0.1.0 del CHANGELOG.
- [ ] No se publican imágenes Docker: cada instalación las construye. Si algún día se publican, revisar antes la nota sobre imágenes de [dependencias.md](../legal/dependencias.md).

## 7. Después

- [ ] Volver a versión de desarrollo (`0.2.0.dev0` / `0.2.0-dev`), con `uv lock`, `npm install --package-lock-only` y `make openapi`.
- [ ] Marcar OF-504 como hecho en [roadmap.md](../product/roadmap.md) y actualizar el estado del README.
- [ ] Actualizar la instalación de casa a la etiqueta siguiendo «8. Actualizar» en [Instalar en casa](../deployment/home.md).
