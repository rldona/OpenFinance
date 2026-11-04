# ADR-0017: Change log with undo and redo

- Status: Accepted
- Date: 2026-11-01

## Context

Phase 7 (OF-701 … OF-706) allows correcting data from the web app: a transaction's type, person and note, categories in bulk, rules, cash transactions, and undoing an import. Every correction must be traced (who, when, before and after) and be undoable without fear.

The audit first proposed a `transaction_corrections` table (OF-701) and later extending it into a general log (OF-706). Doing it in two steps forces migrating real data in the middle of the month of use. The general log is built from the start and OF-701 is its first use.

## Decision

### Model

- **Operation** (`change_operations`): one action by one person, with household, author, date, type (`transaction.edit`, `transactions.categorize`, `rule.delete`, `import.undo`…), a human-readable summary and, if it has been undone, when and by whom. Several writes go in the same operation (setting a category and having the rule classify 40 others).
- **Change** (`change_entries`): entity (`transaction`, `rule`, `import`), its identifier, field, value before and value after (JSON). Only correctable fields are recorded: on a transaction `kind`, `member_id`, `category_id`, `note` and `voided`; on a rule, its category (`null` = no rule); on an import, its status.
- **Nothing is deleted.** Deleting a manual transaction or undoing an import sets `voided = true` (and it stays in the log). Queries, totals and the export ignore voided transactions. The amount, date, description and fingerprint of an imported transaction never change.
- Creating a manual transaction: recorded as `voided: true → false`, so undoing it voids it.

### Undo and redo

- Each person only undoes and redoes **their own** operations.
- Undo walks the changes backwards and sets the "before" value **only where the current value is still the "after"**. If someone (that person or the partner) changed it afterwards, that change is respected and the response says how many were left and who touched them. Redo is the mirror image. A later change is never overwritten.
- Consequence: undoing all operations in reverse order returns to the initial state (property test).
- Undo or redo is also recorded on the operation (`undone_at`, `undone_by`).

### Privacy (ADR-0013)

- A transaction's history is visible only if the transaction is visible: the partner does not see that of someone else's personal account (404, like the transaction itself).
- A person's operation list includes only their own. Personal rules and their changes are visible only to their owner.

## Consequences

- Every new write on transactions, rules or imports goes through the log: it is the basis for merchant merges, the rules engine and the assistant's proposals in later phases.
- Transaction queries always carry the `voided = false` filter; there are tests that check this in listings, totals and export.
- Re-importing an undone statement reactivates its transactions (same fingerprint, same identifier) instead of duplicating them.
- The log grows with use. With two people it is a few hundred rows per month; it is not purged.
