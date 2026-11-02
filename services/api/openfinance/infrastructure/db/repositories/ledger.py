"""Repositorios de cuentas y movimientos."""

from __future__ import annotations

import calendar
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.orm import Session

from openfinance.application.ports import TransactionQuery
from openfinance.domain.categories import CategoryId
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    AccountType,
    Institution,
    Transaction,
    TransactionKind,
)
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import (
    AccountId,
    TransactionId,
    UserId,
    WorkspaceId,
)
from openfinance.domain.splits import SplitPart
from openfinance.domain.tags import tag_key
from openfinance.infrastructure.db.models import (
    AccountRow,
    TransactionLinkRow,
    TransactionRow,
    TransactionSplitRow,
    TransactionTagRow,
)
from openfinance.infrastructure.db.repositories._common import (
    _AMOUNT_QUANTUM,
    _flush,
)
from openfinance.infrastructure.db.repositories.splits import SqlSplitRepository

_KIND_ORDER = {AccountKind.JOINT: 0, AccountKind.SAVINGS: 1, AccountKind.PERSONAL: 2}


def _account(row: AccountRow) -> Account:
    currency = Currency(row.currency)
    return Account(
        id=AccountId(row.id),
        household_id=WorkspaceId(row.household_id),
        name=row.name,
        institution=Institution(row.institution),
        kind=AccountKind(row.kind),
        type=AccountType(row.type),
        currency=currency,
        opening_balance=Money.of(row.opening_balance, currency),
        owner_id=UserId(row.owner_id) if row.owner_id else None,
    )


class SqlAccountRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[Account]:
        rows = self._s.scalars(select(AccountRow).where(AccountRow.household_id == household_id))
        return sorted((_account(r) for r in rows), key=lambda a: (_KIND_ORDER[a.kind], a.name))

    def add(self, account: Account) -> None:
        self._s.add(
            AccountRow(
                id=account.id,
                household_id=account.household_id,
                name=account.name,
                institution=account.institution.value,
                kind=account.kind.value,
                type=account.type.value,
                currency=account.currency.code,
                opening_balance=account.opening_balance.amount,
                owner_id=account.owner_id,
            )
        )
        self._s.flush()


def _transaction(row: TransactionRow) -> Transaction:
    return Transaction(
        id=TransactionId(row.id),
        household_id=WorkspaceId(row.household_id),
        account_id=AccountId(row.account_id),
        booked_at=row.booked_at,
        value_date=row.value_date,
        description=row.description,
        amount=Money.of(row.amount, row.currency),
        kind=TransactionKind(row.kind),
        category_id=CategoryId(row.category_id) if row.category_id else None,
        merchant=row.merchant,
        member_id=UserId(row.member_id) if row.member_id else None,
        bank_type=row.bank_type,
        source=row.source,
        fingerprint=row.fingerprint,
        import_id=row.import_id,
        note=row.note,
        voided=row.voided,
    )


_ACTIVE = TransactionRow.voided.is_(False)
_NOT_SPLIT = TransactionRow.id.not_in(select(TransactionSplitRow.transaction_id))
"""Un movimiento dividido tiene su categoría en las partes, no en él (OF-1003)."""
"""Los movimientos anulados no cuentan en ninguna consulta (ADR-0017)."""


def _expand(t: Transaction, parts: list[SplitPart] | None) -> list[Transaction]:
    """Un movimiento dividido se cuenta como una parte por categoría (mismo id y concepto)."""
    if not parts:
        return [t]
    return [replace(t, amount=p.amount, category_id=p.category_id) for p in parts]


def _new_row(t: Transaction) -> TransactionRow:
    return TransactionRow(
        id=t.id,
        household_id=t.household_id,
        account_id=t.account_id,
        booked_at=t.booked_at,
        value_date=t.value_date,
        description=t.description,
        amount=t.amount.amount,
        currency=t.amount.currency.code,
        kind=t.kind.value,
        category_id=t.category_id,
        merchant=t.merchant,
        member_id=t.member_id,
        bank_type=t.bank_type,
        source=t.source,
        fingerprint=t.fingerprint,
        import_id=t.import_id,
        note=t.note,
        voided=t.voided,
    )


class SqlTransactionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _filtered(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> Select[TransactionRow]:
        stmt = select(TransactionRow).where(
            TransactionRow.household_id == household_id,
            TransactionRow.account_id.in_(account_ids),
            _ACTIVE,
        )
        if query.year is not None and query.month is not None:
            last_day = calendar.monthrange(query.year, query.month)[1]
            start = datetime(query.year, query.month, 1)  # noqa: DTZ001 - hora local del banco
            end = datetime(query.year, query.month, last_day, 23, 59, 59, 999999)  # noqa: DTZ001
            stmt = stmt.where(TransactionRow.booked_at.between(start, end))
        if query.text:
            stmt = stmt.where(
                TransactionRow.description.icontains(query.text.strip(), autoescape=True)
            )
        if query.category_id is not None:
            stmt = stmt.where(
                or_(
                    TransactionRow.category_id == query.category_id,
                    TransactionRow.id.in_(
                        select(TransactionSplitRow.transaction_id).where(
                            TransactionSplitRow.category_id == query.category_id
                        )
                    ),
                )
            )
        if query.tag:
            stmt = stmt.where(
                TransactionRow.id.in_(
                    select(TransactionTagRow.transaction_id).where(
                        TransactionTagRow.household_id == household_id,
                        TransactionTagRow.tag_key == tag_key(query.tag),
                    )
                )
            )
        if query.uncategorized:
            stmt = stmt.where(
                TransactionRow.kind == TransactionKind.EXPENSE.value,
                TransactionRow.category_id.is_(None),
                _NOT_SPLIT,
            )
        return stmt

    def search(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> list[Transaction]:
        stmt = self._filtered(household_id, account_ids, query)
        if query.after is not None:
            # Orden del listado: fecha descendente y, a igual fecha, identificador ascendente.
            at, last_id = query.after
            stmt = stmt.where(
                or_(
                    TransactionRow.booked_at < at,
                    and_(TransactionRow.booked_at == at, TransactionRow.id > last_id),
                )
            )
        stmt = stmt.order_by(TransactionRow.booked_at.desc(), TransactionRow.id).limit(query.limit)
        return [_transaction(r) for r in self._s.scalars(stmt)]

    def totals(
        self, household_id: WorkspaceId, account_ids: list[AccountId], query: TransactionQuery
    ) -> tuple[int, Decimal]:
        filtered = self._filtered(household_id, account_ids, query).subquery()
        count = 0
        total = Decimal(0)
        # Se suma en Python: SUM sobre decimales exactos no es fiable en todos los motores.
        for (amount,) in self._s.execute(select(filtered.c.amount)):
            count += 1
            total += amount
        return count, total

    def for_account(self, household_id: WorkspaceId, account_id: AccountId) -> list[Transaction]:
        rows = self._s.scalars(
            select(TransactionRow).where(
                TransactionRow.household_id == household_id,
                TransactionRow.account_id == account_id,
                _ACTIVE,
            )
        )
        return [_transaction(r) for r in rows]

    def balances(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> dict[AccountId, Decimal]:
        """Lo que suman los movimientos activos de cada cuenta, calculado en la base de datos
        (OF-905): sin cargar los movimientos. Una cuenta sin movimientos no aparece."""
        if not account_ids:
            return {}
        rows = self._s.execute(
            select(TransactionRow.account_id, func.sum(TransactionRow.amount))
            .where(
                TransactionRow.household_id == household_id,
                TransactionRow.account_id.in_(account_ids),
                _ACTIVE,
            )
            .group_by(TransactionRow.account_id)
        )
        # SQLite suma en coma flotante: se redondea a la escala de la columna (4 decimales).
        return {
            AccountId(account_id): Decimal(str(total or 0)).quantize(_AMOUNT_QUANTUM)
            for account_id, total in rows
        }

    def add(self, transaction: Transaction) -> None:
        self.add_many([transaction])

    def add_many(self, transactions: list[Transaction]) -> None:
        """Inserta varios movimientos con un solo flush (OF-905)."""
        if not transactions:
            return
        self._s.add_all([_new_row(t) for t in transactions])
        _flush(self._s)

    def get(
        self,
        household_id: WorkspaceId,
        transaction_id: TransactionId,
        *,
        include_voided: bool = False,
    ) -> Transaction | None:
        stmt = select(TransactionRow).where(
            TransactionRow.id == transaction_id, TransactionRow.household_id == household_id
        )
        if not include_voided:
            stmt = stmt.where(_ACTIVE)
        row = self._s.scalar(stmt)
        return _transaction(row) if row else None

    def save(self, transaction: Transaction) -> None:
        """Guarda los campos corregibles (ADR-0017); el resto del movimiento no cambia."""
        t = transaction
        self._s.execute(
            update(TransactionRow)
            .where(TransactionRow.id == t.id, TransactionRow.household_id == t.household_id)
            .values(
                kind=t.kind.value,
                member_id=t.member_id,
                category_id=t.category_id,
                note=t.note,
                voided=t.voided,
                import_id=t.import_id,
            )
        )
        _flush(self._s)

    def for_import(self, household_id: WorkspaceId, import_id: UUID) -> list[Transaction]:
        rows = self._s.scalars(
            select(TransactionRow)
            .where(
                TransactionRow.household_id == household_id,
                TransactionRow.import_id == import_id,
                _ACTIVE,
            )
            .order_by(TransactionRow.booked_at)
        )
        return [_transaction(r) for r in rows]

    def accounts_of(
        self, household_id: WorkspaceId, ids: list[TransactionId]
    ) -> dict[TransactionId, AccountId]:
        out: dict[TransactionId, AccountId] = {}
        for i in range(0, len(ids), 500):
            rows = self._s.execute(
                select(TransactionRow.id, TransactionRow.account_id).where(
                    TransactionRow.household_id == household_id,
                    TransactionRow.id.in_(ids[i : i + 500]),
                )
            )
            out.update({TransactionId(r.id): AccountId(r.account_id) for r in rows})
        return out

    def voided_with_fingerprints(
        self, household_id: WorkspaceId, account_id: AccountId, fingerprints: list[str]
    ) -> dict[str, Transaction]:
        """Movimientos anulados con esas huellas: se reactivan al volver a importar."""
        found: dict[str, Transaction] = {}
        for i in range(0, len(fingerprints), 500):
            rows = self._s.scalars(
                select(TransactionRow).where(
                    TransactionRow.household_id == household_id,
                    TransactionRow.account_id == account_id,
                    TransactionRow.fingerprint.in_(fingerprints[i : i + 500]),
                    TransactionRow.voided.is_(True),
                )
            )
            found.update({r.fingerprint: _transaction(r) for r in rows if r.fingerprint})
        return found

    def set_category(
        self, household_id: WorkspaceId, ids: list[TransactionId], category_id: CategoryId | None
    ) -> None:
        for i in range(0, len(ids), 500):
            self._s.execute(
                update(TransactionRow)
                .where(
                    TransactionRow.household_id == household_id,
                    TransactionRow.id.in_(ids[i : i + 500]),
                    TransactionRow.kind == TransactionKind.EXPENSE.value,
                    _ACTIVE,
                    _NOT_SPLIT,
                )
                .values(category_id=category_id)
            )
        _flush(self._s)

    def _uncategorized(self, household_id: WorkspaceId, account_ids: list[AccountId]):  # type: ignore[no-untyped-def]
        return (
            TransactionRow.household_id == household_id,
            TransactionRow.account_id.in_(account_ids),
            TransactionRow.kind == TransactionKind.EXPENSE.value,
            TransactionRow.category_id.is_(None),
            _ACTIVE,
            _NOT_SPLIT,
        )

    def transfer_candidates(
        self,
        household_id: WorkspaceId,
        account_ids: list[AccountId],
        transaction: Transaction,
        days: int,
    ) -> list[Transaction]:
        others = [a for a in account_ids if a != transaction.account_id]
        if not others:
            return []
        delta = timedelta(days=days)
        rows = self._s.scalars(
            select(TransactionRow)
            .where(
                TransactionRow.household_id == household_id,
                TransactionRow.account_id.in_(others),
                TransactionRow.amount == -transaction.amount.amount,
                TransactionRow.currency == transaction.amount.currency.code,
                TransactionRow.booked_at.between(
                    transaction.booked_at - delta, transaction.booked_at + delta
                ),
                TransactionRow.id.not_in(select(TransactionLinkRow.transaction_id)),
                _ACTIVE,
            )
            .order_by(TransactionRow.booked_at)
        )
        return [_transaction(r) for r in rows]

    def merchant_totals(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> list[tuple[str, int, Decimal]]:
        if not account_ids:
            return []
        rows = self._s.execute(
            select(TransactionRow.merchant, func.count(), func.sum(TransactionRow.amount))
            .where(
                TransactionRow.household_id == household_id,
                TransactionRow.account_id.in_(account_ids),
                TransactionRow.merchant != "",
                _ACTIVE,
            )
            .group_by(TransactionRow.merchant)
        )
        return [(m, int(n), Decimal(str(t or 0)).quantize(_AMOUNT_QUANTUM)) for m, n, t in rows]

    def uncategorized_with_merchant(
        self, household_id: WorkspaceId, account_ids: list[AccountId], key: str
    ) -> list[Transaction]:
        rows = self._s.scalars(
            select(TransactionRow).where(
                *self._uncategorized(household_id, account_ids),
                TransactionRow.merchant == key,
            )
        )
        return [_transaction(r) for r in rows]

    def uncategorized_with_merchant_word(
        self, household_id: WorkspaceId, account_ids: list[AccountId], first_word: str
    ) -> list[Transaction]:
        rows = self._s.scalars(
            select(TransactionRow).where(
                *self._uncategorized(household_id, account_ids),
                or_(
                    TransactionRow.merchant == first_word,
                    TransactionRow.merchant.startswith(f"{first_word} ", autoescape=True),
                ),
            )
        )
        return [_transaction(r) for r in rows]

    def in_range(
        self,
        household_id: WorkspaceId,
        account_ids: list[AccountId],
        start: datetime,
        end: datetime,
        *,
        only_category: bool = False,
        category_id: CategoryId | None = None,
    ) -> list[Transaction]:
        if not account_ids:
            return []
        stmt = select(TransactionRow).where(
            TransactionRow.household_id == household_id,
            TransactionRow.account_id.in_(account_ids),
            TransactionRow.booked_at.between(start, end),
            _ACTIVE,
        )
        txns = [_transaction(r) for r in self._s.scalars(stmt.order_by(TransactionRow.booked_at))]
        # Los informes cuentan las partes de un movimiento dividido, no el total (OF-1003).
        parts = SqlSplitRepository(self._s).for_transactions(household_id, [t.id for t in txns])
        if parts:
            txns = [p for t in txns for p in _expand(t, parts.get(t.id))]
        if only_category:
            txns = [t for t in txns if t.category_id == category_id]
        return txns

    def first_booked_at(
        self, household_id: WorkspaceId, account_ids: list[AccountId]
    ) -> datetime | None:
        if not account_ids:
            return None
        return self._s.scalar(
            select(func.min(TransactionRow.booked_at)).where(
                TransactionRow.household_id == household_id,
                TransactionRow.account_id.in_(account_ids),
                _ACTIVE,
            )
        )

    def count_uncategorized(self, household_id: WorkspaceId, account_ids: list[AccountId]) -> int:
        return int(
            self._s.scalar(
                select(func.count())
                .select_from(TransactionRow)
                .where(*self._uncategorized(household_id, account_ids))
            )
            or 0
        )

    def existing_fingerprints(
        self, household_id: WorkspaceId, account_id: AccountId, fingerprints: list[str]
    ) -> set[str]:
        found: set[str] = set()
        for i in range(0, len(fingerprints), 500):
            chunk = fingerprints[i : i + 500]
            found.update(
                f
                for f in self._s.scalars(
                    select(TransactionRow.fingerprint).where(
                        TransactionRow.household_id == household_id,
                        TransactionRow.account_id == account_id,
                        TransactionRow.fingerprint.in_(chunk),
                        _ACTIVE,
                    )
                )
                if f is not None
            )
        return found
