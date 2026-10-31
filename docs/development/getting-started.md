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
make api                      # http://localhost:8000 · OpenAPI en /docs
make web                      # http://localhost:5173 (proxy de /api y /health a la API)
```

`/health` y `/api/v1/meta` no necesitan base de datos, así que la API arranca aunque PostgreSQL no esté disponible todavía.

## Con Docker Compose

```bash
cp .env.example .env          # define POSTGRES_PASSWORD
make up                       # db + api + web
```

- Web (nginx con el build de producción y proxy a la API): http://localhost:8080
- API: http://localhost:8000

Los puertos solo se publican en `127.0.0.1`. `make down` para parar; los datos persisten en el volumen `db-data`.

## Calidad

```bash
make check     # lint, tipos, contratos de capas, tests y build
make test      # solo tests
```

CI (`.github/workflows/ci.yml`) ejecuta lo mismo y además aplica las migraciones sobre PostgreSQL y verifica con `alembic check` que el modelo y las migraciones coinciden.
