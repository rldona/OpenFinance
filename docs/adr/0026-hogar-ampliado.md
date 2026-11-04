# ADR-0026: Extended household: more people with roles, expense splitting and events

- Status: Accepted
- Date: 2026-11-03

## Context

The household started out for two people ([ADR-0012](0012-empezar-por-el-hogar.md)) and sign-ups are done from the server. The model already admits more than two members, but there is no way to invite them, everyone can write everything and the expense splitting foreseen by [ADR-0011](0011-perfiles-compartidos-reparto.md) does not exist. A shared flat or a group trip needs three things: more people with different permissions, splitting what one person pays on behalf of everyone, and grouping expenses by event.

The **household** is reused as the boundary ([ADR-0002](0002-workspace-frontera-aislamiento.md)) instead of creating a separate shared workspace: a four-person household is the "shared flat". Out of scope, and documented as pending, are expenses paid from the common account split per person (the "fund balance" of ADR-0011) and the link between a personal transaction and a shared expense.

## Decision

### People and roles (OF-1601)

- Each household membership has a **role**: `owner`, `editor` or `viewer` (ADR-0002). People who were already there are `owner`. At most **10 people** per household.
  - `owner`: everything, and also invites, changes roles and removes people.
  - `editor`: writes in the household (transactions, imports, rules, budgets…), but does not manage people.
  - `viewer`: read only. Can change their own password, sign out, dismiss alerts, choose their notifications and run reports (these do not write household data).
- The role **does not open personal accounts**: an `owner` does not see another person's personal account either (ADR-0013). It is a write and management permission, not a visibility one.
- The check is **central**: every non-read request is rejected (403) for a `viewer` except for the list above, without depending on each route remembering to do so. People management requires `owner` on every route.
- **Invitations**: an `owner` creates an invitation with the chosen role; they receive a link **only once** (256 random bits; only its SHA-256 hash is stored in the database). It expires after 7 days, is valid once and can be revoked. Whoever opens it chooses their name, email and password (minimum 10 characters) and enters with an open session. There is no public sign-up: without a valid invitation nothing is created. Accepting is limited by attempts and by IP like sign-in. An email that already has an account is rejected (a person belongs to one household).
- **Removing someone** (`owner`): their sessions are closed and they stop belonging to the household. A person with **personal accounts** cannot be removed (it would have to be decided what happens to their transactions), nor oneself, nor the last `owner`. Changing someone's role cannot leave the household without an `owner`.

### Expense splitting (OF-1602)

- **Participants**: the household's people and **guests without a user** (just a name, no access to anything; whoever has a write role records for them). A guest is only archived with a zero balance.
- **Shared expense**: date, description, amount (in the household currency), **who paid** (one or several people; the amount paid sums exactly to the total) and **how it is split**: `equal`, `percentage`, `exact` or `shares`, among the whole group or a subset. Calculations are in whole cents and the remainder is assigned by **largest remainder** with ties broken by the given order; the sum of the parts is **always** the amount and, if it does not add up, it is rejected. The result of each part is stored, not just the rule. An expense can be corrected (it is recalculated) and is voided without being deleted.
- **Balance between people** = paid − their share + settlements sent − settlements received (only confirmed ones). The sum of all balances is exactly **zero**. The "who pays whom" suggestions come from those balances with the minimum number of transfers, matching the largest debtors with the largest creditors.
- **Settlements**: whoever pays records it and it stays **pending** until the recipient confirms it (or an `owner` or `editor` if the recipient is a guest). Only then does it change the balances. Recording the same settlement twice with the same reference does not duplicate it. It can be cancelled while pending.
- **Visibility**: shared expenses belong to the household and everyone sees them. They are not linked to transactions in personal accounts, so they leak nothing from them.

### Events and trips (OF-1603)

- An **event** (trip, birthday, renovation) has a name, icon and optional dates. Shared expenses can belong to one. Its summary shows the total, what was paid and each participant's share, the balances **using only the event's expenses** and the spending by category.
- An event can be **closed**: it admits no new expenses until reopened. An event with expenses is not deleted, it is closed.

## Consequences

- `memberships.role`, `invitations`, `guests`, `shared_expenses` (with their payers and shares), `settlements` and `events` are added.
- `Actor` carries the role; existing use cases keep working because the default value is `owner` and the `viewer` restriction is applied in the API.
- Mandatory tests: the shares sum to the expense amount, the balances sum to zero, repeating a settlement changes nothing, a `viewer` writes on no write route (all are traversed), an invitation is valid once and expires, and nothing from another household is visible or modifiable.
- Export v2 ([ADR-0025](0025-informes-y-patrimonio.md)) includes guests, events, shared expenses and settlements: they belong to the household and everyone sees them.
- Pending (no ticket): expenses paid from the common account split per person, and linking a personal transaction with a shared expense ("Gasto compartido · Casa" ("Shared expense · Home")).
