# Primeros pasos

## Requisitos

- Python 3.12 y [uv](https://docs.astral.sh/uv/)
- Node.js 24 y npm
- PostgreSQL 16 (o Docker, que lo levanta por ti)

## Desarrollo local sin Docker

```bash
cp .env.example .env          # ajusta DATABASE_URL
make setup
make migrate                  # requiere PostgreSQL accesible en DATABASE_URL
make bootstrap                # alta del hogar: dos personas, cuenta conjunta y cuentas personales
make api                      # http://localhost:8000 · OpenAPI en /docs
make web                      # http://localhost:5173 (proxy de /api y /health a la API)
```

Para probar sin PostgreSQL basta con `DATABASE_URL=sqlite:///./dev.db` (solo desarrollo).

`make bootstrap` pregunta por el nombre del hogar, el nombre, el email y la contraseña de cada persona, el saldo inicial de la cuenta conjunta de Revolut y si se añaden las cuentas personales de Bankinter. No hay registro público: el alta se hace una vez desde el servidor.

### API disponible

| Método | Ruta | Qué hace |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Inicia sesión (`{"email", "password"}`) y deja una cookie `HttpOnly` |
| `POST` | `/api/v1/auth/logout` | Cierra la sesión |
| `GET` | `/api/v1/me` | Persona, hogar y miembros |
| `GET` | `/api/v1/accounts` | Cuentas visibles con su saldo |
| `GET` | `/api/v1/transactions` | Movimientos visibles; filtros `month=AAAA-MM`, `q`, `uncategorized`, `account_id` |

Los importes viajan como texto decimal exacto: `{"amount": "-87.34", "currency": "EUR"}`.

`/health` y `/api/v1/meta` no necesitan base de datos, así que la API arranca aunque PostgreSQL no esté disponible todavía.

## Con Docker Compose

```bash
cp .env.example .env          # define POSTGRES_PASSWORD
make up                       # db + api + web
```

- Web (nginx con el build de producción y proxy a la API): http://localhost:8080
- API: http://localhost:8000
- Alta del hogar: `docker compose exec api openfinance bootstrap`

Los puertos solo se publican en `127.0.0.1`. `make down` para parar; los datos persisten en el volumen `db-data`.

En producción la cookie de sesión es `Secure`: funciona por HTTPS y en `http://localhost`. Si entráis desde otro equipo de casa por `http://` (p. ej. `http://192.168.1.20:8080`), poned `OPENFINANCE_SESSION_COOKIE_SECURE=false` en `.env`; fuera de casa, usad siempre HTTPS.

## Calidad

```bash
make check     # lint, tipos, contratos de capas, tests y build
make test      # solo tests
```

CI (`.github/workflows/ci.yml`) ejecuta lo mismo, pero los tests de base de datos corren contra PostgreSQL (`TEST_DATABASE_URL`) en lugar de SQLite. Además aplica las migraciones y verifica con `alembic check` que el modelo y las migraciones coinciden.
