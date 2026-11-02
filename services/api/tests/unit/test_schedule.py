"""OF-1201: calendario de pagos programados y emparejado con lo cobrado."""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.schedule import (
    Frequency,
    OccurrenceStatus,
    ScheduledPayment,
    ScheduleError,
    ScheduleId,
    from_definition,
    match,
    occurrences,
    upcoming,
)
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import AccountId, TransactionId, WorkspaceId

HOUSEHOLD = WorkspaceId(uuid4())
ACCOUNT = AccountId(uuid4())


def payment(
    first: date,
    frequency: Frequency = Frequency.MONTHLY,
    amount: str = "-900.00",
    **extra: object,
) -> ScheduledPayment:
    return ScheduledPayment(
        id=ScheduleId(uuid4()),
        household_id=HOUSEHOLD,
        name="Alquiler",
        amount=Money.of(amount, "EUR"),
        account_id=ACCOUNT,
        frequency=frequency,
        first_due=first,
        **extra,  # type: ignore[arg-type]
    )


def txn(day: date, amount: str = "-900.00", account: AccountId = ACCOUNT) -> Transaction:
    value = Money.of(amount, "EUR")
    return Transaction(
        id=TransactionId(uuid4()),
        household_id=HOUSEHOLD,
        account_id=account,
        booked_at=datetime(day.year, day.month, day.day, 10),  # noqa: DTZ001
        value_date=day,
        description="PAGO",
        amount=value,
        kind=TransactionKind.EXPENSE if value.is_negative else TransactionKind.INCOME,
    )


class TestCalendar:
    def test_monthly_keeps_the_day(self) -> None:
        p = payment(date(2026, 1, 5))
        assert occurrences(p, date(2026, 1, 1), date(2026, 4, 30)) == [
            date(2026, 1, 5),
            date(2026, 2, 5),
            date(2026, 3, 5),
            date(2026, 4, 5),
        ]

    def test_short_months_clip_and_the_day_comes_back(self) -> None:
        p = payment(date(2026, 1, 31))
        assert occurrences(p, date(2026, 1, 1), date(2026, 4, 30)) == [
            date(2026, 1, 31),
            date(2026, 2, 28),
            date(2026, 3, 31),
            date(2026, 4, 30),
        ]

    def test_leap_february(self) -> None:
        p = payment(date(2027, 12, 31))
        assert date(2028, 2, 29) in occurrences(p, date(2028, 1, 1), date(2028, 3, 1))

    def test_every_n_months(self) -> None:
        p = payment(date(2026, 1, 10), interval=3)
        assert occurrences(p, date(2026, 1, 1), date(2026, 12, 31)) == [
            date(2026, 1, 10),
            date(2026, 4, 10),
            date(2026, 7, 10),
            date(2026, 10, 10),
        ]

    def test_weekly_and_biweekly(self) -> None:
        p = payment(date(2026, 1, 1), Frequency.WEEKLY, interval=2)
        assert occurrences(p, date(2026, 1, 1), date(2026, 2, 1)) == [
            date(2026, 1, 1),
            date(2026, 1, 15),
            date(2026, 1, 29),
        ]

    def test_yearly_and_leap_day(self) -> None:
        p = payment(date(2024, 2, 29), Frequency.YEARLY, "-380.00")
        assert occurrences(p, date(2024, 1, 1), date(2028, 12, 31)) == [
            date(2024, 2, 29),
            date(2025, 2, 28),
            date(2026, 2, 28),
            date(2027, 2, 28),
            date(2028, 2, 29),
        ]

    def test_once_appears_only_in_its_range(self) -> None:
        p = payment(date(2026, 3, 14), Frequency.ONCE)
        assert occurrences(p, date(2026, 3, 1), date(2026, 3, 31)) == [date(2026, 3, 14)]
        assert occurrences(p, date(2026, 3, 15), date(2026, 12, 31)) == []

    def test_the_end_date_is_inclusive_and_nothing_comes_after(self) -> None:
        p = payment(date(2026, 1, 5), ends_on=date(2026, 3, 5))
        assert occurrences(p, date(2026, 1, 1), date(2027, 1, 1))[-1] == date(2026, 3, 5)

    def test_nothing_before_the_first_date(self) -> None:
        p = payment(date(2026, 6, 1))
        assert occurrences(p, date(2026, 1, 1), date(2026, 5, 31)) == []

    @pytest.mark.parametrize("frequency", [Frequency.WEEKLY, Frequency.MONTHLY, Frequency.YEARLY])
    @pytest.mark.parametrize("interval", [1, 2, 5])
    def test_any_window_is_a_slice_of_the_whole_calendar(
        self, frequency: Frequency, interval: int
    ) -> None:
        p = payment(date(2025, 1, 31), frequency, interval=interval)
        whole = occurrences(p, date(2025, 1, 1), date(2033, 12, 31))
        for start, end in [
            (date(2026, 2, 1), date(2026, 8, 1)),
            (date(2029, 3, 15), date(2031, 1, 1)),
            (date(2025, 1, 31), date(2025, 1, 31)),
        ]:
            window = occurrences(p, start, end)
            assert window == [d for d in whole if start <= d <= end]
            assert window == sorted(set(window))

    def test_a_huge_range_is_capped(self) -> None:
        p = payment(date(2026, 1, 1), Frequency.WEEKLY)
        assert len(occurrences(p, date(2026, 1, 1), date(9000, 1, 1))) == 1000


class TestValidation:
    @pytest.mark.parametrize(
        "bad",
        [
            {"name": " "},
            {"name": "x" * 61},
            {"amount": "0.00"},
            {"interval": 0},
            {"interval": 61},
            {"frequency": Frequency.ONCE, "interval": 2},
            {"ends_on": date(2025, 12, 31)},
        ],
    )
    def test_rejects(self, bad: dict) -> None:
        base = {
            "id": ScheduleId(uuid4()),
            "household_id": HOUSEHOLD,
            "name": "Alquiler",
            "amount": Money.of("-1.00", "EUR"),
            "account_id": ACCOUNT,
            "frequency": Frequency.MONTHLY,
            "first_due": date(2026, 1, 1),
        }
        if "amount" in bad:
            bad = {"amount": Money.of(bad["amount"], "EUR")}
        with pytest.raises(ScheduleError):
            ScheduledPayment(**{**base, **bad})  # type: ignore[arg-type]

    def test_definition_round_trips(self) -> None:
        p = payment(date(2026, 1, 31), interval=2, ends_on=date(2027, 1, 31), variable=True)
        again = from_definition(p.id, HOUSEHOLD, p.definition())
        assert again == p


class TestMatching:
    def test_a_payment_on_the_day_fulfils_it(self) -> None:
        p = payment(date(2026, 3, 1))
        t = txn(date(2026, 3, 1))
        assert match(p, [date(2026, 3, 1)], [t]) == {date(2026, 3, 1): t.id}

    def test_a_week_either_side_but_not_more(self) -> None:
        p = payment(date(2026, 3, 10))
        assert match(p, [date(2026, 3, 10)], [txn(date(2026, 3, 17))])
        assert match(p, [date(2026, 3, 10)], [txn(date(2026, 3, 3))])
        assert not match(p, [date(2026, 3, 10)], [txn(date(2026, 3, 18))])

    def test_amount_tolerance_is_five_percent(self) -> None:
        p = payment(date(2026, 3, 1))
        assert match(p, [date(2026, 3, 1)], [txn(date(2026, 3, 1), "-945.00")])
        assert not match(p, [date(2026, 3, 1)], [txn(date(2026, 3, 1), "-946.00")])

    def test_variable_payments_take_any_amount_of_the_same_sign(self) -> None:
        p = payment(date(2026, 3, 1), amount="-60.00", variable=True)
        assert match(p, [date(2026, 3, 1)], [txn(date(2026, 3, 1), "-143.20")])
        assert not match(p, [date(2026, 3, 1)], [txn(date(2026, 3, 1), "143.20")])

    def test_other_account_voided_and_wrong_sign_never_match(self) -> None:
        p = payment(date(2026, 3, 1))
        other = txn(date(2026, 3, 1), account=AccountId(uuid4()))
        gone = txn(date(2026, 3, 1))
        object.__setattr__(gone, "voided", True)
        refund = txn(date(2026, 3, 1), "900.00")
        assert match(p, [date(2026, 3, 1)], [other, gone, refund]) == {}

    def test_one_charge_fulfils_one_date_and_the_closest_wins(self) -> None:
        p = payment(date(2026, 3, 1), Frequency.WEEKLY)
        dues = [date(2026, 3, 1), date(2026, 3, 8)]
        near_first = txn(date(2026, 3, 2))
        near_second = txn(date(2026, 3, 8))
        got = match(p, dues, [near_second, near_first])
        assert got == {dues[0]: near_first.id, dues[1]: near_second.id}
        assert len(match(p, dues, [near_first])) == 1

    def test_matching_is_stable_regardless_of_input_order(self) -> None:
        p = payment(date(2026, 3, 1))
        a, b = txn(date(2026, 3, 3)), txn(date(2026, 3, 3))
        first = match(p, [date(2026, 3, 1)], [a, b])
        second = match(p, [date(2026, 3, 1)], [b, a])
        assert first == second


class TestUpcoming:
    TODAY = date(2026, 3, 10)

    def test_states(self) -> None:
        p = payment(date(2026, 1, 5))
        paid = txn(date(2026, 2, 5))
        out = upcoming(p, [paid], self.TODAY, date(2026, 5, 31))
        assert [(o.due, o.status) for o in out] == [
            (date(2026, 2, 5), OccurrenceStatus.PAID),
            (date(2026, 3, 5), OccurrenceStatus.LATE),
            (date(2026, 4, 5), OccurrenceStatus.PENDING),
            (date(2026, 5, 5), OccurrenceStatus.PENDING),
        ]
        assert out[0].transaction_id == paid.id

    def test_today_is_pending_not_late(self) -> None:
        p = payment(date(2026, 3, 10))
        assert upcoming(p, [], self.TODAY, self.TODAY)[0].status is OccurrenceStatus.PENDING

    def test_old_unpaid_dates_are_not_reported(self) -> None:
        p = payment(date(2025, 1, 5))
        assert all(
            o.due >= self.TODAY - timedelta(days=45)
            for o in upcoming(p, [], self.TODAY, date(2026, 6, 1))
        )

    def test_an_inactive_payment_has_no_occurrences(self) -> None:
        assert (
            upcoming(payment(date(2026, 3, 12), active=False), [], self.TODAY, date(2027, 1, 1))
            == []
        )

    def test_computing_twice_gives_the_same(self) -> None:
        p = payment(date(2026, 1, 5))
        ts = [txn(date(2026, 2, 6))]
        assert upcoming(p, ts, self.TODAY, date(2026, 9, 1)) == upcoming(
            p, ts, self.TODAY, date(2026, 9, 1)
        )
