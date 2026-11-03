"""OF-1503: definición y agregación de informes a medida."""

from datetime import datetime
from uuid import uuid4

import pytest

from openfinance.domain.insights import Month
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.reports import (
    GroupBy,
    Measure,
    ReportError,
    aggregate,
    from_dict,
    make_definition,
    to_dict,
)
from openfinance.domain.shared import Currency, Money

EUR = Currency("EUR")
ACCOUNT = uuid4()


def tx(amount, kind=TransactionKind.EXPENSE, month=10, desc="Mercadona", **extra):
    when = datetime(2026, month, 5, 12)  # noqa: DTZ001
    return Transaction(
        id=uuid4(),
        household_id=uuid4(),
        account_id=ACCOUNT,
        booked_at=when,
        value_date=when.date(),
        description=desc,
        amount=Money.of(amount, "EUR"),
        kind=kind,
        **extra,
    )


def spec(**kw):
    base = {"from_month": "2026-10", "to_month": "2026-10", "measure": "spent", "group_by": "month"}
    return make_definition(**{**base, **kw})


def test_a_refund_subtracts_from_spending():
    result = aggregate(spec(), [tx("-100.00"), tx("30.00")], EUR, {})
    assert result.total == Money.of("70.00", "EUR")
    assert result.count == 2


def test_voided_and_out_of_period_movements_do_not_count():
    result = aggregate(
        spec(), [tx("-10.00", voided=True), tx("-20.00", month=9), tx("-5.00")], EUR, {}
    )
    assert result.total == Money.of("5.00", "EUR")


def test_net_is_income_minus_spending_and_ignores_the_rest():
    txns = [
        tx("1000.00", TransactionKind.INCOME),
        tx("-200.00"),
        tx("-300.00", TransactionKind.SAVINGS_TRANSFER),
        tx("50.00", TransactionKind.INTERNAL_TRANSFER),
    ]
    assert aggregate(spec(measure="net"), txns, EUR, {}).total == Money.of("800.00", "EUR")
    assert aggregate(spec(measure="saved"), txns, EUR, {}).total == Money.of("300.00", "EUR")


def test_groups_sort_by_weight_and_months_by_date():
    txns = [tx("-10.00", desc="Cafe"), tx("-90.00", desc="Super"), tx("-10.00", month=9)]
    by_merchant = aggregate(spec(group_by="merchant", from_month="2026-09"), txns, EUR, {})
    ordered = [abs(r.amount.amount) for r in by_merchant.rows]
    assert ordered == sorted(ordered, reverse=True)
    by_month = aggregate(spec(from_month="2026-09"), txns, EUR, {})
    assert [r.key for r in by_month.rows] == ["2026-09", "2026-10"]


def test_row_cap_reports_what_is_hidden():
    txns = [tx("-1.00", desc=f"Comercio {i}", merchant=f"M{i:03d}") for i in range(130)]
    result = aggregate(spec(group_by="merchant"), txns, EUR, {})
    assert len(result.rows) == 100 and result.hidden_rows == 30
    assert result.total == Money.of("130.00", "EUR")  # el total no se recorta


def test_definition_round_trips():
    d = spec(
        group_by="category",
        account_ids=[uuid4()],
        category_ids=[uuid4()],
        uncategorized=True,
        tags=["#Viaje", "viaje", "Cena"],
        min_amount="12.50",
    )
    assert d.tags == ("Cena", "Viaje")
    assert from_dict(to_dict(d)) == d


@pytest.mark.parametrize(
    "kw",
    [
        {"from_month": "2026-10", "to_month": "2026-09"},
        {"from_month": "2023-01", "to_month": "2026-01"},
        {"measure": "x"},
        {"group_by": "x"},
        {"min_amount": "-0.01"},
        {"min_amount": "NaN"},
        {"tags": [""]},
        {"tags": ["a|b"]},
        {"account_ids": [uuid4() for _ in range(51)]},
    ],
)
def test_invalid_definitions(kw):
    with pytest.raises(ReportError):
        spec(**kw)


def test_exactly_36_months_is_allowed():
    d = spec(from_month="2024-01", to_month="2026-12")
    assert d.from_month == Month(2024, 1) and d.group_by is GroupBy.MONTH
    assert d.measure is Measure.SPENT
