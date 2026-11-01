"""OF-107: extracto de Bankinter en Excel. Datos sintéticos (cuenta e importes inventados)."""

import pytest

from openfinance.domain.imports import ClassificationRules, TransactionKind
from openfinance.domain.ledger import Institution
from openfinance.domain.shared import Money
from openfinance.infrastructure.importers import StatementParserRegistry
from openfinance.infrastructure.importers.bankinter import parse_bankinter
from openfinance.infrastructure.importers.common import ImportFormatError
from tests.xlsx_factory import make_xlsx

FAKE_IBAN = "ES9100000000000000000000"
RULES = ClassificationRules(outflow_member_patterns={"titular": ["REVOLUT**"]})
HEADER = ["Fecha contable", "Fecha valor", "Descripción", "Importe", "Saldo", "Divisa"]

# Del más antiguo al más reciente; el archivo los lista al revés.
MOVEMENTS = [
    ["01/10/2026", "01/10/2026", "TRANS /EMPRESA FICTICIA NOMINA", 2000, 3000, "EUR"],
    ["01/10/2026", "01/10/2026", "Revolut**1234*", -1500, 1500, "EUR"],
    ["02/10/2026", "02/10/2026", "CAFE INVENTADO       02/10/26", -1.8, 1498.2, "EUR"],
    ["02/10/2026", "02/10/2026", "CAFE INVENTADO       02/10/26", -1.8, 1496.4, "EUR"],
    ["03/10/2026", "02/10/2026", "BIZUM DE PERSONA FICTICIA", 20, 1516.4, "EUR"],
    ["03/10/2026", "03/10/2026", "BIZUM A PERSONA FICTICIA", -10.0, 1506.4, "EUR"],
]


def statement(movements: list[list[object]], pending: bool = True) -> bytes:
    rows: list[list[object]] = [[f"MOVIMIENTOS DE LA CUENTA {FAKE_IBAN}"], []]
    if pending:
        rows += [
            ["MOVIMIENTOS PENDIENTES -12,50 EUR"],
            [],
            ["Fecha", "Descripción", "Importe", "Divisa"],
            ["04/10/2026", "TIENDA PENDIENTE     04/10/26", -12.5, "EUR"],
        ]
    rows += [
        [],
        ["MOVIMIENTOS"],
        ["Concepto", "-"],
        ["Fecha", "01/10/2026 - 03/10/2026"],
        ["Tipo de movimiento", "-"],
        ["Importe", "Desde 0,00 hasta -"],
        [],
        HEADER,
        *reversed(movements),
    ]
    return make_xlsx(rows, sheet="Movimientos")


@pytest.fixture
def result():
    return parse_bankinter(statement(MOVEMENTS), "bankinter-titular", RULES)


def test_rows_come_out_oldest_first_and_reconcile(result) -> None:
    assert [r.description for r in result.rows][:2] == [
        "TRANS /EMPRESA FICTICIA NOMINA",
        "Revolut**1234*",
    ]
    assert result.balance_mismatches == []
    assert result.closing_balance == Money.of("1506.40", "EUR")


def test_dates_and_amounts(result) -> None:
    bizum = result.rows[4]
    assert bizum.booked_at.isoformat() == "2026-10-03T00:00:00"
    assert bizum.value_date.isoformat() == "2026-10-02"
    assert bizum.amount == Money.of("20.00", "EUR")
    assert result.rows[2].amount == Money.of("-1.80", "EUR")
    assert all(r.bank_type == "" for r in result.rows)


def test_pending_rows_are_skipped_with_a_reason(result) -> None:
    assert [(s.reason, s.description) for s in result.skipped] == [
        ("pendiente: se importará cuando se contabilice", "TIENDA PENDIENTE     04/10/26")
    ]


def test_kinds(result) -> None:
    assert [(r.suggested_kind, r.member) for r in result.rows] == [
        (TransactionKind.INCOME, None),
        (TransactionKind.CONTRIBUTION, "titular"),
        (TransactionKind.EXPENSE, None),
        (TransactionKind.EXPENSE, None),
        (TransactionKind.INCOME, None),
        (TransactionKind.EXPENSE, None),
    ]


def test_identical_rows_on_the_same_day_are_not_merged(result) -> None:
    cafes = [r for r in result.rows if r.description.startswith("CAFE")]
    assert len(cafes) == 2
    assert cafes[0].fingerprint != cafes[1].fingerprint


def test_overlapping_statement_reuses_fingerprints(result) -> None:
    later = [*MOVEMENTS[2:], ["04/10/2026", "04/10/2026", "TIENDA", -12.5, 1493.9, "EUR"]]
    again = parse_bankinter(statement(later, pending=False), "bankinter-titular", RULES)
    first = {r.fingerprint for r in result.rows}
    second = [r.fingerprint for r in again.rows]
    assert [f in first for f in second] == [True, True, True, True, False]
    assert again.balance_mismatches == []
    assert again.skipped == []


def test_detects_a_missing_row_through_the_balance() -> None:
    without = [m for i, m in enumerate(MOVEMENTS) if i != 2]
    result = parse_bankinter(statement(without), "k", RULES)
    assert len(result.balance_mismatches) == 1


def test_account_number_never_leaks() -> None:
    result = parse_bankinter(statement(MOVEMENTS), "k", RULES)
    texts = [s.reason + s.description for s in result.skipped]
    texts += [r.description for r in result.rows]
    assert not any(FAKE_IBAN in t for t in texts)
    with pytest.raises(ImportFormatError) as exc:
        parse_bankinter(make_xlsx([[f"MOVIMIENTOS DE LA CUENTA {FAKE_IBAN}"]]), "k", RULES)
    assert FAKE_IBAN not in str(exc.value)


def test_invalid_row_is_skipped_without_echoing_values() -> None:
    bad = [*MOVEMENTS, [FAKE_IBAN, "", "RARA", "abc", 1, "EUR"]]
    result = parse_bankinter(statement(bad), "k", RULES)
    invalid = [s for s in result.skipped if s.reason.startswith("fila no válida")]
    assert [s.description for s in invalid] == ["RARA"]
    assert FAKE_IBAN not in invalid[0].reason


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"Fecha;Concepto;Importe\n01/10/2026;x;-1,00\n", "No es un archivo Excel"),
        (bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 64, r"\.xlsx"),
    ],
)
def test_only_xlsx_is_accepted(content, message) -> None:
    with pytest.raises(ImportFormatError, match=message):
        parse_bankinter(content, "k", RULES)


def test_is_registered_for_bankinter() -> None:
    assert StatementParserRegistry().get(Institution.BANKINTER) is parse_bankinter


@pytest.mark.parametrize("amount", [1e300, "1E+50"])
def test_absurd_amount_is_a_skipped_row(amount) -> None:
    bad = [*MOVEMENTS, ["04/10/2026", "04/10/2026", "ENORME", amount, 1, "EUR"]]
    result = parse_bankinter(statement(bad), "k", RULES)
    assert [s.description for s in result.skipped if "importe" in s.reason] == ["ENORME"]


def test_zero_and_missing_amounts_are_skipped_without_breaking_the_balance() -> None:
    extra = [
        ["04/10/2026", "04/10/2026", "VERIFICACION TARJETA", 0, 1506.4, "EUR"],
        ["04/10/2026", "04/10/2026", "SIN IMPORTE", None, 1506.4, "EUR"],
    ]
    result = parse_bankinter(statement([*MOVEMENTS, *extra]), "k", RULES)
    assert len(result.rows) == len(MOVEMENTS)
    reasons = {s.description: s.reason for s in result.skipped}
    assert reasons["VERIFICACION TARJETA"] == "importe cero: no mueve dinero"
    assert reasons["SIN IMPORTE"] == "fila no válida: falta el importe"
    assert result.balance_mismatches == []
