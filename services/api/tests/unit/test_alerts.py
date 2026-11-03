"""OF-1301: los detectores de avisos, uno a uno."""

from datetime import date, datetime, timedelta
from uuid import uuid4

from openfinance.domain.alerts import (
    AlertKind,
    Severity,
    duplicates,
    fees,
    price_rises,
    sort_alerts,
)
from openfinance.domain.insights import Month
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.savings import PriceChange, RecurringCharge
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId, WorkspaceId

HOUSEHOLD = WorkspaceId(uuid4())
ACCOUNT = AccountId(uuid4())
TODAY = date(2026, 11, 3)


def txn(
    days_ago: int,
    amount: str = "-10.00",
    description: str = "Cine",
    *,
    account: AccountId = ACCOUNT,
    kind: TransactionKind = TransactionKind.EXPENSE,
    bank_type: str = "",
    voided: bool = False,
) -> Transaction:
    when = datetime.combine(TODAY - timedelta(days=days_ago), datetime.min.time())
    return Transaction(
        id=TransactionId(uuid4()),
        household_id=HOUSEHOLD,
        account_id=account,
        booked_at=when,
        value_date=when.date(),
        description=description,
        amount=Money.of(amount, "EUR"),
        kind=kind,
        bank_type=bank_type,
        voided=voided,
    )


class TestDuplicates:
    def test_two_equal_charges_two_days_apart(self) -> None:
        found = duplicates([txn(2), txn(0)], TODAY)
        assert [a.kind for a in found] == [AlertKind.DUPLICATE]
        assert found[0].on == TODAY

    def test_three_in_a_row_warn_twice_against_the_previous_one(self) -> None:
        assert len(duplicates([txn(2), txn(1), txn(0)], TODAY)) == 2

    def test_three_days_apart_is_not_a_duplicate(self) -> None:
        assert duplicates([txn(3), txn(0)], TODAY) == []

    def test_other_account_amount_merchant_or_sign_do_not_count(self) -> None:
        other = AccountId(uuid4())
        items = [
            txn(1),
            txn(0, account=other),
            txn(0, amount="-10.01"),
            txn(0, description="Teatro"),
            txn(0, amount="10.00"),
        ]
        assert duplicates(items, TODAY) == []

    def test_voided_and_non_expenses_are_ignored(self) -> None:
        items = [txn(1), txn(0, voided=True), txn(0, kind=TransactionKind.INTERNAL_TRANSFER)]
        assert duplicates(items, TODAY) == []

    def test_old_ones_are_not_news(self) -> None:
        assert duplicates([txn(40), txn(39)], TODAY) == []

    def test_the_key_is_stable_between_runs(self) -> None:
        items = [txn(1), txn(0)]
        assert [a.key for a in duplicates(items, TODAY)] == [
            a.key for a in duplicates(items, TODAY)
        ]


class TestFees:
    def test_by_description_or_bank_type(self) -> None:
        found = fees(
            [txn(1, "-2.00", "Comisión mantenimiento"), txn(2, "-1.00", "Cargo", bank_type="FEE")],
            TODAY,
        )
        assert [a.severity for a in found] == [Severity.INFO, Severity.INFO]

    def test_normal_expenses_and_old_fees_do_not_warn(self) -> None:
        assert fees([txn(1, "-5.00", "Mercadona"), txn(31, "-2.00", "Comisión")], TODAY) == []

    def test_a_refunded_fee_is_not_a_fee(self) -> None:
        assert fees([txn(1, "2.00", "Devolución comisión")], TODAY) == []


def recurring(before: str, after: str, month: Month) -> RecurringCharge:
    eur = lambda v: Money.of(v, "EUR")  # noqa: E731
    return RecurringCharge(
        "Netflix",
        None,
        eur(after),
        eur(before),
        TODAY,
        6,
        [PriceChange(month, eur(before), eur(after))],
    )


class TestPriceRises:
    def test_a_rise_this_month_or_the_last_warns(self) -> None:
        found = price_rises(
            [
                recurring("10.00", "12.00", Month(2026, 11)),
                recurring("10.00", "11.00", Month(2026, 10)),
            ],
            TODAY,
        )
        assert [a.title for a in found] == [
            "Netflix ha subido un 20 %",
            "Netflix ha subido un 10 %",
        ]
        assert found[0].amount == Money.of("2.00", "EUR")

    def test_small_old_or_downward_changes_do_not(self) -> None:
        assert price_rises([recurring("10.00", "10.40", Month(2026, 11))], TODAY) == []
        assert price_rises([recurring("10.00", "15.00", Month(2026, 8))], TODAY) == []
        assert price_rises([recurring("15.00", "10.00", Month(2026, 11))], TODAY) == []

    def test_the_key_names_the_month_so_a_new_rise_warns_again(self) -> None:
        a = price_rises([recurring("10.00", "12.00", Month(2026, 10))], TODAY)[0]
        b = price_rises([recurring("12.00", "15.00", Month(2026, 11))], TODAY)[0]
        assert a.key != b.key


def test_most_serious_first_then_most_recent() -> None:
    fee = fees([txn(1, "-2.00", "Comisión")], TODAY)[0]
    dup = duplicates([txn(2), txn(0)], TODAY)[0]
    rise = price_rises([recurring("10.00", "12.00", Month(2026, 11))], TODAY)[0]
    assert sort_alerts([fee, dup, rise]) == [
        rise if rise.on > dup.on else dup,
        dup if rise.on > dup.on else rise,
        fee,
    ]
