# ADR-0024: Bank connection through a PSD2 aggregator

- Status: Accepted
- Date: 2026-11-03

## Context

Until now, transactions enter through statements (CSV, OFX, CAMT…) or by hand. Revolut and Bankinter, the household's banks, publish their information through PSD2, but a bank only hands it to an authorized provider (AISP). A self-hosted project cannot be an AISP, so it needs an **aggregator** that is one. The installation is self-hosted: each household creates its own account with the aggregator and the keys never leave its server.

## Decision

### Aggregator: Enable Banking

- [Enable Banking](https://enablebanking.com) is used with **the household's own account**. Its restricted production mode allows linking the accounts of whoever registers the application, with no commercial contract. OpenFinance does not go through any server of ours.
- The API is signed with an RS256 JWT (`kid` = application identifier, `iss` = `enablebanking.com`, `aud` = `api.enablebanking.com`, expires in one hour) using the private key downloaded by whoever registers the application. It is configured with `OPENFINANCE_BANK_APP_ID`, `OPENFINANCE_BANK_PRIVATE_KEY` (the PEM) and `OPENFINANCE_BANK_REDIRECT_URL`. **Without those variables the connection is off** and "Ajustes" ("Settings") says so; the rest of the app does not change.
- The aggregator sits behind a port (`BankAggregator`). Another provider (GoCardless, Tink…) would be one more adapter. Tests use a simulated aggregator: there is no testing against real banks in CI.
- No new dependency: the client uses `urllib` from the standard library and `cryptography` (already present through `pywebpush`, which is now declared as a direct dependency).

### Consent (OF-1401)

- A **connection** is created by one person for one bank and is **theirs**: only they see it, link it, sync it or revoke it. Another person in the household, or in another household, gets 404.
- Flow: `POST /bank/connections` (bank and country) returns the bank's URL and stores a random single-use `state`; the bank redirects to `OPENFINANCE_BANK_REDIRECT_URL` with `code` and `state`; the web app calls `POST /bank/connections/complete`, which requires the `state` to belong to a pending connection **of the signed-in person**. Completion is a POST (with `X-Requested-With`), not a GET with side effects, so a foreign link cannot complete anything.
- On completion, the aggregator returns the authorized accounts. Each one stays **unlinked** until the person assigns it to an OpenFinance account they can see (ADR-0013) and of the same currency; another person's personal account cannot be chosen. A bank account links to a single OpenFinance account and vice versa.
- The aggregator's session identifier is never returned by the API nor written to logs. What is shown about the bank is the name and the last four digits of the IBAN.
- **Revoking** asks the aggregator to close the session (if that fails, it is marked revoked anyway and a warning is shown) and stops synchronization. Transactions already fetched are not touched.

### Synchronization (OF-1402)

- It reuses **the same pipeline as import**: each bank transaction becomes a normalized row with its fingerprint and goes through the same rules for categories, merchants and contributions. The fingerprint is `bank:<bank identifier>` when the bank provides one, and the usual fingerprint by date, amount and description when it does not, so syncing twice does not duplicate.
- Each synchronization creates an **import batch** (`banco:<name>`), so it shows in the history and can be undone like any other import.
- Only **booked** transactions (`BOOK`) come in; pending ones do not count until the bank settles them, so that a held charge that later changes amount does not create a duplicate.
- Window: the first time, 90 days; afterwards, from 7 days before the last successful synchronization (banks correct dates late, and the fingerprints avoid repeats).
- **Nothing runs inside the server**: `openfinance bank sync` is launched by cron, like backups and alerts. There is also a "Sincronizar ahora" ("Sync now") button per connection. A failed synchronization stores the reason and touches nothing in that account, and there are no aggressive retries: PSD2 allows about 4 queries per day per account without the person present, so `bank sync` does not query a connection that was synchronized less than 6 hours ago, and "Sincronizar ahora" (with the person present) waits 5 minutes between presses.
- Synchronization acts **as the person who owns the connection** and only writes to the linked accounts, which that person can see.

### Consent expiry (OF-1403)

- PSD2 limits consent (up to 180 days). `valid_until` is stored; after that date the connection becomes **expired** and stops synchronizing.
- A new alert (`consent`, ADR-0023) fires 14 days before expiry and another, more serious one, once it has expired (for one month; if another active connection with the same bank already exists it is considered renewed). They are only for the owning person and can be dismissed and chosen as a notification. Renewing is creating a new connection and linking it to the same accounts: each transaction's fingerprint is the bank's reference, **without** the connection identifier or the account identifier in the aggregator (they change on renewal), so the history is not duplicated.

### Automatic reconciliation (OF-1404)

- When synchronizing, a bank row that is not a duplicate by fingerprint looks for a transaction **already recorded** (by hand or imported from a statement) in the same account with the **same amount** and a date within **≤ 3 days**, that does not already come from the bank nor is reconciled. If there is **exactly one**, it is reconciled: no other is created. With several candidates it does not guess: the new transaction is created and the household decides. Each already-recorded transaction is reconciled with only one row.
- Reconciliation stores the bank fingerprint **separately** (`transactions.bank_ref`) and does not touch the transaction's own fingerprint or its batch. This way re-importing the same statement after reconciling still does not duplicate (household rule) and undoing a synchronization does not void what someone recorded. The text, category and note of what was recorded are not rewritten.
- After synchronizing, the balance reported by the bank (the booked closing one, if provided) is compared with the one computed in OpenFinance at that date and the difference is stored on the link; it is shown in "Ajustes". It is informational: nothing is corrected on its own and no balance reconciliation (OF-1006) is created unless someone does it.

## Consequences

- `bank_connections` and `bank_links` are added, along with `transactions.bank_ref`. Fetched transactions enter the change log through their import batch, like those from a statement.
- Bank data goes through the aggregator chosen by the household. The deployment documentation explains how to create the application, what is shared and how to revoke.
- **Tested with Revolut (`ES`) on 3 November 2026**: JWT signing, bank list, authorization, return from the bank, accounts and a real synchronization (132 transactions over 90 days, sum equal to the bank balance). **Bankinter has not** been tested yet. The adapter continues to be tested in CI with simulated responses.
- The aggregator **only accepts `https` return addresses**; for local testing `https://localhost/` works with Compose's `https` mode. An account's opening balance is the one prior to the first synchronized transaction (see the deployment guide).
- Payments and transfers initiated from OpenFinance are out of scope: read-only access to accounts.
