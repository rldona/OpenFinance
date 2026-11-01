API_DIR := services/api
WEB_DIR := apps/web

.PHONY: setup api web test lint typecheck check up down db migrate bootstrap openapi demo backup restore e2e licenses

setup:
	cd $(API_DIR) && uv sync
	cd $(WEB_DIR) && npm ci

api:
	cd $(API_DIR) && uv run uvicorn openfinance.main:app --reload --port 8000

web:
	cd $(WEB_DIR) && npm run dev

test:
	cd $(API_DIR) && uv run pytest
	cd $(WEB_DIR) && npm test -- --run

lint:
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
	cd $(WEB_DIR) && npm run lint

typecheck:
	cd $(API_DIR) && uv run mypy openfinance
	cd $(WEB_DIR) && npm run typecheck

check: lint typecheck test
	cd $(WEB_DIR) && npm run build

up:
	docker compose up --build -d

down:
	docker compose down

# PostgreSQL publicado en 127.0.0.1:5432 para desarrollar con `make api`
db:
	docker compose -f compose.yaml -f compose.dev.yaml up -d db

# Copia de la base de datos en backups/ (o DIR=...). Contiene todo y no va cifrada.
backup:
	deploy/scripts/backup.sh "$(DIR)"

# make restore FILE=backups/openfinance-....dump [YES=1]
restore:
	@test -n "$(FILE)" || { echo "Indica la copia: make restore FILE=backups/openfinance-....dump" >&2; exit 2; }
	deploy/scripts/restore.sh "$(FILE)" $(if $(YES),--yes,)

# Licencias de las dependencias (docs/legal/dependencias.md). CHECK=1 falla fuera de la lista permitida.
licenses:
	deploy/scripts/licenses.sh $(if $(CHECK),--check,)

# Pruebas de extremo a extremo (Playwright) contra una instancia en marcha (E2E_BASE_URL)
e2e:
	cd $(WEB_DIR) && npm run e2e

migrate:
	cd $(API_DIR) && uv run alembic upgrade head

bootstrap:
	cd $(API_DIR) && uv run openfinance bootstrap

openapi:
	cd $(API_DIR) && uv run python -m openfinance.api.export_openapi > ../../$(WEB_DIR)/openapi.json
	cd $(WEB_DIR) && npm run gen:api

demo:
	cd $(API_DIR) && uv run openfinance demo
