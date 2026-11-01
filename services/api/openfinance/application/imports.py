"""Importación de extractos con vista previa y confirmación idempotente (OF-105)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from openfinance.application.categories import rules_for_account
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import StatementParsers, UnitOfWork
from openfinance.domain.categories import CategoryId, best_rule, merchant_key
from openfinance.domain.identity import User
from openfinance.domain.imports import (
    BalanceMismatch,
    ClassificationRules,
    ImportedRow,
    MemberPattern,
    ParseResult,
    PatternDirection,
    SkippedRow,
)
from openfinance.domain.imports.batch import (
    MAX_FILE_BYTES,
    ImportBatch,
    ImportStatus,
    safe_filename,
)
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    Institution,
    Transaction,
    TransactionKind,
    account_balance,
)
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId, UserId
from openfinance.domain.shared.text import normalize_text
from openfinance.domain.workspaces import Actor

# Pendiente de validar con extractos reales (docs/product/bancos.md).
DEFAULT_SAVINGS_PATTERNS = ("To pocket",)
DEFAULT_OUTFLOW_CONTRIBUTION_PATTERNS = ("REVOLUT**",)
"""Salidas de una cuenta personal de Bankinter hacia Revolut: la recarga de la conjunta
(ADR-0015). En otras entidades ese texto no tiene por qué significar lo mismo."""
MAX_SOURCE = 200
_MIN_PATTERN = 3


@dataclass(frozen=True, slots=True)
class PreviewRow:
    row: ImportedRow
    duplicate: bool
    member_id: UserId | None
    category_id: CategoryId | None = None
    """Categoría propuesta por una regla aprendida."""


@dataclass(frozen=True, slots=True)
class ImportPreview:
    batch: ImportBatch
    account: Account
    rows: list[PreviewRow]
    skipped: list[SkippedRow]
    balance_mismatches: list[BalanceMismatch]
    bank_balance: Money | None
    """Saldo que informa el banco tras la última fila del extracto."""
    balance_after_import: Money
    """Saldo que tendrá la cuenta en OpenFinance si se confirma."""

    @property
    def new_count(self) -> int:
        return sum(1 for r in self.rows if not r.duplicate)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for r in self.rows if r.duplicate)


@dataclass(frozen=True, slots=True)
class ImportResult:
    batch: ImportBatch
    created: int = field(default=0)
    duplicates: int = field(default=0)
    skipped: int = field(default=0)


def classification_rules(
    account: Account, members: list[User], patterns: list[MemberPattern]
) -> ClassificationRules:
    """Cómo reconocer aportaciones en los conceptos de esta cuenta (ADR-0015).

    En la conjunta (y las huchas), las entradas con el nombre de una persona o uno de sus
    patrones de entrada son su aportación. En una cuenta personal solo cuentan como
    aportación las salidas del titular que coinciden con sus patrones de salida (y, en
    Bankinter, ``REVOLUT**``): un Bizum de la pareja ahí es un ingreso, no una aportación.
    """
    member_ids = {m.id for m in members}
    known = [p for p in patterns if p.user_id in member_ids]
    if account.kind is AccountKind.PERSONAL:
        owner = account.owner_id
        defaults = (
            DEFAULT_OUTFLOW_CONTRIBUTION_PATTERNS
            if account.institution is Institution.BANKINTER
            else ()
        )
        outflow = [
            p.pattern
            for p in known
            if p.direction is PatternDirection.OUTFLOW and p.user_id == owner
        ]
        return ClassificationRules(
            savings_patterns=DEFAULT_SAVINGS_PATTERNS,
            outflow_member_patterns={str(owner): [*defaults, *outflow]},
        )
    inflow: dict[str, list[str]] = {}
    for m in members:
        name = normalize_text(m.display_name)
        candidates = [
            p for p in dict.fromkeys((name, name.split(" ")[0])) if len(p) >= _MIN_PATTERN
        ]
        candidates += [
            p.pattern for p in known if p.direction is PatternDirection.INFLOW and p.user_id == m.id
        ]
        inflow[str(m.id)] = candidates
    return ClassificationRules(member_patterns=inflow, savings_patterns=DEFAULT_SAVINGS_PATTERNS)


def _account(uow: UnitOfWork, actor: Actor, account_id: UUID) -> Account:
    account = next((a for a in visible_accounts(uow, actor) if a.id == account_id), None)
    if account is None:
        raise NotFoundError("Cuenta no encontrada")
    return account


def _parse(
    uow: UnitOfWork, parsers: StatementParsers, actor: Actor, account: Account, content: bytes
) -> ParseResult:
    parser = parsers.get(account.institution)
    if parser is None:
        raise InvalidRequestError(
            f"Todavía no se pueden importar extractos de {account.institution.value}"
        )
    rules = classification_rules(
        account,
        uow.households.members(actor.household_id),
        uow.member_patterns.for_household(actor.household_id),
    )
    try:
        result = parser(content, str(account.id), rules)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    valid: list[ImportedRow] = []
    for row in result.rows:
        if row.amount.currency != account.currency:
            result.skipped.append(
                SkippedRow(
                    row.line, f"moneda {row.amount.currency} distinta de la cuenta", row.description
                )
            )
        else:
            valid.append(row)
    result.rows = valid
    result.skipped.sort(key=lambda s: s.line)
    return result


def _preview_rows(
    uow: UnitOfWork, actor: Actor, account: Account, result: ParseResult
) -> list[PreviewRow]:
    existing = uow.transactions.existing_fingerprints(
        actor.household_id, account.id, [r.fingerprint for r in result.rows]
    )
    rules = rules_for_account(uow, account)
    hidden = {c.id for c in uow.categories.for_household(actor.household_id) if c.hidden}
    rows = []
    for r in result.rows:
        category = None
        if r.suggested_kind is TransactionKind.EXPENSE:
            rule = best_rule(rules, merchant_key(r.description))
            if rule is not None and rule.category_id not in hidden:
                category = rule.category_id
        member = UserId(UUID(r.member)) if r.member else None
        rows.append(PreviewRow(r, r.fingerprint in existing, member, category))
    return rows


def _build_preview(
    uow: UnitOfWork, actor: Actor, account: Account, batch: ImportBatch, result: ParseResult
) -> ImportPreview:
    rows = _preview_rows(uow, actor, account, result)
    current = account_balance(account, uow.transactions.for_account(actor.household_id, account.id))
    after = current
    for r in rows:
        if not r.duplicate:
            after = after + r.row.amount
    return ImportPreview(
        batch,
        account,
        rows,
        result.skipped,
        result.balance_mismatches,
        result.closing_balance,
        after,
    )


def preview_import(
    uow: UnitOfWork,
    parsers: StatementParsers,
    actor: Actor,
    account_id: UUID,
    filename: str,
    content: bytes,
    now: datetime,
) -> ImportPreview:
    if not content:
        raise InvalidRequestError("El archivo está vacío")
    if len(content) > MAX_FILE_BYTES:
        raise InvalidRequestError("El archivo es demasiado grande (máximo 5 MB)")
    account = _account(uow, actor, account_id)
    result = _parse(uow, parsers, actor, account, content)
    batch = ImportBatch(
        id=uuid4(),
        household_id=actor.household_id,
        account_id=account.id,
        filename=safe_filename(filename),
        created_by=actor.user_id,
        created_at=now,
    )
    uow.imports.purge_expired_content(now)
    uow.imports.add(batch, content)
    uow.commit()
    return _build_preview(uow, actor, account, batch, result)


def commit_import(
    uow: UnitOfWork, parsers: StatementParsers, actor: Actor, batch_id: UUID, now: datetime
) -> ImportResult:
    batch = uow.imports.get(actor.household_id, batch_id)
    if batch is None:
        raise NotFoundError("Importación no encontrada")
    account = _account(uow, actor, batch.account_id)
    if batch.status is ImportStatus.COMMITTED:
        return ImportResult(batch, batch.created_count, batch.duplicate_count, batch.skipped_count)
    if batch.is_expired(now):
        raise ConflictError("La vista previa ha caducado; vuelve a subir el archivo")
    content = uow.imports.content(batch.id)
    if content is None:
        raise ConflictError("El archivo de esta importación ya no está disponible")

    # Reclamar el lote de forma atómica: si otra petición ya lo está confirmando, gana ella.
    if not uow.imports.claim(batch.id):
        uow.commit()
        claimed = uow.imports.get(actor.household_id, batch.id)
        if claimed is None or claimed.status is not ImportStatus.COMMITTED:
            raise ConflictError("Esta importación se está guardando; vuelve a intentarlo")
        return ImportResult(
            claimed, claimed.created_count, claimed.duplicate_count, claimed.skipped_count
        )

    # Se vuelve a leer el archivo con las reglas actuales; el resultado coincide con la vista
    # previa salvo que entre medias cambien los miembros del hogar o sus patrones.
    result = _parse(uow, parsers, actor, account, content)
    rows = _preview_rows(uow, actor, account, result)
    created = 0
    for r in rows:
        if r.duplicate:
            continue
        row = r.row
        kind = row.suggested_kind
        member = r.member_id
        if kind is TransactionKind.CONTRIBUTION and member is None:
            kind = TransactionKind.INCOME
        uow.transactions.add(
            Transaction(
                id=TransactionId(uuid4()),
                household_id=actor.household_id,
                account_id=account.id,
                booked_at=row.booked_at,
                value_date=row.value_date,
                description=row.description,
                amount=row.amount,
                kind=kind,
                member_id=member if kind is TransactionKind.CONTRIBUTION else None,
                category_id=r.category_id if kind is TransactionKind.EXPENSE else None,
                bank_type=row.bank_type,
                source=f"import:{batch.filename}"[:MAX_SOURCE],
                fingerprint=row.fingerprint,
                import_id=batch.id,
            )
        )
        created += 1
    done = batch.committed(now, created, len(rows) - created, len(result.skipped))
    uow.imports.save_committed(done)
    uow.commit()
    return ImportResult(done, done.created_count, done.duplicate_count, done.skipped_count)
