# Roadmap and backlog

Scope: [ADR-0012 · Empezar por el hogar](../adr/0012-empezar-por-el-hogar.md) (Start with the household). Visual reference: [prototype](prototypes/index.html).

A ticket is done when it meets its acceptance criteria, has tests, and `make check` is green. Criteria marked with 🧪 must end up as automated tests.

## Summary

| Phase | Goal | Tickets | Status |
| --- | --- | --- | --- |
| 0 · Foundation | Repository, CI, environment and `Money` | OF-001 … OF-003 | ✅ Done |
| 1 · Data | Get the real transactions from Revolut (joint) and Bankinter (personal) in | OF-101 … OF-108 | ✅ Done |
| 2 · Categories | Give every expense a category with almost no effort | OF-201 … OF-203 | ✅ Done |
| 3 · Charts | "Este mes" (This month), "¿En qué gastamos?" (What do we spend on?) and "Evolución" (Evolution) | OF-301 … OF-305 | ✅ Done |
| 4 · Savings | Budgets, goals, ideas and simulator | OF-401 … OF-405 | ✅ Done |
| 5 · Real use | Installed at home, with backups | OF-501 … OF-504 | ✅ OF-501 to OF-503 (CI green, `compose-e2e` too) · OF-504 prepared: the `v0.1.0` tag is missing until after the month of real use |
| 6 · Reliable data | Any real statement imports without errors or inflated entries | OF-601 … OF-608 | ✅ Done · recognising OF-602's internal transfers is missing (waiting on a real statement) |
| 7 · Correct without fear | Edit, undo and adjust from the web, with history | OF-701 … OF-706 | ✅ Done (still to be tried in the month of real use) |
| 8 · Daily use | Mobile, PWA, accessibility and an honest current month (v0.2) | OF-801 … OF-806 | ✅ Done (still to be tried on a real phone and to run `make e2e`) |
| 9 · Operations | Encrypted backups, dependencies and updates (v0.2) | OF-901 … OF-907 | ✅ |
| 10 – 17 | From the complete ledger to 1.0 | OF-1001 … OF-1705 | See [After v0.2](#after-v02) |

**Milestone v0.1:** phases 6 and 7 finished and at least one month of real use with your data. The audit of 1 November 2026 found bugs that, with real data, leave imports that cannot be confirmed or inflated totals that cannot be corrected; that is why phase 6 comes before the month of real use.

## How to resume

Status as of 1 November 2026. Code at [github.com/rldona/OpenFinance](https://github.com/rldona/OpenFinance) (public, `main` branch). CI green in all its jobs: `backend`, `frontend`, `licenses` and `compose-e2e` in the `direct` and `https` modes.

### What is left for v0.1, in order

0. ✅ **Phases 6 and 7 done.** Only recognising OF-602's internal transfers is left; it needs to see their text in a real statement, so it can be closed with the first statement of step 1. Whatever comes out of the month of real use can already be corrected from the web, with history and undo.
1. **Install at home** following [Instalar en casa](../deployment/home.md) (Install at home), in HTTPS mode with your own domain, on an x86-64 machine:
   1. Configure the domain's DNS and open ports 80 and 443 on the router towards the machine.
   2. In `.env`: `COMPOSE_FILE=compose.yaml:compose.https.yaml`, `OPENFINANCE_DOMAIN` and a random PostgreSQL password.
   3. `docker compose up -d --wait` and then `make bootstrap` to create the household, the two people and their accounts.
   4. **Before importing anything**, store the last digits of the card each person uses to top up the joint account: `openfinance member-patterns add <email> '*NNNN'`. Revolut shows top-ups as "Recarga de \*NNNN" (Top-up from \*NNNN), without a name. Without that pattern they come in as income and **cannot be reclassified afterwards**.
   5. Check a statement without touching the database: `openfinance statement-check --bank revolut|bankinter FILE`. It only shows counts.
   6. Import from the **Importar** (Import) screen: Revolut into the joint account and each person's Bankinter into their personal account.
   7. Schedule `make backup` with cron and try `make restore FILE=…` once.
   8. Open it from a real phone: tabs, Importar, export download, and the keyboard not covering the fields.
2. **One month of real use** with your data.
3. **Release:** follow [release.md](../development/release.md). The versions must be bumped to 0.1.0, the annotated tag `v0.1.0` created and the release published on GitHub.

### Minor pending items (do not block v0.1)

- Revolut (see [bancos.md](bancos.md)): confirm whether the times are local or UTC, the sign of the fee, and how pockets appear in the Spanish-language Excel. The October statement has no fees or pockets, so it will be confirmed with the next ones.
- "Cerrar todas las sesiones" (Log out of all sessions) from the web, once password change exists. Today it only exists in the CLI: `openfinance sessions revoke-all`.

### Environment notes

- **Real statements:** they go in `/Extractos`, which is in `.gitignore`. They are never copied into tests, fixtures or documentation. Tests use synthetic files.
- **No Docker or PostgreSQL on the development laptop:** database tests run locally with SQLite, and Compose is only tested in CI. Playwright does work locally with the API on SQLite and Vite (see [getting-started](../development/getting-started.md)).
- **Git identity:** commits with `Raúl López Doña <1206870+rldona@users.noreply.github.com>` (already configured in this repository) and signed off with DCO (`git commit -s`).
- **npm:** the machine's `~/.npmrc` points to a corporate registry. If the lock is regenerated, it must be done with `npm install --registry=https://registry.npmjs.org/`. CI fails if `package-lock.json` contains URLs from another registry.
- **Vercel:** preview deployments are never launched. Everything goes through GitHub Actions.

---

## Phase 0 · Foundation ✅

| ID | Ticket | Status |
| --- | --- | --- |
| OF-001 | Monorepo: `services/api` (FastAPI) and `apps/web` (React) with layers and `import-linter` | ✅ |
| OF-002 | Environment: Docker Compose, `.env.example`, `Makefile` | ✅ (Compose reviewed in OF-502 and tested end to end in CI: `compose-e2e` job) |
| OF-003 | CI: lint, types, tests, build and migrations on PostgreSQL | ✅ |

---

## Phase 1 · Data

### OF-101 · Household and people ✅
One household (`Workspace`) with two people who log in with email and password.
- ✅ `make bootstrap` (or `openfinance bootstrap`) creates the household, the two people and their accounts; there is no public sign-up.
- ✅ Server-side session with an `HttpOnly`, `SameSite=Lax` cookie (`Secure` configurable); only the token hash is stored in the database. Passwords use Argon2id, minimum 10 characters.
- ✅ Both people have full access to shared data; there are no roles.
- ✅ 🧪 Without a session the API responds 401; with a session it only returns data from its own household. A wrong password and an unknown email give the same response; the session expires and logging out invalidates it.
- ✅ Security review applied:
  - Login attempt limiter: 5 per email and 20 per IP every 15 minutes, also in nginx.
  - At most 2 Argon2 verifications at a time.
  - The cookie is `Secure` in production.
  - On login the previous session is replaced and expired ones are purged.
  - 422 errors do not echo back what was submitted.
  - CORS `*` is rejected and `/docs` is hidden in production.
  - Composite foreign keys that prevent mixing households in transactions and holders.
- Pending: login screen in the web app (OF-106); "cerrar todas las sesiones" once password change exists; require JSON and check `Origin` in future write endpoints.

### OF-102 · Accounts ✅
Revolut joint account, pockets and Bankinter personal accounts, with institution, currency and opening balance ([ADR-0013](../adr/0013-cuentas-personales-privadas.md)).
- ✅ A personal account has a holder and only that person sees it.
- ✅ 🧪 Current balance = opening balance + sum of transactions, computed with `Money`.
- ✅ `GET /api/v1/accounts`: the joint account first, then pockets and finally personal accounts.

### OF-103 · Transactions ✅
Transaction model and API.
- ✅ Fields: account, date and time, value date, original description, amount (`Money`, fee included), type, category (optional), person (on contributions), bank-specific type, provenance and deduplication fingerprint (unique per account).
- ✅ Types: `contribution`, `expense` (a positive amount is a refund), `income`, `savings_transfer` and `internal_transfer`.
- ✅ `GET /api/v1/transactions?month=2026-10&q=…&uncategorized=true&account_id=…`.
- ✅ 🧪 Transfers and internal transfers do not count as expenses; contributions count as inflows; refunds reduce expenses; a contribution leaving a personal account is neither an inflow nor an expense of the household.
- ✅ 🧪 Isolation: neither another household's transactions nor those of your partner's personal account appear; requesting them by id gives 404.
- Note: the category is for now free text (`super`, `vivienda`…); OF-201 will turn it into an entity.

### OF-104 · Revolut statement reader ✅
Reading the Revolut joint account statement. Format and decisions in [bancos.md](bancos.md) and [ADR-0015](../adr/0015-patrones-por-persona-y-xlsx.md).
- ✅ `parse_revolut` reader that detects the format: CSV with English headers or Excel (.xlsx) in Spanish, validated with a real statement. Only completed rows of the account's product, fee included in the amount.
- ✅ Amounts never go through `float`: from CSV they are read as text and from Excel from their decimal representation.
- ✅ Headers with broken encoding (`DescripciÃ³n`) repaired; Excel times rounded to the second; pending rows with no end date or balance discarded with their reason.
- ✅ Proposes the type: contribution by person (name or saved pattern), transfer to pocket, income, expense or refund (including a positive card payment).
- ✅ Stable fingerprint for deduplication, without merging identical rows from the same file. 🧪 The same statement as CSV and as Excel gives the same fingerprints; 🧪 already-stored fingerprints do not change.
- ✅ Balance check row by row in file order (completion date); the bank's final balance is that of the last row.
- ✅ Each person's patterns stored in the household (`member_patterns`) and managed with `openfinance member-patterns` (ADR-0015).
- ✅ Safe Excel reading: limits on size, compression ratio, rows and columns; no formulas or links; XML with `defusedxml`.
- ✅ `openfinance statement-check` to check a statement without a database, showing only counts.
- Pending (see [bancos.md](bancos.md)): local time or UTC, sign of the fee and pocket text in the Spanish-language Excel.

### OF-105 · Idempotent import ✅
Preview → confirmation, without duplicates.
- ✅ `POST /api/v1/imports` (multipart: `account_id`, `file`): reads the statement and returns the preview without saving transactions. It reports new ones, already imported ones, discarded rows with their reason, internal mismatches in the statement, and whether the final balance will match the bank's.
- ✅ `POST /api/v1/imports/{id}/commit`: saves only the new ones, with provenance (`import:<file>` and `import_id`). Repeating it returns the same result without saving again.
- ✅ Deduplication by fingerprint, unique per account in the database, and a prior check of the existing fingerprints.
- ✅ Contributions recognised by each person's name in the description; "To pocket" → pocket. It will be tuned with the real statements.
- ✅ Limits: 5 MB per file and preview valid for 24 h. The file content is deleted on confirmation.
- ✅ 🧪 Importing the same file twice creates no new transactions; confirming twice does not either.
- ✅ 🧪 Two identical coffees on the same day in the same file are **not** considered duplicates.
- ✅ 🧪 A statement that overlaps a previous one only adds what is new.
- ✅ 🧪 You cannot import into your partner's personal account or into another household; nobody from another household can confirm someone else's preview.
- ✅ API writes require the `X-Requested-With: OpenFinance` header (CSRF protection).

### OF-106 · Transactions and Import screens ✅
Real version of the prototype screens.
- ✅ Login screen and header with household, tabs, members and "Salir" (Log out).
- ✅ **Movimientos** (Transactions): by month (or all), search, filter by account and "only uncategorised". Each row indicates its type: contribution from whom, to the pocket, refund, income or uncategorised.
- ✅ **Importar** (Import) in 3 steps: choose account and statement; review new, already imported, discarded and whether the balance matches the bank's; confirm.
- ✅ Typed API client with types generated from OpenAPI (`make openapi`); CI fails if the contract or the types are not up to date (ADR-0009).
- ✅ Amounts formatted from the exact decimal, without `float`, in the browser too.
- ✅ Tested in real browsers with Playwright (OF-503), together with the chart tabs (phase 3).

### OF-107 · Bankinter reader (personal accounts) ✅
- ✅ `parse_bankinter` reader for the transactions Excel, validated with a real statement: skips the preamble and filters, discards pending rows with their reason and reverses the order (the bank lists from newest to oldest) so that the balance matches.
- ✅ The account number in the preamble is not read nor does it appear in errors or discarded rows. Old `.xls` files and CSVs are rejected with a clear message.
- ✅ 🧪 With no time in the statement, the fingerprint includes the balance: two identical transactions on the same day are not merged and an overlapping statement does not duplicate.
- ✅ 🧪 Outgoing "Revolut\*\*NNNN\*" transfers and those matching an outgoing pattern of the holder are a **contribution** by the holder; they count neither as an expense nor in the household totals.
- ✅ 🧪 Names are not used in the personal account: a Bizum from the partner is income. Transfers and Bizum depend on the sign.
- ✅ 🧪 Only the holder can preview, confirm and see the imported transactions; neither the partner nor another household.
- The personal "mi gasto" (my spending) view moves to OF-108.
- Depends on: OF-105.

### OF-108 · Each person's "mi gasto" view ✅
View of each person's personal accounts, visible only to them (ADR-0013).
- ✅ `GET /api/v1/insights/month` and `/insights/category` accept `view=household|mine` (default `household`). `mine` uses only the asker's personal accounts: spent, income, contributed to the joint account (`contributed`) and spending by category with its average; when a category is chosen, its 12 months and merchants.
- ✅ `GET /api/v1/transactions?mine_only=true` lists the transactions of those accounts (incompatible with `shared_only`).
- ✅ Web: "Hogar / Mío" (Household / Mine) selector in "Este mes" (This month) and "¿En qué gastamos?" (What do we spend on?), shared between the two screens. Under "Mío", what was contributed to the joint account is shown separately ("no cuenta como gasto tuyo", i.e. does not count as your spending) and budgets do not appear, as they belong to the household.
- ✅ 🧪 Negative tests: the partner sees neither the aggregates nor the transactions of the other's personal account, not even by requesting a category; another household does not either. The personal view does not alter the household totals.
- Decided: the month view is enough. "Evolución" (Evolution; 12 months of everything) remains household-only; if a personal evolution is needed, it deserves its own ticket.
- Depends on: OF-107.

---

## Phase 2 · Categories

### OF-201 · Categories ✅
- ✅ Categories per household with name, icon, colour and order; each household starts with the prototype's 13 (identified by `slug`).
- ✅ Create, rename, change icon or colour, and hide (`GET/POST /api/v1/categories`, `PATCH /api/v1/categories/{id}`). They are not deleted.
- ✅ Names unique per household, ignoring case and accents.
- ✅ 🧪 Hiding a category does not delete that of its transactions; a hidden category cannot be assigned to new transactions.
- ✅ Migration 0004 of existing data: free text becomes a category (unknown ones are created as custom) and each transaction's merchant is computed.

### OF-202 · Rules per merchant ✅
- ✅ Normalised merchant (`merchant_key`): strips bank prefixes ("COMPRA TARJETA 4821", "PAGO CON TARJETA", "RECIBO DE"…), card or terminal numbers and company-type suffixes. Example: "MERCADONA 0087" → `MERCADONA`.
- ✅ When an expense's category is corrected, the "merchant → category" rule is stored and applied to **uncategorised** expenses of that merchant; it never overrides one chosen by hand. When the category is removed, the rule is forgotten.
- ✅ Caution over coverage:
  - A rule applies if its words are the beginning of the merchant (`MERCADONA` → `MERCADONA VALENCIA`), never the other way round.
  - Rules of a single short word (`BAR`, `GAS`) or of intermediaries (`PAYPAL`, `AMAZON`…) only apply to the exact merchant and do not propagate.
- ✅ Privacy (ADR-0013): a rule learned in a personal account belongs only to its holder and only affects their personal accounts. Household rules affect the accounts visible to whoever corrects.
- ✅ Rules are applied in the import preview and on confirmation.
- ✅ 🧪 Correcting "MERCADONA 1234" also classifies "MERCADONA 0087" and "COMPRA TARJETA … MERCADONA VALENCIA".

### OF-203 · Correction in the table ✅
- ✅ `PATCH /api/v1/transactions/{id}` (`category_id`, `learn`) returns the learned rule and how many more transactions were classified.
- ✅ Web: category selector on each expense, "N gastos sin categoría" (N uncategorised expenses) notice with direct access to the filter, and a counter on the tab (`GET /api/v1/transactions/uncategorized-count`).
- ✅ Message "Regla guardada: «Mercadona» → Supermercado · 2 más clasificados" (Rule saved: "Mercadona" → Supermarket · 2 more classified).
- ✅ **Categorías** (Categories) screen (`#categorias`) to create, rename, change icon or colour, and hide.
- ✅ The import preview shows the category proposed by rule.

---

## Phase 3 · Charts

### OF-301 · Aggregates API (`insights`) ✅
The Core computes and the frontend only draws. Household totals use only the joint account and the pockets (ADR-0013).
- ✅ `GET /api/v1/insights/month`: spent, inflows (contributions per person), savings and %, spending by category with its average, cumulative spending per day, previous month and average of previous months with data.
- ✅ Current month: the curve runs up to today (in the household's time zone, `OPENFINANCE_TIMEZONE`) and is compared with the same stretch of the previous month.
- ✅ `GET /api/v1/insights/category`: 12 months of a category (or "uncategorised"), its average and the main merchants of the last 3 months.
- ✅ `GET /api/v1/insights/trends`: 12 months of spending, inflows, savings and spending by category; totals, averages, savings % and best and worst month.
- ✅ `GET /api/v1/transactions?category_id=…&shared_only=true` to list the transactions behind a chart.
- ✅ 🧪 Sums by category match the month's spending; transfers to savings are left out of spending; personal accounts never count; months without data do not enter the averages.

### OF-302 · Chart components ✅
- ✅ Decided in [ADR-0014](../adr/0014-graficos-svg-propios.md), with measurements: own SVG (≈ 4 KB) versus Chart.js (+62 KB gzip) and Recharts (+122 KB gzip).
- ✅ Donut, bars (with reference, highlighted month and negatives), stacked bars, lines with area and progress ring in `apps/web/src/components/charts/`.
- ✅ Accessible (`role="img"` with a summary and a data table hidden for screen readers) and scalable with `viewBox`.

### OF-303 · "Este mes" (This month) screen ✅
- ✅ Home screen: spent (versus the previous month and the average), saved and %, where most goes, donut with the top 5 categories, spending pace versus the previous month and what changed most versus the average.
- Budgets will be added with OF-401.

### OF-304 · "¿En qué gastamos?" (What do we spend on?) screen ✅
- ✅ Donut and category ranking; when one is chosen (or "uncategorised"): 12 months versus the average, main merchants and transactions of the month.

### OF-305 · "Evolución" (Evolution) screen ✅
- ✅ 12-month stacked bars (6 main categories + rest), each month's savings with its average, saved over the period and best and worst month.

### Demo
- ✅ `make demo` creates a fictional household with 12 months of data to see the charts without real data. It is all or nothing and refuses to run in production except with `--force`, because the password is public.

---

## Phase 4 · Savings

### OF-401 · Budgets ✅
- ✅ Monthly limit per category (`GET /api/v1/budgets?month=`, `PUT/DELETE /api/v1/budgets/{category_id}`), with a warning at 85 % ("cerca", near) and when exceeded ("pasado", over).
- ✅ 🧪 The percentage uses only expenses of that category and that month, from the joint account and the pockets. It is rounded down and the status is decided with the exact amounts.
- ✅ "Este mes" shows the budget bars. The total budget line in the spending pace only appears if everything spent has a budget.
- ✅ **Presupuestos** (Budgets) screen (`#presupuestos`) with your average for each category and a button to use it, rounded up to tens.

### OF-402 · Savings goals ✅
- ✅ Name, icon, target, saved (by hand or the balance of a linked pocket), monthly contribution and optional deadline (`/api/v1/goals`).
- ✅ Projection: progress, months remaining, estimated date and, with a deadline, what would need to be set aside each month and whether it is reached in time.
- ✅ Only the household's own pockets can be linked (never personal accounts or those of another household).

### OF-403 · Recurring charges ✅
- ✅ Detects instalments: same merchant in at least 3 months (≥ 75 % of the period), no more than 2 charges per month, a repeating amount (±1 %) and active in the last 45 days. An instalment charged in two parts counts as one.
- ✅ Amount and price increases computed with complete months (the current month only confirms it is still active).
- ✅ 🧪 Detects the Netflix increase in the test dataset.

### OF-404 · Savings ideas ✅
- ✅ Deterministic ideas, no AI, each with its backing (transactions and period) and the estimate it is based on:
  - instalments that have gone up in price;
  - subscriptions;
  - restaurants (−25 %), supermarket (−10 %) and utilities (−10 %).
- ✅ Averages only with complete months: the current month and the first imported month, if it starts mid-month, are excluded. With no complete months nothing is projected.

### OF-405 · Cuts simulator ✅
- ✅ Sliders per category that compute the extra monthly and yearly savings (exact cents with BigInt) and how many months sooner the first pending goal is reached.

---

## Phase 5 · Real use

### OF-501 · Export and backup ✅
- ✅ `GET /api/v1/export?format=json|csv`: what the requester sees (never the other person's personal account, sessions, hashes or fingerprints), with `format_version` 1, exact amounts as text and CSV protected against formulas. **Exportar** (Export) button in the header.
- ✅ 🧪 Negative visibility tests: personal account, the partner's outgoing rules and patterns, and another household.
- ✅ `make backup` and `make restore FILE=…` ([ADR-0016](../adr/0016-exposicion-y-copias.md)); restoring applies migrations and closes all sessions (`openfinance sessions revoke-all`).
- ✅ 🧪 Restoring a backup on a clean installation leaves the same balances (CI, `compose-e2e`).

### OF-502 · Installation at home ✅
- ✅ Docker Compose tested end to end in CI in two modes: `direct` (local network over http) and `caddy` (HTTPS with your own domain). Neither PostgreSQL nor the API publish ports.
- ✅ The real IP reaches the API without the client being able to forge it (nginx overwrites `X-Forwarded-For`); log warning if the `Secure` cookie arrives over http.
- ✅ Guide: [Instalar en casa](../deployment/home.md) (phone on the local network, HTTPS, scheduled backups and updating).

### OF-503 · Mobile ✅ (still to be tried on a real phone)
- ✅ The 6 screens, login, Categorías and Presupuestos work on a phone: tabs in a scrollable row, tables as compact rows, touch targets of at least 40 px and 16 px fields so iOS does not zoom the page.
- ✅ Charts legible on a narrow screen: they are drawn at the real width (text does not shrink with the `viewBox`) and write fewer labels when they do not fit. They are still fed by the Core aggregates.
- ✅ 🧪 Playwright (`apps/web/e2e`, `make e2e`) on Chrome at 360 px, Safari (WebKit) at 390 px and desktop: no horizontal scroll, charts inside the screen with labels of at least 11 px and no overlaps, reachable tabs, Importar in 3 steps with a synthetic statement and export download. In CI against Docker Compose (`compose-e2e`, `direct` mode).

### OF-504 · Release v0.1 — prepared (tag missing until after the month of real use)
- ✅ Dependency licences audited ([docs/legal/dependencias.md](../legal/dependencias.md)): all compatible with AGPL-3.0; psycopg is LGPL-3.0-only and poses no problems. `make licenses` lists them and the CI `licenses` job fails if a production dependency falls outside the allowed list.
- ✅ `LICENSE` with the verbatim AGPL-3.0 text and [ADR-0008](../adr/0008-licencia-agpl.md) accepted: AGPL-3.0-or-later, contributions with DCO (`git commit -s`, [CONTRIBUTING.md](../../CONTRIBUTING.md)), no CLA and no per-file SPDX headers.
- ✅ [CHANGELOG.md](../../CHANGELOG.md) (Keep a Changelog) with phases 0 to 5 and what is pending.
- ✅ Release checklist: [docs/development/release.md](../development/release.md).
- Pending: bump the versions to 0.1.0 and create the annotated tag `v0.1.0` with its GitHub release, **after one month of real use**. Decided this way on purpose.

---

## Phase 6 · Reliable data

So that any real Revolut or Bankinter statement imports without errors and without inflating inflows. It comes from the audit of 1 November 2026 and **comes before the month of real use**.

### OF-601 · Zero or empty amount rows ✅
A card verification of 0.00 € passed the preview, but on confirmation the domain rejected it and the API responded 500: the statement could never be imported.
- ✅ The Revolut and Bankinter readers discard zero-amount rows ("importe cero: no mueve dinero", zero amount: moves no money) and empty-amount rows ("fila no válida: falta el importe", invalid row: amount missing), with their reason in the preview. The balance still matches.
- ✅ If the domain rejects a row on confirmation, the API responds 422 and saves nothing: the batch is not claimed and can be confirmed again.
- ✅ 🧪 A statement with a 0.00 card verification is previewed and confirmed; 🧪 a domain error on confirmation gives 422 and leaves the import intact.

### OF-602 · Classification: pockets in both directions, names by whole word and internal transfers ✅ (except internal transfers)
- ✅ Pocket patterns "To pocket" and "From pocket". Withdrawing from the pocket is a positive `savings_transfer`: it does not count as income, it subtracts from what was transferred to savings, and in Movimientos it reads "De la hucha" (From the pocket). The Spanish texts are still pending a real statement ([bancos.md](bancos.md)).
- ✅ All patterns (names, per-person patterns, pockets) are searched by whole word after normalising: "MARIANA" is not a contribution by Ana and "\*1234" does not match "\*12345". A boundary is only required at the end that is a letter or digit, so "REVOLUT\*\*" still matches "Revolut\*\*9876\*".
- ⏳ `internal_patterns` with the joint account's top-ups to the personal accounts: **pending seeing the text in a real statement**. Making it up would misclassify real transactions that then cannot be reclassified (until OF-701).
- ✅ 🧪 "From pocket EUR Viaje" does not count as an inflow; ✅ 🧪 "Transferencia de MARIANA LOPEZ" is not a contribution by Ana; ✅ 🧪 already-stored fingerprints do not change (the sample's one is pinned in the test and does not depend on the rules).

### OF-603 · Search with "#" and global ErrorBoundary ✅
- ✅ The Movimientos query key is `JSON.stringify([query, version])`, without splitting it on "#". Before, searching "#1" threw a `SyntaxError` and the list froze.
- ✅ An `ErrorBoundary` per tab in `App.tsx` shows "Algo ha fallado · Recargar" (Something went wrong · Reload) instead of freezing the screen; the header and the other tabs keep working.
- ✅ 🧪 Searching "#1", "%", quotes or apostrophes sends the search as is and the list keeps working; ✅ 🧪 a response that breaks the screen shows the notice with "Recargar".

### OF-604 · Ambiguous amounts: reject instead of guessing ✅
- ✅ `to_decimal` receives the bank's decimal separator and the other one can only group thousands in threes. The Revolut CSV declares "."; the Revolut and Bankinter Excel files carry numbers, and if a cell arrives as text only the unambiguous is accepted ("12,30", "1.234,56"), because their text format has not been seen in a real statement.
- ✅ Whatever does not follow the format ("12,30" in the English CSV, "1,23,456", "1.5.") is an invalid row with its reason.
- ✅ 🧪 "1,234" in the English CSV is read as 1234 and the balance matches; ✅ 🧪 with no declared format, "1,234" and "1.234" are rejected as "importe ambiguo" (ambiguous amount), never read as 1.234.

### OF-605 · Shared `useLoad` with loading, error and retry states ✅
- ✅ `useLoad` in `src/lib/useLoad.ts`, with `reload`: on reload the data stays visible until the new data arrives, and an error is cleared on retry. Used by Este mes, ¿En qué gastamos? (and its panel), Evolución, Ahorrar (Save) and Presupuestos; Movimientos keeps its own loading (rows dimmed while the new query arrives) with the same "Reintentar" (Retry).
- ✅ Components `<Loading/>` and `<ErrorState onRetry/>` in `src/components/LoadState.tsx`. `<UncategorizedNotice/>` was not extracted: the notice only appears in Este mes.
- ✅ 🧪 If a category's transactions fail, the error is shown with "Reintentar" and on retry they load; ✅ 🧪 Presupuestos recovers on retry (before, the error stayed forever).

### OF-606 · Maintenance CLI: password, accounts and people ✅
- ✅ `openfinance users set-password <email>`: the password is prompted for without echo (never as an argument), and only that person's sessions are closed.
- ✅ `openfinance accounts add <email> <name> [--kind savings|joint|personal] [--bank …] [--opening-balance …]`: adds an account to that person's household; with `personal`, they are its holder. The name cannot be repeated in the household.
- ✅ 🧪 After changing the password, the previous session gives 401, the other person's stays open and the old password no longer works; ✅ 🧪 a new personal account is only seen by its holder and cannot be given to someone from another household.
- Guide: [Instalar en casa](../deployment/home.md).

### OF-607 · Purge the content of expired imports ✅
- ✅ The file of an unconfirmed preview older than 24 h is deleted when the API starts, on every login and on every preview. `make backup` runs `openfinance imports purge` before dumping. If the database does not respond at startup, the API starts anyway and logs it.
- ✅ 🧪 A preview older than 24 h does not keep its content after the next login (by any person in the household); ✅ 🧪 a recent one does; ✅ 🧪 startup and `imports purge` also delete it.

### OF-608 · The current month in the Core ✅
- ✅ `insights/trends` takes averages from complete months: if the period reaches the current month, from the 12 months before it, just like Este mes. The current month counts in the totals, but not in the averages or in the best or worst month, and is flagged with `is_partial`.
- ✅ `insights/month` returns for each category its `reference` (the average or, in the current month, the average of what was spent up to the same day) and its `change`, and the `changes` list with those that change most (max. 4, no amounts under €20). The frontend no longer computes it.
- ✅ 🧪 Evolución and Este mes give the same average; ✅ 🧪 on day 1 no category appears below its average; ✅ 🧪 the best and worst month do not include the current month; ✅ 🧪 a past month keeps its 12-month window.

---

## Phase 7 · Correct without fear

So that any data error can be fixed from the web, is traced and can be undone. It is done during the month of real use; when finished, `v0.1.0` is tagged. Each ticket carries its own negative privacy tests (the partner and another household).

**Design decision ([ADR-0017](../adr/0017-registro-de-cambios.md)):** the general log of OF-706 is built first and OF-701 uses it from the start, instead of creating `transaction_corrections` and migrating it later. Nothing is deleted: voiding a transaction is `voided = true`, with its log entry.

### Change log foundation (from OF-706) ✅
- ✅ Tables `change_operations` (author, date, type, summary, undone) and `change_entries` (entity, field, before and after as JSON). Migration `0007_change_log`, which also adds `note` and `voided` to transactions.
- ✅ All transaction queries ignore voided ones: listings, totals, charts, balances, fingerprints and export.
- ✅ `POST /api/v1/changes/{id}/undo` and `/redo`: only your own operations (the partner's give 404). Undo restores the previous value only where the current one is still the one the operation left; whatever someone changed afterwards is respected and the response says who it was.
- ✅ 🧪 Property: for 12 random sequences of corrections by the two people, undoing all of them in reverse order returns the initial state.

### OF-701 · Edit a transaction's type, person and note, with history ✅
- ✅ `PATCH /api/v1/transactions/{id}` accepts `kind`, `member_id`, `note` and `category_id` (only what is sent changes), with the domain invariants: person only on contributions and from the same household, category only on expenses. A transaction that stops being an expense loses its category, and the change is recorded.
- ✅ The amount, date, description and fingerprint never change.
- ✅ `GET /api/v1/transactions/{id}/history`: who, when and what ("Bizum de E M: Ingreso → Aportación de Elena", i.e. Bizum from E M: Income → Contribution by Elena).
- ✅ In Movimientos, the description opens the detail: type, person, note and history. Each correction shows a notice with "Deshacer" (Undo) for 8 s.
- ✅ 🧪 The partner can neither edit nor see the history of the other's personal account (404), nor can another household; ✅ 🧪 correcting an income to a contribution changes the month's inflows; ✅ 🧪 each correction leaves a history row with its author.

### OF-702 · Visible rules: confirm, undo and manage ✅
- ✅ When categorising, the notice says how many transactions the rule classified and carries "Deshacer" for 8 s: it reverts the category, the rule and what it classified (a single log operation).
- ✅ Bizum and transfers to or from people (by description or by bank type) do not learn rules: their "merchant" is someone's name.
- ✅ Reglas (Rules) screen (`#reglas`, linked from Movimientos and Categorías; `GET /api/v1/rules`, `DELETE /api/v1/rules/{household|personal}/{merchant}`): merchant, category, how many transactions match and whether it is personal. Deleting does not change what was already classified, is recorded in the log and can be undone.
- ✅ 🧪 Undo returns to "sin categoría" (uncategorised) only the transactions the rule had classified (those corrected by hand afterwards are respected); ✅ 🧪 the partner neither sees nor deletes the other's personal rules, nor does another household.

### OF-703 · Import history and undoing an import ✅
- ✅ In Importar, the list of imports (`GET /api/v1/imports`): file, account, who, when, new, already imported and discarded, and whether it is undone. Only for the accounts each person sees.
- ✅ "Deshacer" with confirmation on the screen itself (`POST /api/v1/imports/{id}/undo`): voids its transactions, with their corrections, in a log operation that can also be undone. Only the last confirmed import of each account.
- ✅ Re-importing an undone file reactivates the same transactions (same identifier and corrections) instead of duplicating them.
- Whether the balance matched on confirmation is not stored: the preview checks it, but the history does not show it yet.
- ✅ 🧪 Undoing and re-importing the same file gives the same result (same new, same duplicates, same transactions); ✅ 🧪 an import into the partner's personal account cannot be undone (404) nor one from another household, nor seen in the list.

### OF-704 · Ajustes (Settings): own account, sessions and joint-account top-ups ✅
- ✅ Ajustes screen (⚙️ in the header, `#ajustes`). Changing the password asks for the current one (`POST /api/v1/me/password`); a wrong current one gives 422 and not 401 (a 401 would log out the web session) and counts towards the attempt limit.
- ✅ "Cerrar sesión en los demás dispositivos" (Log out on other devices) (`POST /api/v1/me/sessions/revoke-others`). Changing the password also closes them; this browser's session stays open. The others are closed and not all of them, so as not to kick out whoever presses it: "Salir" already exists to log out.
- ✅ "Recargas de la conjunta" (Joint-account top-ups): each person stores and removes their `*NNNN` (`GET/POST/DELETE /api/v1/me/patterns`); [ADR-0015](../adr/0015-patrones-por-persona-y-xlsx.md) updated. When importing into the Revolut joint account, the preview says who has no stored card and does not allow confirming without ticking "Importar igualmente" (Import anyway).
- ✅ Entries to Categorías, Presupuestos and Reglas from Ajustes.
- ✅ 🧪 Changing the password revokes that person's other sessions (not the partner's) and the new one works; ✅ 🧪 a person neither sees nor deletes the other's patterns, nor does another household; ✅ 🧪 repeated attempts with a wrong current password give 429.

### OF-705 · Classify several at once and cash transactions ✅
- ✅ In "Solo sin categoría" (Only uncategorised), checkboxes to select several expenses and "Poner categoría" (Set category) (`POST /api/v1/transactions/categorize`): without learning rules and as a single operation, which "Deshacer" reverts entirely. If any cannot be seen, none is touched (404).
- ✅ "+ Añadir a mano" (Add by hand) (`POST /api/v1/transactions`): expense or income with date, description, positive amount (the type gives the sign), account and category, with provenance `manual`. An account from "otra entidad" (another institution) is proposed; on a bank account it warns that its balance will no longer match the statement. Until phase 10 there are no own cash accounts: they are created with `openfinance accounts add … --bank other`.
- ✅ "Borrar" (Delete) in the detail of a manual transaction (`DELETE /api/v1/transactions/{id}`): it is voided and recorded in the log, and can be undone. Imported ones are not deleted (422): their import is undone (OF-703).
- ✅ 🧪 A manual transaction counts in the totals and once deleted stops counting (neither in listings nor in the export), with its creation and removal in the history; ✅ 🧪 imported ones are not deleted; ✅ 🧪 the partner neither adds nor deletes in the other's personal account, nor does another household.

### OF-706 · Change log with undo and redo ✅
- ✅ On top of the foundation above: corrections, rules, classifying several, manual transactions and imports write to the log, and everything is undone by the same rule.
- ✅ "Mis cambios" (My changes) screen (`#cambios`, from Ajustes and Movimientos): your last 50 operations with "Deshacer" or "Rehacer" (Redo).
- ✅ Summaries are stored without counts and counted when read, over what the reader sees: a household rule the partner learns also classifies their personal accounts, and counting them in the joint account's history would reveal how many transactions they have there.
- ✅ 🧪 Undo does not expose data from another person's personal account: neither identifiers nor counts in the history, and the undo result only says who changed something afterwards, not what they set; ✅ 🧪 each person only lists their own operations, from newest to oldest.

--- | --- | --- |
| OF-701 | Edit a transaction's type, person and note, with correction history (`transaction_corrections`) | L |
| OF-702 | Visible rules: notice with "Deshacer", Reglas screen (`GET/DELETE /api/v1/rules`), Bizum do not learn rules | M |
| OF-703 | Import history and undoing an import (traced voiding, never silent deletion) | M |
| OF-704 | Ajustes: password change, closing sessions, top-up cards from the web (revises ADR-0015) | M |
| OF-705 | Classify several at once and cash transactions | M |
| OF-706 | Change log with undo and redo: rules foundation, merges, imports and assistant | L |

Each ticket carries its own negative privacy tests (the partner and another household).

---

## Phase 8 · Daily use (v0.2) ✅

So that the web app is used every day from the phone, laptop or tablet, with no surprises in the current month's numbers. No new ADR: it changes the presentation and adds the minimum to the API.

### OF-801 · Adaptive navigation and state in the URL ✅
- ✅ Bottom bar on the phone (< 640 px), a rail on the left on the tablet (640–1023 px) and a sidebar with full names on desktop. The header keeps the household name, Exportar, Ajustes and Salir. The notice (toast) moves up so as not to end up behind the bottom bar.
- ✅ The month, "Hogar / Mío", the chosen category and the Movimientos filters (`q`, `cuenta`, `sin`, `todos`) live in the URL hash (`#movimientos?mes=2026-09&q=luz`): they are shared with a link and survive a reload. Changing a filter adds no history entries. The menu carries the month and view over when switching screens.
- ✅ 🧪 Filters are read from and written to the URL; an invalid month is ignored; the menu keeps the month; the current screen carries `aria-current`.
- Pending verification on a real phone: `make e2e` (the touch-target test now measures `.nav a`).

### OF-802 · An honest "Este mes" ✅
- ✅ `GET /api/v1/insights/month` adds `forecast` (spending with which the current month would close) and `pending_charges` (usual instalments that have not arrived yet, with their usual day; those that were already due and have not arrived are marked `late` and are not added up). Forecast = what was spent + instalments yet to arrive + daily pace of variable spending (without the instalments already charged) × days remaining. No forecast before day 7 or in closed months.
- ✅ Budgets: fixed instalments (charged or yet to be charged) do not trigger "cerca" (near); the warning looks only at the margin they leave for variable spending, and "pasado" (over) always applies. `BudgetOut.fixed` shows it ("120 € son cuotas fijas", i.e. €120 are fixed instalments).
- ✅ 🧪 Forecast and pending items with paid, yet-to-arrive and late instalments; closed month and few days with no forecast; the "Mío" view does not list the partner's instalments and another household does not leak in; fixed instalments alone do not say "cerca" but variable spending does, and going over always warns.

### OF-803 · Transactions with cursor pagination ✅
- ✅ `GET /api/v1/transactions/page`: 50 per page (up to 200), opaque cursor (date + identifier, stable with ties), and on every page `count` and `total` for the whole filter. The simple listing `GET /api/v1/transactions` remains for the charts.
- ✅ In Movimientos, "Cargar más" (Load more), "Mostrando 50 de 70 movimientos" (Showing 50 of 70 transactions) and "Suma del filtro" (Filter total). Changing a filter returns to the first page. Changing a category updates only that row (the list is requested again only if the rule has classified more transactions or the row stops meeting the filter). The 1000-transaction cap disappears.
- ✅ 🧪 Walking the cursor returns each transaction once and in the same order as the listing; the total does not change between pages nor count voided ones; the partner's personal account does not enter pages or totals (neither with someone else's cursor nor by requesting its `account_id`, 404); another household sees nothing; invalid cursor and limit give 422.

### OF-804 · Accessibility ✅
- ✅ `document.title` per screen ("Movimientos · OpenFinance"), "Saltar al contenido" (Skip to content) link, focus moves to the content when switching screens, and a visible focus ring.
- ✅ Errors next to the field (`aria-invalid` + `aria-describedby`, and focus returns to the field): login, wrong current password, "Añadir a mano" amount and budgets (what was typed is kept).
- ✅ 🧪 axe-core (WCAG 2.1 A/AA) with no violations on the eleven screens and on login. Contrast cannot be measured in jsdom: a test computes the ratio of each colour pair in `index.css` across the three themes (minimum 4.5:1). The background of the green and orange labels was raised, as they were at 4.3:1.
- axe-core is MPL-2.0 and development-only ([dependencias](../legal/dependencias.md)).

### OF-805 · Dark mode and installable on the phone ✅
- ✅ Dark theme via colour tokens: it follows the system and in Ajustes → Apariencia (Appearance) "Claro" (Light) or "Oscuro" (Dark) can be forced (remembered in the browser; if it cannot be saved, it applies for the visit).
- ✅ PWA: `manifest.webmanifest`, own icons (192, 512, maskable and iOS; they replace Vite's default logo) and a minimal service worker that caches only the app shell. It never touches `/api/` or `/health`. It registers only in production and over HTTPS.
- ✅ 🧪 Choosing and remembering the theme; manifest with existing icons; `index.html` links the manifest, colour and icon; the service worker excludes the API.
- No offline data access: without a network the shell opens with a notice that there is no connection.

### OF-806 · Simulator with all categories and dismissible ideas ✅
- ✅ The simulator offers all categories with spending (before, six fixed ones), from highest to lowest average: six are shown plus "Mostrar las N restantes" (Show the remaining N); the total also counts the collapsed ones.
- ✅ "Descartar" (Dismiss) an idea hides it for the whole household (`PUT/DELETE /api/v1/savings/ideas/{id}/dismissed`, migration `0008_dismissed_ideas`); "Ver N ideas descartadas" (See N dismissed ideas) and "Recuperar" (Restore). Only existing ideas are valid (404 otherwise).
- ✅ 🧪 Dismissing and restoring is idempotent and looks the same from the partner's side; made-up ideas give 404; another household is unaffected; without a session it is not possible.

## Phase 9 · Operations (v0.2) ✅

| ID | Ticket |
| 

Implementation notes (not tested on a machine with Docker; the CI jobs `security`, `scripts` and `compose-e2e` check it):

- OF-901: `make backup` requires `OPENFINANCE_BACKUP_RECIPIENT`; it is tested with `make scripts-test` (simulated docker and age).
- OF-902: Trivy and `pip-audit` may fail on vulnerabilities that already exist in the dependencies: they are fixed or justified in `.trivyignore`.
- OF-903: `deploy/scripts/ci/headers.sh` checks headers, caching and gzip against a real installation.
- OF-905: `repositories.py` is now a package with one module per context.
- OF-906: password change also uses the new limiter, but its Argon2 stays in the common thread pool (only for people with a session).
- OF-907: the version check is opt-in for privacy; the image signature is only visible on the first published tag.

--- | --- |
| OF-901 | Encrypted backups with `age`, rotation and a recipe to store them off the machine |
| OF-902 | Images by digest, actions by SHA, Renovate, `pip-audit`, `npm audit` and Trivy |
| OF-903 | nginx with `gzip`, `Cache-Control` and headers; hardened Compose and log rotation |
| OF-904 | Configured logging, request identifier and `/ready` with database |
| OF-905 | Balances with `SUM` in SQL, a single flush on confirmation and `repositories.py` split by context |
| OF-906 | Bounded and atomic login limiter; Argon2 out of the common threadpool |
| OF-907 | Published and signed images; new-version notice |

---

## Phase 10 · Complete ledger (v0.3) ✅

Done (not tested on a machine with Docker: `compose-e2e` checks it). Scope in [ADR-0018](../adr/0018-libro-contable-completo.md) and [ADR-0019](../adr/0019-varias-monedas.md), both accepted on 1 November 2026. Each ticket carries its migration, its OpenAPI change (`make openapi`), negative privacy tests and change log with undo.

| ID | Ticket | Definition of done |
| --- | --- | --- |
| OF-1001 ✅ | Merchants: entity with bank variants, rename and merge | Merging two merchants reclassifies their transactions and can be undone; the visible name appears in listings and reports |
| OF-1002 ✅ | Tags and long notes on transactions | Filter by tag; tags belong to the household and inherit the transaction's visibility |
| OF-1003 ✅ | Split a transaction into parts with a category | The sum of the parts is the original amount; reports use the parts (property test: splitting does not change the total) |
| OF-1004 ✅ | Linked transfers between own accounts | The two sides are linked and neither counts as expense or income; linking and unlinking can be undone |
| OF-1005 ✅ | Account types: cash, card, loan and investment | The balance of `card` and `loan` subtracts; they do not enter spending or budgets; migration without touching existing accounts |
| OF-1006 ✅ | Reconciliation: reviewed and balance against the bank's on a date | A reviewed transaction does not change with an import; the balance difference is shown |
| OF-1007 ✅ | Attachments (receipt, invoice) on a transaction | On disk, with the transaction's privacy, in the backup and with a size and type limit |
| OF-1008 ✅ | Multiple currencies with manual exchange rates (ADR-0019) | Without a rate, the transaction is not converted and the report says so; a single-currency household does not change |

---

## Phase 11 · Rules and universal import (v0.4) ✅

Scope in [ADR-0020](../adr/0020-motor-de-reglas-e-importacion-universal.md). Each ticket carries its migration, its OpenAPI change (`make openapi`), negative privacy tests and, if it changes data, change log with undo. Test statements are always synthetic.

| ID | Ticket | Definition of done |
| --- | --- | --- |
| OF-1101 ✅ | Rules with conditions, actions and phases | Each condition and each action has its test; "first to set wins"; learned rules keep working; no regular expressions |
| OF-1102 ✅ | Rule preview and apply to existing data | The preview does not write; applying is an operation that can be undone; it never overrides what was set by hand, reviewed or split; idempotency test |
| OF-1103 ✅ | Import OFX and QIF | Synthetic sample files; same fingerprints when importing twice; balance checked if the format carries it |
| OF-1104 ✅ | Import CAMT.053 | XML with `defusedxml` (no entities); several transactions per entry; debit and credit with their sign |
| OF-1105 ✅ | CSV from any bank with profiles | Profile created from the preview, saved and reused; date and number in several formats; debit/credit in two columns |

---

## Phase 12 · Planning (v0.5) ✅

Done (not tested on a machine with Docker or PostgreSQL: CI checks it). Scope in [ADR-0021](../adr/0021-pagos-programados-y-prevision.md) and [ADR-0022](../adr/0022-presupuestos-con-limites-o-sobres.md), both accepted on 2 November 2026. Each ticket carries its migration, its OpenAPI change (`make openapi`), negative privacy tests and, if it changes data, change log with undo.

| ID | Ticket | Definition of done |
| --- | --- | --- |
| OF-1201 ✅ | Scheduled payments: calendar, matching with what was charged, and overdue ones | Occurrences are a pure function of the calendar (short months, end, range); matching does not write transactions (it is computed, see ADR-0021); creating, changing and deleting can be undone; a detected charge becomes a scheduled payment from "Ahorrar" |
| OF-1202 ✅ | Balance forecast per account and for the household | Day-by-day balance; first day in the red and minimum; another person's personal account does not enter; `card` and `loan` excluded; each currency is summed separately, without mixing |
| OF-1203 ✅ | Budgets with limits or envelopes, carry-over and per-month amounts (ADR-0022) | Existing budgets remain limits; carry-over is recomputed from spending (up to 36 months back); an overspent envelope carries the deficit forward; personal accounts never count. Export v1 only carries the base amount (v2, from phase 15, carries mode and per-month amounts) |
| OF-1204 ✅ | Transaction templates | Creating from a template uses the normal manual entry, with change log and undo; a household template does not use personal accounts and a personal one is only seen by its owner |
| OF-1205 ✅ | "Hoy podéis gastar" (Today you can spend) | A figure with its breakdown; with insufficient data it says so instead of making things up; only the joint account counts, so it does not depend on who looks; shows what is left in each envelope |
| OF-1206 ✅ | Goals v2: contributions, priority and reminder | Contributions feed the saved amount if there is no pocket; split by priority (only suggests); contributing, withdrawing and deleting can be undone; the reminder is a pre-filled scheduled payment |

---

## Phase 13 · Alerts (v0.6) ✅

Done (not tested on a real phone or with a real push service: the tests use a simulated sender). Scope in [ADR-0023](../adr/0023-avisos-y-notificaciones.md), accepted on 3 November 2026. Alerts are pure functions that are recomputed; only who dismissed which one is stored. Notification channel: Web Push.

| ID | Ticket | Definition of done |
| --- | --- | --- |
| OF-1301 ✅ | Alert engine and inbox | Duplicates, fees, rising bills, overdue payments, forecast negative balance and exceeded budget, each with its test; dismissing is per person; another person's personal account neither generates, shows nor allows dismissing alerts |
| OF-1302 ✅ | Web Push notifications and preferences | Subscription per device and alert types per person; `openfinance alerts notify` is idempotent; the text carries no amounts or merchants; without VAPID keys it is off and says so |
| OF-1303 ✅ | Weekly summary | The week's spending versus the previous one, heaviest categories, payments in the next 7 days and open alerts; once per week and person; can be turned off |

---

## Phase 14 · Bank connection (v0.7) ✅

Done. Tested with Revolut (`ES`) on 3 November 2026; Bankinter still to be tested. CI tests use a simulated aggregator. Scope in [ADR-0024](../adr/0024-conexion-con-el-banco.md), accepted on 3 November 2026. PSD2 aggregator using the household's own account; read-only.

| ID | Ticket | Definition of done |
| --- | --- | --- |
| OF-1401 ✅ | Connection and consent | Each person connects their bank and the connection is theirs (another person or another household gets 404); the `state` is single-use and only completed by whoever created it; the bank's accounts are linked only to accounts the person sees and in their currency; the aggregator session does not leave through the API; without Enable Banking variables it is off and says so; revoking closes the session and does not delete transactions |
| OF-1402 ✅ | Sync through the import pipeline | Same fingerprint and same rules as a statement; syncing twice does not duplicate; each sync is a batch that can be undone; pending items do not enter; a bank failure touches nothing and is reported; `openfinance bank sync` for cron |
| OF-1403 ✅ | Consent expiry | After the date it stops syncing and shows as expired; notice 14 days before and on expiry, only for its holder; renewing does not lose the history |
| OF-1404 ✅ | Automatic reconciliation | A transaction already recorded (by hand or imported) with the same amount within ≤ 3 days is reconciled instead of duplicated and keeps its own fingerprint (re-importing its statement does not duplicate); with several candidates it does not guess; undoing a sync does not void what was reconciled; the bank's balance is compared with the computed one and the difference is visible |

---

## Phase 15 · Reports and net worth (v0.8) ✅

Done. Scope in [ADR-0025](../adr/0025-informes-y-patrimonio.md), accepted on 3 November 2026. Everything is views computed with the permissions of whoever requests them.

| ID | Ticket | Definition of done |
| --- | --- | --- |
| OF-1501 ✅ | Net worth | Assets (positive balances) minus debts (negative) of the accounts the asker sees; today and 12 month-ends; another person's personal account never adds up; other currencies are converted and, without an exchange rate, listed separately instead of made up; voided transactions do not count |
| OF-1502 ✅ | Cash flow | Per month and over the liquid money the asker sees, in the household currency: income, net contributions, spending, savings and own transfers; their sum is exactly the month's balance change; cards, loans, investments and accounts in another currency excluded (and it says so) |
| OF-1503 ✅ | Custom reports | Closed definition (period, measure, grouping, filters) that runs with the permissions of whoever runs it; save as personal or shared (a shared one does not filter by personal accounts and, if an account stops being visible, it does not widen); filtering by an account that is not visible is 404; CSV protected against formulas |
| OF-1504 ✅ | Export v2 | `format_version` 2 with budgets per month, contributions, scheduled payments, templates, rules, merchants, reports and bank connections (without session or `state`); v1 continues with `?version=1`; list of fields that never leave |

---

## Phase 16 · Extended household (v0.9) ✅

Done (not tested with real people inviting and splitting; only tests and the demo installation). Scope in [ADR-0026](../adr/0026-hogar-ampliado.md), accepted on 3 November 2026. The household is reused as the boundary: a four-person household is the "shared flat".

| ID | Ticket | Definition of done |
| --- | --- | --- |
| OF-1601 ✅ | More people with roles and invitations | Roles `owner`, `editor` and `viewer` (up to 10 people); a `viewer` does not write on any write route (all of them are walked); only an `owner` invites, changes roles and removes people, without leaving the household without an `owner` or removing someone who has personal accounts; the role does not open personal accounts; the invitation is shown once, only its hash is stored, it is valid for 7 days and a single use, and every failure gives the same message; accepting is attempt-limited |
| OF-1602 ✅ | Expense splitting | Shares that add up exactly to the amount (largest remainder); balances between people that sum to zero; suggestions with the minimum number of transfers; settlements with double confirmation and idempotent; guests without a user; nothing from another household |
| OF-1603 ✅ | Events and trips | An event groups shared expenses and summarises total, paid, each person's share, balances using only its expenses, and spending by category; once closed it admits no new expenses |

---

## After v0.2

Inspired by Wallet, Spendee, Fintonic and Actual Budget. Each phase starts with its ADR and is broken down into tickets when started. Estimated effort for one person full time.

| Phase | Version | What it delivers | Tickets | Effort |
| --- | --- | --- | --- | --- |
| 10 · Complete ledger | v0.3 | Done: [Phase 10](#phase-10--complete-ledger-v03) | OF-1001 … OF-1008 | ✅ |
| 11 · Rules and universal import | v0.4 | Done: [Phase 11](#phase-11--rules-and-universal-import-v04) | OF-1101 … OF-1105 | ✅ |
| 12 · Planning | v0.5 | Done: [Phase 12](#phase-12--planning-v05) | OF-1201 … OF-1206 | ✅ |
| 13 · Alerts | v0.6 | Done: [Phase 13](#phase-13--alerts-v06) | OF-1301 … OF-1303 | ✅ |
| 14 · Bank connection | v0.7 | Done: [Phase 14](#phase-14--bank-connection-v07) | OF-1401 … OF-1404 | ✅ |
| 15 · Reports and net worth | v0.8 | Done: [Phase 15](#phase-15--reports-and-net-worth-v08) | OF-1501 … OF-1504 | ✅ |
| 16 · Extended household | v0.9 | Done: [Phase 16](#phase-16--extended-household-v09) | OF-1601 … OF-1603 | ✅ |
| 17 · Platform 1.0 | v1.0 | API with tokens, read-only MCP server, assistant with approval (ADR-0004, ADR-0005), external security audit | OF-1701 … OF-1705 | 6 weeks |

Deliberately out of scope: financial scoring, loans, insurance and interest-bearing accounts (they are an intermediation business) and end-to-end encryption (it would prevent computing the aggregates on the server; it is covered with disk and backup encryption).
