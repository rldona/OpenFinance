"""Repositorio de tipos de cambio manuales (OF-1008)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.rates import ExchangeRate
from openfinance.domain.shared import Currency
from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.infrastructure.db.models import ExchangeRateRow
from openfinance.infrastructure.db.repositories._common import _flush

_RATE_QUANTUM = Decimal("0.00000001")


def _rate(r: ExchangeRateRow) -> ExchangeRate:
    return ExchangeRate(
        WorkspaceId(r.household_id),
        Currency(r.currency),
        r.on_date,
        Decimal(str(r.rate)).quantize(_RATE_QUANTUM),
        r.source,
    )


class SqlRateRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def all(self, household_id: WorkspaceId) -> list[ExchangeRate]:
        rows = self._s.scalars(
            select(ExchangeRateRow)
            .where(ExchangeRateRow.household_id == household_id)
            .order_by(ExchangeRateRow.currency, ExchangeRateRow.on_date)
        )
        return [_rate(r) for r in rows]

    def get(self, household_id: WorkspaceId, currency: Currency, on: date) -> ExchangeRate | None:
        row = self._s.get(ExchangeRateRow, (household_id, currency.code, on))
        return _rate(row) if row else None

    def upsert(self, rate: ExchangeRate, created_by: UserId) -> None:
        row = self._s.get(ExchangeRateRow, (rate.household_id, rate.currency.code, rate.on))
        if row is None:
            self._s.add(
                ExchangeRateRow(
                    household_id=rate.household_id,
                    currency=rate.currency.code,
                    on_date=rate.on,
                    rate=rate.rate,
                    source=rate.source,
                    created_by=created_by,
                )
            )
        else:
            row.rate = rate.rate
            row.source = rate.source
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, currency: Currency, on: date) -> None:
        self._s.execute(
            delete(ExchangeRateRow).where(
                ExchangeRateRow.household_id == household_id,
                ExchangeRateRow.currency == currency.code,
                ExchangeRateRow.on_date == on,
            )
        )
        _flush(self._s)
