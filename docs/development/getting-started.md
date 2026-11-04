# Getting started

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 24 and npm
- PostgreSQL 16 (or Docker, which starts it for you)

## Local development without Docker

```bash
cp .env.example .env          # adjust DATABASE_URL
make setup
make db                       # optional: PostgreSQL in Docker, published on 127.0.0.1:5432
make migrate                  # requires PostgreSQL reachable at DATABASE_URL
make bootstrap                # household setup: two people, joint account and personal accounts
make api                      # http://localhost:8000 · OpenAPI at /docs
make web                      # http://localhost:5173 (proxies /api and /health to the API)
```

To try it without PostgreSQL, `DATABASE_URL=sqlite:///./dev.db` is enough (development only).

To see the charts without real data: `make demo` creates a fictional household with 12 months of transactions (users `raul@demo.openfinance` and `elena@demo.openfinance`, password `demo-openfinance`). Do not use it on an installation with real data.

`make bootstrap` asks for the household name, each person's name, email and password, the initial balance of the joint Revolut account, and whether to add the personal Bankinter accounts. There is no public sign-up: setup is done once from the server.

### Available API

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Signs in (`{"email", "password"}`) and sets an `HttpOnly` cookie |
| `POST` | `/api/v1/auth/logout` | Signs out |
| `GET` | `/api/v1/me` | Person, household and members |
| `GET` | `/api/v1/accounts` | Visible accounts with their balance |
| `GET` | `/api/v1/transactions` | Visible transactions; filters `month=YYYY-MM`, `q`, `uncategorized`, `account_id` |
| `POST` | `/api/v1/imports` | Preview of a statement (multipart: `account_id`, `file`); saves nothing |
| `POST` | `/api/v1/imports/{id}/commit` | Saves the new transactions from the preview; repeating it does not duplicate |
| `GET` / `POST` | `/api/v1/categories` | Household categories / create one |
| `PATCH` | `/api/v1/categories/{id}` | Rename, icon, color or hide |
| `PATCH` | `/api/v1/transactions/{id}` | Set or remove an expense's category; with `learn` it learns the merchant rule |
| `GET` | `/api/v1/transactions/uncategorized-count` | Uncategorized expenses visible to you |
| `GET` | `/api/v1/insights/month?month=YYYY-MM` | Month summary for the "Este mes" (This month) screen |
| `GET` | `/api/v1/insights/category?month=&category_id=` | One category over 12 months and its merchants |
| `GET` | `/api/v1/insights/trends?month=&months=12` | Monthly trends |
| `GET` | `/api/v1/budgets?month=` | Budgets with amount spent and status |
| `PUT` / `DELETE` | `/api/v1/budgets/{category_id}` | Set or remove a category's budget |
| `GET` / `POST` | `/api/v1/goals` | Savings goals with their projection / create one |
| `PATCH` / `DELETE` | `/api/v1/goals/{id}` | Update or delete a goal |
| `GET` | `/api/v1/savings/overview` | "Ahorrar" (Save) screen: averages, fixed payments, ideas and goals |
| `GET` | `/api/v1/export?format=json\|csv` | Downloads what the requester can see: JSON or a ZIP with one CSV per entity |

All requests that write (`POST`, `PUT`, `PATCH`, `DELETE`) must carry the `X-Requested-With: OpenFinance` header; the web client adds it automatically.

If you change the API, regenerate the contract and the web types with `make openapi` (CI checks they are up to date).

Amounts travel as exact decimal text: `{"amount": "-87.34", "currency": "EUR"}`.

`/health` and `/api/v1/meta` do not need a database, so the API starts even if PostgreSQL is not available yet.

## With Docker Compose

```bash
cp .env.example .env          # set POSTGRES_PASSWORD
make up                       # db + api + web
```

- Web (nginx with the production build and a proxy to the API): http://localhost:8080
- Household setup: `docker compose exec api openfinance bootstrap`
- Neither PostgreSQL nor the API publishes ports; to develop against the Docker PostgreSQL use `make db`.

`make down` stops it; data persists in the `db-data` volume. Phone access, HTTPS with your own domain, backups (`make backup`, `make restore`) and upgrading: [Install at home](../deployment/home.md).

## Quality

```bash
make check     # lint, types, layer contracts, tests and build
make test      # tests only
```

CI (`.github/workflows/ci.yml`) runs the same, but the database tests run against PostgreSQL (`TEST_DATABASE_URL`) instead of SQLite. It also applies the migrations and verifies with `alembic check` that the model and the migrations match.

### Browser tests (Playwright)

`make e2e` runs `apps/web/e2e` against a running instance with the `openfinance demo` data: it checks that the screens are usable on a phone (Chrome at 360 px and Safari/WebKit at 390 px) and on desktop, that the charts fit and are legible, the "Importar" (Import) flow and the export. It is not part of `make check`. The first time, install the browsers with `cd apps/web && npx playwright install chromium webkit`.

```bash
# Without Docker: throwaway SQLite, API, demo and vite (each in its own terminal)
export DATABASE_URL=sqlite:////tmp/openfinance-e2e.db
make migrate && make demo && make api
make web
E2E_BASE_URL=http://localhost:5173 make e2e
```

By default it targets `http://127.0.0.1:8080`, the Docker Compose installation in direct mode; this is how CI runs it against a throwaway installation (`openfinance demo --force`).

Variables: `E2E_BASE_URL`, `E2E_EMAIL` and `E2E_PASSWORD` (the demo ones by default), `E2E_INSECURE_TLS=1` for Caddy's internal certificate and `E2E_SCREENSHOTS=<dir>` to save screenshots of each screen. Each run imports new transactions into the joint account: use it with test data, never against your real installation. Sign-in happens only once per run (nginx rate-limits attempts).

The `compose-e2e` job brings up the Docker Compose installation in both modes (`direct` and `https` with Caddy) and checks ports, spoofed IP, the `Secure` cookie, Playwright, export, backup and restore with the same balances, and that the logs contain no secrets (`deploy/scripts/ci/`). Without Docker locally, that part is only verified in CI.
