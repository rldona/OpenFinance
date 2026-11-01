#!/usr/bin/env bash
# CI (OF-903): cabeceras de seguridad en todas las respuestas, caché larga solo para los
# ficheros con hash, sin caché para la página, el service worker y la API, y gzip en lo estático.
#
#   headers.sh BASE_URL
set -euo pipefail

base="${1:?Uso: $0 BASE_URL}"
opts=(--silent --show-error --dump-header -)
if [ "${INSECURE:-}" = "1" ]; then
  opts+=(--insecure)
fi

fail() { echo "FALLA: $*" >&2; exit 1; }

# headers URL [curl-args...] → cabeceras en minúsculas
headers() {
  local url="$1"
  shift
  curl "${opts[@]}" --output /dev/null "$@" "$url" | tr -d '\r' | tr '[:upper:]' '[:lower:]'
}
has() { grep -qiE "$2" <<< "$1" || fail "$3"; }

index="$(headers "$base/")"
for h in x-content-type-options x-frame-options referrer-policy content-security-policy \
  cross-origin-opener-policy permissions-policy; do
  has "$index" "^$h:" "falta $h en /"
done
has "$index" '^cache-control: no-cache' "/ debería llevar no-cache"
grep -qi '^server: nginx/' <<< "$index" && fail "nginx enseña su versión"

page_opts=(--silent --show-error)
if [ "${INSECURE:-}" = "1" ]; then
  page_opts+=(--insecure)
fi
asset="$(curl "${page_opts[@]}" "$base/" | grep -oE '/assets/[^"]+\.js' | head -n 1)"
[ -n "$asset" ] || fail "no encuentro ningún /assets/*.js en la página"
js="$(headers "$base$asset" -H 'Accept-Encoding: gzip')"
has "$js" '^cache-control: public, max-age=31536000, immutable' "$asset debería ser inmutable"
has "$js" '^content-encoding: gzip' "$asset debería ir con gzip"
has "$js" '^x-content-type-options: nosniff' "$asset sin cabeceras de seguridad"

sw="$(headers "$base/sw.js")"
has "$sw" '^cache-control: no-cache' "sw.js debería llevar no-cache"

api="$(headers "$base/api/v1/me")"
has "$api" '^cache-control: no-store' "/api/ debería llevar no-store"
grep -qi '^content-encoding:' <<< "$api" && fail "la API no debería ir comprimida"
has "$api" '^x-content-type-options: nosniff' "/api/ sin cabeceras de seguridad"

echo "Cabeceras y cachés: bien"
