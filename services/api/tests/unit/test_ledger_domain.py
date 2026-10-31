from datetime import date, datetime
from uuid import uuid4

import pytest

from openfinance.domain.categories import CategoryId
from openfinance.domain.identity import InvalidUserError, normalize_email, validate_password
from openfinance.domain.ledger import (
    Account,
    AccountKind,
    Institution,
    LedgerError,
    Transaction,
    TransactionKind,
    account_balance,
    summarize,
)
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId, TransactionId, UserId, WorkspaceId

EUR = Currency("EUR")
HOUSE = WorkspaceId(uuid4())
RAUL = UserId(uuid4())
ELENA = UserId(uuid4())


def account(kind=AccountKind.JOINT, owner=None, opening="100.00") -> Account:
    return Account(
        id=AccountId(uuid4()),
        household_id=HOUSE,
        name="Cuenta",
        institution=Institution.REVOLUT,
        kind=kind,
        currency=EUR,
        opening_balance=Money.of(opening, EUR),
        owner_id=owner,
    )


JOINT = account()


SUPER = CategoryId(uuid4())


def tx(amount: str, kind=TransactionKind.EXPENSE, member=None, acc=JOINT, category=None):
    return Transaction(
        id=TransactionId(uuid4()),
        household_id=HOUSE,
        account_id=acc.id,
        booked_at=datetime(2026, 10, 5, 12, 0),  # noqa: DTZ001
        value_date=date(2026, 10, 5),
        description="x",
        amount=Money.of(amount, EUR),
        kind=kind,
        member_id=member,
        category_id=category,
    )


MONTH = [
    tx("1600.00", TransactionKind.CONTRIBUTION, RAUL),
    tx("1400.00", TransactionKind.CONTRIBUTION, ELENA),
    tx("-300.00", TransactionKind.SAVINGS_TRANSFER),
    tx("-87.34", category=SUPER),
    tx("-51.50"),
    tx("23.99", category=SUPER),  # devolución
    tx("22.50", TransactionKind.INCOME),
    tx("-40.00", TransactionKind.INTERNAL_TRANSFER),
]


class TestSummary:
    def test_transfers_and_savings_are_not_spending(self) -> None:
        s = summarize(MONTH, EUR)
        assert s.spent == Money.of("114.85", EUR)  # 87.34 + 51.50 - 23.99

    def test_contributions_count_as_inflow(self) -> None:
        s = summarize(MONTH, EUR)
        assert s.contributions == Money.of("3000.00", EUR)
        assert s.inflow == Money.of("3022.50", EUR)

    def test_savings_transfer_is_tracked_as_saving(self) -> None:
        assert summarize(MONTH, EUR).saved_to_savings == Money.of("300.00", EUR)

    def test_saved_is_inflow_minus_spent(self) -> None:
        assert summarize(MONTH, EUR).saved == Money.of("2907.65", EUR)

    def test_contribution_leaving_a_personal_account_is_not_inflow(self) -> None:
        personal = account(AccountKind.PERSONAL, owner=RAUL)
        out = tx("-1600.00", TransactionKind.CONTRIBUTION, RAUL, acc=personal)
        assert summarize([out], EUR).inflow.is_zero
        assert summarize([out], EUR).spent.is_zero


def test_balance_is_opening_plus_movements() -> None:
    assert account_balance(JOINT, MONTH) == Money.of("2667.65", EUR)


def test_balance_rejects_movements_of_other_accounts() -> None:
    with pytest.raises(LedgerError):
        account_balance(account(), MONTH)


class TestAccounts:
    def test_personal_account_needs_owner(self) -> None:
        with pytest.raises(LedgerError, match="titular"):
            account(AccountKind.PERSONAL)

    def test_joint_account_has_no_owner(self) -> None:
        with pytest.raises(LedgerError):
            account(AccountKind.JOINT, owner=RAUL)

    def test_opening_balance_currency_must_match(self) -> None:
        with pytest.raises(LedgerError):
            Account(
                AccountId(uuid4()), HOUSE, "C", Institution.OTHER, AccountKind.JOINT,
                EUR, Money.of(1, "USD"),
            )  # fmt: skip

    def test_visibility(self) -> None:
        personal = account(AccountKind.PERSONAL, owner=RAUL)
        assert personal.visible_to(RAUL)
        assert not personal.visible_to(ELENA)
        assert JOINT.visible_to(ELENA)
        assert account(AccountKind.SAVINGS).visible_to(ELENA)


class TestTransactions:
    def test_contribution_needs_member(self) -> None:
        with pytest.raises(LedgerError, match="de quién"):
            tx("10.00", TransactionKind.CONTRIBUTION)

    def test_only_contributions_have_member(self) -> None:
        with pytest.raises(LedgerError):
            tx("-10.00", member=RAUL)

    def test_only_expenses_have_category(self) -> None:
        with pytest.raises(LedgerError, match="categoría"):
            tx("-300.00", TransactionKind.SAVINGS_TRANSFER, category=SUPER)

    def test_merchant_is_derived_from_description(self) -> None:
        t = Transaction(
            id=TransactionId(uuid4()),
            household_id=HOUSE,
            account_id=JOINT.id,
            booked_at=datetime(2026, 10, 5, 12, 0),  # noqa: DTZ001
            value_date=date(2026, 10, 5),
            description="COMPRA TARJETA 4821 MERCADONA 1234",
            amount=Money.of("-1.00", EUR),
            kind=TransactionKind.EXPENSE,
        )
        assert t.merchant == "MERCADONA"

    def test_zero_amount_is_rejected(self) -> None:
        with pytest.raises(LedgerError):
            tx("0.00")

    def test_uncategorized_only_applies_to_expenses(self) -> None:
        assert tx("-5.00").is_uncategorized
        assert not tx("-5.00", category=SUPER).is_uncategorized
        assert not tx("-5.00", TransactionKind.SAVINGS_TRANSFER).is_uncategorized


class TestIdentity:
    def test_email_is_normalized(self) -> None:
        assert normalize_email("  Raul@Example.ORG ") == "raul@example.org"

    @pytest.mark.parametrize("bad", ["", "raul", "raul@", "a b@c.d"])
    def test_invalid_email(self, bad: str) -> None:
        with pytest.raises(InvalidUserError):
            normalize_email(bad)

    def test_password_length(self) -> None:
        with pytest.raises(InvalidUserError):
            validate_password("corta")
        validate_password("suficientemente-larga")


def test_safe_filename() -> None:
    from openfinance.domain.imports.batch import safe_filename

    assert safe_filename("C:\\Users\\raul\\extracto.csv") == "extracto.csv"
    assert safe_filename("../../etc/pass\x00wd\n.csv") == "passwd.csv"
    assert safe_filename("   ") == "extracto"
    assert len(safe_filename("a" * 500)) == 150
