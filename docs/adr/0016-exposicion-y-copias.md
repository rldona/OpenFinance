# ADR-0016: Exposición en casa, copias de seguridad y exportación

- Estado: Accepted
- Fecha: 2026-11-01

## Contexto

La fase 5 (OF-501, OF-502) pone OpenFinance en uso real en un equipo de casa (x86-64) con Docker Compose. Hacen falta tres cosas que hasta ahora no estaban decididas:

1. **Cómo se llega a la aplicación**: desde el propio equipo, desde el móvil en la red de casa y, si se quiere, desde fuera con HTTPS. La cookie de sesión es `Secure` en producción, y un navegador descarta esa cookie si llega por `http://` a un host que no es `localhost`.
2. **Qué IP ve la API**: el límite de intentos de login cuenta fallos por IP. Detrás de proxies, si la API se fía de un `X-Forwarded-For` que puede escribir el cliente, cualquiera se salta el límite inventando IPs.
3. **Copias y exportación**: poder volver a una copia con un comando y llevarse los datos en un formato abierto, sin romper la privacidad de las cuentas personales (ADR-0013).

## Decisión

### Dos modos de exposición, excluyentes por instalación

- **`direct`** (por defecto): el navegador habla con nginx (contenedor `web`), publicado en `${OPENFINANCE_BIND:-127.0.0.1}:${OPENFINANCE_PORT:-8080}`. Para entrar desde el móvil se publica en la IP de la red local y se pone `OPENFINANCE_SESSION_COOKIE_SECURE=false`, porque se entra por `http://`.
- **`caddy`**: se añade `compose.https.yaml` (`COMPOSE_FILE=compose.yaml:compose.https.yaml` en `.env`). Caddy publica 80/443, obtiene el certificado del dominio (`OPENFINANCE_DOMAIN`) y añade `Strict-Transport-Security`; nginx deja de publicar puertos (`ports: !reset []`, Docker Compose ≥ 2.24) y la cookie es siempre `Secure`.
- Ni PostgreSQL ni la API publican puertos. Redes: `data` (interna, `db` y `api`), `app` (`api` y `web`) y `edge` (`web` y `caddy`, solo en el modo `caddy`). Para desarrollar, `compose.dev.yaml` publica PostgreSQL en `127.0.0.1:5432` (`make db`).
- Web y API comparten origen detrás de nginx: `OPENFINANCE_CORS_ORIGINS=[]`.
- Al iniciar sesión, si la cookie es `Secure` y la petición llegó por `http` a un host que no es `localhost`, la API escribe un aviso en el log (sin datos de la petición).

### IP real del cliente

- nginx **sobrescribe** siempre `X-Forwarded-For` con `$remote_addr` y `X-Forwarded-Proto` con el esquema; nunca añade a lo que mande el cliente.
- La configuración de nginx es una plantilla (`deploy/docker/nginx/default.conf.template`, sustituida por la imagen oficial con `envsubst`) que incluye `proxy-${OPENFINANCE_PROXY_MODE}.conf`. El modo no se lee de `.env`: `compose.yaml` lo fija a `direct` y solo `compose.https.yaml` lo cambia a `caddy`:
  - `direct`: el esquema es el de la conexión.
  - `caddy`: `real_ip` toma la IP de `X-Forwarded-For` que pone Caddy (que, sin proxies de confianza configurados, la sobrescribe con la IP real) y el esquema de `X-Forwarded-Proto`. Es seguro confiar en cualquier origen porque a nginx solo llega Caddy.
- El límite de nginx (`limit_req` en el login) y el de la API usan esa IP. Uvicorn arranca con `--proxy-headers --forwarded-allow-ips "*"`: la API solo es alcanzable desde nginx por la red interna.

### Copias de seguridad

- `make backup` (`deploy/scripts/backup.sh`): `pg_dump -Fc` dentro del contenedor, escrito con `umask 077` a `backups/openfinance-AAAAmmdd-HHMMSS.dump.part`, verificado con `pg_restore --list`, con permisos `600` y renombrado al final (nunca queda una copia a medias con el nombre bueno).
- La copia contiene **todo** el hogar, incluidas las cuentas personales de ambas personas y los hashes de las contraseñas. Desde OF-901 **va cifrada con `age`** (`.dump.age`) a la clave pública `OPENFINANCE_BACKUP_RECIPIENT`; la privada no tiene por qué estar en el equipo. Sin clave pública `make backup` se niega, salvo `OPENFINANCE_BACKUP_PLAINTEXT=1`. Como lo cifrado ya no se puede comprobar, el volcado se verifica con `pg_restore --list` antes de cifrarlo; el volcado en claro vive unos segundos en la misma carpeta con permisos 600. `OPENFINANCE_BACKUP_KEEP` (30) rota las copias antiguas, solo las de nombre exacto `openfinance-AAAAmmdd-HHMMSS.dump[.age]`. `make restore` de una copia cifrada pide `OPENFINANCE_BACKUP_IDENTITY` y la descifra a un temporal 600.
- `make restore FILE=… [YES=1]` (`deploy/scripts/restore.sh`): comprueba la copia con `pg_restore --list`, pide escribir «restaurar» (salvo `--yes`), para la API, restaura con `pg_restore --clean --if-exists --no-owner --single-transaction`, borra las sesiones restauradas con `psql` antes de migrar, aplica las migraciones pendientes y **cierra todas las sesiones** (`openfinance sessions revoke-all`, que también purga el contenido caducado de importaciones). Si algo falla, avisa y deja la API parada. Se restaura con la misma versión de OpenFinance o una más nueva, y solo copias propias: `pg_restore` corre como superusuario de la base de datos.

### Exportación

- `GET /api/v1/export?format=json|csv` exporta **lo que ve quien la pide**: cuentas visibles (sin la personal de la otra persona) con sus movimientos y saldos, categorías, reglas del hogar y las personales propias, presupuestos, objetivos (sin la cuenta vinculada si no es visible), y los patrones propios y los de entrada de los demás. Nunca sesiones, hashes, lotes de importación ni huellas de movimientos. Se decide en un único caso de uso (`application/export.py`).
- JSON: importes como texto decimal exacto (`"-12.30"`), fechas ISO 8601. CSV: un ZIP con `manifest.json` y un CSV por entidad (UTF-8 con BOM, RFC 4180 con todos los campos entre comillas, punto decimal); los textos que empiezan por `=`, `+`, `-`, `@`, tabulador o retorno de carro, o que tras un `;`, tabulador o salto de línea (y espacios) tienen uno de `=`, `+`, `-`, `@`, llevan delante un apóstrofo para que una hoja de cálculo (Excel en español separa con `;`) no los ejecute como fórmula. Importes y fechas nunca se tocan.
- Desde OF-1002 cada movimiento lleva `tags` (etiquetas separadas por «|»). Añadir un campo no cambia `format_version`.
- El archivo lleva `format_version` (hoy `1`): sube si cambia su forma. Las respuestas van con `Content-Disposition: attachment`, `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`.

## Consecuencias

- Para usar el modo `caddy` hacen falta un dominio, DNS apuntando a la IP pública y los puertos 80/443 abiertos en el router. Sin eso, el modo `direct` en la red local es lo recomendado.
- Mezclar modos (publicar nginx y además Caddy) no está soportado: con `real_ip` desde cualquier origen, publicar nginx en modo `caddy` permitiría falsificar la IP.
- La exportación no sirve como copia de seguridad: no incluye lo que la persona no ve. La copia completa es `make backup`.
- Guardar las copias fuera del equipo queda en manos de quien instala (la guía da recetas con `rsync` y `rclone`). Perder la clave privada de `age` es perder las copias.
- CI (`compose-e2e`) prueba ambos modos de extremo a extremo: puertos, IP falsificada, cookie `Secure`, exportación, copia y restauración con los mismos saldos, y que los logs no contienen secretos.

## Operación (OF-901 … OF-907)

- **Cadena de suministro:** las imágenes base y las actions de GitHub van fijadas por digest o SHA; Renovate propone las actualizaciones. CI ejecuta `pip-audit`, `npm audit` y Trivy (repositorio e imágenes) y falla con vulnerabilidades altas o críticas que tengan arreglo.
- **Endurecimiento:** todos los contenedores con `no-new-privileges`; API y nginx con sistema de ficheros de solo lectura y sin capacidades salvo las que nginx necesita para abrir el puerto 80; logs con rotación (5 × 10 MB). nginx comprime solo lo estático (nunca la API, por BREACH), pone caché larga solo a los ficheros con hash, `no-cache` a la página y al service worker, y `no-store` a la API.
- **Observabilidad:** `OPENFINANCE_LOG_LEVEL` se aplica; cada petición lleva `X-Request-ID` (el de nginx si es válido) y deja una línea sin query ni cabeceras. `/ready` comprueba la base de datos y es el `healthcheck` de la API.
- **Imágenes publicadas y firmadas:** en cada etiqueta `vX.Y.Z`, ghcr.io con cosign sin claves (OIDC de GitHub). Quien prefiera construir en local puede seguir haciéndolo.
- **Aviso de versión nueva opt-in:** consultar GitHub revela que hay una instalación en esa IP, y el proyecto es local-first (ADR-0007), así que `OPENFINANCE_UPDATE_CHECK` está apagado por defecto; no envía datos y solo avisa.

## Adjuntos (OF-1007)

- Los adjuntos de movimientos son archivos en el volumen `attachments` (`/data/attachments` en la API), con el identificador por nombre en dos niveles de carpetas y permisos 600; los metadatos están en la tabla `attachments`. Solo PDF, PNG, JPEG y WebP reconocidos por su contenido, 5 MB como máximo y 10 por movimiento. Se descargan siempre como descarga (`Content-Disposition: attachment`, `nosniff`, `no-store` y CSP `sandbox`).
- Heredan la visibilidad del movimiento: quien no ve la cuenta no puede listarlos, descargarlos, borrarlos ni deshacer su alta. Borrar es suave: el archivo se conserva 30 días y se purga al arrancar la API.
- `make backup` guarda los adjuntos en un segundo fichero con la misma fecha y el mismo cifrado; `make restore` los restaura. La exportación JSON/CSV solo lleva su número, no los archivos.
