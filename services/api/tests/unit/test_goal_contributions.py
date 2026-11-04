"""OF-1206: aportaciones, prioridad y reparto de los objetivos."""

from datetime import date
from uuid import uuid4

import pytest

from openfinance.domain.savings import (
    MAX_PRIORITY,
    ContributionId,
    Goal,
    GoalContribution,
    GoalId,
    SavingsError,
    contribution_from_definition,
    distribute,
)
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import WorkspaceId

HOUSE = WorkspaceId(uuid4())


def eur(amount: str) -> Money:
    return Money.of(amount, "EUR")


def goal(priority: int = 50, name: str = "Fondo") -> Goal:
    return Goal(
        id=GoalId(uuid4()),
        household_id=HOUSE,
        name=name,
        icon="🎯",
        target=eur("1000"),
        monthly=eur("0"),
        saved=eur("0"),
        priority=priority,
    )


class TestPriority:
    def test_default_and_bounds(self) -> None:
        assert goal().priority == 50
        for bad in (0, MAX_PRIORITY + 1, -3):
            with pytest.raises(SavingsError):
                goal(priority=bad)


class TestContribution:
    def make(self, amount: str = "100.00", note: str = "") -> GoalContribution:
        return GoalContribution(
            ContributionId(uuid4()), HOUSE, GoalId(uuid4()), date(2026, 11, 2), eur(amount), note
        )

    def test_a_withdrawal_is_a_negative_contribution(self) -> None:
        assert self.make("-30.00").amount.is_negative

    @pytest.mark.parametrize("amount, note", [("0.00", ""), ("5", "x" * 201), ("5", "a\nb")])
    def test_rejects(self, amount: str, note: str) -> None:
        with pytest.raises(SavingsError):
            self.make(amount, note)

    def test_definition_round_trips(self) -> None:
        c = self.make("-12.50", "Reparación de la caldera")
        assert contribution_from_definition(c.id, HOUSE, c.definition()) == c


class TestDistribute:
    def test_the_most_important_goal_is_filled_first(self) -> None:
        a, b = goal(1, "A"), goal(2, "B")
        got = distribute(eur("300"), [(b, eur("500")), (a, eur("200"))])
        assert got == [(a.id, eur("200")), (b.id, eur("100"))]

    def test_it_never_gives_more_than_is_missing_nor_than_there_is(self) -> None:
        a, b = goal(1), goal(2)
        assert distribute(eur("50"), [(a, eur("200")), (b, eur("10"))]) == [(a.id, eur("50"))]
        assert distribute(eur("1000"), [(a, eur("200")), (b, eur("10"))]) == [
            (a.id, eur("200")),
            (b.id, eur("10")),
        ]

    def test_a_finished_goal_gets_nothing(self) -> None:
        a, b = goal(1), goal(2)
        assert distribute(eur("100"), [(a, eur("0")), (b, eur("40"))]) == [(b.id, eur("40"))]

    def test_equal_priority_keeps_the_given_order(self) -> None:
        a, b = goal(5, "A"), goal(5, "B")
        assert distribute(eur("10"), [(b, eur("100")), (a, eur("100"))]) == [(b.id, eur("10"))]

    def test_nothing_to_share(self) -> None:
        assert distribute(eur("0"), [(goal(), eur("10"))]) == []
        assert distribute(eur("-5"), [(goal(), eur("10"))]) == []
        assert distribute(eur("10"), []) == []

    def test_the_total_given_never_exceeds_the_amount(self) -> None:
        goals = [(goal(p), eur(str(r))) for p, r in ((3, 40), (1, 25), (2, 90), (9, 10))]
        for amount in ("0.01", "7.77", "60", "120.50", "500"):
            total = sum(m.amount for _, m in distribute(eur(amount), goals))
            assert total <= eur(amount).amount
