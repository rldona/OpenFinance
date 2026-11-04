"""OF-1202: previsión de saldo a partir de ocurrencias pendientes."""

from datetime import date
from uuid import uuid4

from openfinance.domain.forecast import combine, forecast
from openfinance.domain.schedule import Occurrence, OccurrenceStatus, ScheduleId
from openfinance.domain.shared import Money

TODAY = date(2026, 11, 2)
END = date(2026, 12, 31)


def eur(amount: str) -> Money:
    return Money.of(amount, "EUR")


def occ(day: date, amount: str, status: OccurrenceStatus = OccurrenceStatus.PENDING) -> Occurrence:
    return Occurrence(ScheduleId(uuid4()), day, eur(amount), status)


class TestForecast:
    def test_no_payments_keeps_the_balance(self) -> None:
        f = forecast(eur("100.00"), [], TODAY, END)
        assert [(p.day, str(p.balance.amount)) for p in f.points] == [(TODAY, "100.00")]
        assert f.first_negative is None and f.end == eur("100.00")

    def test_pending_payments_move_the_balance_day_by_day(self) -> None:
        f = forecast(
            eur("1000.00"),
            [occ(date(2026, 11, 5), "-900.00"), occ(date(2026, 11, 28), "1600.00")],
            TODAY,
            END,
        )
        assert [(p.day, str(p.balance.amount)) for p in f.points] == [
            (TODAY, "1000.00"),
            (date(2026, 11, 5), "100.00"),
            (date(2026, 11, 28), "1700.00"),
        ]
        assert f.lowest.day == date(2026, 11, 5) and f.lowest.balance == eur("100.00")
        assert f.first_negative is None

    def test_same_day_payments_add_up(self) -> None:
        f = forecast(
            eur("50.00"),
            [occ(date(2026, 11, 3), "-30.00"), occ(date(2026, 11, 3), "-40.00")],
            TODAY,
            END,
        )
        assert [str(p.balance.amount) for p in f.points] == ["50.00", "-20.00"]

    def test_first_negative_day_and_lowest(self) -> None:
        f = forecast(
            eur("100.00"),
            [
                occ(date(2026, 11, 3), "-80.00"),
                occ(date(2026, 11, 10), "-80.00"),
                occ(date(2026, 11, 20), "-5.00"),
            ],
            TODAY,
            END,
        )
        assert f.first_negative == date(2026, 11, 10)
        assert f.lowest.day == date(2026, 11, 20) and f.lowest.balance == eur("-65.00")

    def test_a_payment_today_counts_in_todays_point(self) -> None:
        f = forecast(eur("100.00"), [occ(TODAY, "-30.00")], TODAY, END)
        assert f.points[0].balance == eur("70.00") and f.start == eur("100.00")

    def test_late_and_paid_are_never_added(self) -> None:
        f = forecast(
            eur("100.00"),
            [
                occ(date(2026, 11, 3), "-50.00", OccurrenceStatus.LATE),
                occ(date(2026, 11, 4), "-50.00", OccurrenceStatus.PAID),
            ],
            TODAY,
            END,
        )
        assert f.end == eur("100.00")

    def test_out_of_range_dates_are_ignored(self) -> None:
        f = forecast(
            eur("100.00"),
            [occ(date(2026, 10, 30), "-50.00"), occ(date(2027, 1, 2), "-50.00")],
            TODAY,
            END,
        )
        assert f.end == eur("100.00")

    def test_the_input_order_does_not_matter(self) -> None:
        items = [occ(date(2026, 11, 20), "-5.00"), occ(date(2026, 11, 3), "-80.00")]
        assert forecast(eur("100"), items, TODAY, END) == forecast(
            eur("100"), items[::-1], TODAY, END
        )

    def test_the_end_is_start_plus_everything_pending(self) -> None:
        items = [occ(date(2026, 11, d), "-1.50") for d in range(2, 30)]
        f = forecast(eur("100.00"), items, TODAY, END)
        assert f.end == eur("58.00")


class TestCombine:
    def test_the_household_curve_is_the_sum_of_the_accounts(self) -> None:
        a = forecast(eur("100.00"), [occ(date(2026, 11, 5), "-30.00")], TODAY, END)
        b = forecast(eur("200.00"), [occ(date(2026, 11, 8), "-250.00")], TODAY, END)
        total = combine([a, b], TODAY)
        assert [(p.day, str(p.balance.amount)) for p in total.points] == [
            (TODAY, "300.00"),
            (date(2026, 11, 5), "270.00"),
            (date(2026, 11, 8), "20.00"),
        ]
        assert total.start == eur("300.00") and total.end == eur("20.00")
        assert total.first_negative is None
        assert total.lowest.balance == eur("20.00")

    def test_one_account_in_debt_does_not_hide_inside_a_positive_total(self) -> None:
        a = forecast(eur("10.00"), [occ(date(2026, 11, 5), "-30.00")], TODAY, END)
        assert a.first_negative == date(2026, 11, 5)
        b = forecast(eur("500.00"), [], TODAY, END)
        assert combine([a, b], TODAY).first_negative is None
