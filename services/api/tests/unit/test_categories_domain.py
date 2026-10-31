from uuid import uuid4

import pytest

from openfinance.domain.categories import (
    HOUSEHOLD_SCOPE,
    Category,
    CategoryError,
    CategoryId,
    CategoryRule,
    best_rule,
    can_learn,
    merchant_key,
    merchant_label,
    rule_matches,
)
from openfinance.domain.shared.ids import WorkspaceId

HOUSE = WorkspaceId(uuid4())


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("MERCADONA 1234", "MERCADONA"),
        ("MERCADONA 0087", "MERCADONA"),
        ("COMPRA TARJETA 4821 MERCADONA", "MERCADONA"),
        ("NETFLIX.COM 866-579", "NETFLIX"),
        ("SPOTIFY P2F1A8C", "SPOTIFY"),
        ("Iberdrola, S.A.", "IBERDROLA"),
        ("AMAZON EU SARL", "AMAZON"),
        ("Café Central", "CAFE CENTRAL"),
        ("Cash at Cajero Plaza Mayor", "CAJERO PLAZA MAYOR"),
        ("RESTAURANTE LA PEPICA VALENCIA", "RESTAURANTE LA PEPICA"),
        ("12345", ""),
        ("PAGO MERCADONA", "MERCADONA"),
        ("PAGO CON TARJETA MERCADONA", "MERCADONA"),
        ("COMPRA EN MERCADONA", "MERCADONA"),
        ("RECIBO DE IBERDROLA CLIENTES", "IBERDROLA CLIENTES"),
        ("PAGO CON TARJETA", ""),
        ("TARJETA 1234", ""),
        ("TOLEDO PARKING", "TOLEDO PARKING"),
    ],
)
def test_merchant_key(description: str, expected: str) -> None:
    assert merchant_key(description) == expected


def test_merchant_label() -> None:
    assert merchant_label("CAFE CENTRAL") == "Cafe Central"


def test_rule_matches_when_rule_is_the_start_of_the_merchant() -> None:
    assert rule_matches("MERCADONA", "MERCADONA")
    assert rule_matches("MERCADONA", "MERCADONA VALENCIA")
    assert not rule_matches("MERCADONA VALENCIA", "MERCADONA")
    assert not rule_matches("MERCADONA", "MERCADERIAS LOPEZ")
    assert not rule_matches("RESTAURANTE LA PEPICA", "RESTAURANTE EL FARO")
    assert not rule_matches("", "MERCADONA")


@pytest.mark.parametrize(
    ("rule", "merchant"),
    [
        ("GAS", "GAS NATURAL"),
        ("BAR", "BAR CENTRAL"),
        ("PAYPAL", "PAYPAL SPOTIFY"),
        ("AMAZON", "AMAZON PRIME VIDEO"),
        ("PAYPAL SPOTIFY", "PAYPAL"),
    ],
)
def test_short_or_broad_rules_only_match_exactly(rule: str, merchant: str) -> None:
    assert not rule_matches(rule, merchant)
    assert rule_matches(rule, rule)


def test_can_learn() -> None:
    assert can_learn("MERCADONA")
    assert can_learn("BAR CENTRAL")
    assert not can_learn("")
    assert not can_learn("BAR")
    assert not can_learn("PAYPAL")


def test_best_rule_prefers_exact_then_most_specific() -> None:
    a, b = CategoryId(uuid4()), CategoryId(uuid4())
    general = CategoryRule(HOUSE, "EL CORTE", a)
    specific = CategoryRule(HOUSE, "EL CORTE INGLES", b)
    assert best_rule([general, specific], "EL CORTE INGLES") is specific
    assert best_rule([general, specific], "EL CORTE") is general
    assert best_rule([general], "LIDL") is None


def test_best_rule_prefers_personal_on_tie() -> None:
    a, b = CategoryId(uuid4()), CategoryId(uuid4())
    household = CategoryRule(HOUSE, "ZARA", a)
    personal = CategoryRule(HOUSE, "ZARA", b, scope="user-1")
    assert best_rule([household, personal], "ZARA") is personal
    assert household.scope == HOUSEHOLD_SCOPE


@pytest.mark.parametrize(
    ("name", "icon", "color"),
    [("", "x", "#000000"), (" a", "x", "#000000"), ("a", "", "#000000"), ("a", "x", "red")],
)
def test_invalid_categories(name: str, icon: str, color: str) -> None:
    with pytest.raises(CategoryError):
        Category(CategoryId(uuid4()), HOUSE, name, icon, color)


def test_category_key_ignores_case_and_accents() -> None:
    c = Category(CategoryId(uuid4()), HOUSE, "Café y Té", "☕", "#000000")
    assert c.key == "CAFE Y TE"
