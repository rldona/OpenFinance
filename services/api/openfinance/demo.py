"""Hogar de demostración con 12 meses de movimientos ficticios (``openfinance demo``).

Sirve para ver los gráficos sin datos reales. Los datos se generan siempre igual (semilla
fija) y terminan en el mes actual, con el mes en curso hasta hoy.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from openfinance.application.households import (
    BootstrapRequest,
    NewAccount,
    NewMember,
    bootstrap_household,
)
from openfinance.application.ports import PasswordHasher, UnitOfWork
from openfinance.domain.categories import CategoryId
from openfinance.domain.insights import Month
from openfinance.domain.ledger import AccountKind, Institution, Transaction, TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import TransactionId, UserId

DEMO_PASSWORD = "demo-openfinance"  # noqa: S105 - pública a propósito: solo para datos ficticios
DEMO_EMAILS = ("raul@demo.openfinance", "elena@demo.openfinance")
_UNCATEGORIZED_RECENT = 3


@dataclass(frozen=True, slots=True)
class DemoResult:
    household: str
    emails: tuple[str, ...]
    password: str
    transactions: int
    months: tuple[str, str]


def _cents(value: int) -> Money:
    return Money.of(Decimal(value) / 100, "EUR")


def create_demo(uow: UnitOfWork, hasher: PasswordHasher, today: date) -> DemoResult:
    household = bootstrap_household(
        uow,
        hasher,
        BootstrapRequest(
            "Casa de demostración",
            [
                NewMember("Raúl", DEMO_EMAILS[0], DEMO_PASSWORD),
                NewMember("Elena", DEMO_EMAILS[1], DEMO_PASSWORD),
            ],
            [NewAccount("Cuenta conjunta", Institution.REVOLUT, AccountKind.JOINT, "250.00")],
        ),
        commit=False,  # todo o nada: el commit se hace al final
    )
    account = uow.accounts.for_household(household.id)[0]
    users = {u.display_name: u.id for u in uow.households.members(household.id)}
    cats = {c.slug: c.id for c in uow.categories.for_household(household.id) if c.slug}
    rnd = random.Random(20261031)  # noqa: S311 - datos ficticios, no criptografía

    def between(a: int, b: int) -> int:
        return rnd.randint(a, b)

    def pick(options: list[str]) -> str:
        return rnd.choice(options)

    last = Month.of(today)
    months = [last.shift(i - 11) for i in range(12)]
    rows: list[Transaction] = []

    def add(
        month: Month,
        day: int,
        desc: str,
        cents: int,
        kind: TransactionKind = TransactionKind.EXPENSE,
        slug: str | None = None,
        member: UserId | None = None,
    ) -> None:
        day = min(day, month.days)
        when = datetime(month.year, month.month, day, between(8, 21), between(0, 59))  # noqa: DTZ001
        if when.date() > today:
            return
        category: CategoryId | None = cats.get(slug) if slug else None
        rows.append(
            Transaction(
                id=TransactionId(uuid4()),
                household_id=household.id,
                account_id=account.id,
                booked_at=when,
                value_date=when.date(),
                description=desc,
                amount=_cents(cents),
                kind=kind,
                category_id=category,
                member_id=member,
                source="demo",
            )
        )

    for mo in months:
        winter = mo.month in (11, 12, 1, 2, 3)
        summer = mo.month in (6, 7, 8)
        add(
            mo,
            1,
            "Payment from Raul (Bankinter)",
            160000,
            TransactionKind.CONTRIBUTION,
            member=users["Raúl"],
        )
        add(
            mo,
            1,
            "Payment from Elena (Bankinter)",
            140000,
            TransactionKind.CONTRIBUTION,
            member=users["Elena"],
        )
        add(mo, 2, "To pocket EUR Ahorro", -30000, TransactionKind.SAVINGS_TRANSFER)
        add(mo, 1, "RECIBO HIPOTECA PRESTAMO 0042", -72000, slug="vivienda")
        add(mo, 5, "COMUNIDAD PROPIETARIOS C/ MAYOR 12", -6500, slug="vivienda")
        for _ in range(between(6, 9)):
            add(
                mo,
                between(1, 30),
                pick(["MERCADONA 1234", "LIDL VALENCIA", "CARREFOUR MARKET", "CONSUM 0087"]),
                -between(2800, 11500),
                slug="super",
            )
        light = (
            between(8500, 11800)
            if winter
            else between(7000, 9500)
            if summer
            else between(5200, 6800)
        )
        add(mo, between(10, 16), "IBERDROLA CLIENTES", -light, slug="suministros")
        add(mo, 8, "DIGI SPAIN TELECOM FIBRA", -3990, slug="suministros")
        if mo.month % 2 == 0:
            add(mo, 20, "AGUAS DE VALENCIA", -between(2800, 3600), slug="suministros")
        if winter:
            add(mo, between(18, 25), "NATURGY GAS", -between(4200, 8800), slug="suministros")
        for _ in range(between(5, 8) if summer or mo.month == 12 else between(3, 5)):
            add(
                mo,
                between(1, 30),
                pick(
                    ["RESTAURANTE LA PEPICA", "BAR CENTRAL", "GLOVO", "JUST EAT", "PIZZERIA NAPOLI"]
                ),
                -between(1800, 7500),
                slug="restaurantes",
            )
        for _ in range(between(2, 4)):
            add(
                mo,
                between(1, 30),
                pick(["REPSOL ESTACION 22", "CEPSA AV FRANCIA", "BP OIL"]),
                -between(4500, 7000),
                slug="transporte",
            )
        july = (mo.year, mo.month) >= (last.shift(-3).year, last.shift(-3).month)
        add(mo, 12, "NETFLIX.COM", -1799 if july else -1399, slug="suscripciones")
        add(mo, 14, "SPOTIFY DUO", -1499, slug="suscripciones")
        add(mo, 3, "APPLE.COM/BILL ICLOUD", -299, slug="suscripciones")
        add(mo, 2, "GIMNASIO FIT LIFE CUOTA X2", -7980, slug="salud")
        for _ in range(between(1, 3)):
            add(
                mo,
                between(1, 30),
                pick(["CINES YELMO", "TICKETMASTER", "FNAC"]),
                -between(1500, 6500),
                slug="ocio",
            )
        for _ in range(between(2, 4) if mo.month in (1, 7) else between(0, 2)):
            add(
                mo,
                between(1, 30),
                pick(["ZARA", "DECATHLON", "PRIMARK"]),
                -between(2500, 9000),
                slug="ropa",
            )
        for _ in range(between(0, 2)):
            add(
                mo,
                between(1, 30),
                pick(["IKEA VALENCIA", "LEROY MERLIN"]),
                -between(1500, 14000),
                slug="hogar",
            )
        if mo.month == 8:
            add(mo, 4, "VUELING AIRLINES", -38400, slug="viajes")
            add(mo, 6, "BOOKING.COM HOTEL", -61500, slug="viajes")
        if mo.month == 12:
            add(mo, 15, "EL CORTE INGLES REGALOS", -18500, slug="regalos")
        if rnd.random() < 0.4:
            add(mo, between(1, 30), "AMAZON EU MARKETPLACE", -between(800, 4500), slug="otros")
        if rnd.random() < 0.3:
            add(mo, between(5, 25), "AMAZON EU DEVOLUCION", between(800, 2500), slug="otros")

    # Algunos gastos recientes sin categoría, para ver el aviso y probar las reglas.
    for desc, cents in (
        ("FERRETERIA PEPE", -1850),
        ("BIZUM A LUCIA CENA", -2250),
        ("PAPELERIA SOL", -640),
    )[:_UNCATEGORIZED_RECENT]:
        add(last, max(1, today.day - 1), desc, cents)

    for t in rows:
        uow.transactions.add(t)
    uow.commit()
    return DemoResult(
        household.name, DEMO_EMAILS, DEMO_PASSWORD, len(rows), (str(months[0]), str(last))
    )
