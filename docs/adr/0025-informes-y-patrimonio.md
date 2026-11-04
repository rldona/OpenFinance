# ADR-0025: Net worth, cash flow, custom reports and export v2

- Status: Accepted
- Date: 2026-11-03

## Context

With accounts of several types (ADR-0018), several currencies (ADR-0019), scheduled payments (ADR-0021) and data that now arrives on its own from the bank (ADR-0024), the month and evolution screens fall short for two questions: "how much do we really have?" and "where does the money come from and where does it go?". In addition, export v1 does not carry what has been added since phase 10 and nobody can ask for a report other than the fixed ones.

All of these are **computed views** over the transactions, with no new tables except for saved reports.

## Decision

### Net worth (OF-1501)

- **Net worth = assets − debts**, in the household currency and with the accounts visible to whoever asks (ADR-0013): another person's personal account does not add up, neither in the total nor in the history. **Assets** are the sum of positive balances and **debts** the sum of negative ones (in absolute value), whatever the account type: a card or a loan with a negative balance is what is owed, and so is an overdraft on a bank account. A card with a positive balance (overpaid) is an asset: it is not hidden. The breakdown by type (bank, cash, investment, card, loan) shows the net of each.
- It shows the total, the breakdown by type and by account and the **evolution over the last 12 month-ends** plus today's. The balance at each date is the opening balance plus the transactions up to that day (voided ones do not count).
- **Other currencies** are converted at the most recent exchange rate on or before each date (ADR-0019). An account without a rate for a date **does not enter** at that date and is listed separately, to say "falta el tipo de USD" ("the USD rate is missing") instead of inventing a value.
- Net worth includes the personal accounts of whoever is looking. Whoever looks at the household view sees their own; there is no "couple's net worth" that adds up other people's accounts.

### Cash flow (OF-1502)

- Per month, over the **liquid money** visible to whoever asks (bank accounts and cash) **in the household currency**: **income**, **contributions** (net: what goes into the joint account minus what leaves a personal one, so they offset when both are seen), **spending** (net of refunds), **to savings** (net of what is withdrawn from the piggy bank), **own transfers** (net, normally zero) and the **balance at month end**. Income + contributions − spending − savings + transfers = change in the month = difference between month-end balances: the identity is checked in tests.
- Liquid accounts in **another currency are left out** (they are counted in the result and the screen says so): converting transactions and balances with different rates would make the identity not balance to the cent, and it is preferable not to show a figure that looks exact and is not.
- The last 12 months by default (1 to 36). The current month is marked as partial.
- Cards, loans and investments are not liquid and are left out: their purchases are already card spending (ADR-0018) and mixing them in would count twice.

### Custom reports (OF-1503)

- A report is a **definition** (not a result): period (month to month, maximum 36 months), what to measure (**spending** net of refunds, **income**, net **savings** or **net** = income minus spending), what to group by (category, merchant, account or month) and optional filters: accounts, categories (with "sin categoría" ("uncategorized")), tags (transactions with **any** of them) and minimum amount per transaction. The accounts counted are those visible to whoever runs it and that enter reports (not loans or investments), in the household currency; transactions in another currency without an exchange rate are left out and a warning is shown.
- It always runs with the **permissions of whoever runs it**: the same definition gives different results to each person because each sees different accounts, and a result is never stored. Filtering by an account that is not visible gives **404**, not an empty result.
- They can be **saved** (`saved_reports`): personal or shared with the household. Maximum 30 per person. A personal report does not exist for anyone else (404). A shared one can be run by the household members, with their own permissions; only its owner changes or deletes it. **A shared report cannot filter by personal accounts** (it would reveal their identifiers). If an account in a shared report's filter stops being visible to whoever runs it, it is ignored and a warning is shown; if none remain, the result is **empty**, never "all accounts".
- The result can be downloaded as **CSV** with the same formula-injection protection as the export (OF-501). The list shows up to 100 groups (the heaviest); the total includes all of them and it states how many do not fit.
- There is no query language or expressions: only closed, validated fields.

### Export v2 (OF-1504)

- `format_version: 2` adds what v1 did not carry: budget amounts per month and mode (limit or envelope), goal contributions, scheduled payments, templates, automation rules, merchants with their own name, tags, saved reports (own and shared), bank connections (bank, status, expiry and last four digits of the IBAN) and exchange rates.
- The aggregator's session identifier, a connection's `state`, the VAPID keys, push subscriptions, transaction fingerprints, sessions and password hashes are **never** exported. Neither is anything belonging to another household member (personal accounts, personal reports, connections, their personal rules), as in v1.
- Each block applies its own visibility rule: scheduled payments only from visible accounts; templates and rules, the household's and one's own; saved reports, one's own and the shared ones; bank connections, only one's own (a link to an account that is not visible comes out without an account). A **merchant with its own name is only exported if any of its variants appears in the exported transactions**: its variants could betray an expense from another person's personal account.
- v1 remains available with `?version=1` for those who use it; without a parameter, v2 is delivered. The transactions CSV does not change.

## Consequences

- One new table, `saved_reports`; the rest does not touch the schema.
- Net worth and cash flow have their figures cross-checked in tests (change in the month = difference of balances; the sum by type = the total).
- Custom reports are another surface for reading transactions: each query goes through the visible accounts and has negative tests across people and across households.
- Export v2 is larger than v1 and is tested with an explicit list of fields that it must **not** contain.
