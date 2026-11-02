"""OF-1205: «hoy podéis gastar»."""

from datetime import date
from uuid import uuid4

from openfinance.domain.allowance import Horizon, allowance, month_end
from openfinance.domain.schedule import Occurrence, OccurrenceStatus, ScheduleId
from openfinance.domain.shared import Money

TODAY = date(2026, 11, 10)


def eur(amount: str) -> Money:
    return Money.of(amount, "EUR")


def occ(day: date, amount: str, status: OccurrenceStatus = OccurrenceStatus.PENDING) -> Occurrence:
    return Occurrence(ScheduleId(uuid4()), day, eur(amount), status)


class TestHorizon:
    def test_without_income_it_runs_to_the_end_of_the_month(self) -> None:
        a = allowance(eur("600.00"), [], TODAY)
        assert (a.horizon, a.until, a.days) == (Horizon.MONTH_END, date(2026, 11, 30), 21)
        assert a.next_income is None

    def test_the_next_income_sets_the_horizon(self) -> None:
        income = occ(date(2026, 11, 28), "1600.00")
        a = allowance(eur("600.00"), [income], TODAY)
        assert (a.horizon, a.until, a.days) == (Horizon.INCOME, date(2026, 11, 28), 18)
        assert a.next_income == income

    def test_an_income_after_the_month_end_still_counts(self) -> None:
        a = allowance(eur("600.00"), [occ(date(2026, 12, 1), "1600.00")], TODAY)
        assert (a.horizon, a.days) == (Horizon.INCOME, 21)

    def test_an_income_today_does_not_end_the_period(self) -> None:
        a = allowance(eur("600.00"), [occ(TODAY, "1600.00")], TODAY)
        assert a.horizon is Horizon.MONTH_END

    def test_the_closest_income_wins(self) -> None:
        a = allowance(
            eur("600.00"),
            [occ(date(2026, 11, 28), "1600.00"), occ(date(2026, 11, 15), "50.00")],
            TODAY,
        )
        assert a.until == date(2026, 11, 15)


class TestAmounts:
    def test_pending_payments_are_taken_out_before_dividing(self) -> None:
        a = allowance(eur("1000.00"), [occ(date(2026, 11, 20), "-379.00")], TODAY)
        assert a.committed == eur("379.00") and a.available == eur("621.00")
        assert a.per_day == eur("29.57")  # 621 / 21 = 29,5714…, hacia abajo

    def test_rounds_down_to_the_cent_never_up(self) -> None:
        a = allowance(eur("100.00"), [], date(2026, 11, 28))  # 3 días
        assert a.per_day == eur("33.33")

    def test_payments_after_the_horizon_are_not_taken_out(self) -> None:
        a = allowance(
            eur("1000.00"),
            [occ(date(2026, 11, 28), "1600.00"), occ(date(2026, 12, 3), "-900.00")],
            TODAY,
        )
        assert a.committed == eur("0.00")

    def test_a_payment_on_the_income_day_is_covered_by_that_income(self) -> None:
        a = allowance(
            eur("1000.00"),
            [occ(date(2026, 11, 28), "1600.00"), occ(date(2026, 11, 28), "-900.00")],
            TODAY,
        )
        assert a.committed == eur("0.00")

    def test_a_payment_today_counts(self) -> None:
        a = allowance(eur("1000.00"), [occ(TODAY, "-100.00")], TODAY)
        assert a.committed == eur("100.00")

    def test_late_and_paid_payments_never_count(self) -> None:
        a = allowance(
            eur("1000.00"),
            [
                occ(date(2026, 11, 5), "-100.00", OccurrenceStatus.LATE),
                occ(date(2026, 11, 12), "-100.00", OccurrenceStatus.PAID),
            ],
            TODAY,
        )
        assert a.committed == eur("0.00")

    def test_not_enough_money_gives_zero_a_day_and_says_it_is_short(self) -> None:
        a = allowance(eur("100.00"), [occ(date(2026, 11, 20), "-500.00")], TODAY)
        assert a.available == eur("-400.00") and a.per_day == eur("0.00") and a.short

    def test_a_negative_balance_gives_zero(self) -> None:
        a = allowance(eur("-5.00"), [], TODAY)
        assert a.per_day == eur("0.00") and a.short

    def test_exactly_zero_available_is_not_short(self) -> None:
        a = allowance(eur("100.00"), [occ(date(2026, 11, 20), "-100.00")], TODAY)
        assert a.available == eur("0.00") and not a.short and a.per_day == eur("0.00")

    def test_the_last_day_of_the_month_is_one_day(self) -> None:
        a = allowance(eur("90.00"), [], date(2026, 11, 30))
        assert (a.days, a.per_day) == (1, eur("90.00"))

    def test_the_same_inputs_give_the_same_answer(self) -> None:
        items = [occ(date(2026, 11, 20), "-379.00"), occ(date(2026, 11, 28), "1600.00")]
        assert allowance(eur("1000"), items, TODAY) == allowance(eur("1000"), items[::-1], TODAY)


def test_month_end() -> None:
    assert month_end(date(2028, 2, 3)) == date(2028, 2, 29)
    assert month_end(date(2026, 12, 31)) == date(2026, 12, 31)
