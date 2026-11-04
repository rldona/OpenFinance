# ADR-0018: Scope of the full ledger

- Status: Accepted
- Date: 2026-11-01

## Context

Up to phase 9, OpenFinance treats a transaction as an inflow or expense of a household with a bank account behind it ([ADR-0012](0012-empezar-por-el-hogar.md)). That is enough to import statements and view the month. It is not enough for what the household really does with money: paying for a purchase between two accounts, splitting a receipt into several categories, keeping track of cash, seeing what is owed on the mortgage or what a set of funds is worth.

The roadmap left "loans" out of scope. What was left out is **selling or brokering** loans, insurance and interest-bearing accounts (a brokerage business). **Keeping track of a loan you already have** is something else: it is a balance that goes down. This ADR sets that boundary.

## Decision

### In scope (phase 10)

1. **More account types**, all tracking-only (nothing is contracted or moved from OpenFinance): `cash` (cash), `card` (credit card: the balance is what is owed), `loan` (an existing loan or mortgage: outstanding balance) and `investment` (value recorded by hand or through transactions; no live quotes).
2. **Merchants** as an entity: a display name, with its bank variants ("MERCADONA 0451" → "Mercadona"), which can be renamed and merged.
3. **Splitting a transaction** into several parts, each with its category; the sum of the parts is always the original amount.
4. **Linked transfers**: the two sides of a transfer between own accounts are linked to each other, so that neither counts as an expense or as income and the pair is visible.
5. **Reconciliation**: marking transactions as reviewed and checking an account's balance against the bank's on a given date.
6. **Tags, notes and attachments** (receipt, invoice) on a transaction. Attachments live on disk under the same privacy rule as the transaction and are included in the backup.
7. **Multiple currencies** ([ADR-0019](0019-varias-monedas.md)).

### Out of scope (unchanged)

Contracting, comparing or recommending loans, insurance or interest-bearing accounts; real-time quotes and returns of investments; financial advice; end-to-end encryption.

### Rules that do not change

- Every query filters by household and by account visibility ([ADR-0013](0013-cuentas-personales-privadas.md)). Tags, parts, links and attachments inherit the transaction's visibility; one negative test for each.
- Every change to a correctable piece of data goes through the change log ([ADR-0017](0017-registro-de-cambios.md)), with undo and redo.
- Amounts are `Decimal`; never `float`.
- An imported transaction keeps its amount, date, description and fingerprint. Splitting it does not touch them: the parts are a layer on top.

### Effect on reports

- `loan` and `investment` accounts do not count toward the month's spending or toward budgets. Loan installments are an expense (category) on the account they are paid from; the loan balance goes down through the linked transfer to the `loan` account.
- The household balance remains the sum of the visible accounts; `card` and `loan` subtract.

## Consequences

- One migration per ticket is needed, and a public API change with each one (`make openapi`).
- The phase 3 reports have to ignore the parts of a split transaction and use the parts instead; this is covered by a property test (the per-category sum does not change when splitting).
- It can be implemented in independent tickets in this order: merchants → tags and notes → splitting → linked transfers → account types → reconciliation → attachments → currencies. Currencies go last because they touch the whole Core.
