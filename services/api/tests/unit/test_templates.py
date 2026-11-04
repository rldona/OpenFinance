"""OF-1204: plantillas de movimientos."""

from decimal import Decimal
from uuid import uuid4

import pytest

from openfinance.domain.categories import CategoryId
from openfinance.domain.ledger import TransactionKind
from openfinance.domain.shared.ids import AccountId, WorkspaceId
from openfinance.domain.templates import TemplateError, build, from_definition

HOUSE = WorkspaceId(uuid4())
ACCOUNT = AccountId(uuid4())


def make(**kw):
    base = {
        "template_id": uuid4(),
        "household_id": HOUSE,
        "scope": "",
        "name": "Café de la oficina",
        "kind": TransactionKind.EXPENSE,
        "amount": "1,80",
        "description": "Café",
        "account_id": ACCOUNT,
        "category_id": CategoryId(uuid4()),
        "tags": ["trabajo", "#Café"],
        "note": "  con   leche ",
    }
    return build(**{**base, **kw})


class TestBuild:
    def test_normalizes_what_the_client_sent(self) -> None:
        t = make()
        assert t.amount == Decimal("1.80") and t.note == "con leche"
        assert t.tags == ("Café", "trabajo") and not t.personal

    def test_personal_scope(self) -> None:
        assert make(scope=str(uuid4())).personal

    @pytest.mark.parametrize(
        "bad",
        [
            {"name": " "},
            {"name": "x" * 61},
            {"amount": "0"},
            {"amount": "-3"},
            {"amount": "1.234"},
            {"amount": "mucho"},
            {"description": ""},
            {"kind": TransactionKind.SAVINGS_TRANSFER},
            {"kind": TransactionKind.INCOME},
            {"note": "x" * 2001},
            {"tags": ["a|b"]},
            {"tags": [f"t{i}" for i in range(11)]},
        ],
    )
    def test_rejects(self, bad: dict) -> None:
        with pytest.raises(TemplateError):
            make(**bad)

    def test_an_income_has_no_category(self) -> None:
        with pytest.raises(TemplateError):
            make(kind=TransactionKind.INCOME)
        assert make(kind=TransactionKind.INCOME, category_id=None).kind is TransactionKind.INCOME


def test_definition_round_trips() -> None:
    t = make(scope=str(uuid4()))
    assert from_definition(t.id, HOUSE, t.definition()) == t
