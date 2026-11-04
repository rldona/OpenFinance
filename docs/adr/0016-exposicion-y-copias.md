# ADR-0016: Home exposure, backups and export

- Status: Accepted
- Date: 2026-11-01

## Context

Phase 5 (OF-501, OF-502) puts OpenFinance into real use on a home machine (x86-64) with Docker Compose. Three things are needed that had not been decided until now:

1. **How the application is reached**: from the machine itself, from a phone on the home network and, if desired, from outside with HTTPS. The session cookie is `Secure` in production, and a browser discards that cookie if it arrives over `http://` at a host that is not `localhost`.
2. **Which IP the API sees**: the login attempt limit counts failures per IP. Behind proxies, if the API trusts an `X-Forwarded-For` that the client can write, anyone can bypass the limit by inventing IPs.
3. **Backups and export**: being able to go back to a backup with one command and take the data away in an open format, without breaking the privacy of personal accounts (ADR-0013).

## Decision

### Two exposure modes, mutually exclusive per installation

- **`direct`** (default): the browser talks to nginx (the `web` container), published at `${OPENFINANCE_BIND:-127.0.0.1}:${OPENFINANCE_PORT:-8080}`. To reach it from a phone, it is published on the local network IP and `OPENFINANCE_SESSION_COOKIE_SECURE=false` is set, because access is over `http://`.
- **`caddy`**: `compose.https.yaml` is added (`COMPOSE_FILE=compose.yaml:compose.https.yaml` in `.env`). Caddy publishes 80/443, obtains the certificate for the domain (`OPENFINANCE_DOMAIN`) and adds `Strict-Transport-Security`; nginx stops publishing ports (`ports: !reset []`, Docker Compose ≥ 2.24) and the cookie is always `Secure`.
- Neither PostgreSQL nor the API publish ports. Networks: `data` (internal, `db` and `api`), `app` (`api` and `web`) and `edge` (`web` and `caddy`, only in `caddy` mode). For development, `compose.dev.yaml` publishes PostgreSQL on `127.0.0.1:5432` (`make db`).
- Web and API share an origin behind nginx: `OPENFINANCE_CORS_ORIGINS=[]`.
- On login, if the cookie is `Secure` and the request arrived over `http` at a host that is not `localhost`, the API writes a warning to the log (without request data).

### Real client IP

- nginx always **overwrites** `X-Forwarded-For` with `$remote_addr` and `X-Forwarded-Proto` with the scheme; it never appends to what the client sends.
- The nginx configuration is a template (`deploy/docker/nginx/default.conf.template`, substituted by the official image with `envsubst`) that includes `proxy-${OPENFINANCE_PROXY_MODE}.conf`. The mode is not read from `.env`: `compose.yaml` sets it to `direct` and only `compose.https.yaml` changes it to `caddy`:
  - `direct`: the scheme is that of the connection.
  - `caddy`: `real_ip` takes the IP from the `X-Forwarded-For` that Caddy sets (which, with no trusted proxies configured, overwrites it with the real IP) and the scheme from `X-Forwarded-Proto`. It is safe to trust any origin because only Caddy reaches nginx.
- The nginx limit (`limit_req` on login) and the API limit use that IP. Uvicorn starts with `--proxy-headers --forwarded-allow-ips "*"`: the API is reachable only from nginx over the internal network.

### Backups

- `make backup` (`deploy/scripts/backup.sh`): `pg_dump -Fc` inside the container, written with `umask 077` to `backups/openfinance-YYYYmmdd-HHMMSS.dump.part`, verified with `pg_restore --list`, with `600` permissions and renamed at the end (a half-written backup never remains under the real name).
- The backup contains **everything** in the household, including both people's personal accounts and password hashes. Since OF-901 it is **encrypted with `age`** (`.dump.age`) to the public key `OPENFINANCE_BACKUP_RECIPIENT`; the private key does not need to be on the machine. Without a public key `make backup` refuses, unless `OPENFINANCE_BACKUP_PLAINTEXT=1`. Since encrypted content can no longer be checked, the dump is verified with `pg_restore --list` before encrypting; the plaintext dump lives for a few seconds in the same folder with 600 permissions. `OPENFINANCE_BACKUP_KEEP` (30) rotates old backups, only those with the exact name `openfinance-YYYYmmdd-HHMMSS.dump[.age]`. `make restore` of an encrypted backup asks for `OPENFINANCE_BACKUP_IDENTITY` and decrypts it to a 600 temporary file.
- `make restore FILE=… [YES=1]` (`deploy/scripts/restore.sh`): checks the backup with `pg_restore --list`, asks you to type "restaurar" (restore) (unless `--yes`), stops the API, restores with `pg_restore --clean --if-exists --no-owner --single-transaction`, deletes the restored sessions with `psql` before migrating, applies pending migrations and **closes all sessions** (`openfinance sessions revoke-all`, which also purges expired import content). If anything fails, it warns and leaves the API stopped. Restore with the same OpenFinance version or a newer one, and only your own backups: `pg_restore` runs as the database superuser.

### Export

- `GET /api/v1/export?format=json|csv` exports **what the requester can see**: visible accounts (excluding the other person's personal one) with their transactions and balances, categories, household rules and the requester's own personal ones, budgets, goals (without the linked account if it is not visible), and the requester's own patterns and the inflow patterns of the others. Never sessions, hashes, import batches or transaction fingerprints. It is decided in a single use case (`application/export.py`).
- JSON: amounts as exact decimal text (`"-12.30"`), ISO 8601 dates. CSV: a ZIP with `manifest.json` and one CSV per entity (UTF-8 with BOM, RFC 4180 with all fields quoted, decimal point); texts that start with `=`, `+`, `-`, `@`, tab or carriage return, or that have one of `=`, `+`, `-`, `@` after a `;`, tab or line break (and spaces), are prefixed with an apostrophe so that a spreadsheet (Spanish Excel separates with `;`) does not execute them as a formula. Amounts and dates are never touched.
- Since OF-1002 each transaction carries `tags` (tags separated by "|"). Adding a field does not change `format_version`.
- The file carries `format_version` (currently `1`): it goes up if its shape changes. Responses are sent with `Content-Disposition: attachment`, `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

## Consequences

- To use `caddy` mode you need a domain, DNS pointing to the public IP, and ports 80/443 open on the router. Without that, `direct` mode on the local network is recommended.
- Mixing modes (publishing nginx and also Caddy) is not supported: with `real_ip` from any origin, publishing nginx in `caddy` mode would allow IP spoofing.
- The export does not work as a backup: it does not include what the person cannot see. The full backup is `make backup`.
- Storing backups off the machine is up to whoever installs (the guide gives recipes with `rsync` and `rclone`). Losing the `age` private key means losing the backups.
- CI (`compose-e2e`) tests both modes end to end: ports, spoofed IP, `Secure` cookie, export, backup and restore with the same balances, and that the logs contain no secrets.

## Operations (OF-901 … OF-907)

- **Supply chain:** base images and GitHub actions are pinned by digest or SHA; Renovate proposes updates. CI runs `pip-audit`, `npm audit` and Trivy (repository and images) and fails on high or critical vulnerabilities that have a fix.
- **Hardening:** all containers run with `no-new-privileges`; API and nginx with a read-only filesystem and no capabilities except those nginx needs to open port 80; logs with rotation (5 × 10 MB). nginx compresses only static content (never the API, because of BREACH), applies long caching only to hashed files, `no-cache` to the page and the service worker, and `no-store` to the API.
- **Observability:** `OPENFINANCE_LOG_LEVEL` is applied; each request carries `X-Request-ID` (nginx's if valid) and leaves one line without query string or headers. `/ready` checks the database and is the API's `healthcheck`.
- **Published and signed images:** on each `vX.Y.Z` tag, ghcr.io with keyless cosign (GitHub OIDC). Anyone who prefers to build locally can still do so.
- **Opt-in new-version notice:** querying GitHub reveals that there is an installation at that IP, and the project is local-first (ADR-0007), so `OPENFINANCE_UPDATE_CHECK` is off by default; it sends no data and only notifies.

## Attachments (OF-1007)

- Transaction attachments are files in the `attachments` volume (`/data/attachments` in the API), named by identifier in two levels of folders and with 600 permissions; the metadata is in the `attachments` table. Only PDF, PNG, JPEG and WebP recognized by their content, 5 MB at most and 10 per transaction. They are always served as a download (`Content-Disposition: attachment`, `nosniff`, `no-store` and CSP `sandbox`).
- They inherit the transaction's visibility: whoever cannot see the account cannot list, download or delete them, nor undo their creation. Deletion is soft: the file is kept for 30 days and purged when the API starts.
- `make backup` stores the attachments in a second file with the same date and the same encryption; `make restore` restores them. The JSON/CSV export carries only their count, not the files.
