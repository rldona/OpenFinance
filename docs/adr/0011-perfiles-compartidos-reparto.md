# ADR-0011: Shared profiles and expense splitting

- Status: Proposed
- Date: 2026-10-31

## Context

Besides each person's profile, shared profiles are needed, such as "Casa" (Home), in which several people share expenses (wifi, electricity, water, groceries…). Both the 1-to-1 case (a couple) and the N-to-N case (a shared flat) must be covered. A shared profile can have a joint account and also expenses that one person pays out of pocket. Some people in the group may not have a user in OpenFinance.

## Decision

### Shared profile = shared workspace

`Workspace` (ADR-0002) is reused with `kind = personal | shared`. A shared workspace can use a template (Casa, Pareja, Viaje, Grupo; that is, Home, Couple, Trip, Group) that provides an icon and default categories, without changing the model. Expense splitting is an official module (`official.sharing`, ADR-0006) and a new domain context, `sharing`.

### Entities

| Entity | Responsibility |
| --- | --- |
| `Participant` | Person who shares expenses in the workspace. May or may not have a `user_id`. |
| `SharedExpense` | Expense with amount, date, category, **who paid** and **how it is split**. |
| `ExpenseSplit` | Each participant's share of an expense. The resulting amount is stored, not just the rule. |
| `Contribution` | A participant's contribution to the joint account. |
| `Settlement` | Settlement of a debt between two participants. |

- **Participants without a user:** they are created by name and have no access to anything. An owner or editor records the transactions on their behalf. Later they can be linked to a user through an invitation without losing the history.
- **Members and participants:** each member with a user has a `Participant`. The role (`owner`/`editor`/`viewer`) controls what they can do; the participant, what is split among them.

### Who pays

An expense is paid by one of these two sources:

1. **The joint account**: it is an `Account` of the shared workspace and is funded by `Contribution`s.
2. **One or several participants out of pocket.** The sum of what was paid must equal the expense amount.

### How it is split

Methods: `equal` (equal shares), `percentage`, `exact` (amounts) and `shares` (weights, for example 2:1:1). A subset of the group can take part (1 to 1 within a group of N).

- Calculations are done in integer minor units (cents). If cents are left over, they are assigned with the **largest remainder** method, with deterministic tie-breaking by participant order. The sum of the parts is always **exactly** the expense amount. If it does not add up, the Core rejects the expense.
- The method and the result are stored. Changing the method recalculates and leaves a trace in the audit.

### Two separate balances

So that the joint account's money does not get mixed with the debts between people:

- **Each person's stake in the fund** = contributed − their share of the expenses paid with the joint account. The sum of all stakes is exactly the joint account's balance.
- **Balance between people** = paid out of pocket − their share of those expenses + settlements sent − settlements received. The sum of all balances is exactly 0.

The "who pays whom" suggestions are calculated only on the balance between people: the money stays in the joint account unless the group decides to distribute it. The algorithm will match debtors and creditors with the minimum number of transfers.

### Settlements with double confirmation

The payer records the `Settlement` and it stays `pending_confirmation` until the receiver confirms it, or an owner or editor if the receiver has no user. Only then does it change the balances.

### Relationship with the personal profile

If Ana pays Casa's electricity bill (€90, a third of which is hers) from her personal account:

- In her personal workspace, the −€90 transaction is linked to the `SharedExpense` as **"Gasto compartido · Casa" (Shared expense · Home)**. Her **real expense is €30**; the remaining €60 is an amount pending collection from the group, not an expense.
- A contribution to the joint account is a movement towards the shared profile, like a transfer: **it does not count as an expense**. The expense appears when the joint account pays something, for the share that corresponds to each person.
- The other members of Casa see "paid by Ana", but **never** the personal account or the originating transaction (ADR-0002).

### Manager

The Manager can suggest a split or the category of an expense imported from the joint account. It can also prepare settlements. Everything goes through proposal and approval (ADR-0005).

## Consequences

- New `sharing` context and official module `official.sharing`.
- Links between workspaces (personal transaction ↔ shared expense) are needed, visible only to the owner of the originating transaction. They require negative isolation tests.
- A participant can only be removed when both of their balances are 0.
- Multi-currency: each workspace has a base currency. An expense in another currency stores the applied exchange rate explicitly. In v0.1 only the base currency is supported.
- Mandatory tests: the parts always add up to the expense amount, the sum of the balances between people is 0, the sum of the stakes equals the joint account's balance, and repeating the recording of a settlement is idempotent.
