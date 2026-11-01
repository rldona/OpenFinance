#!/usr/bin/env bash
# Prueba backup.sh y restore.sh (OF-901) con «docker» y «age» de mentira: no hace falta ni
# Docker ni age. Comprueba el cifrado obligatorio, los permisos, la rotación y la restauración.
#
#   deploy/scripts/test/backup.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin" "$work/repo/deploy/scripts"
cp "$root/deploy/scripts/backup.sh" "$root/deploy/scripts/restore.sh" "$work/repo/deploy/scripts/"
repo="$work/repo"
export STUB_LOG="$work/calls.log"
export STUB_RESTORED="$work/restored.bin"

cat > "$work/bin/docker" <<'STUB'
#!/usr/bin/env bash
echo "docker $*" >> "$STUB_LOG"
case "$*" in
  *pg_dump*) printf 'PGDMP-contenido-de-prueba' ;;
  *"pg_restore --list"*)
    head -c 5 | grep -q '^PGDMP' || exit 1 ;;
  *pg_restore*) cat > "$STUB_RESTORED" ;;
  *"revoke-all"*) echo 0 ;;
  *) cat > /dev/null < /dev/null || true ;;
esac
STUB
cat > "$work/bin/age" <<'STUB'
#!/usr/bin/env bash
# age de mentira: «cifra» anteponiendo la clave pública; «descifra» si la identidad la casa.
mode=enc; out=""; recipients=(); identity=""; in=""
while [ $# -gt 0 ]; do
  case "$1" in
    --decrypt) mode=dec ;;
    -r) recipients+=("$2"); shift ;;
    -R) recipients+=("$(cat "$2")"); shift ;;
    -i) identity="$2"; shift ;;
    -o) out="$2"; shift ;;
    --) ;;
    *) in="$1" ;;
  esac
  shift
done
if [ "$mode" = enc ]; then
  { echo "AGE:${recipients[0]}"; cat "$in"; } > "$out"
else
  head -n 1 "$in" | grep -qx "AGE:$(cat "$identity")" || { echo "age: no identity matched" >&2; exit 1; }
  tail -n +2 "$in" > "$out"
fi
STUB
chmod +x "$work/bin/docker" "$work/bin/age"
export PATH="$work/bin:$PATH"

fail() { echo "FALLA: $*" >&2; exit 1; }
run_backup() { (cd "$repo" && deploy/scripts/backup.sh "$@" > "$work/out.txt" 2>&1); }

# 1. Sin clave pública no hay copia.
if run_backup "$work/b1"; then fail "sin clave debería rechazar la copia"; fi
[ -z "$(ls -A "$work/b1" 2> /dev/null)" ] || fail "no debería haber dejado ficheros"

# 2. Cifrada: nombre, permisos y sin restos en claro.
OPENFINANCE_BACKUP_RECIPIENT=age1clave run_backup "$work/b2"
file="$(ls "$work"/b2/openfinance-*.dump.age)"
[ "$(stat -c %a "$file" 2> /dev/null || stat -f %Lp "$file")" = "600" ] || fail "permisos distintos de 600"
head -n 1 "$file" | grep -q '^AGE:age1clave$' || fail "no está cifrada para la clave pública"
grep -q 'PGDMP' <(head -n 1 "$file") && fail "el volcado está en claro"
[ "$(ls "$work/b2" | wc -l)" -eq 1 ] || fail "quedan ficheros temporales: $(ls "$work/b2")"

# 3. Sin cifrar solo si se pide a propósito.
OPENFINANCE_BACKUP_PLAINTEXT=1 run_backup "$work/b3"
ls "$work"/b3/openfinance-*.dump > /dev/null || fail "debería haber un .dump"
grep -q 'NO va cifrada' "$work/out.txt" || fail "debería avisar de que no va cifrada"

# 4. La clave puede venir de .env (cron no lo carga) y de un fichero de claves.
echo 'OPENFINANCE_BACKUP_RECIPIENT="age1deenv"' > "$repo/.env"
run_backup "$work/b4"
head -n 1 "$(ls "$work"/b4/openfinance-*.dump.age)" | grep -q '^AGE:age1deenv$' || fail ".env no se lee"
rm "$repo/.env"

# 5. Rotación: solo las N más recientes y solo ficheros con el nombre de las copias.
mkdir -p "$work/b5"
for d in 20200101 20200102 20200103 20200104; do touch "$work/b5/openfinance-$d-030000.dump.age"; done
touch "$work/b5/otros-datos.dump.age" "$work/b5/openfinance-20200101-030000.dump.age.part"
OPENFINANCE_BACKUP_RECIPIENT=age1clave OPENFINANCE_BACKUP_KEEP=2 run_backup "$work/b5"
left="$(ls "$work/b5")"
echo "$left" | grep -q 'openfinance-20200104' || fail "la más reciente antigua debería quedar"
echo "$left" | grep -q 'openfinance-20200103' && fail "debería haber borrado la 20200103"
echo "$left" | grep -q 'otros-datos' || fail "no debe tocar ficheros ajenos"
echo "$left" | grep -q '.part' || fail "no debe tocar ficheros .part ajenos"
[ "$(echo "$left" | grep -c "^openfinance-.*\.dump\.age$")" -eq 2 ] || fail "deberían quedar 2 copias: $left"

# 6. Restaurar una cifrada: sin clave, con otra clave y con la buena.
enc="$file"
echo age1clave > "$work/id-buena.txt"
echo age1otra > "$work/id-mala.txt"
(cd "$repo" && deploy/scripts/restore.sh "$enc" --yes > /dev/null 2>&1) && fail "sin clave privada no debe restaurar"
(cd "$repo" && OPENFINANCE_BACKUP_IDENTITY="$work/id-mala.txt" deploy/scripts/restore.sh "$enc" --yes > /dev/null 2>&1) \
  && fail "con otra clave no debe restaurar"
grep -q 'compose stop api' "$STUB_LOG" && fail "no debe parar la API si no puede descifrar"
(cd "$repo" && OPENFINANCE_BACKUP_IDENTITY="$work/id-buena.txt" deploy/scripts/restore.sh "$enc" --yes > /dev/null 2>&1) \
  || fail "con la clave buena debería restaurar"
[ "$(cat "$STUB_RESTORED")" = "PGDMP-contenido-de-prueba" ] || fail "se restauró un contenido distinto"

# 7. Restaurar una sin cifrar sigue funcionando.
rm -f "$STUB_RESTORED"
(cd "$repo" && deploy/scripts/restore.sh "$(ls "$work"/b3/openfinance-*.dump)" --yes > /dev/null 2>&1) || fail "la copia en claro debería restaurar"
[ -s "$STUB_RESTORED" ] || fail "no se restauró la copia en claro"

echo "backup.sh y restore.sh: bien"
