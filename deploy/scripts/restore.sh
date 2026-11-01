#!/usr/bin/env bash
# Restaura una copia hecha con backup.sh sobre la base de datos de OpenFinance.
#
#   deploy/scripts/restore.sh FICHERO [--yes]
#
# Sustituye TODOS los datos actuales. Restaura con la misma versión de OpenFinance que hizo
# la copia o una más nueva: después se aplican las migraciones pendientes. Al terminar se
# cierran todas las sesiones, así que hay que volver a entrar.
set -euo pipefail

usage() {
  echo "Uso: $0 FICHERO [--yes]" >&2
  exit 2
}

[ $# -ge 1 ] || usage
file="$1"
yes="${2:-}"
[ -z "$yes" ] || [ "$yes" = "--yes" ] || usage

if [ ! -f "$file" ] || [ ! -r "$file" ]; then
  echo "No se encuentra o no se puede leer la copia: $file" >&2
  exit 1
fi
file="$(cd "$(dirname "$file")" && pwd)/$(basename "$file")"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

if [ "$yes" != "--yes" ]; then
  echo "Se van a sustituir TODOS los datos de OpenFinance por los de:"
  echo "  $file"
  read -r -p "Escribe «restaurar» para continuar: " answer
  if [ "$answer" != "restaurar" ]; then
    echo "Cancelado." >&2
    exit 1
  fi
fi

# Antes de tocar nada: la copia tiene que poder leerse.
if ! docker compose exec -T db pg_restore --list < "$file" > /dev/null; then
  echo "La copia no es válida (pg_restore --list ha fallado). No se ha cambiado nada." >&2
  exit 1
fi

step="parar la API"
on_error() {
  echo >&2
  echo "La restauración falló al $step." >&2
  echo "La API queda parada y los datos pueden estar a medias (pg_restore va en una sola" >&2
  echo "transacción: si falló ahí, la base de datos sigue como estaba)." >&2
  echo "No arranques la API sin ejecutar antes:" >&2
  echo "  docker compose run --rm --no-deps -T api openfinance sessions revoke-all" >&2
  echo "Puedes repetir la restauración con la misma copia." >&2
}
trap on_error ERR

docker compose stop api

step="restaurar la copia"
# shellcheck disable=SC2016 # las variables se expanden dentro del contenedor
docker compose exec -T db sh -c \
  'pg_restore --clean --if-exists --no-owner --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < "$file"

# Las sesiones de la copia dejan de valer en cuanto existen: se borran antes de migrar.
step="borrar las sesiones restauradas"
# shellcheck disable=SC2016 # las variables se expanden dentro del contenedor
docker compose exec -T db sh -c \
  'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DELETE FROM sessions"'

step="aplicar las migraciones"
docker compose run --rm --no-deps -T api alembic upgrade head

step="cerrar las sesiones"
printf 'Sesiones cerradas: '
docker compose run --rm --no-deps -T api openfinance sessions revoke-all

step="arrancar la API"
docker compose start api
# nginx resuelve «api» al arrancar: se reinicia por si el contenedor cambió de IP.
docker compose restart web
docker compose up -d --wait
trap - ERR

echo "Copia restaurada. Volved a iniciar sesión."
