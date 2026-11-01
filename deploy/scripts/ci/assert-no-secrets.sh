#!/usr/bin/env bash
# CI (OF-502): los logs de los contenedores no contienen secretos.
#
#   assert-no-secrets.sh [COOKIE_JAR...]
#
# Busca la contraseña de PostgreSQL (POSTGRES_PASSWORD o .env), la contraseña de la
# demostración (E2E_PASSWORD), el valor de las cookies de sesión de los jars indicados y
# el nombre de la cookie seguido de «=».
set -euo pipefail

cookie_name="${OPENFINANCE_SESSION_COOKIE_NAME:-of_session}"
db_password="${POSTGRES_PASSWORD:-}"
if [ -z "$db_password" ] && [ -f .env ]; then
  db_password="$(sed -n 's/^POSTGRES_PASSWORD=//p' .env | tail -n 1)"
fi
[ -n "$db_password" ] || { echo "No se conoce POSTGRES_PASSWORD" >&2; exit 2; }

secrets=("$db_password" "${E2E_PASSWORD:-demo-openfinance}" "$cookie_name=")
for jar in "$@"; do
  # Formato Netscape: el valor es la 7.ª columna; las cookies HttpOnly empiezan por #HttpOnly_.
  while IFS= read -r value; do
    [ -n "$value" ] && secrets+=("$value")
  done < <(awk -v name="$cookie_name" '$6 == name { print $7 }' "$jar")
done

logs="$(mktemp)"
trap 'rm -f "$logs"' EXIT
docker compose logs --no-color > "$logs"

found=0
for i in "${!secrets[@]}"; do
  if grep -qF -- "${secrets[$i]}" "$logs"; then
    # No se imprime el secreto, solo qué tipo de secreto aparece.
    echo "Los logs contienen el secreto n.º $i" >&2
    found=1
  fi
done
[ "$found" -eq 0 ] || exit 1
echo "Sin secretos en $(wc -l < "$logs") líneas de logs (${#secrets[@]} valores comprobados)."
