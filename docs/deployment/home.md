# Install OpenFinance at home

Guide to getting OpenFinance running on a home machine with Docker Compose. The underlying decisions are in [ADR-0016](../adr/0016-exposicion-y-copias.md).

## Requirements

- An **x86-64** machine that is on whenever you use it (a mini PC, an old laptop or a NAS with Docker).
- **Docker** with **Docker Compose ≥ 2.24** (`docker compose version`).
- `make` and `git` (or download the repository).

## 1. Configuration

```bash
git clone <repositorio> openfinance && cd openfinance
cp .env.example .env
openssl rand -hex 24          # use it as POSTGRES_PASSWORD in .env
```

Edit `.env`: at a minimum `POSTGRES_PASSWORD`. The remaining values are explained in the following sections.

## 2. Start

```bash
make up                       # builds and starts db + api + web
docker compose ps             # all "healthy"
```

By default it can only be reached from the machine itself: http://localhost:8080. Neither the database nor the API publish ports.

## 3. Household setup

```bash
docker compose exec api openfinance bootstrap
```

It asks for the household name, each person's name, email and password, and the accounts. There is no public sign-up: more people join with an invitation created by whoever administers the household in **"Ajustes → Personas del hogar"** (Settings → Household members) (a single-use link valid for 7 days).

To identify contributions that do not carry your name (card top-ups, outflows from personal accounts), see `docker compose exec api openfinance member-patterns --help`.

More maintenance tasks from the server:

- If someone forgets their password: `docker compose exec api openfinance users set-password <email>`. It asks for it without echo and closes that person's open sessions.
- To add a pocket or an account after setup: `docker compose exec api openfinance accounts add <email> 'Hucha viaje' --kind savings --opening-balance 120.50`. With `--kind personal` the account belongs to that person and only its owner sees it.

## 4. Access from a phone at home (http)

In `.env`:

```dotenv
OPENFINANCE_BIND=192.168.1.20                 # the machine's IP on the home network (or 0.0.0.0)
OPENFINANCE_SESSION_COOKIE_SECURE=false       # accessed over http: the cookie cannot be Secure
```

Run `make up` again and open `http://192.168.1.20:8080` on the phone (it is a good idea to fix that IP in the router). If you forget `OPENFINANCE_SESSION_COOKIE_SECURE=false`, the login "works" but the browser does not keep the session; the API warns about it in `docker compose logs api`.

**Installing it as an app (OF-805).** With HTTPS and your own domain, the phone's browser offers "Add to home screen" (Chrome: ⋮ menu → *Install app*; Safari: Share → *Add to Home Screen*). Over `http://` on the local network only a shortcut is saved, without a service worker. The installed app only stores its shell: data is always requested from the server. The light or dark theme is chosen in "Ajustes → Apariencia" (Settings → Appearance).

This way traffic goes unencrypted inside the home network: use it only on a trusted network.

## 5. Access from outside with HTTPS (own domain)

You need a domain (or subdomain) with a DNS record pointing to the home's public IP and ports **80 and 443** on the router forwarded to this machine. In `.env`:

```dotenv
COMPOSE_FILE=compose.yaml:compose.https.yaml
OPENFINANCE_DOMAIN=finanzas.example.org
```

and remove `OPENFINANCE_SESSION_COOKIE_SECURE=false` if you had it. `make up` additionally starts Caddy, which obtains and renews the certificate, redirects http to https and adds `Strict-Transport-Security`. nginx stops publishing port 8080 and the cookie is always `Secure`. Use `https://finanzas.example.org`, also from home.

> **Warning.** In `caddy` mode, **do not publish nginx's port** (do not add `ports` to the `web` service or remove it from `compose.https.yaml`). In that mode nginx trusts the IP that Caddy passes in `X-Forwarded-For`; if nginx could be reached directly, anyone could forge the IP and bypass the login attempt limit. The two modes are mutually exclusive, and the mode is decided by the Compose file, not by a `.env` variable.

## 6. Backups

Backups are **encrypted with [age](https://github.com/FiloSottile/age)**: they cannot be opened without the private key, so they can leave the house without risk. The machine only stores the **public** key; the private one is kept elsewhere and is only needed to restore.

Once:

```bash
sudo apt install age          # or: brew install age
age-keygen -o clave.txt       # prints "Public key: age1..."
```

Store `clave.txt` **off the machine** (password manager, paper in a safe place, the other person): if you lose it, the backups cannot be recovered. In `.env` put only the public key:

```dotenv
OPENFINANCE_BACKUP_RECIPIENT=age1...
OPENFINANCE_BACKUP_KEEP=30     # backups kept (default 30; 0 = never delete)
```

(To encrypt to several keys, `OPENFINANCE_BACKUP_RECIPIENTS_FILE=fichero` with one public key per line.)

```bash
make backup                   # backups/openfinance-AAAAmmdd-HHMMSS.dump.age (permissions 600)
make backup DIR=/mnt/disco    # into another folder
```

Without a public key, `make backup` refuses to make the backup. It can only be done in plaintext knowingly, with `OPENFINANCE_BACKUP_PLAINTEXT=1`. The backup contains **everything**: both people's personal accounts and the password hashes. Attachments (receipts and invoices of transactions) live in a separate Docker volume and go in a second file with the same date, `openfinance-AAAAmmdd-HHMMSS.attachments.tar.age`, encrypted the same way; if there are no attachments it is not created. Before encrypting, the dump is checked to be readable; the plaintext dump is written briefly in the same folder with 600 permissions and deleted right away.

After each backup, the oldest ones are deleted until only `OPENFINANCE_BACKUP_KEEP` remain. Only files with the exact name `openfinance-AAAAmmdd-HHMMSS.dump[.age]` are touched.

### Keeping them off the machine

A backup on the same disk is useless if the disk fails. With encrypted backups, any of these works, because whoever steals them cannot read them:

- **Another disk or machine at home**: `make backup DIR=/mnt/disco/openfinance` (or `rsync -a backups/ otro-equipo:openfinance/`).
- **Cloud storage** with [rclone](https://rclone.org/): `rclone copy backups remoto:openfinance --include 'openfinance-*.dump.age'`.
- **A USB drive** that you move to a different place from time to time.

Daily backup with `cron` (`crontab -e`), at 3:30; rotation is already handled by the script:

```cron
30 3 * * * cd /ruta/a/openfinance && make backup DIR=/mnt/disco/openfinance >> /var/log/openfinance-backup.log 2>&1
```

Test a restore at least once (next section): a backup that has never been restored is not a backup.

### Phone notifications

Alerts (duplicates, fees, rising bills, late payments, negative balance) always show in "Este mes" (This month). To also receive them as phone notifications, Web Push is used ([ADR-0023](../adr/0023-avisos-y-notificaciones.md)); it needs HTTPS mode and, on iPhone, iOS 16.4 or later with the app added to the home screen.

1. Generate the keys once: `docker compose run --rm --no-deps -T api openfinance alerts keys`.
2. Paste the three lines into `.env` (the private one is a secret, like the PostgreSQL password), set `OPENFINANCE_VAPID_SUBJECT` to a `mailto:` of yours and run `docker compose up -d`.
3. On each phone: **"Ajustes → Notificaciones → Activar en este dispositivo"** (Settings → Notifications → Enable on this device). Each person chooses which types of alert they want.
4. Schedule the sending with `cron`; it is idempotent, it does not repeat what was already sent:

```cron
0 * * * * cd /ruta/a/openfinance && docker compose exec -T api openfinance alerts notify >> /var/log/openfinance-alerts.log 2>&1
```

The message only says how many alerts there are and of what type, with no amounts or merchants. The push services of Google, Apple and Mozilla see that there is a notification, not its financial content.

### Connecting the bank

Besides importing statements, OpenFinance can fetch transactions directly from the bank via PSD2 ([ADR-0024](../adr/0024-conexion-con-el-banco.md)). A bank only hands that data to an authorized provider, so you use **your own account** at [Enable Banking](https://enablebanking.com): its application data stays on your server and the transactions do not pass through any server of ours. It is read-only: it never moves money. It needs HTTPS mode.

1. Go to the [Enable Banking panel](https://enablebanking.com/cp/applications) and register an application:
   - **Environment: Production** (not Sandbox: Sandbox only talks to simulated banks). It stays "Inactive".
   - **Key:** leave "Generate in the browser". On registering, a `.pem` named with the application identifier is downloaded. Store it **outside the repository**; it is the key that signs all requests.
   - **Allowed redirect URLs:** the root of your website, **with `https` only** (`http://…` is rejected: "unsupported scheme"), with the trailing slash: `https://finanzas.ejemplo.org/`. To test on your machine, `https://localhost/` works with Compose's `https` mode (Caddy uses an internal CA: the browser warns about the certificate and you accept it once).
   - **Privacy URL and Terms URL:** the form asks for them even though they are marked as optional. For personal use, the repository address works.
   - Click **Activate by linking accounts** and authorize your accounts at the bank. Until then the application is inactive and can only read the **linked** accounts (restricted mode, for individual non-commercial use). The "Billing" screen is a commercial quote request: not needed.
2. In `.env`: `OPENFINANCE_BANK_APP_ID` (the application identifier), `OPENFINANCE_BANK_REDIRECT_URL` (that same address, identical) and `OPENFINANCE_BANK_PRIVATE_KEY` with the PEM on **a single line**, replacing each line break with `\n` and **in single quotes** (with double quotes Compose expands `\n`). The key is a secret, like the PostgreSQL password. Then `docker compose up -d`. A command that writes it without showing the key:

```bash
PEM=/ruta/a/ID-DE-LA-APLICACION.pem
printf "OPENFINANCE_BANK_PRIVATE_KEY='%s'\n" "$(awk '{printf "%s\\n",$0}' "$PEM")" >> .env
```

3. Each person, in **"Ajustes → Conexión con el banco"** (Settings → Bank connection), chooses country and bank (as the aggregator names it: **Revolut** and **Bankinter** appear with country `ES`; the dropdown suggests the exact names), authorizes on the bank's website and, on returning, chooses which OpenFinance account each bank account feeds. A connection belongs to whoever creates it: the other person does not see it.
4. Transactions are fetched with **"Sincronizar ahora"** (Sync now) or by scheduling `cron`; it is idempotent (it does not duplicate) and respects the bank's query limit (it does not query a connection again if it was synced less than 6 hours ago):

```cron
0 */6 * * * cd /ruta/a/openfinance && docker compose exec -T api openfinance bank sync >> /var/log/openfinance-bank.log 2>&1
```

   Each sync with new data is a batch in "Importar" (Import) and can be undone like any statement.
5. The PSD2 consent expires (after up to 180 days). A warning appears 14 days before; renewing it means connecting again. **Revoking** in Settings stops the sync and asks the bank to close the session.

**Tested with Revolut (`ES`, on 3 November 2026)**: authorization, reading accounts and a 90-day sync (132 transactions) whose sum matches the bank's balance to the cent. Bankinter not yet.

**The account's opening balance is the one from before the first fetched transaction, not today's.** If you enter the current balance, after the first sync Settings will show a difference equal (with opposite sign) to the sum of the fetched transactions. That difference is what corrects the opening balance: `bank balance − sum of the transactions`. From the first sync, 90 days of history are requested; anything earlier must be imported with a statement.

### Restoring

```bash
make restore FILE=backups/openfinance-20261101-033000.dump.age OPENFINANCE_BACKUP_IDENTITY=clave.txt
```

Attachments of the same date are also restored, if any (the current ones are replaced). If the backup is encrypted you must provide the private key (`OPENFINANCE_BACKUP_IDENTITY`); it is decrypted to a temporary file with 600 permissions that is deleted when done. First it checks that the backup is readable; then it asks you to type "restaurar" (restore) and replaces **all** current data. Restore with the same version of OpenFinance that made the backup or a newer one: pending migrations are applied afterwards. When finished, all sessions are closed and you have to sign in again.

> **Restore only your own backups** (made with `make backup` on your installation). `pg_restore` runs as the installation's PostgreSQL user, which is a database superuser: a tampered backup could run arbitrary SQL with those permissions.

If the restore fails midway, the script says so and leaves the API stopped. Do not start it without first running `docker compose run --rm --no-deps -T api openfinance sessions revoke-all` (or repeat the restore with the same backup).

## 7. Exporting your data

From the web app, **"Exportar"** (Export) (top right) downloads a JSON or a ZIP with one CSV per entity. Each person exports what they see: the other's personal account is not included. For a full backup, use `make backup`.

## 8. Published and signed images (optional)

By default `make up` builds the images on your machine. Each version (`vX.Y.Z`) is also published prebuilt for x86-64 and ARM at `ghcr.io/rldona/openfinance-api` and `ghcr.io/rldona/openfinance-web`, **signed with [cosign](https://github.com/sigstore/cosign)** without own keys: the signature comes from the identity of the GitHub workflow that built them and is recorded in Sigstore's public log. They also carry a bill of materials (SBOM) and provenance.

Verify the signature **before starting** (needs `cosign`):

```bash
V=0.2.0
for img in api web; do
  cosign verify "ghcr.io/rldona/openfinance-$img:$V" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity "https://github.com/rldona/OpenFinance/.github/workflows/release.yml@refs/tags/v$V"
done
```

If `Verification for … --` does not appear with the signature, do not use the image. To use them, in `.env`:

```dotenv
COMPOSE_FILE=compose.yaml:compose.images.yaml      # or compose.yaml:compose.images.yaml:compose.https.yaml
OPENFINANCE_VERSION=0.2.0
```

and `docker compose pull && make up`. Always pin a specific version, never `latest`.

### Notifying about new versions

With `OPENFINANCE_UPDATE_CHECK=true` in `.env`, the server asks GitHub's public API once a day for the latest release. If it is newer than yours, the web app shows a notice with a link to the release notes (it can be dismissed and does not return until the next version). **It only notifies**: nothing updates itself, and the query sends no data about the installation (GitHub sees the server's IP, as with any visit). It is off by default. To update, follow the next section.

## 9. Updating

```bash
make backup                   # first of all
git pull
make up                       # rebuilds; migrations are applied when the API starts
# with published images: change OPENFINANCE_VERSION in .env, verify the signature and `docker compose pull && make up`
```

## Common problems

| Symptom | Cause |
| --- | --- |
| I sign in and return to the login screen | `Secure` cookie over http: `OPENFINANCE_SESSION_COOKIE_SECURE=false` in `direct` mode, or use HTTPS |
| `Define POSTGRES_PASSWORD en .env` | `.env` or the variable is missing |
| `ports: !reset` invalid | Docker Compose older than 2.24 |
| Caddy does not get the certificate | DNS does not point home or ports 80/443 do not reach the machine |
| `Demasiados intentos` (Too many attempts) | Login attempt limit: wait 15 minutes |

## Logs and health checks

- `docker compose logs -f api` shows one line per request: `date LEVEL name [request-id] GET /path -> status in N ms`. It does not include the URL query, bodies, cookies or headers. The level is changed with `OPENFINANCE_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- Every response carries `X-Request-ID`: if something fails, give that identifier and the exact line can be found. The identifier is set by nginx and reaches the API.
- Each container's logs rotate automatically: 5 files of 10 MB.
- `/health` says the API is alive; `/ready` (only inside Compose) also checks that the database responds. The API's `healthcheck` uses `/ready`.
