# Instalar OpenFinance en casa

Guía para dejar OpenFinance funcionando en un equipo de casa con Docker Compose. Las decisiones de fondo están en [ADR-0016](../adr/0016-exposicion-y-copias.md).

## Requisitos

- Un equipo **x86-64** encendido mientras lo uséis (un mini PC, un portátil viejo o una NAS con Docker).
- **Docker** con **Docker Compose ≥ 2.24** (`docker compose version`).
- `make` y `git` (o descargar el repositorio).

## 1. Configuración

```bash
git clone <repositorio> openfinance && cd openfinance
cp .env.example .env
openssl rand -hex 24          # úsalo como POSTGRES_PASSWORD en .env
```

Edita `.env`: como mínimo `POSTGRES_PASSWORD`. El resto de valores se explica en los apartados siguientes.

## 2. Arrancar

```bash
make up                       # construye y arranca db + api + web
docker compose ps             # todos «healthy»
```

Por defecto solo se entra desde el propio equipo: http://localhost:8080. Ni la base de datos ni la API publican puertos.

## 3. Alta del hogar

```bash
docker compose exec api openfinance bootstrap
```

Pregunta el nombre del hogar, el nombre, el email y la contraseña de cada persona y las cuentas. No hay registro público.

Para identificar las aportaciones que no llevan vuestro nombre (recargas con tarjeta, salidas de las cuentas personales), consulta `docker compose exec api openfinance member-patterns --help`.

Más tarea de mantenimiento desde el servidor:

- Si alguien olvida su contraseña: `docker compose exec api openfinance users set-password <email>`. La pide sin eco y cierra las sesiones abiertas de esa persona.
- Para añadir una hucha o una cuenta después del alta: `docker compose exec api openfinance accounts add <email> 'Hucha viaje' --kind savings --opening-balance 120.50`. Con `--kind personal` la cuenta es de esa persona y solo la ve su titular.

## 4. Entrar desde el móvil en casa (http)

En `.env`:

```dotenv
OPENFINANCE_BIND=192.168.1.20                 # IP del equipo en la red de casa (o 0.0.0.0)
OPENFINANCE_SESSION_COOKIE_SECURE=false       # se entra por http: la cookie no puede ser Secure
```

`make up` de nuevo y abrid `http://192.168.1.20:8080` en el móvil (conviene fijar esa IP en el router). Si olvidáis `OPENFINANCE_SESSION_COOKIE_SECURE=false`, el login «funciona» pero el navegador no guarda la sesión; la API lo avisa en `docker compose logs api`.

**Instalarla como app (OF-805).** Con HTTPS y dominio propio, el navegador del móvil ofrece «Añadir a la pantalla de inicio» (Chrome: menú ⋮ → *Instalar aplicación*; Safari: Compartir → *Añadir a pantalla de inicio*). Por `http://` en la red local solo se guarda un acceso directo, sin service worker. La app instalada guarda únicamente su carcasa: los datos siempre se piden al servidor. El tema claro u oscuro se elige en Ajustes → Apariencia.

Así el tráfico va sin cifrar dentro de la red de casa: usadlo solo en una red de confianza.

## 5. Entrar desde fuera con HTTPS (dominio propio)

Necesitáis un dominio (o subdominio) con un registro DNS apuntando a la IP pública de casa y los puertos **80 y 443** del router redirigidos a este equipo. En `.env`:

```dotenv
COMPOSE_FILE=compose.yaml:compose.https.yaml
OPENFINANCE_DOMAIN=finanzas.example.org
```

y quitad `OPENFINANCE_SESSION_COOKIE_SECURE=false` si lo teníais. `make up` arranca además Caddy, que obtiene y renueva el certificado, redirige http a https y añade `Strict-Transport-Security`. nginx deja de publicar el puerto 8080 y la cookie es siempre `Secure`. Entrad por `https://finanzas.example.org`, también desde casa.

> **Aviso.** En modo `caddy`, **no publiquéis el puerto de nginx** (no añadáis `ports` al servicio `web` ni lo saquéis de `compose.https.yaml`). En ese modo nginx se fía de la IP que le pasa Caddy en `X-Forwarded-For`; si se pudiera llegar a nginx directamente, cualquiera podría inventarse la IP y saltarse el límite de intentos de login. Los dos modos son excluyentes, y el modo lo decide el fichero de Compose, no una variable de `.env`.

## 6. Copias de seguridad

Las copias van **cifradas con [age](https://github.com/FiloSottile/age)**: sin la clave privada no se pueden abrir, así que pueden salir de casa sin riesgo. El equipo solo guarda la clave **pública**; la privada se guarda fuera y solo hace falta para restaurar.

Una sola vez:

```bash
sudo apt install age          # o: brew install age
age-keygen -o clave.txt       # imprime «Public key: age1...»
```

Guardad `clave.txt` **fuera del equipo** (gestor de contraseñas, papel en un sitio seguro, la otra persona): si la perdéis, las copias no se pueden recuperar. En `.env` poned solo la clave pública:

```dotenv
OPENFINANCE_BACKUP_RECIPIENT=age1...
OPENFINANCE_BACKUP_KEEP=30     # copias que se conservan (por defecto 30; 0 = no borrar)
```

(Para cifrar a varias claves, `OPENFINANCE_BACKUP_RECIPIENTS_FILE=fichero` con una clave pública por línea.)

```bash
make backup                   # backups/openfinance-AAAAmmdd-HHMMSS.dump.age (permisos 600)
make backup DIR=/mnt/disco    # en otra carpeta
```

Sin clave pública, `make backup` se niega a hacer la copia. Solo se puede hacer en claro a sabiendas, con `OPENFINANCE_BACKUP_PLAINTEXT=1`. La copia contiene **todo**: las cuentas personales de ambas personas y los hashes de las contraseñas. Antes de cifrar se comprueba que el volcado se puede leer; el volcado en claro se escribe un instante en la misma carpeta con permisos 600 y se borra enseguida.

Tras cada copia se borran las más antiguas hasta dejar `OPENFINANCE_BACKUP_KEEP`. Solo se tocan ficheros con el nombre exacto `openfinance-AAAAmmdd-HHMMSS.dump[.age]`.

### Guardarlas fuera del equipo

Una copia en el mismo disco no sirve si el disco falla. Con las copias cifradas, cualquiera de estas vale, porque quien las robe no puede leerlas:

- **Otro disco o equipo de casa**: `make backup DIR=/mnt/disco/openfinance` (o `rsync -a backups/ otro-equipo:openfinance/`).
- **Almacenamiento en la nube** con [rclone](https://rclone.org/): `rclone copy backups remoto:openfinance --include 'openfinance-*.dump.age'`.
- **Un disco USB** que cambiéis de sitio de vez en cuando.

Copia diaria con `cron` (`crontab -e`), a las 3:30; la rotación ya la hace el script:

```cron
30 3 * * * cd /ruta/a/openfinance && make backup DIR=/mnt/disco/openfinance >> /var/log/openfinance-backup.log 2>&1
```

Probad una restauración al menos una vez (sección siguiente): una copia que nunca se ha restaurado no es una copia.

### Restaurar

```bash
make restore FILE=backups/openfinance-20261101-033000.dump.age OPENFINANCE_BACKUP_IDENTITY=clave.txt
```

Si la copia está cifrada hay que dar la clave privada (`OPENFINANCE_BACKUP_IDENTITY`); se descifra a un fichero temporal con permisos 600 que se borra al terminar. Primero comprueba que la copia se puede leer; luego pide escribir «restaurar» y sustituye **todos** los datos actuales. Restaurad con la misma versión de OpenFinance que hizo la copia o una más nueva: después se aplican las migraciones pendientes. Al terminar se cierran todas las sesiones y hay que volver a entrar.

> **Restaurad solo copias vuestras** (hechas con `make backup` en vuestra instalación). `pg_restore` se ejecuta con el usuario de PostgreSQL de la instalación, que es superusuario de la base de datos: una copia manipulada podría ejecutar SQL arbitrario con esos permisos.

Si la restauración falla a medias, el script lo dice y deja la API parada. No la arranquéis sin ejecutar antes `docker compose run --rm --no-deps -T api openfinance sessions revoke-all` (o repetid la restauración con la misma copia).

## 7. Exportar vuestros datos

Desde la web, **Exportar** (arriba a la derecha) descarga un JSON o un ZIP con un CSV por entidad. Cada persona exporta lo que ve: la cuenta personal de la otra no se incluye. Para una copia completa, usad `make backup`.

## 8. Imágenes publicadas y firmadas (opcional)

Por defecto `make up` construye las imágenes en vuestro equipo. Cada versión (`vX.Y.Z`) también se publica ya construida para x86-64 y ARM en `ghcr.io/rldona/openfinance-api` y `ghcr.io/rldona/openfinance-web`, **firmadas con [cosign](https://github.com/sigstore/cosign)** sin claves propias: la firma sale de la identidad del workflow de GitHub que las construyó y queda en el registro público de Sigstore. Llevan además lista de materiales (SBOM) y procedencia.

Comprobad la firma **antes de arrancar** (necesita `cosign`):

```bash
V=0.2.0
for img in api web; do
  cosign verify "ghcr.io/rldona/openfinance-$img:$V" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity "https://github.com/rldona/OpenFinance/.github/workflows/release.yml@refs/tags/v$V"
done
```

Si no sale `Verification for … --` con la firma, no uséis la imagen. Para usarlas, en `.env`:

```dotenv
COMPOSE_FILE=compose.yaml:compose.images.yaml      # o compose.yaml:compose.images.yaml:compose.https.yaml
OPENFINANCE_VERSION=0.2.0
```

y `docker compose pull && make up`. Fijad siempre una versión concreta, nunca `latest`.

### Avisar de versiones nuevas

Con `OPENFINANCE_UPDATE_CHECK=true` en `.env`, el servidor pregunta una vez al día a la API pública de GitHub cuál es la última release. Si es posterior a la vuestra, la web enseña un aviso con un enlace a las novedades (se puede descartar y no vuelve hasta la siguiente versión). **Solo avisa**: nada se actualiza solo, y la consulta no envía ningún dato de la instalación (GitHub ve la IP del servidor, como con cualquier visita). Está apagado por defecto. Para actualizar, seguid la sección siguiente.

## 9. Actualizar

```bash
make backup                   # antes de nada
git pull
make up                       # reconstruye; las migraciones se aplican al arrancar la API
# con imágenes publicadas: cambiad OPENFINANCE_VERSION en .env, comprobad la firma y `docker compose pull && make up`
```

## Problemas frecuentes

| Síntoma | Causa |
| --- | --- |
| Entro y vuelvo a la pantalla de login | Cookie `Secure` por http: `OPENFINANCE_SESSION_COOKIE_SECURE=false` en el modo `direct`, o usad HTTPS |
| `Define POSTGRES_PASSWORD en .env` | Falta `.env` o la variable |
| `ports: !reset` no válido | Docker Compose anterior a 2.24 |
| Caddy no obtiene el certificado | DNS no apunta a casa o los puertos 80/443 no llegan al equipo |
| `Demasiados intentos` | Límite de intentos de login: esperad 15 minutos |

## Logs y comprobaciones de estado

- `docker compose logs -f api` enseña una línea por petición: `fecha NIVEL nombre [id-de-petición] GET /ruta -> estado en N ms`. No lleva la query de la URL, cuerpos, cookies ni cabeceras. El nivel se cambia con `OPENFINANCE_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- Cada respuesta lleva `X-Request-ID`: si algo falla, dad ese identificador y se busca la línea exacta. El identificador lo pone nginx y llega a la API.
- Los logs de cada contenedor rotan solos: 5 ficheros de 10 MB.
- `/health` dice que la API está viva; `/ready` (solo dentro de Compose) comprueba además que la base de datos contesta. El `healthcheck` de la API usa `/ready`.
