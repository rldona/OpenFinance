"""Alta inicial del hogar, sus personas y sus cuentas (OF-101, OF-102)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from openfinance.application.categories import seed_default_categories
from openfinance.application.errors import ConflictError, InvalidRequestError
from openfinance.application.ports import PasswordHasher, UnitOfWork
from openfinance.domain.identity import (
    InvalidUserError,
    User,
    normalize_email,
    validate_password,
)
from openfinance.domain.ledger import Account, AccountKind, Institution, LedgerError
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId
from openfinance.domain.workspaces import Household


@dataclass(frozen=True, slots=True)
class NewMember:
    display_name: str
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class NewAccount:
    name: str
    institution: Institution
    kind: AccountKind
    opening_balance: str = "0"
    owner_email: str | None = None


@dataclass(frozen=True, slots=True)
class BootstrapRequest:
    household_name: str
    members: list[NewMember]
    accounts: list[NewAccount] = field(default_factory=list)
    currency: str = "EUR"


def bootstrap_household(
    uow: UnitOfWork, hasher: PasswordHasher, request: BootstrapRequest
) -> Household:
    if not request.members:
        raise InvalidRequestError("El hogar necesita al menos una persona")
    try:
        currency = Currency(request.currency)
        household = Household(WorkspaceId(uuid4()), request.household_name.strip(), currency)
        emails = [normalize_email(m.email) for m in request.members]
        for m in request.members:
            validate_password(m.password)
    except (ValueError, InvalidUserError) as exc:
        raise InvalidRequestError(str(exc)) from exc
    if len(set(emails)) != len(emails):
        raise InvalidRequestError("Hay emails repetidos")
    for email in emails:
        if uow.users.get_by_email(email) is not None:
            raise ConflictError(f"Ya existe un usuario con el email {email}")

    uow.households.add(household)
    seed_default_categories(uow, household.id)
    users: dict[str, UserId] = {}
    for member, email in zip(request.members, emails, strict=True):
        user = User(
            UserId(uuid4()), email, member.display_name.strip(), hasher.hash(member.password)
        )
        uow.users.add(user)
        uow.households.add_member(household.id, user.id)
        users[email] = user.id

    for spec in request.accounts:
        owner = None
        if spec.owner_email is not None:
            owner = users.get(normalize_email(spec.owner_email))
            if owner is None:
                raise InvalidRequestError(f"El titular de «{spec.name}» no es del hogar")
        try:
            account = Account(
                id=AccountId(uuid4()),
                household_id=household.id,
                name=spec.name.strip(),
                institution=spec.institution,
                kind=spec.kind,
                currency=currency,
                opening_balance=Money.of(spec.opening_balance, currency),
                owner_id=owner,
            )
        except (LedgerError, ValueError, TypeError) as exc:
            raise InvalidRequestError(f"Cuenta «{spec.name}»: {exc}") from exc
        uow.accounts.add(account)

    uow.commit()
    return household
