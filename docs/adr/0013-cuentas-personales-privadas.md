# ADR-0013: Personal accounts in the household, private by default

- Status: Accepted
- Date: 2026-10-31

## Context

The joint account is at Revolut and each person also has a personal account at Bankinter, from which they contribute to the joint one. We want to be able to bring in those personal accounts without losing the simplicity of ADR-0012 and without exposing each person's finances to the other unless they decide so.

## Decision

- Each `Account` has a **type** (`joint`, `savings`, `personal`) and an **institution** (`revolut`, `bankinter`, `other`).
- A `personal` account must have an **owner** (`owner_id`); the others have no owner. The database guarantees this with a `CHECK` constraint.
- **Visibility:** the joint account and the savings pockets are visible to all household members. A personal account is **visible only to its owner**, and its transactions do not appear to anyone else either, neither in listings nor when querying by id (404).
- Contributions are recorded as `contribution` with the contributing person: in the joint account they are an **inflow**; in the personal account, if imported, they are an **outflow** that does not count as spending.
- Household totals (spending, savings and charts) are calculated over the joint account and the savings pockets. Personal accounts will have their own view once they are imported (OF-107).

## Consequences

- Every account and transaction query filters by household **and** by visibility; there are negative tests for both cases.
- If in the future you want to share a personal account, it will be enough to add an explicit permission ("compartir con…", share with…) without changing the model.
- This decision extends ADR-0012 on a single point (personal accounts); the rest of the v0.1 scope does not change.
