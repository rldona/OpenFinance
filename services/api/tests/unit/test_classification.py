"""Clasificación de movimientos importados y patrones por persona."""

from uuid import uuid4

import pytest

from openfinance.domain.imports import (
    ClassificationRules,
    MemberPattern,
    PatternDirection,
    PatternError,
    TransactionKind,
    normalize_member_pattern,
    suggest_kind,
)
from openfinance.domain.shared.ids import UserId, WorkspaceId

RULES = ClassificationRules(
    member_patterns={"ana": ["ANA PEREZ", "*1234"]},
    savings_patterns=["To pocket"],
    internal_patterns=["Traspaso interno"],
    outflow_member_patterns={"ana": ["REVOLUT**"]},
)


@pytest.mark.parametrize(
    ("description", "inflow", "refund", "expected"),
    [
        ("Transferencia de Ana Pérez", True, False, (TransactionKind.CONTRIBUTION, "ana")),
        ("Recarga de *1234", True, False, (TransactionKind.CONTRIBUTION, "ana")),
        ("Bizum de alguien", True, False, (TransactionKind.INCOME, None)),
        ("To pocket EUR Viaje", False, False, (TransactionKind.SAVINGS_TRANSFER, None)),
        ("Traspaso interno", False, False, (TransactionKind.INTERNAL_TRANSFER, None)),
        ("Revolut**9876*", False, False, (TransactionKind.CONTRIBUTION, "ana")),
        ("Mercado", False, False, (TransactionKind.EXPENSE, None)),
        # Una devolución nunca es aportación, aunque el concepto coincida.
        ("Ana Perez tienda", True, True, (TransactionKind.EXPENSE, None)),
        # Una entrada que coincide con un patrón de salida no es aportación.
        ("Revolut**9876*", True, False, (TransactionKind.INCOME, None)),
        # Los patrones se buscan por palabra completa: no dentro de otra palabra o cifra.
        ("Transferencia de MARIANA PEREZ", True, False, (TransactionKind.INCOME, None)),
        ("Recarga de *12345", True, False, (TransactionKind.INCOME, None)),
        ("ANA PEREZ.", True, False, (TransactionKind.CONTRIBUTION, "ana")),
    ],
)
def test_suggest_kind(description, inflow, refund, expected) -> None:
    assert suggest_kind(description, inflow, RULES, is_refund=refund) == expected


def test_outflow_patterns_do_not_apply_to_inflows_of_member_patterns() -> None:
    rules = ClassificationRules(member_patterns={}, outflow_member_patterns={"ana": ["ANA"]})
    assert suggest_kind("Bizum de Ana", True, rules) == (TransactionKind.INCOME, None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("*1234", "*1234"), ("  recarga  de *1234 ", "RECARGA DE *1234"), ("Raúl", "RAUL")],
)
def test_normalize_member_pattern(raw, expected) -> None:
    assert normalize_member_pattern(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "***", "ab", "*12", "x" * 61, "abc\u200bdef\x00"])
def test_rejects_weak_or_invalid_patterns(raw) -> None:
    with pytest.raises(PatternError):
        normalize_member_pattern(raw)


def test_member_pattern_must_be_normalized() -> None:
    h, u = WorkspaceId(uuid4()), UserId(uuid4())
    assert MemberPattern(h, u, "*1234").direction is PatternDirection.INFLOW
    with pytest.raises(PatternError):
        MemberPattern(h, u, "recarga *1234", PatternDirection.OUTFLOW)
