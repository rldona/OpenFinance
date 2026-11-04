"""Alta inicial del hogar, sus personas y sus cuentas (OF-101, OF-102)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from openfinance.application.categories import seed_default_categories
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ports import PasswordHasher, UnitOfWork
from openfinance.domain.identity import (
    InvalidUserError,
    User,
    normalize_email,
    validate_password,
)
from openfinance.domain.ledger import Account, AccountKind, AccountType, Institution, LedgerError
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId
from openfinance.domain.shared.text import normalize_text
from openfinance.domain.workspaces import Actor, Household


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
    type: AccountType = AccountType.BANK
    currency: str | None = None
    """Moneda de la cuenta (OF-1008); por defecto, la del hogar."""


@dataclass(frozen=True, slots=True)
class BootstrapRequest:
    household_name: str
    members: list[NewMember]
    accounts: list[NewAccount] = field(default_factory=list)
    currency: str = "EUR"


def bootstrap_household(
    uow: UnitOfWork, hasher: PasswordHasher, request: BootstrapRequest, *, commit: bool = True
) -> Household:
    """Crea hogar, personas, categorías y cuentas. Con ``commit=False`` lo deja a quien llama."""
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
        uow.accounts.add(_account(spec, household, users))

    if commit:
        uow.commit()
    return household


def _account(spec: NewAccount, household: Household, members: dict[str, UserId]) -> Account:
    """La cuenta de ``spec`` en el hogar; ``members`` va de email normalizado a persona."""
    owner = None
    if spec.owner_email is not None:
        try:
            owner = members.get(normalize_email(spec.owner_email))
        except InvalidUserError as exc:
            raise InvalidRequestError(str(exc)) from exc
        if owner is None:
            raise InvalidRequestError(f"El titular de «{spec.name}» no es del hogar")
    try:
        currency = Currency(spec.currency.strip().upper()) if spec.currency else household.currency
        return Account(
            id=AccountId(uuid4()),
            household_id=household.id,
            name=spec.name.strip(),
            institution=spec.institution,
            kind=spec.kind,
            type=spec.type,
            currency=currency,
            opening_balance=Money.of(spec.opening_balance, currency),
            owner_id=owner,
        )
    except (LedgerError, ValueError, TypeError) as exc:
        raise InvalidRequestError(f"Cuenta «{spec.name}»: {exc}") from exc


def add_account(uow: UnitOfWork, member_email: str, spec: NewAccount) -> Account:
    """Añade una cuenta al hogar de ``member_email`` (una hucha, otra cuenta personal…).

    Se usa desde el servidor (``openfinance accounts add``). El nombre no puede repetirse en
    el hogar, sin distinguir mayúsculas ni tildes.
    """
    try:
        user = uow.users.get_by_email(normalize_email(member_email))
    except InvalidUserError as exc:
        raise InvalidRequestError(str(exc)) from exc
    if user is None:
        raise NotFoundError(f"No hay ninguna persona con el email {member_email}")
    households = uow.households.households_of(user.id)
    if len(households) != 1:
        raise InvalidRequestError(
            f"{user.email} pertenece a {len(households)} hogares; se esperaba exactamente uno"
        )
    household = uow.households.get(households[0])
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    name = normalize_text(spec.name)
    if any(normalize_text(a.name) == name for a in uow.accounts.for_household(household.id)):
        raise ConflictError(f"Ya existe una cuenta llamada «{spec.name.strip()}» en el hogar")
    members = {m.email: m.id for m in uow.households.members(household.id)}
    account = _account(spec, household, members)
    uow.accounts.add(account)
    uow.commit()
    return account


def create_account(
    uow: UnitOfWork,
    actor: Actor,
    name: str,
    account_type: AccountType,
    *,
    shared: bool,
    opening_balance: str,
    currency: str | None = None,
) -> Account:
    """Una cuenta nueva desde la web (OF-1005): de todo el hogar o solo de quien la crea.

    Las de efectivo, tarjeta, préstamo e inversión no tienen banco: no se importan extractos.
    """
    household = uow.households.get(actor.household_id)
    user = uow.users.get(actor.user_id)
    if household is None or user is None:
        raise NotFoundError("Hogar no encontrado")
    wanted = normalize_text(name)
    if any(normalize_text(a.name) == wanted for a in uow.accounts.for_household(household.id)):
        raise ConflictError(f"Ya existe una cuenta llamada «{name.strip()}» en el hogar")
    spec = NewAccount(
        name,
        Institution.OTHER,
        AccountKind.JOINT if shared else AccountKind.PERSONAL,
        opening_balance,
        owner_email=None if shared else user.email,
        type=account_type,
        currency=currency,
    )
    account = _account(spec, household, {user.email: user.id})
    uow.accounts.add(account)
    uow.commit()
    return account
