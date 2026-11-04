# ADR-0005: Human approval for operations prepared by agents

- Status: Accepted
- Date: 2026-10-31

## Context

Agents can prepare operations, but the authority to execute them belongs to the user. An approval must not be reusable for anything other than what was reviewed.

## Decision

- Every Manager write is materialized as an `ActionProposal`: operation, typed arguments, scope and a **fingerprint** (canonical hash of all of the above). The proposal is immutable.
- `Approval` references the proposal and its fingerprint, with approver, decision and date.
- States: `draft → pending_approval → approved → executing → succeeded`, with branches `rejected`, `expired`, `cancelled` and `failed`.
- When moving from `approved` to `executing`, permissions, the current state of the resources and business conditions are revalidated.
- `ActionExecution` records each attempt with an idempotency key; retrying does not duplicate effects.
- Approvals expire and never authorize future operations.

## Consequences

- A state machine and auditing are needed from phase 3.
- In the MVP only internal operations are proposed (categorizations, rules); no real payments or transfers.
