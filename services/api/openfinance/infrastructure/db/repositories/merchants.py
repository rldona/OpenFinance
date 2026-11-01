"""Repositorio de comercios con nombre propio (OF-1001)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.merchants import Merchant, MerchantId
from openfinance.domain.shared.ids import WorkspaceId
from openfinance.infrastructure.db.models import MerchantKeyRow, MerchantRow
from openfinance.infrastructure.db.repositories._common import _flush


class SqlMerchantRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _build(self, rows: list[MerchantRow]) -> list[Merchant]:
        if not rows:
            return []
        keys: dict[object, list[str]] = {}
        for k in self._s.scalars(
            select(MerchantKeyRow).where(MerchantKeyRow.merchant_id.in_([r.id for r in rows]))
        ):
            keys.setdefault(k.merchant_id, []).append(k.key)
        return [
            Merchant(
                MerchantId(r.id),
                WorkspaceId(r.household_id),
                r.name,
                tuple(sorted(keys.get(r.id, []))),
            )
            for r in rows
        ]

    def get(self, household_id: WorkspaceId, merchant_id: MerchantId) -> Merchant | None:
        row = self._s.scalar(
            select(MerchantRow).where(
                MerchantRow.id == merchant_id, MerchantRow.household_id == household_id
            )
        )
        return self._build([row])[0] if row else None

    def for_keys(self, household_id: WorkspaceId, keys: list[str]) -> dict[str, Merchant]:
        if not keys:
            return {}
        found: dict[str, Merchant] = {}
        for i in range(0, len(keys), 500):
            ids = {
                k.merchant_id
                for k in self._s.scalars(
                    select(MerchantKeyRow).where(
                        MerchantKeyRow.household_id == household_id,
                        MerchantKeyRow.key.in_(keys[i : i + 500]),
                    )
                )
            }
            if not ids:
                continue
            rows = list(self._s.scalars(select(MerchantRow).where(MerchantRow.id.in_(ids))))
            for merchant in self._build(rows):
                for key in merchant.keys:
                    found[key] = merchant
        return {k: found[k] for k in keys if k in found}

    def all(self, household_id: WorkspaceId) -> list[Merchant]:
        rows = list(
            self._s.scalars(
                select(MerchantRow)
                .where(MerchantRow.household_id == household_id)
                .order_by(MerchantRow.name)
            )
        )
        return self._build(rows)

    def add(self, merchant: Merchant) -> None:
        self._s.add(
            MerchantRow(id=merchant.id, household_id=merchant.household_id, name=merchant.name)
        )
        _flush(self._s)
        self.set_keys(merchant.household_id, merchant.id, list(merchant.keys))

    def set_name(self, household_id: WorkspaceId, merchant_id: MerchantId, name: str) -> None:
        row = self._s.scalar(
            select(MerchantRow).where(
                MerchantRow.id == merchant_id, MerchantRow.household_id == household_id
            )
        )
        if row is not None:
            row.name = name
            _flush(self._s)

    def set_keys(self, household_id: WorkspaceId, merchant_id: MerchantId, keys: list[str]) -> None:
        self._s.execute(
            delete(MerchantKeyRow).where(
                MerchantKeyRow.household_id == household_id,
                MerchantKeyRow.merchant_id == merchant_id,
            )
        )
        self._s.add_all(
            MerchantKeyRow(household_id=household_id, key=key, merchant_id=merchant_id)
            for key in dict.fromkeys(keys)
        )
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, merchant_id: MerchantId) -> None:
        # Sin depender de ON DELETE CASCADE (SQLite lo ignora sin PRAGMA): primero las variantes.
        self._s.execute(
            delete(MerchantKeyRow).where(
                MerchantKeyRow.household_id == household_id,
                MerchantKeyRow.merchant_id == merchant_id,
            )
        )
        self._s.execute(
            delete(MerchantRow).where(
                MerchantRow.id == merchant_id, MerchantRow.household_id == household_id
            )
        )
        _flush(self._s)
