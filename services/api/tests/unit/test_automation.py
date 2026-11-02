"""OF-1101: el motor de reglas (función pura)."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from openfinance.domain.automation import (
    AutomationRule,
    Fixed,
    Phase,
    RowView,
    RuleError,
    decide,
    from_definition,
    matches,
    parse_action,
    parse_actions,
    parse_condition,
    parse_conditions,
)
from openfinance.domain.categories import CategoryId
from openfinance.domain.ledger import TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import WorkspaceId

HOUSEHOLD = WorkspaceId(uuid4())
CAT_A, CAT_B, CAT_C = (str(uuid4()) for _ in range(3))
ACCOUNT = str(uuid4())


def view(description="Pago AMAZON PRIME", amount="-14.99", kind=TransactionKind.EXPENSE, **kw):
    return RowView(
        description=description,
        merchant=kw.pop("merchant", "AMAZON PRIME"),
        amount=Money.of(amount, "EUR"),
        kind=kind,
        account_id=kw.pop("account_id", ACCOUNT),
        bank_type=kw.pop("bank_type", "CARD_PAYMENT"),
    )


def rule(
    conditions, actions, *, phase="normal", priority=10, enabled=True, name="r"
) -> AutomationRule:
    return AutomationRule(
        uuid4(), HOUSEHOLD, "", name, Phase(phase), priority, enabled,
        parse_conditions(conditions), parse_actions(actions),
    )  # fmt: skip


def contains(text):
    return {"field": "description", "op": "contains", "value": text}


def set_cat(cat):
    return {"type": "set_category", "value": cat}


class TestConditions:
    @pytest.mark.parametrize(
        ("op", "text", "expected"),
        [
            ("contains", "amazon", True),
            ("contains", "PRIME", True),
            ("contains", "netflix", False),
            ("starts_with", "pago", True),
            ("starts_with", "prime", False),
            ("equals", "pago amazon prime", True),
            ("equals", "amazon", False),
        ],
    )
    def test_text_matching_ignores_case_and_accents(self, op, text, expected) -> None:
        r = rule([{"field": "description", "op": op, "value": text}], [set_cat(CAT_A)])
        assert matches(r, view()) is expected

    def test_accents_are_ignored(self) -> None:
        r = rule([contains("peluquería")], [set_cat(CAT_A)])
        assert matches(r, view("PELUQUERIA MARI")) is True

    def test_amount_is_between_in_absolute_value(self) -> None:
        r = rule([{"field": "amount", "op": "between", "value": ["10", "20"]}], [set_cat(CAT_A)])
        assert matches(r, view(amount="-14.99")) and matches(r, view(amount="14.99"))
        assert not matches(r, view(amount="-9.99")) and not matches(r, view(amount="-20.01"))
        assert matches(r, view(amount="-10.00")) and matches(r, view(amount="-20.00"))

    def test_direction(self) -> None:
        out = rule([{"field": "direction", "op": "is", "value": "expense"}], [set_cat(CAT_A)])
        inn = rule([{"field": "direction", "op": "is", "value": "income"}], [set_cat(CAT_A)])
        assert matches(out, view(amount="-5")) and not matches(inn, view(amount="-5"))
        assert matches(inn, view(amount="5")) and not matches(out, view(amount="5"))

    def test_account_merchant_and_bank_type(self) -> None:
        assert matches(
            rule([{"field": "account", "op": "in", "value": [ACCOUNT]}], [set_cat(CAT_A)]), view()
        )
        assert not matches(
            rule([{"field": "account", "op": "in", "value": [str(uuid4())]}], [set_cat(CAT_A)]),
            view(),
        )
        assert matches(
            rule(
                [{"field": "merchant", "op": "equals", "value": "amazon prime"}], [set_cat(CAT_A)]
            ),
            view(),
        )
        assert matches(
            rule(
                [{"field": "bank_type", "op": "equals", "value": "card_payment"}], [set_cat(CAT_A)]
            ),
            view(),
        )

    def test_all_conditions_must_hold(self) -> None:
        r = rule(
            [contains("amazon"), {"field": "amount", "op": "between", "value": ["100", "200"]}],
            [set_cat(CAT_A)],
        )
        assert matches(r, view()) is False

    @pytest.mark.parametrize(
        "bad",
        [
            {"field": "description", "op": "regex", "value": ".*"},  # sin expresiones regulares
            {"field": "description", "op": "contains", "value": ""},
            {"field": "description", "op": "contains", "value": "x" * 101},
            {"field": "amount", "op": "between", "value": ["20", "10"]},
            {"field": "amount", "op": "between", "value": ["a", "10"]},
            {"field": "amount", "op": "between", "value": ["-5", "10"]},
            {"field": "direction", "op": "is", "value": "sideways"},
            {"field": "account", "op": "in", "value": []},
            {"field": "account", "op": "in", "value": ["no-uuid"]},
            {"field": "weather", "op": "is", "value": "rain"},
        ],
    )
    def test_invalid_conditions(self, bad) -> None:
        with pytest.raises(RuleError):
            parse_condition(bad)

    def test_needs_at_least_one_condition_and_not_too_many(self) -> None:
        with pytest.raises(RuleError):
            parse_conditions([])
        with pytest.raises(RuleError):
            parse_conditions([contains(f"x{i}") for i in range(9)])


class TestActions:
    @pytest.mark.parametrize(
        "bad",
        [
            {"type": "set_category", "value": "no-uuid"},
            {"type": "set_kind", "value": "contribution"},  # lo fija una persona
            {"type": "set_kind", "value": "nada"},
            {"type": "add_tags", "value": []},
            {"type": "add_tags", "value": ["a|b"]},
            {"type": "set_note", "value": " "},
            {"type": "set_note", "value": "x" * 201},
            {"type": "set_merchant", "value": "mercadona 0451 valencia 2"},
            {"type": "delete_everything", "value": 1},
            {"type": "set_amount", "value": "0"},  # nunca el importe
        ],
    )
    def test_invalid_actions(self, bad) -> None:
        with pytest.raises(RuleError):
            parse_action(bad)

    def test_tags_are_cleaned(self) -> None:
        assert parse_action({"type": "add_tags", "value": ["#Viaje", "viaje", "Casa"]}).value == [
            "Casa",
            "Viaje",
        ]


class TestEngine:
    def test_applies_every_action_of_a_matching_rule(self) -> None:
        r = rule(
            [contains("amazon")],
            [
                set_cat(CAT_A),
                {"type": "add_tags", "value": ["suscripción"]},
                {"type": "set_note", "value": "Prime"},
            ],
        )
        d = decide([r], view())
        assert (str(d.category_id), d.tags, d.note, d.fired) == (
            CAT_A,
            ("suscripción",),
            "Prime",
            (r.id,),
        )

    def test_no_match_means_no_change(self) -> None:
        assert decide([rule([contains("netflix")], [set_cat(CAT_A)])], view()).is_empty

    def test_the_first_rule_that_sets_a_field_wins(self) -> None:
        first = rule([contains("amazon")], [set_cat(CAT_A)], priority=5)
        second = rule([contains("amazon")], [set_cat(CAT_B)], priority=10)
        d = decide([second, first], view())  # el orden de entrada da igual: manda la prioridad
        assert str(d.category_id) == CAT_A and d.fired == (first.id,)

    def test_a_later_rule_still_adds_what_the_first_left_free(self) -> None:
        first = rule([contains("amazon")], [set_cat(CAT_A)], priority=5)
        second = rule(
            [contains("amazon")],
            [set_cat(CAT_B), {"type": "add_tags", "value": ["x"]}],
            priority=10,
        )
        d = decide([first, second], view())
        assert str(d.category_id) == CAT_A and d.tags == ("x",) and d.fired == (first.id, second.id)

    def test_phases_run_before_normal_after(self) -> None:
        late = rule([contains("amazon")], [set_cat(CAT_C)], phase="after", priority=1)
        mid = rule([contains("amazon")], [set_cat(CAT_B)], phase="normal", priority=99)
        early = rule([contains("amazon")], [set_cat(CAT_A)], phase="before", priority=99)
        assert str(decide([late, mid, early], view()).category_id) == CAT_A
        assert str(decide([late, mid], view()).category_id) == CAT_B
        assert str(decide([late], view()).category_id) == CAT_C

    def test_the_learned_category_decides_what_no_explicit_rule_did(self) -> None:
        learned = CategoryId(UUID(CAT_B))
        none_match = rule([contains("netflix")], [set_cat(CAT_A)])
        assert decide([none_match], view(), learned_category=learned).category_id == learned
        explicit = rule([contains("amazon")], [set_cat(CAT_A)])
        assert str(decide([explicit], view(), learned_category=learned).category_id) == CAT_A

    def test_an_after_rule_cannot_override_the_learned_category(self) -> None:
        learned = CategoryId(UUID(CAT_B))
        after = rule([contains("amazon")], [set_cat(CAT_C)], phase="after")
        assert decide([after], view(), learned_category=learned).category_id == learned

    def test_what_a_person_fixed_is_never_overwritten(self) -> None:
        r = rule(
            [contains("amazon")],
            [
                set_cat(CAT_A),
                {"type": "set_note", "value": "n"},
                {"type": "add_tags", "value": ["t"]},
            ],
        )
        d = decide([r], view(), Fixed(category=True, note=True))
        assert d.category_id is None and d.note is None and d.tags == ("t",)

    def test_disabled_rules_do_nothing(self) -> None:
        assert decide(
            [rule([contains("amazon")], [set_cat(CAT_A)], enabled=False)], view()
        ).is_empty

    def test_tags_accumulate_without_duplicates_ignoring_case(self) -> None:
        a = rule([contains("amazon")], [{"type": "add_tags", "value": ["Casa"]}], priority=1)
        b = rule(
            [contains("amazon")], [{"type": "add_tags", "value": ["casa", "Ocio"]}], priority=2
        )
        assert decide([a, b], view()).tags == ("Casa", "Ocio")

    def test_set_kind_and_merchant(self) -> None:
        r = rule(
            [contains("amazon")],
            [
                {"type": "set_kind", "value": "internal_transfer"},
                {"type": "set_merchant", "value": "AMAZON"},
            ],
        )
        d = decide([r], view())
        assert (d.kind, d.merchant) == (TransactionKind.INTERNAL_TRANSFER, "AMAZON")

    def test_it_is_idempotent_given_the_same_view(self) -> None:
        r = rule([contains("amazon")], [set_cat(CAT_A), {"type": "add_tags", "value": ["t"]}])
        assert decide([r], view()) == decide([r], view())


class TestDefinition:
    def test_round_trips_through_the_canonical_text(self) -> None:
        r = rule(
            [contains("amazon"), {"field": "amount", "op": "between", "value": ["1,5", "20"]}],
            [set_cat(CAT_A)],
            name="Suscripciones",
            priority=7,
        )
        again = from_definition(r.id, HOUSEHOLD, r.definition())
        assert again == r
        assert r.definition() == again.definition()
        assert Decimal(r.conditions[1].value[0]) == Decimal("1.5")
