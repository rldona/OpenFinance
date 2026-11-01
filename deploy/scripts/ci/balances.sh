#!/usr/bin/env bash
# CI (OF-501/OF-502): inicia sesión, guarda los saldos de las cuentas visibles y comprueba
# que las dos exportaciones se descargan bien.
#
#   balances.sh BASE_URL SALIDA.json COOKIE_JAR
#
# Credenciales en E2E_EMAIL y E2E_PASSWORD (por defecto, las de `openfinance demo`).
# Con INSECURE=1 acepta el certificado de la CA interna de Caddy.
set -euo pipefail

[ $# -eq 3 ] || { echo "Uso: $0 BASE_URL SALIDA.json COOKIE_JAR" >&2; exit 2; }
base="$1"
out="$2"
jar="$3"
email="${E2E_EMAIL:-raul@demo.openfinance}"
password="${E2E_PASSWORD:-demo-openfinance}"

curl_opts=(--fail --silent --show-error)
if [ "${INSECURE:-}" = "1" ]; then
  curl_opts+=(--insecure)
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

jq -n --arg email "$email" --arg password "$password" '{email: $email, password: $password}' \
  | curl "${curl_opts[@]}" -c "$jar" -o /dev/null \
    -H 'X-Requested-With: OpenFinance' -H 'Content-Type: application/json' \
    --data-binary @- "$base/api/v1/auth/login"

curl "${curl_opts[@]}" -b "$jar" "$base/api/v1/accounts" \
  | jq -S 'map({id, balance: .balance.amount, currency: .balance.currency}) | sort_by(.id)' \
  > "$out"
[ "$(jq length "$out")" -gt 0 ] || { echo "No hay cuentas visibles" >&2; exit 1; }

curl "${curl_opts[@]}" -b "$jar" -o "$tmp/export.json" "$base/api/v1/export?format=json"
jq -e '.format_version == 1' "$tmp/export.json" > /dev/null

curl "${curl_opts[@]}" -b "$jar" -o "$tmp/export.zip" "$base/api/v1/export?format=csv"
unzip -tq "$tmp/export.zip"

echo "Saldos de $(jq length "$out") cuentas guardados en $out; exportaciones JSON y CSV correctas."
