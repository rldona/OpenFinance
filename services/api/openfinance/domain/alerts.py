"""Avisos deterministas: duplicados, comisiones, recibos que suben, atrasos… (ADR-0023, OF-1301).

Un aviso es una función pura de los datos de hoy: no se guarda, se recalcula en cada consulta, y
lo único que se guarda es que alguien lo descartó (por su ``key``, que es estable). Sin
aprendizaje ni umbrales ocultos: cada detector dice exactamente cuándo salta.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from openfinance.domain.bank import EXPIRY_WARNING_DAYS, BankConnection, ConsentStatus
from openfinance.domain.insights import Month
from openfinance.domain.ledger import Transaction, TransactionKind
from openfinance.domain.savings import RecurringCharge
from openfinance.domain.shared import Money

DUPLICATE_DAYS = 2
"""Dos cargos iguales a menos de este margen en días se avisan como posible duplicado."""
RECENT_DAYS = 14
"""Solo se avisa de lo reciente: un duplicado de hace dos meses ya no es noticia."""
FEE_DAYS = 30
PRICE_RISE_MIN = Decimal("0.05")
"""Un recibo que sube menos de un 5 % no se avisa."""
LOW_BALANCE_DAYS = 30
EXPIRED_NAG_DAYS = 30
"""Un consentimiento caducado avisa durante un mes; luego se da por abandonado."""
FEE_WORDS = ("comisión", "comision", "commission", "fee")
"""Palabras del concepto o del tipo de banco que marcan una comisión."""


class AlertKind(StrEnum):
    LATE_PAYMENT = "late_payment"
    LOW_BALANCE = "low_balance"
    BUDGET_OVER = "budget_over"
    DUPLICATE = "duplicate"
    PRICE_RISE = "price_rise"
    FEE = "fee"
    CONSENT = "consent"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


_ORDER = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}


@dataclass(frozen=True, slots=True)
class Alert:
    kind: AlertKind
    key: str
    """Estable entre consultas: es lo que se guarda al descartarlo y al notificarlo."""
    severity: Severity
    title: str
    detail: str
    on: date
    """El día al que se refiere (el del cargo, el vencimiento o el primer saldo negativo)."""
    amount: Money | None = None
    account_id: str | None = None
    """El id de la cuenta, para llevar a su pantalla."""


def sort_alerts(alerts: Iterable[Alert]) -> list[Alert]:
    """Lo más grave primero y, a igual gravedad, lo más reciente."""
    return sorted(alerts, key=lambda a: (_ORDER[a.severity], -a.on.toordinal(), a.key))


def _label(t: Transaction) -> str:
    return t.merchant or t.description


def duplicates(transactions: Iterable[Transaction], today: date) -> list[Alert]:
    """Gastos con la misma cuenta, el mismo comercio y el mismo importe a ≤ 2 días.

    Cada pareja avisa una vez, con el cargo más reciente como referencia. Un tercer cargo
    avisa contra el anterior, no contra el primero.
    """
    groups: dict[tuple[str, str, Decimal], list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.voided or t.kind is not TransactionKind.EXPENSE or not t.amount.is_negative:
            continue
        groups[(str(t.account_id), _label(t).casefold(), t.amount.amount)].append(t)
    found: list[Alert] = []
    for items in groups.values():
        items.sort(key=lambda t: (t.booked_at, str(t.id)))
        for earlier, later in itertools.pairwise(items):
            gap = (later.booked_at.date() - earlier.booked_at.date()).days
            if gap > DUPLICATE_DAYS or (today - later.booked_at.date()).days > RECENT_DAYS:
                continue
            found.append(
                Alert(
                    AlertKind.DUPLICATE,
                    f"duplicate:{later.id}",
                    Severity.WARNING,
                    f"Posible cargo duplicado en {_label(later)}",
                    f"Dos cargos de {(-later.amount).amount:.2f} {later.amount.currency.code} "
                    f"en {gap} día(s). Si es un error, pídele al comercio que lo devuelva.",
                    later.booked_at.date(),
                    -later.amount,
                    str(later.account_id),
                )
            )
    return found


def fees(transactions: Iterable[Transaction], today: date) -> list[Alert]:
    """Gastos cuyo concepto o tipo de banco dice «comisión» en los últimos 30 días."""
    found: list[Alert] = []
    for t in transactions:
        if t.voided or t.kind is not TransactionKind.EXPENSE or not t.amount.is_negative:
            continue
        if (today - t.booked_at.date()).days > FEE_DAYS:
            continue
        text = f"{t.description} {t.bank_type}".casefold()
        if not any(word in text for word in FEE_WORDS):
            continue
        found.append(
            Alert(
                AlertKind.FEE,
                f"fee:{t.id}",
                Severity.INFO,
                f"Comisión: {t.description}",
                f"{(-t.amount).amount:.2f} {t.amount.currency.code} cobrados por el banco.",
                t.booked_at.date(),
                -t.amount,
                str(t.account_id),
            )
        )
    return found


def price_rises(recurring: Iterable[RecurringCharge], today: date) -> list[Alert]:
    """Cuotas cuyo último cambio de precio fue este mes o el anterior y subió al menos un 5 %."""
    since = Month.of(today).shift(-1)
    found: list[Alert] = []
    for r in recurring:
        if not r.changes:
            continue
        change = r.changes[-1]
        if change.month < since or change.after.amount <= change.before.amount:
            continue
        rise = (change.after.amount - change.before.amount) / change.before.amount
        if rise < PRICE_RISE_MIN:
            continue
        found.append(
            Alert(
                AlertKind.PRICE_RISE,
                f"price_rise:{r.merchant}:{change.month.year}-{change.month.month:02d}",
                Severity.WARNING,
                f"{r.merchant} ha subido un {rise * 100:.0f} %",
                f"De {change.before.amount:.2f} a {change.after.amount:.2f} "
                f"{change.after.currency.code} al mes.",
                change.month.start.date(),
                change.after - change.before,
            )
        )
    return found


def consents(connections: Iterable[BankConnection], today: date) -> list[Alert]:
    """Consentimientos con el banco que caducan en 14 días o caducaron en el último mes.

    Si ya hay otra conexión activa con el mismo banco, la caducada se da por renovada.
    """
    live = list(connections)
    renewed = {
        (c.aspsp, c.country)
        for c in live
        if c.status is ConsentStatus.ACTIVE
        and c.valid_until is not None
        and c.valid_until.date() >= today
    }
    found: list[Alert] = []
    for c in live:
        if c.status not in (ConsentStatus.ACTIVE, ConsentStatus.EXPIRED) or c.valid_until is None:
            continue
        end = c.valid_until.date()
        if end >= today:
            if (end - today).days > EXPIRY_WARNING_DAYS:
                continue
            when = "hoy" if end == today else f"el {end.isoformat()}"
            found.append(
                Alert(
                    AlertKind.CONSENT,
                    f"consent:{c.id}:{end.isoformat()}",
                    Severity.WARNING,
                    f"La conexión con {c.aspsp} caduca {when}",
                    "Después dejarán de llegar movimientos. Conéctala de nuevo en Ajustes.",
                    end,
                )
            )
        elif (c.aspsp, c.country) not in renewed and today - end <= timedelta(
            days=EXPIRED_NAG_DAYS
        ):
            found.append(
                Alert(
                    AlertKind.CONSENT,
                    f"consent_expired:{c.id}:{end.isoformat()}",
                    Severity.CRITICAL,
                    f"La conexión con {c.aspsp} ha caducado",
                    f"Dejó de traer movimientos el {end.isoformat()}. "
                    "Conéctala de nuevo en Ajustes.",
                    end,
                )
            )
    return found
