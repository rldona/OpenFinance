#!/usr/bin/env bash
# Copia de seguridad cifrada de la base de datos de OpenFinance (pg_dump en formato custom + age).
#
#   deploy/scripts/backup.sh [DIR]      (por defecto: backups)
#
# Variables (del entorno o de .env):
#   OPENFINANCE_BACKUP_RECIPIENT   clave pública de age (age1...) con la que se cifra. Obligatoria.
#   OPENFINANCE_BACKUP_RECIPIENTS_FILE   alternativa: fichero con una clave pública por línea.
#   OPENFINANCE_BACKUP_KEEP        copias que se conservan en DIR (por defecto 30; 0 = no borrar).
#   OPENFINANCE_BACKUP_PLAINTEXT=1 hacer la copia SIN cifrar (no recomendado).
#
# La clave privada no tiene que estar en este equipo: solo hace falta para restaurar.
# La copia contiene TODO el hogar: las cuentas personales de ambas personas y los hashes de
# las contraseñas.
set -euo pipefail
umask 077

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

# Lee OPENFINANCE_BACKUP_* de .env sin ejecutarlo (cron no lo carga). El entorno manda.
if [ -f .env ]; then
  while IFS='=' read -r key value; do
    case "$key" in
      OPENFINANCE_BACKUP_*)
        value="${value%\"}"
        value="${value#\"}"
        if [ -z "${!key:-}" ]; then export "$key=$value"; fi
        ;;
    esac
  done < <(grep -E '^OPENFINANCE_BACKUP_[A-Z_]+=' .env || true)
fi

dir="${1:-backups}"
case "$dir" in
  /*) ;;
  *) dir="$PWD/$dir" ;;
esac

recipient="${OPENFINANCE_BACKUP_RECIPIENT:-}"
recipients_file="${OPENFINANCE_BACKUP_RECIPIENTS_FILE:-}"
plaintext="${OPENFINANCE_BACKUP_PLAINTEXT:-}"
keep="${OPENFINANCE_BACKUP_KEEP:-30}"

case "$keep" in
  '' | *[!0-9]*)
    echo "OPENFINANCE_BACKUP_KEEP debe ser un número (0 = no borrar nada)." >&2
    exit 2
    ;;
esac

age_args=()
if [ "$plaintext" = "1" ]; then
  suffix=".dump"
else
  if [ -n "$recipient" ]; then
    age_args+=(-r "$recipient")
  fi
  if [ -n "$recipients_file" ]; then
    [ -r "$recipients_file" ] || { echo "No se puede leer $recipients_file" >&2; exit 2; }
    age_args+=(-R "$recipients_file")
  fi
  if [ ${#age_args[@]} -eq 0 ]; then
    echo "Falta la clave pública con la que cifrar la copia." >&2
    echo "  age-keygen -o clave.txt      # guarda clave.txt FUERA de este equipo" >&2
    echo "  OPENFINANCE_BACKUP_RECIPIENT=age1... en .env (la línea «Public key» de clave.txt)" >&2
    echo "Para hacerla sin cifrar, a sabiendas: OPENFINANCE_BACKUP_PLAINTEXT=1" >&2
    exit 2
  fi
  command -v age > /dev/null || { echo "Falta «age» en este equipo (apt install age)." >&2; exit 2; }
  suffix=".dump.age"
fi

mkdir -p "$dir"
stamp="$(date +%Y%m%d-%H%M%S)"
name="openfinance-$stamp$suffix"
part="$dir/$name.part"
plain="$dir/openfinance-$stamp.dump.plain.part"
trap 'rm -f "$part" "$plain"' EXIT

# Antes de volcar, se borran los extractos de vistas previas caducadas (OF-607): la copia no
# debe llevarse archivos que la aplicación ya no tiene por qué guardar.
docker compose exec -T api openfinance imports purge

# shellcheck disable=SC2016 # las variables se expanden dentro del contenedor
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$plain"

# Comprueba que la copia se puede leer antes de darla por buena (cifrada ya no se podría).
docker compose exec -T db pg_restore --list < "$plain" > /dev/null

if [ "$plaintext" = "1" ]; then
  mv "$plain" "$part"
else
  age "${age_args[@]}" -o "$part" "$plain"
  rm -f "$plain"
fi

chmod 600 "$part"
mv "$part" "$dir/$name"
trap - EXIT

echo "Copia guardada en $dir/$name"

# Rotación: se conservan las $keep más recientes. Solo se tocan ficheros con el nombre exacto
# que pone este script; el nombre lleva la fecha, así que ordenar por nombre es ordenar por edad.
if [ "$keep" -gt 0 ]; then
  # Los nombres llevan la fecha y la hora: en orden alfabético inverso, de más nueva a más vieja.
  copies=()
  for f in "$dir"/openfinance-*.dump "$dir"/openfinance-*.dump.age; do
    [ -f "$f" ] || continue
    case "$(basename "$f")" in
      openfinance-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9].dump | \
        openfinance-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9].dump.age)
        copies+=("$f")
        ;;
    esac
  done
  count=0
  while IFS= read -r old; do
    count=$((count + 1))
    if [ "$count" -gt "$keep" ]; then
      rm -f -- "$old"
      echo "Copia antigua borrada: $(basename "$old")"
    fi
  done < <(printf '%s\n' "${copies[@]}" | awk -F/ '{print $NF "\t" $0}' | sort -r | cut -f2-)
fi

if [ "$plaintext" = "1" ]; then
  echo "Aviso: contiene todos los datos del hogar (también las cuentas personales de ambos" \
    "y los hashes de las contraseñas) y NO va cifrada."
else
  echo "Cifrada con age: sin la clave privada no se puede abrir. Guarda una copia de esa clave" \
    "fuera de este equipo."
fi
