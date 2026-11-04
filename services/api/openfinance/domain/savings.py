"""Ahorro: presupuestos, objetivos, cargos recurrentes e ideas (fase 4). Funciones puras."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum
from itertools import pairwise
from typing import NewType
from uuid import UUID

from openfinance.domain.categories import CategoryId
from openfinance.domain.insights import Month
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, WorkspaceId

GoalId = NewType("GoalId", UUID)


class SavingsError(ValueError):
    pass


# --- OF-401 · Presupuestos ------------------------------------------------------------------

WARNING_PERCENT = 85


class BudgetStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    """Se ha llegado al 85 %."""
    OVER = "over"
    """Se ha superado el límite."""


@dataclass(frozen=True, slots=True)
class Budget:
    household_id: WorkspaceId
    category_id: CategoryId
    amount: Money
    """Límite mensual."""

    def __post_init__(self) -> None:
        if self.amount.amount <= 0:
            raise SavingsError("El presupuesto debe ser mayor que cero")


def percent_of(part: Money, whole: Money) -> int:
    """Porcentaje entero redondeado hacia abajo (no anuncia un 100 % que aún no se ha
    alcanzado); 0 si ``whole`` no es positivo."""
    if whole.amount <= 0:
        return 0
    value = max(part.amount, Decimal(0)) * 100 / whole.amount
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def budget_status(
    spent: Money, limit: Money, fixed: Money | None = None
) -> tuple[int, BudgetStatus]:
    """El estado se decide con los importes exactos, no con el porcentaje redondeado.

    ``fixed`` son las cuotas fijas de la categoría (cobradas o por cobrar este mes). Una cuota
    ya está comprometida: no avisa de «cerca» por sí sola. El aviso mira solo el margen que
    queda para el gasto variable (límite menos cuotas) y, si las cuotas lo agotan, no avisa
    hasta que se supera el límite.
    """
    percent = percent_of(spent, limit)
    if spent.amount > limit.amount:
        return percent, BudgetStatus.OVER
    if fixed is None or fixed.amount <= 0:
        near = spent.amount * 100 >= limit.amount * WARNING_PERCENT
    else:
        room = limit.amount - fixed.amount
        variable = max(spent.amount - min(fixed.amount, spent.amount), Decimal(0))
        near = room > 0 and variable * 100 >= room * WARNING_PERCENT
    return percent, BudgetStatus.WARNING if near else BudgetStatus.OK


# --- OF-402 · Objetivos ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Goal:
    id: GoalId
    household_id: WorkspaceId
    name: str
    icon: str
    target: Money
    monthly: Money
    """Lo que se aparta cada mes para este objetivo."""
    saved: Money
    """Lo ahorrado, si se lleva a mano (se ignora si hay ``account_id``)."""
    deadline: Month | None = None
    account_id: AccountId | None = None
    """Hucha cuyo saldo es lo ahorrado."""

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > 60:
            raise SavingsError("El objetivo necesita un nombre de hasta 60 caracteres")
        if not self.icon.strip() or len(self.icon) > 8:
            raise SavingsError("Icono no válido")
        if self.target.amount <= 0:
            raise SavingsError("La meta debe ser mayor que cero")
        if self.monthly.is_negative or self.saved.is_negative:
            raise SavingsError("Las cantidades no pueden ser negativas")
        if len({self.target.currency, self.monthly.currency, self.saved.currency}) != 1:
            raise SavingsError("Todas las cantidades deben estar en la misma moneda")


@dataclass(frozen=True, slots=True)
class GoalProjection:
    saved: Money
    remaining: Money
    progress: int
    """Porcentaje alcanzado (puede pasar de 100)."""
    months_to_go: int | None
    """None si no se aparta nada al mes y aún falta."""
    eta: Month | None
    needed_monthly: Money | None
    """Lo que haría falta apartar al mes para llegar a la fecha límite."""
    on_track: bool | None


def _months_between(start: Month, end: Month) -> int:
    return (end.year * 12 + end.month) - (start.year * 12 + start.month)


def _ceil_cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def project_goal(
    goal: Goal, saved: Money, today: Month, extra_monthly: Money | None = None
) -> GoalProjection:
    """Proyección del objetivo. ``extra_monthly`` simula apartar más cada mes."""
    cur = goal.target.currency
    monthly = goal.monthly + (extra_monthly or Money.zero(cur))
    remaining_amount = max(goal.target.amount - saved.amount, Decimal(0))
    remaining = Money.of(remaining_amount, cur)
    if remaining_amount == 0:
        months: int | None = 0
    elif monthly.amount > 0:
        months = math.ceil(remaining_amount / monthly.amount)
    else:
        months = None
    eta = today.shift(months) if months is not None else None

    needed: Money | None = None
    on_track: bool | None = None
    if goal.deadline is not None:
        months_left = _months_between(today, goal.deadline)
        if remaining_amount == 0:
            on_track = True
        elif months_left <= 0:
            on_track = False
        else:
            needed = Money.of(_ceil_cents(remaining_amount / months_left), cur)
            on_track = eta is not None and eta <= goal.deadline
    return GoalProjection(
        saved=saved,
        remaining=remaining,
        progress=percent_of(saved, goal.target),
        months_to_go=months,
        eta=eta,
        needed_monthly=needed,
        on_track=on_track,
    )


# --- OF-403 · Cargos recurrentes ------------------------------------------------------------

MIN_MONTHS = 3
MAX_CHARGES_PER_MONTH = 2
MIN_REPEAT_RATIO = Decimal("0.6")
"""La cuota se repite igual (±1 %) en al menos el 60 % de los pares de meses consecutivos
(con solo 2 pares, basta con 1). Tolera subidas puntuales y descarta gastos que cambian
cada mes."""
MIN_COVERAGE = Decimal("0.75")
"""El comercio cobra en al menos el 75 % de los meses de su periodo."""
ACTIVE_DAYS = 45
PRICE_CHANGE = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class PriceChange:
    month: Month
    before: Money
    after: Money


@dataclass(frozen=True, slots=True)
class RecurringCharge:
    merchant: str
    category_id: CategoryId | None
    amount: Money
    """Última cuota (positiva)."""
    first_amount: Money
    """Primera cuota del periodo analizado."""
    last_date: date
    months: int
    changes: list[PriceChange]

    @property
    def increase(self) -> Money:
        return self.amount - self.first_amount


def detect_recurring(
    transactions: Iterable[Transaction], currency: Currency, today: date
) -> list[RecurringCharge]:
    """Cuotas: mismo comercio casi todos los meses, con importe estable y aún activas.

    El importe y las subidas se calculan con meses completos: el mes en curso solo sirve
    para saber si la cuota sigue activa (una cuota cobrada en dos veces aún puede estar a
    medias).
    """
    current = Month.of(today)
    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.kind is TransactionKind.EXPENSE and t.amount.is_negative and t.merchant:
            by_merchant[t.merchant].append(t)

    found: list[RecurringCharge] = []
    for merchant, txns in by_merchant.items():
        per_month: dict[Month, list[Transaction]] = defaultdict(list)
        for t in sorted(txns, key=lambda x: x.booked_at):
            per_month[Month.of(t.booked_at)].append(t)
        last = per_month[max(per_month)][-1]
        months = sorted(m for m in per_month if m < current)
        if len(months) < MIN_MONTHS:
            continue
        if any(len(v) > MAX_CHARGES_PER_MONTH for v in per_month.values()):
            continue
        span = _months_between(months[0], months[-1]) + 1
        if Decimal(len(months)) / span < MIN_COVERAGE:
            continue
        # Una cuota por mes: la suma del mes (p. ej. «GIMNASIO x2» en dos cargos).
        monthly = [sum((-t.amount.amount for t in per_month[m]), Decimal(0)) for m in months]
        if any(v <= 0 for v in monthly):
            continue
        pairs = list(pairwise(monthly))
        repeats = sum(1 for a, b in pairs if abs(b - a) / a <= PRICE_CHANGE)
        enough = (
            repeats >= len(pairs) - 1
            if len(pairs) <= 2
            else (Decimal(repeats) / len(pairs) >= MIN_REPEAT_RATIO)
        )
        if not enough:
            continue
        if (today - last.booked_at.date()).days > ACTIVE_DAYS:
            continue
        changes = [
            PriceChange(
                months[i], Money.of(monthly[i - 1], currency), Money.of(monthly[i], currency)
            )
            for i in range(1, len(monthly))
            if abs(monthly[i] - monthly[i - 1]) / monthly[i - 1] > PRICE_CHANGE
        ]
        found.append(
            RecurringCharge(
                merchant=merchant,
                category_id=last.category_id,
                amount=Money.of(monthly[-1], currency),
                first_amount=Money.of(monthly[0], currency),
                last_date=last.booked_at.date(),
                months=len(months),
                changes=changes,
            )
        )
    found.sort(key=lambda r: (-r.amount.amount, r.merchant))
    return found


# --- OF-802 · Cargos pendientes y previsión de cierre ---------------------------------------

MIN_FORECAST_DAYS = 7
"""Con menos días de datos, el ritmo diario no dice nada: no se hace previsión."""


@dataclass(frozen=True, slots=True)
class PendingCharge:
    merchant: str
    category_id: CategoryId | None
    amount: Money
    expected_day: int
    """Día del mes en que suele cobrarse (el del último cargo)."""
    late: bool
    """Ya debería haberse cobrado este mes y no ha llegado: se avisa, pero no se suma."""


def is_fixed(t: Transaction, recurring_merchants: set[str]) -> bool:
    return (
        t.kind is TransactionKind.EXPENSE
        and t.amount.is_negative
        and t.merchant is not None
        and t.merchant in recurring_merchants
    )


def pending_charges(
    recurring: Iterable[RecurringCharge], month_transactions: Iterable[Transaction], today: date
) -> list[PendingCharge]:
    """Cuotas habituales que este mes todavía no han llegado."""
    current = Month.of(today)
    paid = {
        t.merchant
        for t in month_transactions
        if t.kind is TransactionKind.EXPENSE and t.amount.is_negative and t.merchant
    }
    out: list[PendingCharge] = []
    for r in recurring:
        if r.merchant in paid:
            continue
        expected = min(r.last_date.day, current.days)
        out.append(
            PendingCharge(r.merchant, r.category_id, r.amount, expected, late=expected < today.day)
        )
    out.sort(key=lambda p: (p.late, p.expected_day, p.merchant))
    return out


def forecast_month_end(
    spent: Money,
    fixed_paid: Money,
    pending: Iterable[PendingCharge],
    days_elapsed: int,
    days_in_month: int,
    currency: Currency,
) -> Money | None:
    """Gasto con el que cerraría el mes: lo gastado, más las cuotas que faltan, más el
    ritmo diario del gasto variable (sin las cuotas ya cobradas) los días que quedan."""
    if days_elapsed < MIN_FORECAST_DAYS:
        return None
    upcoming = Money.zero(currency)
    for p in pending:
        if not p.late:
            upcoming = upcoming + p.amount
    variable = max(spent.amount - fixed_paid.amount, Decimal(0))
    rest = variable * (days_in_month - days_elapsed) / days_elapsed
    return Money.of(spent.amount + upcoming.amount + rest, currency)


# --- OF-404 · Ideas -------------------------------------------------------------------------

RESTAURANTS_CUT = 25
"""Cambiar una cena fuera a la semana por cocinar en casa: ≈ -25 %."""
GROCERIES_CUT = 10
"""Planificar una compra semanal con lista: ≈ -10 %."""
SUPPLIES_CUT = 10
"""Revisar potencia y tarifa de luz y gas: ≈ -10 %."""


@dataclass(frozen=True, slots=True)
class Idea:
    id: str
    icon: str
    title: str
    detail: str
    yearly_saving: Money
    evidence: str
    """De dónde sale la cifra: periodo y movimientos."""
    assumption: str | None = None
    """Estimación orientativa en la que se basa, si la hay."""


@dataclass(frozen=True, slots=True)
class CategoryStats:
    average: Money
    """Gasto medio mensual."""
    count: int
    """Movimientos en el periodo."""
    min_month: Money
    max_month: Money


def _yearly(monthly: Money, percent: int = 100) -> Money:
    return Money.of(monthly.amount * percent * 12 / 100, monthly.currency)


def build_ideas(
    stats_by_slug: dict[str, CategoryStats],
    recurring: list[RecurringCharge],
    subscriptions: list[RecurringCharge],
    months: int,
    currency: Currency,
) -> list[Idea]:
    """Ideas concretas a partir de los datos del hogar, ordenadas por ahorro anual."""
    ideas: list[Idea] = []
    period = f"últimos {months} meses" if months != 1 else "último mes"

    def fmt(m: Money) -> str:
        return f"{m.amount:.2f} €".replace(".", ",")

    raised = [r for r in recurring if r.increase.amount > 0]
    if raised:
        plural = len(raised) > 1
        title = (
            f"{len(raised)} cuota{'s' if plural else ''} ha{'n' if plural else ''} subido de precio"
        )
        extra = Money.zero(currency)
        for r in raised:
            extra = extra + r.increase
        names = ", ".join(
            f"{r.merchant.title()} ({fmt(r.first_amount)} → {fmt(r.amount)})" for r in raised
        )
        ideas.append(
            Idea(
                "price-increases",
                "📈",
                title,
                f"{names}. Volver al precio anterior (cambiando de plan o de proveedor) supone:",
                _yearly(extra),
                f"Cargos mensuales de los {period}",
            )
        )
    if subscriptions:
        total = Money.zero(currency)
        for s in subscriptions:
            total = total + s.amount
        cheapest = min(subscriptions, key=lambda s: s.amount.amount)
        ideas.append(
            Idea(
                "subscriptions",
                "📺",
                f"Pagáis {fmt(total)} al mes en {len(subscriptions)} suscripciones",
                f"{', '.join(s.merchant.title() for s in subscriptions)}. Prescindir de una, "
                f"por ejemplo {cheapest.merchant.title()}, ahorraría:",
                _yearly(cheapest.amount),
                f"Cargos recurrentes de la categoría Suscripciones en los {period}",
            )
        )
    for slug, icon, label, cut, text in (
        ("restaurantes", "🍽️", "Restaurantes y comida a domicilio", RESTAURANTS_CUT,
         "Cambiar una cena fuera a la semana por cocinar en casa supone:"),
        ("super", "🛒", "Supermercado", GROCERIES_CUT,
         "Planificar una compra semanal con lista suele recortar el gasto; supone:"),
        ("suministros", "💡", "Luz, agua, gas e internet", SUPPLIES_CUT,
         "Revisar la potencia contratada y la tarifa por tramos puede rebajarlo; supone:"),
    ):  # fmt: skip
        st = stats_by_slug.get(slug)
        if st is None or st.average.amount <= 0:
            continue
        per_month = math.ceil(st.count / max(months, 1))
        detail = (
            f"{label}: {fmt(st.average)} al mes de media ({per_month} movimientos al mes; "
            f"entre {fmt(st.min_month)} y {fmt(st.max_month)}). {text}"
        )
        ideas.append(
            Idea(
                f"cut-{slug}",
                icon,
                f"{label}: {fmt(st.average)} al mes",
                detail,
                _yearly(st.average, cut),
                f"{st.count} movimientos de los {period}",
                f"Estimación orientativa: -{cut} %",
            )
        )
    ideas.sort(key=lambda i: -i.yearly_saving.amount)
    return ideas
