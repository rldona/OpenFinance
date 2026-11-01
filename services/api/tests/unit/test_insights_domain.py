from datetime import date, datetime
from uuid import uuid4

import pytest

from openfinance.domain.categories import CategoryId
from openfinance.domain.insights import (
    Month,
    average,
    contributions_out,
    daily_cumulative_spent,
    saving_rate,
    spending_by_category,
    top_merchants,
)
from openfinance.domain.ledger import Transaction, TransactionKind, summarize
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, TransactionId, UserId, WorkspaceId

EUR = Currency("EUR")
SUPER = CategoryId(uuid4())


def tx(day: int, amount: str, desc="X", kind=TransactionKind.EXPENSE, category=None, month=10):
    return Transaction(
        id=TransactionId(uuid4()),
        household_id=WorkspaceId(uuid4()),
        account_id=AccountId(uuid4()),
        booked_at=datetime(2026, month, day, 12),  # noqa: DTZ001
        value_date=date(2026, month, day),
        description=desc,
        amount=Money.of(amount, EUR),
        kind=kind,
        category_id=category,
        member_id=UserId(uuid4()) if kind is TransactionKind.CONTRIBUTION else None,
    )


class TestMonth:
    def test_parse_shift_and_bounds(self) -> None:
        m = Month.parse("2026-01")
        assert str(m.shift(-1)) == "2025-12"
        assert str(m.shift(13)) == "2027-02"
        assert Month(2028, 2).days == 29
        assert m.end.day == 31
        assert Month(2026, 10) > Month(2026, 9)

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            Month(2026, 13)


def test_spending_by_category_nets_refunds() -> None:
    out = spending_by_category(
        [tx(1, "-50.00", category=SUPER), tx(2, "10.00", category=SUPER), tx(3, "-5.00")], EUR
    )
    assert out == {SUPER: Money.of("40.00", EUR), None: Money.of("5.00", EUR)}


def test_contributions_out_only_counts_outgoing_contributions() -> None:
    c = TransactionKind.CONTRIBUTION
    out = contributions_out(
        [tx(1, "-800.00", kind=c), tx(2, "500.00", kind=c), tx(3, "-40.00")], EUR
    )
    assert out == Money.of("800.00", EUR)


def test_daily_cumulative_ignores_other_months_and_non_expenses() -> None:
    days = daily_cumulative_spent(
        [
            tx(2, "-10.00"),
            tx(2, "-5.00"),
            tx(5, "-300.00", kind=TransactionKind.SAVINGS_TRANSFER),
            tx(3, "-99.00", month=9),
        ],
        Month(2026, 10),
        EUR,
    )
    assert len(days) == 31
    assert [str(d.amount) for d in days[:3]] == ["0.00", "15.00", "15.00"]


def test_average_is_exact_to_the_cent() -> None:
    assert average([Money.of("10.00", EUR), Money.of("10.01", EUR)], EUR) == Money.of("10.00", EUR)
    assert average([Money.of("1.00", EUR)] * 3, EUR) == Money.of("1.00", EUR)
    assert average([], EUR) is None


def test_saving_rate() -> None:
    s = summarize([tx(1, "1000.00", kind=TransactionKind.CONTRIBUTION), tx(2, "-750.00")], EUR)
    assert saving_rate(s) == 25
    assert saving_rate(summarize([tx(2, "-1.00")], EUR)) is None


def test_top_merchants() -> None:
    ranked = top_merchants(
        [
            tx(1, "-10.00", "MERCADONA 1"),
            tx(2, "-20.00", "MERCADONA 2"),
            tx(3, "-5.00", "LIDL 1"),
            tx(4, "8.00", "ZARA"),
        ],
        EUR,
    )
    assert [(m.merchant, str(m.spent.amount), m.count) for m in ranked] == [
        ("MERCADONA", "30.00", 2),
        ("LIDL", "5.00", 1),
    ]
