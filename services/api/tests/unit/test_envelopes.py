"""OF-1203: sobres con arrastre e importes por mes (ADR-0022)."""

from uuid import uuid4

import pytest

from openfinance.domain.categories import CategoryId
from openfinance.domain.insights import Month
from openfinance.domain.savings import (
    MAX_ENVELOPE_MONTHS,
    Budget,
    BudgetMode,
    BudgetStatus,
    SavingsError,
    allocation,
    carried_into,
    envelope_status,
)
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import WorkspaceId

HOUSE = WorkspaceId(uuid4())
CAT = CategoryId(uuid4())
START = Month(2026, 1)


def eur(amount: str) -> Money:
    return Money.of(amount, "EUR")


def envelope(amount: str = "100.00", started: Month = START) -> Budget:
    return Budget(HOUSE, CAT, eur(amount), BudgetMode.ENVELOPE, started)


def limit(amount: str = "100.00") -> Budget:
    return Budget(HOUSE, CAT, eur(amount))


class TestModel:
    def test_an_envelope_needs_a_start_and_a_limit_must_not_have_one(self) -> None:
        with pytest.raises(SavingsError):
            Budget(HOUSE, CAT, eur("10"), BudgetMode.ENVELOPE, None)
        with pytest.raises(SavingsError):
            Budget(HOUSE, CAT, eur("10"), BudgetMode.LIMIT, START)

    def test_existing_budgets_are_limits(self) -> None:
        assert Budget(HOUSE, CAT, eur("10")).mode is BudgetMode.LIMIT

    def test_allocation_uses_the_month_override_or_the_base(self) -> None:
        b = envelope()
        assert allocation(b, {Month(2026, 8): eur("300")}, Month(2026, 8)) == eur("300")
        assert allocation(b, {Month(2026, 8): eur("300")}, Month(2026, 9)) == eur("100.00")


class TestCarry:
    def test_a_limit_never_carries(self) -> None:
        assert carried_into(limit(), {}, {Month(2026, 1): eur("5")}, Month(2026, 6)) == eur("0")

    def test_the_start_month_and_earlier_carry_nothing(self) -> None:
        assert carried_into(envelope(), {}, {}, START) == eur("0")
        assert carried_into(envelope(), {}, {}, Month(2025, 6)) == eur("0")

    @pytest.mark.parametrize("n", [1, 2, 7, 12])
    def test_without_spending_n_months_accumulate_n_times_the_allocation(self, n: int) -> None:
        assert carried_into(envelope(), {}, {}, START.shift(n)) == eur(f"{100 * n}.00")

    def test_what_is_left_passes_on_and_a_deficit_too(self) -> None:
        spent = {Month(2026, 1): eur("60.00"), Month(2026, 2): eur("190.00")}
        b = envelope()
        assert carried_into(b, {}, spent, Month(2026, 2)) == eur("40.00")
        assert carried_into(b, {}, spent, Month(2026, 3)) == eur("-50.00")  # 40 + 100 - 190
        assert carried_into(b, {}, spent, Month(2026, 4)) == eur("50.00")  # -50 + 100

    def test_overrides_change_that_month_only(self) -> None:
        b = envelope()
        overrides = {Month(2026, 2): eur("500.00")}
        assert carried_into(b, overrides, {}, Month(2026, 3)) == eur("600.00")

    def test_moving_spending_between_months_never_changes_the_accumulated_total(self) -> None:
        b = envelope()
        a = {Month(2026, 1): eur("90.00"), Month(2026, 3): eur("10.00")}
        c = {Month(2026, 2): eur("100.00")}
        assert carried_into(b, {}, a, Month(2026, 4)) == carried_into(b, {}, c, Month(2026, 4))

    def test_correcting_an_old_movement_corrects_every_later_month(self) -> None:
        b = envelope()
        before = {Month(2026, 1): eur("80.00")}
        after = {Month(2026, 1): eur("30.00")}
        for n in range(1, 8):
            month = START.shift(n)
            diff = carried_into(b, {}, after, month) - carried_into(b, {}, before, month)
            assert diff == eur("50.00")

    def test_a_refund_adds_to_the_envelope(self) -> None:
        assert carried_into(envelope(), {}, {Month(2026, 1): eur("-20.00")}, Month(2026, 2)) == eur(
            "120.00"
        )

    def test_it_looks_back_a_bounded_number_of_months(self) -> None:
        b = envelope(started=Month(2000, 1))
        far = Month(2026, 1)
        assert carried_into(b, {}, {}, far) == eur(f"{100 * MAX_ENVELOPE_MONTHS}.00")


class TestStatus:
    def test_within_the_envelope(self) -> None:
        assert envelope_status(eur("10.00"), eur("100.00")) == (10, BudgetStatus.OK)

    def test_near_and_over_follow_the_limit_rules(self) -> None:
        assert envelope_status(eur("90.00"), eur("100.00"))[1] is BudgetStatus.WARNING
        assert envelope_status(eur("100.01"), eur("100.00"))[1] is BudgetStatus.OVER

    def test_a_carried_deficit_makes_it_over_even_with_no_spending(self) -> None:
        assert envelope_status(eur("0.00"), eur("-5.00"))[1] is BudgetStatus.OVER

    def test_an_exactly_empty_envelope_is_not_over(self) -> None:
        assert envelope_status(eur("0.00"), eur("0.00")) == (0, BudgetStatus.OK)

    def test_any_spending_with_nothing_available_is_over(self) -> None:
        assert envelope_status(eur("1.00"), eur("0.00"))[1] is BudgetStatus.OVER
