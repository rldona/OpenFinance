API_DIR := services/api
WEB_DIR := apps/web

.PHONY: setup api web test lint typecheck check up down migrate bootstrap openapi demo

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

migrate:
	cd $(API_DIR) && uv run alembic upgrade head

bootstrap:
	cd $(API_DIR) && uv run openfinance bootstrap

openapi:
	cd $(API_DIR) && uv run python -m openfinance.api.export_openapi > ../../$(WEB_DIR)/openapi.json
	cd $(WEB_DIR) && npm run gen:api

demo:
	cd $(API_DIR) && uv run openfinance demo
