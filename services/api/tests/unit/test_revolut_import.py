from decimal import Decimal
from pathlib import Path

import pytest

from openfinance.domain.imports import ClassificationRules, TransactionKind
from openfinance.domain.shared import Money
from openfinance.infrastructure.importers.revolut import (
    ImportFormatError,
    RevolutProfile,
    parse_revolut_csv,
)

# Muestra sintética con el formato público de Revolut. Sustituir por una muestra real
# anonimizada cuando esté disponible (OF-104).
FIXTURE = Path(__file__).parents[1] / "fixtures" / "revolut_joint_synthetic.csv"

PROFILE = RevolutProfile(
    account_key="revolut-conjunta",
    rules=ClassificationRules(
        member_patterns={"Raúl": ["Raul Lopez"], "Elena": ["Elena Martin"]},
        savings_patterns=["To pocket"],
    ),
)


@pytest.fixture
def result():
    return parse_revolut_csv(FIXTURE.read_bytes(), PROFILE)


def test_imports_completed_rows_of_the_current_account(result) -> None:
    assert len(result.rows) == 10
    assert [s.reason for s in result.skipped] == [
        "producto savings (hucha o ahorro)",
        "pendiente: se importará cuando se complete",
        "revertida por el banco",
    ]


def test_amounts_are_exact_and_include_fees(result) -> None:
    by_line = {r.line: r for r in result.rows}
    assert by_line[6].amount == Money.of("-87.34", "EUR")
    assert by_line[9].amount == Money.of("-51.50", "EUR")
    assert all(isinstance(r.amount.amount, Decimal) for r in result.rows)


def test_running_balance_matches_bank(result) -> None:
    assert result.balance_mismatches == []


def test_suggests_kinds(result) -> None:
    kinds = {r.line: (r.suggested_kind, r.member) for r in result.rows}
    assert kinds[2] == (TransactionKind.CONTRIBUTION, "Raúl")
    assert kinds[3] == (TransactionKind.CONTRIBUTION, "Elena")
    assert kinds[4] == (TransactionKind.SAVINGS_TRANSFER, None)
    assert kinds[6] == (TransactionKind.EXPENSE, None)
    assert kinds[10] == (TransactionKind.EXPENSE, None)  # devolución: gasto positivo
    assert kinds[13] == (TransactionKind.INCOME, None)


def test_dates_and_quoted_descriptions(result) -> None:
    last = result.rows[-1]
    assert last.description == "Iberdrola, S.A."
    assert last.booked_at.isoformat() == "2026-10-10T18:45:10"
    assert str(last.value_date) == "2026-10-11"


def test_identical_rows_in_same_file_are_not_merged(result) -> None:
    cafes = [r for r in result.rows if r.description == "Café Central"]
    assert len(cafes) == 2
    assert cafes[0].fingerprint != cafes[1].fingerprint


def test_fingerprints_are_stable_across_imports(result) -> None:
    again = parse_revolut_csv(FIXTURE.read_text(encoding="utf-8"), PROFILE)
    assert [r.fingerprint for r in again.rows] == [r.fingerprint for r in result.rows]


def test_fingerprint_depends_on_account() -> None:
    other = RevolutProfile(account_key="otra-cuenta", rules=PROFILE.rules)
    a = parse_revolut_csv(FIXTURE.read_bytes(), PROFILE).rows[0]
    b = parse_revolut_csv(FIXTURE.read_bytes(), other).rows[0]
    assert a.fingerprint != b.fingerprint


def test_detects_missing_rows_through_balance() -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    without_mercadona = "\n".join(line for line in lines if "Mercadona" not in line)
    result = parse_revolut_csv(without_mercadona, PROFILE)
    assert len(result.balance_mismatches) == 1
    assert result.balance_mismatches[0].reported == Money.of("2710.86", "EUR")


def test_accepts_utf8_bom() -> None:
    result = parse_revolut_csv(b"\xef\xbb\xbf" + FIXTURE.read_bytes(), PROFILE)
    assert len(result.rows) == 10


def test_rejects_other_formats() -> None:
    with pytest.raises(ImportFormatError, match="faltan las columnas"):
        parse_revolut_csv("Fecha;Concepto;Importe\n01/10/2026;Algo;-1,00\n", PROFILE)


def test_invalid_row_is_skipped_not_fatal() -> None:
    header = FIXTURE.read_text(encoding="utf-8").splitlines()[0]
    bad = f"{header}\nCARD_PAYMENT,Current,ayer,,Tienda,-1.00,0,EUR,COMPLETED,1.00\n"
    result = parse_revolut_csv(bad, PROFILE)
    assert result.rows == []
    assert result.skipped[0].reason.startswith("fila no válida: fecha no válida")
