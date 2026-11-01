from datetime import date, datetime
from uuid import uuid4

import pytest

from openfinance.domain.categories import CategoryId
from openfinance.domain.insights import Month
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.savings import (
    Budget,
    BudgetStatus,
    CategoryStats,
    Goal,
    GoalId,
    SavingsError,
    budget_status,
    build_ideas,
    detect_recurring,
    project_goal,
)
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, TransactionId, WorkspaceId

EUR = Currency("EUR")
HOUSE = WorkspaceId(uuid4())


def m(amount: str) -> Money:
    return Money.of(amount, EUR)


class TestBudgets:
    @pytest.mark.parametrize(
        ("spent", "status", "percent"),
        [
            ("0.00", BudgetStatus.OK, 0),
            ("84.40", BudgetStatus.OK, 84),
            ("84.99", BudgetStatus.OK, 84),
            ("85.00", BudgetStatus.WARNING, 85),
            ("99.99", BudgetStatus.WARNING, 99),
            ("100.00", BudgetStatus.WARNING, 100),
            ("100.01", BudgetStatus.OVER, 100),
            ("150.00", BudgetStatus.OVER, 150),
            ("-10.00", BudgetStatus.OK, 0),
        ],
    )
    def test_status(self, spent: str, status: BudgetStatus, percent: int) -> None:
        assert budget_status(m(spent), m("100.00")) == (percent, status)

    def test_must_be_positive(self) -> None:
        with pytest.raises(SavingsError):
            Budget(HOUSE, CategoryId(uuid4()), m("0.00"))


def goal(target="9000.00", monthly="200.00", saved="6120.00", deadline=None) -> Goal:
    return Goal(
        GoalId(uuid4()),
        HOUSE,
        "Fondo de emergencia",
        "🛟",
        m(target),
        m(monthly),
        m(saved),
        deadline,
    )


class TestGoals:
    def test_eta(self) -> None:
        p = project_goal(goal(), m("6120.00"), Month(2026, 10))
        assert p.remaining == m("2880.00")
        assert p.progress == 68
        assert p.months_to_go == 15  # 2880 / 200 = 14,4 → 15
        assert p.eta == Month(2028, 1)

    def test_extra_monthly_brings_it_forward(self) -> None:
        p = project_goal(goal(), m("6120.00"), Month(2026, 10), extra_monthly=m("100.00"))
        assert p.months_to_go == 10

    def test_deadline_and_needed_monthly(self) -> None:
        g = goal(target="2500.00", monthly="100.00", saved="880.00", deadline=Month(2027, 7))
        p = project_goal(g, m("880.00"), Month(2026, 10))
        assert p.needed_monthly == m("180.00")  # 1620 / 9 meses
        assert p.on_track is False
        assert p.eta == Month(2028, 3)  # 1620 / 100 = 16,2 → 17 meses

    def test_reached_and_no_monthly(self) -> None:
        assert project_goal(goal(), m("9500.00"), Month(2026, 10)).months_to_go == 0
        p = project_goal(goal(monthly="0.00"), m("10.00"), Month(2026, 10))
        assert (p.months_to_go, p.eta) == (None, None)

    def test_past_deadline_is_off_track(self) -> None:
        p = project_goal(goal(deadline=Month(2026, 1)), m("10.00"), Month(2026, 10))
        assert p.on_track is False
        assert p.needed_monthly is None

    @pytest.mark.parametrize(
        "kwargs", [{"target": "0.00"}, {"monthly": "-1.00"}, {"saved": "-1.00"}]
    )
    def test_invalid(self, kwargs) -> None:
        with pytest.raises(SavingsError):
            goal(**kwargs)


def charge(month: int, day: int, desc: str, amount: str, category=None, year=2026) -> Transaction:
    return Transaction(
        id=TransactionId(uuid4()),
        household_id=HOUSE,
        account_id=AccountId(uuid4()),
        booked_at=datetime(year, month, day, 10),  # noqa: DTZ001
        value_date=date(year, month, day),
        description=desc,
        amount=m(amount),
        kind=TransactionKind.EXPENSE,
        category_id=category,
    )


class TestRecurring:
    def test_detects_subscriptions_and_price_increases(self) -> None:
        subs = CategoryId(uuid4())
        txns = [
            charge(mo, 12, "NETFLIX.COM", "-13.99" if mo < 7 else "-17.99", subs)
            for mo in range(1, 11)
        ]
        txns += [charge(mo, 3, "SPOTIFY DUO", "-14.99", subs) for mo in range(4, 11)]
        found = {r.merchant: r for r in detect_recurring(txns, EUR, date(2026, 11, 1))}
        netflix = found["NETFLIX"]
        assert netflix.amount == m("17.99")
        assert netflix.first_amount == m("13.99")
        assert netflix.increase == m("4.00")
        assert [(str(c.month), c.before, c.after) for c in netflix.changes] == [
            ("2026-07", m("13.99"), m("17.99"))
        ]
        assert netflix.category_id == subs
        assert found["SPOTIFY DUO"].changes == []

    def test_ignores_irregular_unstable_and_stopped_charges(self) -> None:
        txns = [
            charge(mo, 5, "MERCADONA", f"-{40 + mo * 13}.00") for mo in range(1, 11)
        ]  # inestable
        txns += [charge(mo, 5, "ZARA", "-30.00") for mo in (1, 5, 9)]  # irregular
        txns += [charge(mo, 5, "GIMNASIO VIEJO", "-40.00") for mo in range(1, 7)]  # dado de baja
        txns += [charge(10, d, "BAR CENTRAL", "-3.00") for d in (1, 2, 3)]  # varias veces al mes
        txns += [charge(mo, 14, "IBERDROLA", f"-{60 + (mo % 3) * 20}.00") for mo in range(1, 11)]
        assert detect_recurring(txns, EUR, date(2026, 10, 31)) == []

    def test_three_months_with_one_price_increase(self) -> None:
        txns = [charge(mo, 12, "HBO MAX", "-8.99" if mo < 9 else "-9.99") for mo in (7, 8, 9)]
        (hbo,) = detect_recurring(txns, EUR, date(2026, 10, 5))
        assert (hbo.first_amount, hbo.amount) == (m("8.99"), m("9.99"))

    def test_current_month_only_proves_it_is_active(self) -> None:
        txns = [charge(mo, 12, "DISNEY PLUS", "-11.99") for mo in (6, 7, 8, 9)]
        txns.append(charge(10, 12, "DISNEY PLUS", "-5.00"))  # mes en curso
        (disney,) = detect_recurring(txns, EUR, date(2026, 10, 20))
        assert (disney.amount, disney.changes, disney.last_date) == (
            m("11.99"),
            [],
            date(2026, 10, 12),
        )

    def test_two_charges_in_a_month_are_one_fee(self) -> None:
        txns = [charge(mo, d, "GIMNASIO FIT", "-39.90") for mo in range(7, 11) for d in (2, 3)]
        (gym,) = detect_recurring(txns, EUR, date(2026, 11, 1))
        assert gym.amount == m("79.80")


class TestIdeas:
    def test_ideas_are_backed_by_data_and_sorted(self) -> None:
        subs = CategoryId(uuid4())
        txns = [
            charge(mo, 12, "NETFLIX.COM", "-13.99" if mo < 7 else "-17.99", subs)
            for mo in range(1, 11)
        ]
        txns += [charge(mo, 3, "SPOTIFY DUO", "-14.99", subs) for mo in range(1, 11)]
        recurring = detect_recurring(txns, EUR, date(2026, 11, 1))
        stats = {
            "restaurantes": CategoryStats(m("216.00"), 48, m("120.00"), m("380.00")),
            "super": CategoryStats(m("520.00"), 84, m("400.00"), m("640.00")),
        }
        ideas = build_ideas(stats, recurring, recurring, 12, EUR)
        by_id = {i.id: i for i in ideas}
        assert by_id["cut-restaurantes"].yearly_saving == m("648.00")  # 216 x 25 % x 12
        assert by_id["cut-super"].yearly_saving == m("624.00")  # 520 x 10 % x 12
        assert by_id["price-increases"].yearly_saving == m("48.00")  # 4 € x 12
        assert by_id["subscriptions"].yearly_saving == m(
            "179.88"
        )  # la más barata hoy: Spotify 14,99 x 12
        assert "Spotify Duo" in by_id["subscriptions"].detail
        assert "Netflix" in by_id["price-increases"].detail
        assert [i.yearly_saving.amount for i in ideas] == sorted(
            (i.yearly_saving.amount for i in ideas), reverse=True
        )
        assert by_id["cut-super"].assumption == "Estimación orientativa: -10 %"

    def test_no_data_no_ideas(self) -> None:
        assert build_ideas({}, [], [], 12, EUR) == []
