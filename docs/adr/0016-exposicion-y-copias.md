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
- La copia contiene **todo** el hogar, incluidas las cuentas personales de ambas personas y los hashes de las contraseñas, y **no va cifrada**.
- `make restore FILE=… [YES=1]` (`deploy/scripts/restore.sh`): comprueba la copia con `pg_restore --list`, pide escribir «restaurar» (salvo `--yes`), para la API, restaura con `pg_restore --clean --if-exists --no-owner --single-transaction`, borra las sesiones restauradas con `psql` antes de migrar, aplica las migraciones pendientes y **cierra todas las sesiones** (`openfinance sessions revoke-all`, que también purga el contenido caducado de importaciones). Si algo falla, avisa y deja la API parada. Se restaura con la misma versión de OpenFinance o una más nueva, y solo copias propias: `pg_restore` corre como superusuario de la base de datos.

### Exportación

- `GET /api/v1/export?format=json|csv` exporta **lo que ve quien la pide**: cuentas visibles (sin la personal de la otra persona) con sus movimientos y saldos, categorías, reglas del hogar y las personales propias, presupuestos, objetivos (sin la cuenta vinculada si no es visible), y los patrones propios y los de entrada de los demás. Nunca sesiones, hashes, lotes de importación ni huellas de movimientos. Se decide en un único caso de uso (`application/export.py`).
- JSON: importes como texto decimal exacto (`"-12.30"`), fechas ISO 8601. CSV: un ZIP con `manifest.json` y un CSV por entidad (UTF-8 con BOM, RFC 4180 con todos los campos entre comillas, punto decimal); los textos que empiezan por `=`, `+`, `-`, `@`, tabulador o retorno de carro, o que tras un `;`, tabulador o salto de línea (y espacios) tienen uno de `=`, `+`, `-`, `@`, llevan delante un apóstrofo para que una hoja de cálculo (Excel en español separa con `;`) no los ejecute como fórmula. Importes y fechas nunca se tocan.
- El archivo lleva `format_version` (hoy `1`): sube si cambia su forma. Las respuestas van con `Content-Disposition: attachment`, `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`.

## Consecuencias

- Para usar el modo `caddy` hacen falta un dominio, DNS apuntando a la IP pública y los puertos 80/443 abiertos en el router. Sin eso, el modo `direct` en la red local es lo recomendado.
- Mezclar modos (publicar nginx y además Caddy) no está soportado: con `real_ip` desde cualquier origen, publicar nginx en modo `caddy` permitiría falsificar la IP.
- La exportación no sirve como copia de seguridad: no incluye lo que la persona no ve. La copia completa es `make backup`.
- Guardar las copias fuera del equipo (y cifrarlas si salen de casa) queda en manos de quien instala; la guía lo explica.
- CI (`compose-e2e`) prueba ambos modos de extremo a extremo: puertos, IP falsificada, cookie `Secure`, exportación, copia y restauración con los mismos saldos, y que los logs no contienen secretos.
