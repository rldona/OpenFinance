#!/usr/bin/env bash
# Copia de seguridad de la base de datos de OpenFinance (pg_dump en formato custom).
#
#   deploy/scripts/backup.sh [DIR]      (por defecto: backups)
#
# La copia contiene TODO el hogar: las cuentas personales de ambas personas y los hashes
# de las contraseñas. No va cifrada: guárdala donde solo vosotros tengáis acceso.
set -euo pipefail
umask 077

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
dir="${1:-backups}"
case "$dir" in
  /*) ;;
  *) dir="$PWD/$dir" ;;
esac
cd "$root"

mkdir -p "$dir"
name="openfinance-$(date +%Y%m%d-%H%M%S).dump"
part="$dir/$name.part"
trap 'rm -f "$part"' EXIT

# shellcheck disable=SC2016 # las variables se expanden dentro del contenedor
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$part"

# Comprueba que la copia se puede leer antes de darla por buena.
docker compose exec -T db pg_restore --list < "$part" > /dev/null

chmod 600 "$part"
mv "$part" "$dir/$name"
trap - EXIT

echo "Copia guardada en $dir/$name"
echo "Aviso: contiene todos los datos del hogar (también las cuentas personales de ambos" \
  "y los hashes de las contraseñas) y no va cifrada."
