# ADR-0021: Scheduled payments, balance forecast and "Hoy podéis gastar" ("Today you can spend")

- Status: Accepted
- Date: 2026-11-02

## Context

Today the app only looks backwards: recurring charges are **detected** from what has already been charged (OF-403), and "Este mes" ("This month") estimates the month-end close from what has already happened (OF-802). A household needs the opposite: to declare "rent is €900 on the 1st", "the €380 annual insurance falls due on 14 March" or "Elena's salary arrives on the 28th", and to know what the balance will be in 30 days and how much can be spent today without running short.

## Decision

### Scheduled payments

- A **scheduled payment** belongs to the household and has: name, amount (positive for income, negative for a payment), account, optional category and merchant, **frequency** (`semanal` (weekly), `cada N meses` (every N months), `anual` (yearly), `una vez` (once)), **next date**, optional end date and an active switch.
- An **occurrence** is an expected date of a payment. **It is not a transaction**: nothing is written to the ledger on its own. What is actually charged still enters through import or manually, and the forecast never changes a real balance.
- **Matching**: an occurrence is considered fulfilled if there is a transaction on the same account, with the same sign and currency, whose amount differs by at most 5% (or the payment has a variable amount) and which falls within ±7 days of the expected date. Each transaction fulfills at most one date, and among several candidates the closest in date wins and, on a tie, the closest in amount. **Matching is not stored: it is computed on every query** from the ledger, so correcting, voiding or undoing a transaction fixes the payment's status with nothing to synchronize.
- If the date passes and nothing arrives, the occurrence becomes **overdue**: it is flagged and not added to the forecast.
- Short months are resolved with the last day of the month (a payment on the 31st falls on the 28th/29th in February). The whole calendar is a pure function of the date; there are no scheduled jobs or clock on the server.
- **Detected** recurring charges can be turned into a scheduled payment with one click (pre-filled with the usual merchant, amount and day). Until converted, they still count toward the forecast as before; if a scheduled payment for the same merchant exists, the detected one is not counted twice.

### Balance forecast

- `forecast(account, until)` = current balance + the sum of pending, non-overdue occurrences up to that date, day by day. It is a pure function in the domain; the application layer only gathers visible balances and payments.
- Only the accounts visible to the person querying count (ADR-0013). The household total sums the visible accounts; another person's personal account enters neither the total nor the alerts. With several currencies (ADR-0019): it is computed per currency; if a rate is missing, that currency is not mixed into the total and this is stated.
- Accounts of type `card` and `loan` do not enter the cash forecast (just as they do not enter spending).

### "Hoy podéis gastar" ("Today you can spend")

- It is an honest calculation, not a promise: `(balance of checking and cash accounts − pending payments until the next expected money inflow, or until month end if there is none) ÷ remaining days`, floored at zero.
- If there are envelope budgets (ADR-0022), what remains in each envelope is also shown. If there is not enough data (no balance or no scheduled payments), the card says so instead of inventing a figure.

### Templates

- A **template** is a saved manual transaction (name, amount, type, account, category, merchant, tags) so it can be created with one click. It is either household-wide or personal. Creating from a template uses the normal OF-701 flow, with change log and undo.

## Consequences

- The occurrence calendar is a pure function and is tested with properties: no occurrence falls outside the requested range, the order is stable, and generating twice gives the same result.
- No automatic transactions are created: this avoids the worst possible failure (a phantom expense that throws the balance off).
- The tables `scheduled_payments` (occurrences and their matching are computed, not stored) and `transaction_templates` are added.
- Negative privacy tests: a payment from another person's personal account does not appear in listings, the forecast or "Hoy podéis gastar".
