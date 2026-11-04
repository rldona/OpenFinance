# ADR-0022: Budgets with limits or envelopes, carry-over and goals v2

- Status: Accepted
- Date: 2026-11-02

## Context

The budgets in OF-401 are a monthly limit per category that resets every month. Two households manage money differently: some want **a cap** and nothing more (if you don't spend it, it is lost) and others want **envelopes** (what is left of "Ocio" ("Leisure") this month is added to the next, and what you overspend is subtracted). The goals in OF-402 only have a fixed monthly contribution.

## Decision

### Two modes per category

- **Limit** (the current one): an amount per month. No carry-over. It is the default mode and **nothing changes** for anyone who touches nothing: no data migration, existing budgets are limits.
- **Envelope**: a monthly amount that **accumulates**. The available amount for a month is `month's allocation + balance carried over from the previous month − spent in the month`. An envelope can go negative (more was spent than was there) and that deficit is carried over, or it can be reset to zero by hand.
- Carry-over is calculated **from the month the envelope was created** and is a pure function of the expenses: the carried-over balance is not stored but recalculated, so correcting an old transaction corrects all following months and it never gets out of sync.
- **Per-month amounts**: a budget can have a different amount in a specific month (holidays in August) without touching the rest. Without an exception, the base amount applies.

### What counts as envelope spending

- The same as today: expenses in the category on household accounts visible to the person querying (checking accounts and piggy banks), including the parts of a split transaction (OF-1003) and converted to the household currency (ADR-0019). `card` and `loan` accounts and transfers do not count. A scheduled bill (ADR-0021) is not deducted until it is charged.
- Budgets and envelopes only count household accounts or accounts visible to the actor; another person's personal account never takes part (ADR-0013).

### Alerts

- The alert at 85% and on going over is kept (OF-401). For an envelope, "over" means a negative available amount. The alert for a category with fixed installments follows the current `budget_status` rule.

### Goals v2

- A goal can have registered **contributions** (date, amount, note; they go in the change log), **priority** (for ordering and for distributing the leftover monthly contribution) and a **reminder** of its monthly contribution as a scheduled payment (ADR-0021) instead of a loose number.
- The OF-402 projection is kept; registered contributions feed "saved" when the goal is not linked to a piggy bank.

## Consequences

- `mode` and `started_on` are added to budgets, along with the `budget_overrides` table and the `goal_contributions` table; the migration does not touch existing rows.
- Property tests: envelopes with no spending accumulate exactly `n × allocation`; reordering expenses between months does not change the accumulated total.
- The front end shows the mode clearly: "Límite" ("Limit") and "Sobre" ("Envelope") are explained on the screen itself, and a negative envelope is not presented as an error but as what it is.
