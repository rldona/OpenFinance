# ADR-0019: Multiple currencies

- Status: Accepted
- Date: 2026-11-01

## Context

`Money` already carries the currency of each amount and operations between different currencies fail, but the whole household is in a single currency and the reports take it for granted. Some people travel, are paid in another currency, or have an account abroad.

## Decision

- **Each account has one currency** and its transactions are in it. There are no multi-currency accounts.
- **The household has a reference currency** (today's, EUR by default). Reports, budgets and goals are computed in it.
- **Exchange rates are manual or imported, never looked up online**: an `exchange_rates` table (household, currency, date, `Decimal` rate with 8 decimals, source `manual|extracto`). OpenFinance does not call any quote service (consistent with [ADR-0007](0007-local-first-self-hosted.md)).
- **Conversion at a date**: the most recent rate on or before the transaction date. If there is none, the transaction is **not converted** and the report says so ("3 transactions in USD without an exchange rate") instead of inventing a value.
- Conversion is always a calculation view: the original amount is not modified and is rounded only once, at the end, with `ROUND_HALF_EVEN`.
- A transfer between accounts in different currencies stores its two real amounts; the implied exchange is shown, not corrected.

## Consequences

- Core reports now receive a converter (port) instead of summing `Money` directly.
- A single-currency household notices nothing: without rates, everything stays as it is.
- It is the last ticket of the phase because it touches the totals on every screen.
