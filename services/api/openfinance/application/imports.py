"""Importación de extractos con vista previa y confirmación idempotente (OF-105)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID, uuid4

from openfinance.application.categories import rules_for_account
from openfinance.application.changes import record
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.member_patterns import members_without_recharge
from openfinance.application.ports import StatementParsers, UnitOfWork
from openfinance.domain.categories import CategoryId, best_rule, merchant_key
from openfinance.domain.changes import Change, Entity
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
    LedgerError,
    Transaction,
    TransactionKind,
    account_balance,
)
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId, UserId
from openfinance.domain.shared.text import normalize_text
from openfinance.domain.workspaces import Actor

# Pendiente de validar con extractos reales (docs/product/bancos.md).
DEFAULT_SAVINGS_PATTERNS = ("To pocket", "From pocket")
"""Revolut: meter en la hucha (importe negativo) y sacar de ella (positivo, no es ingreso)."""
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
    members_without_recharge: list[UserId] = field(default_factory=list)
    """En la conjunta de Revolut: quién no tiene guardada su tarjeta de recarga (OF-704).
    Sus «Recarga de *NNNN» entrarían como ingreso y no como su aportación."""

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
        members_without_recharge(uow, actor.household_id)
        if account.kind is not AccountKind.PERSONAL and account.institution is Institution.REVOLUT
        else [],
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
    # Lo de una importación deshecha vuelve con su identificador y sus correcciones en lugar
    # de duplicarse (ADR-0017): deshacer y volver a importar da el mismo resultado.
    voided = uow.transactions.voided_with_fingerprints(
        actor.household_id, account.id, [r.row.fingerprint for r in rows if not r.duplicate]
    )
    created = 0
    for r in rows:
        if r.duplicate:
            continue
        row = r.row
        previous = voided.get(row.fingerprint)
        if previous is not None:
            uow.transactions.save(replace(previous, voided=False, import_id=batch.id))
            created += 1
            continue
        kind = row.suggested_kind
        member = r.member_id
        if kind is TransactionKind.CONTRIBUTION and member is None:
            kind = TransactionKind.INCOME
        try:
            transaction = Transaction(
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
        except LedgerError as exc:
            # Los lectores ya descartan lo que el dominio no admite; si algo se escapa, la
            # importación entera se deshace (no se guarda nada) en vez de dar un error 500.
            raise InvalidRequestError(
                f"La fila {row.line} del extracto no se puede guardar: {exc}"
            ) from exc
        uow.transactions.add(transaction)
        created += 1
    done = batch.committed(now, created, len(rows) - created, len(result.skipped))
    uow.imports.save_committed(done)
    uow.commit()
    return ImportResult(done, done.created_count, done.duplicate_count, done.skipped_count)


@dataclass(frozen=True, slots=True)
class ImportView:
    batch: ImportBatch
    can_undo: bool
    """Solo la última importación confirmada de cada cuenta se puede deshacer."""


def list_imports(uow: UnitOfWork, actor: Actor) -> list[ImportView]:
    """Importaciones confirmadas o deshechas de las cuentas que ve quien pregunta."""
    batches = uow.imports.committed(
        actor.household_id, [a.id for a in visible_accounts(uow, actor)]
    )
    latest: dict[AccountId, UUID] = {}
    for b in batches:
        if b.status is ImportStatus.COMMITTED:
            latest.setdefault(b.account_id, b.id)
    return [ImportView(b, latest.get(b.account_id) == b.id) for b in batches]


@dataclass(frozen=True, slots=True)
class UndoImportResult:
    voided: int
    operation_id: UUID | None


def undo_import(uow: UnitOfWork, actor: Actor, import_id: UUID, now: datetime) -> UndoImportResult:
    """Anula los movimientos de la última importación de una cuenta (ADR-0017).

    No se borra nada: quedan anulados y en el registro, con sus correcciones, y deshacer esta
    operación los recupera. Volver a importar el mismo archivo también los recupera.
    """
    batch = uow.imports.get(actor.household_id, import_id)
    account_ids = {a.id for a in visible_accounts(uow, actor)}
    if batch is None or batch.account_id not in account_ids:
        raise NotFoundError("Importación no encontrada")
    if batch.status is not ImportStatus.COMMITTED:
        raise ConflictError("Esta importación no está confirmada o ya está deshecha")
    newest = next(
        (
            b
            for b in uow.imports.committed(actor.household_id, [batch.account_id])
            if b.status is ImportStatus.COMMITTED
        ),
        None,
    )
    if newest is None or newest.id != batch.id:
        raise InvalidRequestError(
            "Solo se puede deshacer la última importación de esta cuenta: "
            "deshaz antes las posteriores"
        )
    changes: list[Change] = []
    for t in uow.transactions.for_import(actor.household_id, batch.id):
        uow.transactions.save(replace(t, voided=True))
        changes.append(Change(Entity.TRANSACTION, str(t.id), "voided", False, True))
    uow.imports.set_status(batch.id, ImportStatus.UNDONE)
    changes.append(
        Change(
            Entity.IMPORT,
            str(batch.id),
            "status",
            ImportStatus.COMMITTED.value,
            ImportStatus.UNDONE.value,
        )
    )
    count = len(changes) - 1
    summary = f"Importación deshecha: {batch.filename} ({count} movimientos)"
    operation = record(uow, actor, "import.undo", summary, changes, now)
    uow.commit()
    return UndoImportResult(count, operation.id if operation else None)


def purge_expired_imports(uow: UnitOfWork, now: datetime) -> int:
    """Borra el archivo de las vistas previas caducadas. Devuelve cuántas había (OF-607).

    También ocurre en cada vista previa y en cada inicio de sesión; esto lo usan el
    arranque de la API y ``make backup``, para que la copia no se lleve extractos viejos.
    """
    purged = uow.imports.purge_expired_content(now)
    uow.commit()
    return purged
