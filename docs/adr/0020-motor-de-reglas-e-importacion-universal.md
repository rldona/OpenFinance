# ADR-0020: Rules engine with conditions and universal import

- Status: Accepted
- Date: 2026-11-02

## Context

Today there is a single kind of rule: "merchant → category", which is learned when correcting (OF-202, OF-702). It works for the common case, but not for "payments over €500 from the joint account are *Casa* (Home)", "anything containing *AMAZON PRIME* gets the tag *suscripción* (subscription)" or "bank fees are *Banco* (Bank) and don't count for review". And only two formats from two banks (Revolut and Bankinter) are imported, while other households will have a different bank.

This phase makes rules more powerful without losing what already works, and opens import to standard formats and to any CSV.

## Decision

### Rules with conditions, actions and phases

- A **rule** has a name, a scope (household or personal, as today), **conditions** (all at once), **actions** and a **phase**.
- **Conditions**: the description *contains*, *starts with* or *equals* a text (case- and accent-insensitive); the merchant is a specific one; the amount is *between* two values (in absolute value); it is an expense or an income (sign); the account is one of these; the bank type is this one. **There are no regular expressions**: a rule written by a person cannot hang the server (ReDoS), and the above covers what is asked for in practice.
- **Actions**: set the category, set the type (expense, income, transfer…), add tags, set or append a note, assign the merchant. An action never touches the amount, date or description.
- **Phases**: `antes` (before), `normal` and `después` (after). Within each phase, in priority order (a number that can be reordered). Each action is applied **only if the field has not yet been set by an earlier rule or by a person** ("the first to set wins"): a category chosen by hand is never overwritten, as until now.
- The learned "merchant → category" rules **continue to exist as they are** and are evaluated in the `normal` phase with the lowest priority: what an explicit rule does not decide, the learned one decides. There is no data migration of the current rules.
- A **reviewed** (OF-1006) or **split** (OF-1003) transaction is not changed by any rule.

### Preview and apply to existing

- Every rule can be **tested** before saving it: the preview says which existing transactions (among those visible to the creator) would change, with before and after, without writing anything.
- **Apply to existing** is an explicit action, separate from saving the rule, and leaves an operation in the change log (ADR-0017) that is undone in one go. New rules apply automatically to future imports.
- Privacy (ADR-0013): a household rule sees and changes only the transactions of accounts visible to whoever applies it; a personal rule, only those of its owner's personal accounts. A count never includes what is not visible.

### Universal import

- **Formats**: OFX and QIF (the ones almost all banks export), CAMT.053 (ISO 20022 XML, the European standard) and **CSV from any bank** with a **profile**.
- All of them go through the same pipeline as today: reader → normalized rows (`ImportedRow`) → preview → confirm. Same stable `fingerprint` to avoid duplicates, same balance checks when the format carries balances, same size limits (5 MB), and real statements still never enter the repository.
- XML only with `defusedxml` (no external entities or expansion). Amounts never go through `float`.
- A **CSV profile** stores how to read a bank's file: separator, encoding, date and number format, date, description and amount columns (or debit/credit), sign, and how many header rows to skip. It is created from a preview of the first rows and reused; it belongs to the household and can be deleted. It executes nothing: it is just data.
- A new format does not replace the Revolut and Bankinter readers: those continue to be detected by their header.

## Consequences

- A stable, testable evaluation order is needed: the engine is a pure function (transaction + rules → changes) in the domain, with data access outside.
- The tests include properties: applying the same rules twice changes nothing the second time (idempotence) and a field set by hand is never changed.
- OFX, QIF and CAMT are tested with synthetic files; real statements remain outside the repository.
- Rules with conditions on the account or the amount need the preview to be fast: it is evaluated in memory over the visible transactions, without one query per rule.
