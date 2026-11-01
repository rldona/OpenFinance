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
# Huella de la primera fila de la muestra: si cambia, las importaciones ya guardadas se duplicarían.
FIRST_FINGERPRINT = "54bf843dc07c2532cf9c715b8d46c83d4e6f3ab183c6043703b9ef4e1c82ac36"

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


def test_zero_and_missing_amounts_are_skipped_without_breaking_the_balance() -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    when = "2026-10-12 09:00:00,2026-10-12 09:00:01"
    extra = [
        f"CARD_PAYMENT,Current,{when},Card check,0.00,0.00,EUR,COMPLETED,2619.69",
        f"CARD_PAYMENT,Current,{when},No amount,,0.00,EUR,COMPLETED,2619.69",
    ]
    result = parse_revolut_csv("\n".join([*lines, *extra]), PROFILE)
    assert len(result.rows) == 10
    reasons = {s.description: s.reason for s in result.skipped}
    assert reasons["Card check"] == "importe cero: no mueve dinero"
    assert reasons["No amount"] == "fila no válida: falta el importe"
    assert result.balance_mismatches == []


def test_from_pocket_is_a_savings_transfer_and_keeps_the_balance() -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    when = "2026-10-12 09:00:00,2026-10-12 09:00:01"
    extra = f"TRANSFER,Current,{when},From pocket EUR Viaje,100.00,0.00,EUR,COMPLETED,2719.69"
    profile = RevolutProfile(
        "revolut-conjunta", ClassificationRules(savings_patterns=["To pocket", "From pocket"])
    )
    result = parse_revolut_csv("\n".join([*lines, extra]), profile)
    back = result.rows[-1]
    assert (back.suggested_kind, back.amount) == (
        TransactionKind.SAVINGS_TRANSFER,
        Money.of("100.00", "EUR"),
    )
    assert result.balance_mismatches == []


def test_fingerprints_do_not_depend_on_classification_rules(result) -> None:
    # Cambiar cómo se clasifica no puede cambiar las huellas ya guardadas (OF-602).
    other = RevolutProfile(account_key=PROFILE.account_key, rules=ClassificationRules())
    again = parse_revolut_csv(FIXTURE.read_bytes(), other)
    assert [r.fingerprint for r in again.rows] == [r.fingerprint for r in result.rows]
    assert result.rows[0].fingerprint == FIRST_FINGERPRINT


def test_thousands_in_the_english_csv_are_never_read_as_decimals() -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    when = "2026-10-12 09:00:00,2026-10-12 09:00:01"
    extra = (
        f'TRANSFER,Current,{when},Transferencia de alguien,"1,234",0.00,EUR,COMPLETED,"3,853.69"'
    )
    result = parse_revolut_csv("\n".join([*lines, extra]), PROFILE)
    assert result.rows[-1].amount == Money.of("1234", "EUR")
    assert result.balance_mismatches == []
