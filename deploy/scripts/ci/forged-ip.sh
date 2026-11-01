#!/usr/bin/env bash
# CI (OF-502): un X-Forwarded-For inventado no sirve para saltarse el límite de intentos ni
# llega a la API.
#
#   forged-ip.sh BASE_URL
set -euo pipefail

base="${1:?Uso: $0 BASE_URL}"
curl_opts=(--silent --show-error --output /dev/null --write-out '%{http_code}')
if [ "${INSECURE:-}" = "1" ]; then
  curl_opts+=(--insecure)
fi

limited=0
for i in $(seq 1 30); do
  body="$(jq -n --arg e "nadie$i@example.org" --arg p "incorrecta-$i" '{email: $e, password: $p}')"
  code="$(curl "${curl_opts[@]}" \
    -H 'X-Requested-With: OpenFinance' -H 'Content-Type: application/json' \
    -H "X-Forwarded-For: 203.0.113.$i" --data-binary "$body" "$base/api/v1/auth/login")"
  [ "$code" = "429" ] && limited=$((limited + 1))
done
[ "$limited" -gt 0 ] || { echo "Ningún 429 en 30 intentos con IP falsificada" >&2; exit 1; }

if docker compose logs --no-color api | grep -qF '203.0.113.'; then
  echo "La IP falsificada ha llegado a la API" >&2
  exit 1
fi
echo "IP falsificada ignorada: $limited de 30 intentos limitados."
