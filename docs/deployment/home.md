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

Pregunta el nombre del hogar, el nombre, el email y la contraseña de cada persona y las cuentas. No hay registro público: más personas entran con una invitación que crea quien administra el hogar en **Ajustes → Personas del hogar** (un enlace de un solo uso que vale 7 días).

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

Sin clave pública, `make backup` se niega a hacer la copia. Solo se puede hacer en claro a sabiendas, con `OPENFINANCE_BACKUP_PLAINTEXT=1`. La copia contiene **todo**: las cuentas personales de ambas personas y los hashes de las contraseñas. Los adjuntos (tickets y facturas de los movimientos) viven en un volumen de Docker aparte y van en un segundo fichero de la misma fecha, `openfinance-AAAAmmdd-HHMMSS.attachments.tar.age`, cifrado igual; si no hay adjuntos no se crea. Antes de cifrar se comprueba que el volcado se puede leer; el volcado en claro se escribe un instante en la misma carpeta con permisos 600 y se borra enseguida.

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

### Notificaciones en el móvil

Los avisos (duplicados, comisiones, recibos que suben, pagos atrasados, saldo en negativo) se ven siempre en «Este mes». Para recibirlos también como notificación del móvil se usa Web Push ([ADR-0023](../adr/0023-avisos-y-notificaciones.md)); necesita el modo HTTPS y, en iPhone, iOS 16.4 o superior con la app añadida a la pantalla de inicio.

1. Genera las claves una vez: `docker compose run --rm --no-deps -T api openfinance alerts keys`.
2. Pega las tres líneas en `.env` (la privada es un secreto, como la contraseña de PostgreSQL), pon en `OPENFINANCE_VAPID_SUBJECT` un `mailto:` vuestro y `docker compose up -d`.
3. En cada móvil: **Ajustes → Notificaciones → Activar en este dispositivo**. Cada persona elige qué tipos de aviso quiere.
4. Programa el envío con `cron`; es idempotente, no repite lo ya enviado:

```cron
0 * * * * cd /ruta/a/openfinance && docker compose exec -T api openfinance alerts notify >> /var/log/openfinance-alerts.log 2>&1
```

El mensaje solo dice cuántos avisos hay y de qué tipo, sin importes ni comercios. Los servicios push de Google, Apple y Mozilla ven que hay una notificación, no su contenido financiero.

### Conectar el banco

Además de importar extractos, OpenFinance puede traer los movimientos directamente del banco por PSD2 ([ADR-0024](../adr/0024-conexion-con-el-banco.md)). Un banco solo entrega esos datos a un proveedor autorizado, así que usáis **vuestra propia cuenta** en [Enable Banking](https://enablebanking.com): sus datos de aplicación quedan en vuestro servidor y los movimientos no pasan por ningún servidor nuestro. Es solo lectura: nunca mueve dinero. Necesita el modo HTTPS.

1. Entra en el [panel de Enable Banking](https://enablebanking.com/cp/applications) y registra una aplicación:
   - **Entorno: Production** (no Sandbox: Sandbox solo habla con bancos simulados). Queda «Inactive».
   - **Clave:** deja «Generate in the browser». Al registrar se descarga un `.pem` con el identificador de la aplicación como nombre. Guárdalo **fuera del repositorio**; es la clave que firma todas las peticiones.
   - **Allowed redirect URLs:** la raíz de vuestra web, **solo con `https`** (`http://…` se rechaza: «unsupported scheme»), con la barra final: `https://finanzas.ejemplo.org/`. Para probar en tu equipo vale `https://localhost/` con el modo `https` de Compose (Caddy usa una CA interna: el navegador avisa del certificado y se acepta una vez).
   - **Privacy URL y Terms URL:** el formulario los pide aunque se marquen como opcionales. Para uso propio vale la dirección del repositorio.
   - Pulsa **Activate by linking accounts** y autoriza tus cuentas en el banco. Hasta entonces la aplicación está inactiva y solo puede leer las cuentas **enlazadas** (modo restringido, para uso individual y no comercial). La pantalla «Billing» es una solicitud de presupuesto comercial: no hace falta.
2. En `.env`: `OPENFINANCE_BANK_APP_ID` (el identificador de la aplicación), `OPENFINANCE_BANK_REDIRECT_URL` (esa misma dirección, idéntica) y `OPENFINANCE_BANK_PRIVATE_KEY` con el PEM en **una sola línea**, cambiando cada salto de línea por `\n` y **entre comillas simples** (con comillas dobles Compose expande `\n`). La clave es un secreto, como la contraseña de PostgreSQL. Después `docker compose up -d`. Un comando que lo escribe sin mostrar la clave:

```bash
PEM=/ruta/a/ID-DE-LA-APLICACION.pem
printf "OPENFINANCE_BANK_PRIVATE_KEY='%s'\n" "$(awk '{printf "%s\\n",$0}' "$PEM")" >> .env
```

3. Cada persona, en **Ajustes → Conexión con el banco**, elige país y banco (el que dice el agregador: **Revolut** y **Bankinter** salen con país `ES`; el desplegable propone los nombres exactos), autoriza en la web del banco y, al volver, elige a qué cuenta de OpenFinance alimenta cada cuenta del banco. Una conexión es de quien la crea: la otra persona no la ve.
4. Los movimientos se traen con **Sincronizar ahora** o programando `cron`; es idempotente (no duplica) y respeta el límite de consultas del banco (no vuelve a consultar una conexión sincronizada hace menos de 6 horas):

```cron
0 */6 * * * cd /ruta/a/openfinance && docker compose exec -T api openfinance bank sync >> /var/log/openfinance-bank.log 2>&1
```

   Cada sincronización con novedades es un lote en «Importar» y se puede deshacer como cualquier extracto.
5. El consentimiento PSD2 caduca (hasta 180 días). Se avisa 14 días antes; renovarlo es conectar de nuevo. **Revocar** en Ajustes detiene la sincronización y pide al banco cerrar la sesión.

**Probado con Revolut (`ES`, el 3 de noviembre de 2026)**: autorización, lectura de cuentas y una sincronización de 90 días (132 movimientos) cuya suma coincide con el saldo del banco al céntimo. Bankinter aún no.

**El saldo inicial de la cuenta es el de antes del primer movimiento que se trae, no el de hoy.** Si pones el saldo actual, tras la primera sincronización Ajustes enseñará una diferencia igual (con signo contrario) a la suma de los movimientos traídos. Esa diferencia es la que corrige el saldo inicial: `saldo del banco − suma de los movimientos`. Desde la primera sincronización se piden 90 días de historial; lo anterior hay que importarlo con un extracto.

### Restaurar

```bash
make restore FILE=backups/openfinance-20261101-033000.dump.age OPENFINANCE_BACKUP_IDENTITY=clave.txt
```

Se restauran también los adjuntos de la misma fecha, si hay (los actuales se sustituyen). Si la copia está cifrada hay que dar la clave privada (`OPENFINANCE_BACKUP_IDENTITY`); se descifra a un fichero temporal con permisos 600 que se borra al terminar. Primero comprueba que la copia se puede leer; luego pide escribir «restaurar» y sustituye **todos** los datos actuales. Restaurad con la misma versión de OpenFinance que hizo la copia o una más nueva: después se aplican las migraciones pendientes. Al terminar se cierran todas las sesiones y hay que volver a entrar.

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
