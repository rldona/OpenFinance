#!/usr/bin/env bash
# CI (OF-502): qué puertos publica cada modo.
#
#   ports.sh direct|https
set -euo pipefail

mode="${1:?Uso: $0 direct|https}"

closed() {
  if nc -z -w 2 127.0.0.1 "$1"; then
    echo "El puerto $1 no debería estar publicado" >&2
    exit 1
  fi
}

# Caddy no tiene healthcheck y puede tardar unos segundos en tener el certificado de la CA
# interna tras `up --wait`: se reintenta en lugar de fallar al primer intento.
retry=(--retry 10 --retry-delay 1 --retry-connrefused --retry-all-errors)

closed 5432
closed 8000

case "$mode" in
  direct)
    curl -fsS "${retry[@]}" http://127.0.0.1:8080/health > /dev/null
    ;;
  https)
    closed 8080
    curl -fsSk "${retry[@]}" https://localhost/health > /dev/null
    code="$(curl -sS "${retry[@]}" -o /dev/null -w '%{http_code}' http://localhost/)"
    [ "$code" = "308" ] || { echo "http debería redirigir con 308 y da $code" >&2; exit 1; }
    curl -fsSkI "${retry[@]}" https://localhost/ | grep -qi '^strict-transport-security:' \
      || { echo "Falta Strict-Transport-Security" >&2; exit 1; }
    ;;
  *)
    echo "Modo desconocido: $mode" >&2
    exit 2
    ;;
esac
echo "Puertos correctos en modo $mode."
