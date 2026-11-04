# ADR-0015: Per-person contribution patterns and Excel statements

- Status: Accepted
- Date: 2026-11-01

## Context

The first real statements (OF-104, OF-107) revealed three things that the OF-105 design did not cover:

1. **Revolut downloads as Excel (.xlsx)** when the app is set to Spanish, with Spanish headers (some with broken encoding, `DescripciÃ³n`), Excel dates with fractions of a second, and numeric amounts. The English CSV is still possible.
2. **Bankinter only exports Excel**, with a preamble (account number, pending transactions and filters), `dd/mm/yyyy` dates without time, and transactions from newest to oldest.
3. **Not every contribution carries the person's name.** In the joint account, a top-up from a person's card appears as "Recarga de \*NNNN" (top-up from \*NNNN; the last digits of the card). In Bankinter's personal account, the Revolut top-up appears as an outflow "Revolut\*\*NNNN\*". Neither can be deduced from the name.

## Decision

### Per-person patterns

- Table `member_patterns` (household, direction, pattern → person). The pattern is stored normalized (uppercase, no accents, single spaces), with 3 to 60 characters and at least 3 letters or digits: `*1234` is valid, `***` is not. The person must be a member of the same household (composite foreign key to `memberships`).
- Direction **`inflow`**: inflows in the joint account (and savings pots) that are that person's contribution, in addition to their full name and first name.
- Direction **`outflow`**: outflows from **their** personal account that are their contribution to the household. Stored patterns apply to any personal account of the holder. In addition, **only in Bankinter personal accounts**, `REVOLUT**` is always included (that is how the joint-account top-up appears there); at other banks that text may mean something else (for example, a Revolut card payment) and remains an expense unless it is stored as a pattern.
- In a personal account, names are **not** used: a Bizum from the partner is income, not a contribution. Patterns of other people or of another household are never applied.
- They are managed from the server with `openfinance member-patterns add|list|remove <email> '<pattern>' [--outflow]`.
- **Update (OF-704):** each person also manages **their own** from Settings (`GET/POST/DELETE /api/v1/me/patterns`). The API never lists or deletes the partner's. When importing into the Revolut joint account, the preview says who has no top-up card stored and the web app asks for confirmation before importing, because their top-ups would come in as income.
- Classification stays in the domain (`ClassificationRules`, `suggest_kind`); the `StatementParser` port does not change.

### Reading Excel

- `openpyxl` (with `defusedxml`) only in `infrastructure/importers/xlsx.py`; `import-linter` prevents using it in the domain and application layers.
- Before opening the file, the zip is checked: at most 100 parts and 10 MB uncompressed in total, no part above 8 MB, `xl/styles.xml` up to 1 MB and `xl/sharedStrings.xml` up to 5 MB (openpyxl loads them entirely into memory), a per-part compression ratio of at most 100, and no encrypted part. If `openpyxl` is not using `defusedxml`, no Excel file is read.
- The first sheet is read in read-only mode, without formulas or external links, ignoring the declared dimension (it can be false), with a maximum of 20,000 rows and 30 columns. Old `.xls` files are rejected, asking for `.xlsx`.
- CSV is read in streaming mode with the same row and column limits; empty lines are skipped without accumulating them.
- An amount that does not fit in the columns (`Numeric(19, 4)`: 10¹⁵ or more) or with an absurd exponent is discarded as an invalid row.
- Reading the statement is synchronous work: the API runs it outside the event loop.
- Numbers are converted to `Decimal` from their shortest representation (`repr`), never operating with `float`. Times are rounded to the second.
- The broken encoding (`DescripciÃ³n`) is repaired only in Revolut's Excel. The CSV is read as is so that its fingerprints do not change.
- Error messages do not include cell values (Bankinter's preamble carries the account number).

### Order, balance and fingerprints

- Reader contract: rows come out in the **order in which the bank applies them to the balance**, from oldest to newest. Revolut: the file order (completion date). Bankinter: the reverse of the file. The bank's closing balance is that of the last row with a balance (`ParseResult.closing_balance`), not that of the latest date.
- `fingerprint` accepts an optional `discriminator`. When empty, the fingerprint is identical to the previous one: those already stored remain valid. Bankinter gives no time, so it uses the balance after the transaction as the discriminator: two identical coffees on the same day are not merged, and a statement that overlaps another recognizes those already imported.

### Classification by bank

- Revolut: "Pago con tarjeta" (card payment) (or `CARD_PAYMENT`) with a positive amount is a refund: positive expense.
- Bankinter: transfers and Bizum by sign (inflow = income, outflow = expense), except outflows that match an `outflow` pattern of the holder, which are their contribution.

## Consequences

- Contributions via card top-up and from Bankinter are recognized without touching the code, by storing one pattern per person.
- A contribution imported from the personal account counts neither as an expense nor as a household inflow (ADR-0013).
- `openfinance statement-check --bank revolut|bankinter FILE` checks a statement without a database and shows only counts; it is useful for validating new formats without exposing data.
- Mixing the English CSV and the Spanish Excel of the same account can duplicate transactions: the descriptions do not match ("Payment from…" versus "Transferencia de…" (Transfer from…)), so the fingerprints do not either. Always use the same format.
- Each person's "my spending" view over their personal account is left for OF-108.
