# Primeros pasos

## Requisitos

- Python 3.12 y [uv](https://docs.astral.sh/uv/)
- Node.js 24 y npm
- PostgreSQL 16 (o Docker, que lo levanta por ti)

## Desarrollo local sin Docker

```bash
cp .env.example .env          # ajusta DATABASE_URL
make setup
make db                       # opcional: PostgreSQL en Docker, publicado en 127.0.0.1:5432
make migrate                  # requiere PostgreSQL accesible en DATABASE_URL
make bootstrap                # alta del hogar: dos personas, cuenta conjunta y cuentas personales
make api                      # http://localhost:8000 · OpenAPI en /docs
make web                      # http://localhost:5173 (proxy de /api y /health a la API)
```

Para probar sin PostgreSQL basta con `DATABASE_URL=sqlite:///./dev.db` (solo desarrollo).

Para ver los gráficos sin datos reales: `make demo` crea un hogar ficticio con 12 meses de movimientos (usuarios `raul@demo.openfinance` y `elena@demo.openfinance`, contraseña `demo-openfinance`). No lo uses en una instalación con datos reales.

`make bootstrap` pregunta por el nombre del hogar, el nombre, el email y la contraseña de cada persona, el saldo inicial de la cuenta conjunta de Revolut y si se añaden las cuentas personales de Bankinter. No hay registro público: el alta se hace una vez desde el servidor.

### API disponible

| Método | Ruta | Qué hace |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Inicia sesión (`{"email", "password"}`) y deja una cookie `HttpOnly` |
| `POST` | `/api/v1/auth/logout` | Cierra la sesión |
| `GET` | `/api/v1/me` | Persona, hogar y miembros |
| `GET` | `/api/v1/accounts` | Cuentas visibles con su saldo |
| `GET` | `/api/v1/transactions` | Movimientos visibles; filtros `month=AAAA-MM`, `q`, `uncategorized`, `account_id` |
| `POST` | `/api/v1/imports` | Vista previa de un extracto (multipart: `account_id`, `file`); no guarda nada |
| `POST` | `/api/v1/imports/{id}/commit` | Guarda los movimientos nuevos de la vista previa; repetirlo no duplica |
| `GET` / `POST` | `/api/v1/categories` | Categorías del hogar / crear una |
| `PATCH` | `/api/v1/categories/{id}` | Renombrar, icono, color u ocultar |
| `PATCH` | `/api/v1/transactions/{id}` | Poner o quitar la categoría de un gasto; con `learn` aprende la regla del comercio |
| `GET` | `/api/v1/transactions/uncategorized-count` | Gastos sin categoría visibles para ti |
| `GET` | `/api/v1/insights/month?month=AAAA-MM` | Resumen del mes para «Este mes» |
| `GET` | `/api/v1/insights/category?month=&category_id=` | Una categoría en 12 meses y sus comercios |
| `GET` | `/api/v1/insights/trends?month=&months=12` | Evolución mensual |
| `GET` | `/api/v1/budgets?month=` | Presupuestos con lo gastado y su estado |
| `PUT` / `DELETE` | `/api/v1/budgets/{category_id}` | Poner o quitar el presupuesto de una categoría |
| `GET` / `POST` | `/api/v1/goals` | Objetivos de ahorro con su proyección / crear uno |
| `PATCH` / `DELETE` | `/api/v1/goals/{id}` | Actualizar o borrar un objetivo |
| `GET` | `/api/v1/savings/overview` | Pantalla Ahorrar: medias, cuotas fijas, ideas y objetivos |
| `GET` | `/api/v1/export?format=json\|csv` | Descarga lo que ve quien la pide: JSON o ZIP con un CSV por entidad |

Todas las peticiones que escriben (`POST`, `PUT`, `PATCH`, `DELETE`) deben llevar la cabecera `X-Requested-With: OpenFinance`; el cliente de la web la añade solo.

Si cambias la API, regenera el contrato y los tipos de la web con `make openapi` (CI comprueba que estén al día).

Los importes viajan como texto decimal exacto: `{"amount": "-87.34", "currency": "EUR"}`.

`/health` y `/api/v1/meta` no necesitan base de datos, así que la API arranca aunque PostgreSQL no esté disponible todavía.

## Con Docker Compose

```bash
cp .env.example .env          # define POSTGRES_PASSWORD
make up                       # db + api + web
```

- Web (nginx con el build de producción y proxy a la API): http://localhost:8080
- Alta del hogar: `docker compose exec api openfinance bootstrap`
- Ni PostgreSQL ni la API publican puertos; para desarrollar contra el PostgreSQL de Docker usa `make db`.

`make down` para parar; los datos persisten en el volumen `db-data`. Acceso desde el móvil, HTTPS con dominio propio, copias (`make backup`, `make restore`) y actualización: [Instalar en casa](../deployment/home.md).

## Calidad

```bash
make check     # lint, tipos, contratos de capas, tests y build
make test      # solo tests
```

CI (`.github/workflows/ci.yml`) ejecuta lo mismo, pero los tests de base de datos corren contra PostgreSQL (`TEST_DATABASE_URL`) en lugar de SQLite. Además aplica las migraciones y verifica con `alembic check` que el modelo y las migraciones coinciden.

### Pruebas en navegador (Playwright)

`make e2e` ejecuta `apps/web/e2e` contra una instancia en marcha con los datos de `openfinance demo`: comprueba que las pantallas se usan en un móvil (Chrome a 360 px y Safari/WebKit a 390 px) y en escritorio, que los gráficos caben y se leen, el flujo Importar y la exportación. No forma parte de `make check`. La primera vez instala los navegadores con `cd apps/web && npx playwright install chromium webkit`.

```bash
# Sin Docker: SQLite desechable, API, demo y vite (cada uno en su terminal)
export DATABASE_URL=sqlite:////tmp/openfinance-e2e.db
make migrate && make demo && make api
make web
E2E_BASE_URL=http://localhost:5173 make e2e
```

Por defecto apunta a `http://127.0.0.1:8080`, la instalación de Docker Compose en modo directo; así lo ejecuta CI sobre una instalación desechable (`openfinance demo --force`).

Variables: `E2E_BASE_URL`, `E2E_EMAIL` y `E2E_PASSWORD` (por defecto las del demo), `E2E_INSECURE_TLS=1` para el certificado interno de Caddy y `E2E_SCREENSHOTS=<dir>` para guardar capturas de cada pantalla. Cada ejecución importa movimientos nuevos en la cuenta conjunta: úsalo con datos de prueba, nunca contra vuestra instalación real. El inicio de sesión se hace una sola vez por ejecución (nginx limita los intentos).

El job `compose-e2e` levanta la instalación de Docker Compose en sus dos modos (`direct` y `https` con Caddy) y comprueba puertos, IP falsificada, cookie `Secure`, Playwright, exportación, copia y restauración con los mismos saldos y que los logs no contienen secretos (`deploy/scripts/ci/`). Sin Docker en local, esa parte solo se verifica en CI.
