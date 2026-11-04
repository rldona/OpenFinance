# Household banks

| Account | Bank | In v0.1 | How it comes in |
| --- | --- | --- | --- |
| Joint account (household expenses) | **Revolut** | ✅ Yes | Excel (.xlsx) or CSV statement |
| Pockets of the joint account | **Revolut** | As a transfer to savings | Detected in the same statement |
| Each person's personal accounts | **Bankinter** | ✅ Yes, private to their owner ([ADR-0013](../adr/0013-cuentas-personales-privadas.md)) | Transactions in Excel (.xlsx) |

Decisions: [ADR-0015](../adr/0015-patrones-por-persona-y-xlsx.md). The real statements were validated with `openfinance statement-check` (counts only); none has been copied into the repository.

## Revolut · joint account

**How to download it:** Revolut app → account → *Statement* → *Excel* format → period.

There are two formats and they are detected automatically:

- **Excel (.xlsx)**, the one the app gives in Spanish. Validated with a real statement.
- **CSV**, with English headers (public format, the one from Firefly III's import configuration for Revolut).

> ⚠️ Always use the same format for the same account. Descriptions differ between the English CSV and the Spanish Excel ("Payment from…" versus "Transferencia de…") and the fingerprint depends on the description: mixing formats could duplicate transactions.

| Excel (Spanish) | CSV (English) | Use in OpenFinance |
| --- | --- | --- |
| `Tipo` | `Type` | Origin. Seen: "Pago con tarjeta" (card payment), "Transferir" (transfer), "Recargas" (top-ups). `CARD_REFUND`/`REFUND`, or a card payment with a positive amount, are refunds: an expense with a positive amount |
| `Producto` | `Product` | Only `Actual` / `Current` is imported. Pocket rows (`Savings`) are skipped because the transfer already appears in the account |
| `Fecha de inicio` | `Started Date` | Date and time of the transaction. In Excel it is an Excel date with fractions of a second: rounded to the second |
| `Fecha de finalización` | `Completed Date` | Value date. Empty for pending ones |
| `Descripción` | `Description` | Description: merchant, "Transferencia de …", "Recarga de \*NNNN", "To pocket …" |
| `Importe` | `Amount` | Signed amount. In Excel it is a number with at most 2 decimals; it is converted to `Decimal` without operating on `float` |
| `Comisión` | `Fee` | Separate fee: the effect on the account is `Importe − Comisión` |
| `Divisa` | `Currency` | Currency of the transaction |
| `State` | `State` | Only `COMPLETADO` / `COMPLETED`. Pending ones will be imported once completed; reverted, rejected and failed ones are discarded |
| `Saldo` | `Balance` | Balance after the transaction: used to check that no rows are missing. Empty for pending ones |

Notes on the real Excel:

- Some headers arrive with broken encoding (`DescripciÃ³n`, `ComisiÃ³n`); in the Excel they are repaired (headers and descriptions). Correctly spelled ones are also accepted. The CSV is read as-is, without repair, so as not to change its fingerprints.
- Pending rows are shorter: they have no completion date or balance.
- The file is sorted by **completion date**, and the balance adds up in that order. It is not reordered by start date.
- Some descriptions contain `?` in place of characters that Revolut could not export. They cannot be recovered and are stored as-is.

**Duplicates:** Revolut does not give an identifier per transaction. The fingerprint combines account, date and time to the second, amount, normalized description, and order of appearance of identical rows in the file. The same statement in CSV and in Excel with the same descriptions gives the same fingerprints.

**Automatic classification:**

- Inflows with a person's name (full name or first name, without accents; e.g. "Transferencia de RAUL …") → that person's **contribution**.
- Inflows matching an inflow pattern saved for a person (e.g. "Recarga de \*1234", with the last digits of their card) → that person's **contribution**. See "Patterns per person".
- "To pocket …" → **transfer to savings**; "From pocket …" → transfer from the pocket (positive, not income).
- Names and patterns are matched by whole word: "ANA" does not match "MARIANA".
- Other inflows (received Bizum payments, interest) → **income**.
- Everything else → **expense**, pending a category.

### To be confirmed

- [x] Exact headers: in Spanish in the Excel (see table), in English in the CSV.
- [x] Value of `Producto` in the joint account: `Actual`.
- [x] Text of contributions: "Transferencia de NAME SURNAMES" and "Recarga de \*NNNN".
- [ ] Whether the time is local time or UTC: it decides which day an early-morning payment falls on.
- [ ] Sign of `Comisión` and whether `Saldo` already deducts it: in the sample all fees are 0.
- [ ] Exact text of the transfers to pockets in the Spanish Excel (today "To pocket" and "From pocket" are recognized).
- [ ] Text of the top-ups from the joint account to the personal accounts, to recognize them as an internal transfer (OF-602).

## Bankinter · personal accounts

Each person has their own; **only its owner sees it** (ADR-0013).

**How to download it:** Bankinter website → account → *Movimientos* (Transactions) → download as Excel (.xlsx). Old `.xls` files are not supported: export as `.xlsx`.

Structure of the `Movimientos` sheet (validated with a real statement):

1. First row: "MOVIMIENTOS DE LA CUENTA …" (account transactions) with the account number. It is **not read** and never appears in messages or discarded rows.
2. "MOVIMIENTOS PENDIENTES …" (pending transactions) and, below it, its own header `Fecha, Descripción, Importe, Divisa` with the pending ones. They are discarded with the reason "pendiente: se importará cuando se contabilice" (pending: will be imported once posted).
3. "MOVIMIENTOS" and the filters applied on the website (`Concepto`, `Fecha`, `Tipo de movimiento`, `Importe`). They are ignored.
4. The real header and the transactions:

| Column | Use in OpenFinance |
| --- | --- |
| `Fecha contable` | Date of the transaction, text `dd/mm/aaaa`. Bankinter gives no time: it is stored at 00:00 |
| `Fecha valor` | Value date, `dd/mm/aaaa` |
| `Descripción` | Description |
| `Importe` | Signed amount (integer or decimal number) |
| `Saldo` | Balance after the transaction |
| `Divisa` | Currency |

- Transactions come **from newest to oldest**; they are reversed and the balance adds up in that order.
- **Duplicates:** since there is no time, the fingerprint adds the balance after the transaction. This way two identical transactions on the same day are not merged, and a statement overlapping another only adds what is new.

**Automatic classification:**

- Outflows "Revolut\*\*NNNN\*" (the top-up of the joint account) → **contribution** by the account holder: an outflow that is neither an expense nor counted in the household totals. This rule is Bankinter-only.
- Outflows matching an outflow pattern saved for the holder → **contribution** by the holder.
- Transfers and Bizum: inflow → **income**; outflow → **expense**. In the personal account names are not used: a Bizum from the partner is income.

## Patterns per person

Contributions that do not carry the name are recognized with patterns saved per person (ADR-0015). They are managed from the server; write the pattern **in single quotes** so the shell does not touch `*` or spaces:

```bash
cd services/api
uv run openfinance member-patterns add raul@example.org '*1234'              # inflow in the joint account
uv run openfinance member-patterns add raul@example.org 'TRASPASO CASA' --outflow  # outflow from their Bankinter
uv run openfinance member-patterns list raul@example.org
uv run openfinance member-patterns remove raul@example.org '*1234'
```

- A pattern needs at least 3 letters or digits (`*1234` yes, `***` no) and at most 60 characters.
- `REVOLUT**` as an outflow pattern is already included in Bankinter personal accounts. In a personal account at another institution you have to save it if it means the same.

## Check a statement without saving it

```bash
cd services/api
uv run openfinance statement-check --bank revolut   ruta/al/extracto.xlsx
uv run openfinance statement-check --bank bankinter ruta/a/movimientos.xlsx
```

It only shows counts (rows, importable, discarded by reason, balance mismatches, proposed types, and contributions with or without a person). It does not show descriptions, amounts, account numbers or the file name, and it needs no database.


## Other banks (standard formats and CSV with profile)

Accounts without their own bank (cash, card, loan, investment, and those from a bank not listed above) import through the same preview. The format is recognized by its **content**, not by the file name:

| Format | What to know |
| --- | --- |
| **OFX** (versions 1 and 2) | Carries currency and an identifier for each transaction; if it carries the bank balance, it is checked. A file with several accounts is rejected. |
| **QIF** | Carries no currency (the account's is used) and no identifier. Dates are ambiguous: if all of them are valid as day/month and month/day, the file is rejected instead of guessing; ask for an OFX. |
| **CAMT.053** | The ISO 20022 XML that many European banks provide. It is read with `defusedxml` (no external entities). An entry with several transactions is imported as several rows. Pending items are discarded. |
| **CSV from any bank** | A **profile** is needed: in *Importar → Crear un perfil de CSV* (Import → Create a CSV profile) you choose a sample statement and indicate the date column, the description and the amount (or debit and credit), the date format and the decimal separator. It is tested before saving and reused. |

Real statements never go into the repository: tests use synthetic files (`services/api/tests/fixtures/synthetic*`).
