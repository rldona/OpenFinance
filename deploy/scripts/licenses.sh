#!/usr/bin/env bash
# Licencias de las dependencias que se distribuyen con OpenFinance (OF-504, ADR-0008).
#
#   deploy/scripts/licenses.sh           tablas de las dependencias de producción y resumen de las de desarrollo
#   deploy/scripts/licenses.sh --check   falla si una dependencia de producción no está en la lista permitida
#
# Requiere `make setup` (entorno de uv y node_modules). Resultado comentado en docs/legal/dependencias.md.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:-report}"

pip_licenses="pip-licenses==5.5.5"
npm_checker="license-checker-rseidelsohn@5.0.1"

# Compatibles con AGPL-3.0 (ver docs/legal/dependencias.md). Coincidencia parcial en Python:
# «MIT» cubre «MIT License» y «MIT-0»; «BSD» cubre «BSD-3-Clause»; «Apache» cubre «Apache-2.0».
python_allowed="MIT;BSD;Apache;ISC;Python Software Foundation;PSF-2.0;Unlicense;LGPL-3.0"
npm_allowed="MIT;MIT-0;ISC;BSD-2-Clause;BSD-3-Clause;Apache-2.0;0BSD;CC0-1.0;BlueOak-1.0.0;MPL-2.0"

# Dependencias de runtime según uv.lock (sin el grupo dev ni el propio proyecto).
cd "$root/services/api"
python_packages=()
while IFS= read -r package; do
  python_packages+=("$package")
done < <(
  uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt --quiet \
    | grep -E '^[A-Za-z0-9]' | sed -E 's/[=;].*//'
)

cd "$root/apps/web"
if [ "$mode" = "--check" ]; then
  (cd "$root/services/api" && uv run --frozen --quiet --with "$pip_licenses" pip-licenses --from=mixed \
    --packages "${python_packages[@]}" --partial-match --allow-only="$python_allowed" >/dev/null)
  npx --yes "$npm_checker" --production --excludePrivatePackages --onlyAllow "$npm_allowed" >/dev/null
  echo "Licencias de producción dentro de la lista permitida."
  exit 0
fi

echo "## Python (runtime, services/api)"
echo
(cd "$root/services/api" && uv run --frozen --quiet --with "$pip_licenses" pip-licenses --from=mixed \
  --format=markdown --with-urls --packages "${python_packages[@]}")
echo
echo "## npm (producción, apps/web)"
echo
npx --yes "$npm_checker" --production --excludePrivatePackages --markdown
echo
echo "## npm (desarrollo y build, apps/web; depende de la plataforma instalada)"
npx --yes "$npm_checker" --development --excludePrivatePackages --summary
