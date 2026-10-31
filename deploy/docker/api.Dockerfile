FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY services/api/pyproject.toml services/api/uv.lock services/api/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/api/ ./
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 openfinance
USER openfinance

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn openfinance.main:app --host 0.0.0.0 --port 8000"]
