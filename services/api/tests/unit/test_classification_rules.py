"""Reglas de clasificación por cuenta (ADR-0015)."""

from uuid import uuid4

import pytest

from openfinance.application.imports import classification_rules
from openfinance.domain.identity import User
from openfinance.domain.imports import (
    MemberPattern,
    PatternDirection,
    TransactionKind,
    suggest_kind,
)
from openfinance.domain.ledger import Account, AccountKind, Institution
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, UserId, WorkspaceId

HOUSE = WorkspaceId(uuid4())
ANA = User(UserId(uuid4()), "ana@example.org", "Ana Pérez", "x")
LUIS = User(UserId(uuid4()), "luis@example.org", "Luis", "x")
OUTSIDER = UserId(uuid4())


def account(institution: Institution, kind: AccountKind = AccountKind.PERSONAL) -> Account:
    return Account(
        id=AccountId(uuid4()),
        household_id=HOUSE,
        name="Cuenta",
        institution=institution,
        kind=kind,
        currency=Currency("EUR"),
        opening_balance=Money.of("0", "EUR"),
        owner_id=ANA.id if kind is AccountKind.PERSONAL else None,
    )


def kind_of(acc: Account, description: str, inflow: bool, patterns=()) -> tuple:
    rules = classification_rules(acc, [ANA, LUIS], list(patterns))
    return suggest_kind(description, inflow, rules)


def test_revolut_recharge_is_owner_contribution_in_bankinter() -> None:
    acc = account(Institution.BANKINTER)
    assert kind_of(acc, "Revolut**1234*", False) == (TransactionKind.CONTRIBUTION, str(ANA.id))


@pytest.mark.parametrize("institution", [Institution.OTHER, Institution.REVOLUT])
def test_revolut_recharge_is_an_expense_in_other_personal_accounts(institution) -> None:
    assert kind_of(account(institution), "Revolut**1234*", False) == (
        TransactionKind.EXPENSE,
        None,
    )


def test_stored_outflow_patterns_apply_to_any_personal_account() -> None:
    stored = [MemberPattern(HOUSE, ANA.id, "TRASPASO CASA", PatternDirection.OUTFLOW)]
    acc = account(Institution.OTHER)
    assert kind_of(acc, "Traspaso casa", False, stored) == (
        TransactionKind.CONTRIBUTION,
        str(ANA.id),
    )


def test_partner_outflow_patterns_do_not_apply_to_owner_account() -> None:
    stored = [MemberPattern(HOUSE, LUIS.id, "TRASPASO CASA", PatternDirection.OUTFLOW)]
    acc = account(Institution.BANKINTER)
    assert kind_of(acc, "Traspaso casa", False, stored) == (TransactionKind.EXPENSE, None)


def test_names_are_not_used_in_personal_accounts() -> None:
    assert kind_of(account(Institution.BANKINTER), "Bizum de Luis", True) == (
        TransactionKind.INCOME,
        None,
    )


def test_joint_uses_names_and_inflow_patterns_of_members_only() -> None:
    joint = account(Institution.REVOLUT, AccountKind.JOINT)
    stored = [
        MemberPattern(HOUSE, LUIS.id, "*1234"),
        MemberPattern(HOUSE, OUTSIDER, "*9999"),
    ]
    assert kind_of(joint, "Transferencia de ANA PEREZ", True, stored)[1] == str(ANA.id)
    assert kind_of(joint, "Recarga de *1234", True, stored)[1] == str(LUIS.id)
    assert kind_of(joint, "Recarga de *9999", True, stored) == (TransactionKind.INCOME, None)
    assert kind_of(joint, "Revolut**1234*", False, stored) == (TransactionKind.EXPENSE, None)


def test_names_match_whole_words_only() -> None:
    joint = account(Institution.REVOLUT, AccountKind.JOINT)
    assert kind_of(joint, "Transferencia de MARIANA LOPEZ", True) == (TransactionKind.INCOME, None)
    assert kind_of(joint, "Transferencia de ANA LOPEZ", True)[1] == str(ANA.id)


@pytest.mark.parametrize("kind", [AccountKind.JOINT, AccountKind.PERSONAL])
def test_money_from_a_pocket_is_a_savings_transfer_not_income(kind) -> None:
    acc = account(Institution.REVOLUT, kind)
    assert kind_of(acc, "From pocket EUR Viaje", True) == (TransactionKind.SAVINGS_TRANSFER, None)
    assert kind_of(acc, "To pocket EUR Viaje", False) == (TransactionKind.SAVINGS_TRANSFER, None)
