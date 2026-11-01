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

```bash
make backup                   # backups/openfinance-AAAAmmdd-HHMMSS.dump (permisos 600)
make backup DIR=/mnt/disco    # en otra carpeta
```

La copia contiene **todo**: las cuentas personales de ambas personas y los hashes de las contraseñas. **No va cifrada.** Guardadla fuera del equipo (disco externo, otra máquina) y cifradla si sale de casa.

Copia diaria con `cron` (`crontab -e`), a las 3:30, conservando 30 días:

```cron
30 3 * * * cd /ruta/a/openfinance && make backup DIR=/mnt/disco/openfinance >> /var/log/openfinance-backup.log 2>&1 && find /mnt/disco/openfinance -name 'openfinance-*.dump' -mtime +30 -delete
```

### Restaurar

```bash
make restore FILE=backups/openfinance-20261101-033000.dump
```

Primero comprueba que la copia se puede leer; luego pide escribir «restaurar» y sustituye **todos** los datos actuales. Restaurad con la misma versión de OpenFinance que hizo la copia o una más nueva: después se aplican las migraciones pendientes. Al terminar se cierran todas las sesiones y hay que volver a entrar.

> **Restaurad solo copias vuestras** (hechas con `make backup` en vuestra instalación). `pg_restore` se ejecuta con el usuario de PostgreSQL de la instalación, que es superusuario de la base de datos: una copia manipulada podría ejecutar SQL arbitrario con esos permisos.

Si la restauración falla a medias, el script lo dice y deja la API parada. No la arranquéis sin ejecutar antes `docker compose run --rm --no-deps -T api openfinance sessions revoke-all` (o repetid la restauración con la misma copia).

## 7. Exportar vuestros datos

Desde la web, **Exportar** (arriba a la derecha) descarga un JSON o un ZIP con un CSV por entidad. Cada persona exporta lo que ve: la cuenta personal de la otra no se incluye. Para una copia completa, usad `make backup`.

## 8. Actualizar

```bash
make backup                   # antes de nada
git pull
make up                       # reconstruye; las migraciones se aplican al arrancar la API
```

## Problemas frecuentes

| Síntoma | Causa |
| --- | --- |
| Entro y vuelvo a la pantalla de login | Cookie `Secure` por http: `OPENFINANCE_SESSION_COOKIE_SECURE=false` en el modo `direct`, o usad HTTPS |
| `Define POSTGRES_PASSWORD en .env` | Falta `.env` o la variable |
| `ports: !reset` no válido | Docker Compose anterior a 2.24 |
| Caddy no obtiene el certificado | DNS no apunta a casa o los puertos 80/443 no llegan al equipo |
| `Demasiados intentos` | Límite de intentos de login: esperad 15 minutos |
