FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS base

COPY --from=ghcr.io/astral-sh/uv:0.8@sha256:1d31be550ff927957472b2a491dc3de1ea9b5c2d319a9cea5b6a48021e2990a6 /uv /usr/local/bin/uv

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

# --proxy-headers con cualquier origen es seguro aquí: la API no publica puertos y solo la
# alcanza nginx por la red interna, que sobrescribe X-Forwarded-For y X-Forwarded-Proto.
# --no-access-log: la API escribe su propia línea de acceso (sin la query de la URL, OF-904).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn openfinance.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' --no-access-log"]
