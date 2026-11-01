"""OF-104: extracto de Revolut en Excel (exportación en español). Datos sintéticos."""

# ruff: noqa: DTZ001 - los extractos traen hora local, sin zona

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from openfinance.domain.imports import ClassificationRules, TransactionKind
from openfinance.domain.shared import Money
from openfinance.infrastructure.importers.revolut import (
    ImportFormatError,
    RevolutProfile,
    parse_revolut,
    parse_revolut_csv,
)
from tests.xlsx_factory import make_xlsx

CSV_FIXTURE = Path(__file__).parents[1] / "fixtures" / "revolut_joint_synthetic.csv"

# Cabeceras tal como llegan: algunas con la codificación rota.
HEADER = [
    "Tipo",
    "Producto",
    "Fecha de inicio",
    "Fecha de finalizaciÃ³n",
    "DescripciÃ³n",
    "Importe",
    "ComisiÃ³n",
    "Divisa",
    "State",
    "Saldo",
]

RULES = ClassificationRules(
    member_patterns={"ana": ["ANA PEREZ", "*1234"], "luis": ["LUIS GARCIA"]},
    savings_patterns=["To pocket"],
)
PROFILE = RevolutProfile(account_key="conjunta", rules=RULES)


def d(day: int, hour: int, minute: int = 0, second: int = 0, micro: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, second, micro)


ROWS = [
    ["Transferir", "Actual", d(1, 8), d(1, 8, 0, 3), "Transferencia de ANA PEREZ", 1000.0, 0.0, "EUR", "COMPLETADO", 1100.0],  # noqa: E501
    ["Recargas", "Actual", d(1, 9), d(1, 9, 0, 1), "Recarga de *1234", 500.0, 0.0, "EUR", "COMPLETADO", 1600.0],  # noqa: E501
    # Empezó antes que la anterior pero terminó después: el saldo cuadra en orden de fin.
    ["Pago con tarjeta", "Actual", d(1, 7), d(2, 10), "Supermercado Sintético", -87.34, 0.0, "EUR", "COMPLETADO", 1512.66],  # noqa: E501
    ["Pago con tarjeta", "Actual", d(3, 12), d(4, 9), "Tienda Ficticia", 23.99, 0.0, "EUR", "COMPLETADO", 1536.65],  # noqa: E501
    ["Transferir", "Actual", d(4, 7, 59, 59, 999_990), d(4, 8), "To pocket EUR Viaje", -300.0, 0.0, "EUR", "COMPLETADO", 1236.65],  # noqa: E501
    ["Transferir", "Actual", d(5, 10), d(5, 10), "Transferencia de Persona Ajena", 22.5, 0.0, "EUR", "COMPLETADO", 1259.15],  # noqa: E501
    ["Pago con tarjeta", "Actual", d(6, 21), d(6, 21), "Caf? Ficticio", -3.2, 0.0, "EUR", "COMPLETADO", 1255.95],  # noqa: E501
    # Pendientes: sin fecha de fin ni saldo (fila más corta).
    ["Pago con tarjeta", "Actual", d(7, 20), None, "Restaurante Inventado", -25.4, 0.0, "EUR", "PENDIENTE"],  # noqa: E501
]  # fmt: skip


@pytest.fixture
def result():
    return parse_revolut(make_xlsx([HEADER, *ROWS]), PROFILE)


def test_reads_completed_rows_in_file_order(result) -> None:
    assert [r.line for r in result.rows] == [2, 3, 4, 5, 6, 7, 8]
    assert [(s.line, s.reason) for s in result.skipped] == [
        (9, "pendiente: se importará cuando se complete")
    ]


def test_balance_reconciles_in_file_order(result) -> None:
    assert result.balance_mismatches == []
    assert result.closing_balance == Money.of("1255.95", "EUR")


def test_amounts_are_exact_decimals(result) -> None:
    amounts = [r.amount for r in result.rows]
    assert amounts[2] == Money.of("-87.34", "EUR")
    assert amounts[6] == Money.of("-3.20", "EUR")
    assert all(isinstance(a.amount, Decimal) for a in amounts)


def test_repairs_header_and_rounds_excel_seconds(result) -> None:
    pocket = result.rows[4]
    assert pocket.booked_at == d(4, 8)
    assert pocket.value_date.isoformat() == "2026-10-04"


def test_suggested_kinds(result) -> None:
    kinds = [(r.suggested_kind, r.member) for r in result.rows]
    assert kinds == [
        (TransactionKind.CONTRIBUTION, "ana"),
        (TransactionKind.CONTRIBUTION, "ana"),  # «Recarga de *1234» con su patrón
        (TransactionKind.EXPENSE, None),
        (TransactionKind.EXPENSE, None),  # pago con tarjeta positivo = devolución
        (TransactionKind.SAVINGS_TRANSFER, None),
        (TransactionKind.INCOME, None),
        (TransactionKind.EXPENSE, None),
    ]
    assert result.rows[3].amount.amount > 0
    assert result.rows[0].bank_type == "TRANSFERIR"


def test_topup_without_pattern_is_income() -> None:
    plain = RevolutProfile(account_key="conjunta", rules=ClassificationRules())
    rows = parse_revolut(make_xlsx([HEADER, *ROWS]), plain).rows
    assert rows[1].suggested_kind is TransactionKind.INCOME


def test_unrecoverable_characters_are_kept_as_they_come(result) -> None:
    assert result.rows[6].description == "Caf? Ficticio"


def test_header_with_correct_accents_is_also_accepted() -> None:
    header = [h.replace("Ã³", "ó") for h in HEADER]
    assert len(parse_revolut(make_xlsx([header, *ROWS]), PROFILE).rows) == 7


def test_missing_columns_is_a_format_error() -> None:
    with pytest.raises(ImportFormatError, match="faltan las columnas"):
        parse_revolut(make_xlsx([["Fecha", "Concepto"], [d(1, 1), "x"]]), PROFILE)


def _as_xlsx(csv_text: str) -> bytes:
    rows = list(csv.reader(csv_text.splitlines()))
    out: list[list[object]] = [HEADER]
    for row in rows[1:]:
        typ, prod, start, end, desc, amount, fee, cur, state, balance = row
        out.append(
            [
                typ,
                prod,
                datetime.fromisoformat(start),
                datetime.fromisoformat(end) if end else None,
                desc,
                float(amount),
                float(fee),
                cur,
                state,
                float(balance) if balance else None,
            ]
        )
    return make_xlsx(out)


def test_same_statement_in_csv_and_xlsx_has_the_same_fingerprints() -> None:
    text = CSV_FIXTURE.read_text(encoding="utf-8")
    from_csv = parse_revolut_csv(text, PROFILE)
    from_xlsx = parse_revolut(_as_xlsx(text), PROFILE)
    assert [r.fingerprint for r in from_xlsx.rows] == [r.fingerprint for r in from_csv.rows]
    assert [r.amount for r in from_xlsx.rows] == [r.amount for r in from_csv.rows]
    assert from_xlsx.balance_mismatches == []


CSV_HEADER = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance"
)


def csv_row(description: str, amount: str = "-1.00", balance: str = "99.00") -> str:
    return (
        f"CARD_PAYMENT,Current,2026-10-01 10:00:00,2026-10-01 10:00:01,"
        f"{description},{amount},0,EUR,COMPLETED,{balance}"
    )


def test_csv_text_is_never_repaired_so_its_fingerprints_do_not_change() -> None:
    from openfinance.domain.imports import fingerprint

    raw = "SÃ£o Tienda"  # se repararía como «São Tienda»
    row = parse_revolut_csv(f"{CSV_HEADER}\n{csv_row(raw)}\n", PROFILE).rows[0]
    assert row.description == raw
    when = datetime(2026, 10, 1, 10, 0, 0)
    assert row.fingerprint == fingerprint("conjunta", when, Money.of("-1.00", "EUR"), raw, 0)


def test_xlsx_text_is_repaired() -> None:
    rows = [[*ROWS[0][:4], "SÃ£o Tienda", *ROWS[0][5:]]]
    assert parse_revolut(make_xlsx([HEADER, *rows]), PROFILE).rows[0].description == "São Tienda"


def test_csv_stops_after_max_rows(monkeypatch) -> None:
    from openfinance.infrastructure.importers import common

    monkeypatch.setattr(common, "MAX_ROWS", 3)
    body = "\n".join(csv_row(f"Tienda {i}") for i in range(3))
    with pytest.raises(ImportFormatError, match="supera las 3 filas"):
        parse_revolut_csv(f"{CSV_HEADER}\n{body}\n", PROFILE)


def test_csv_blank_lines_do_not_count_nor_accumulate(monkeypatch) -> None:
    from openfinance.infrastructure.importers import common

    monkeypatch.setattr(common, "MAX_ROWS", 3)
    text = CSV_HEADER + "\n" * 200_000 + csv_row("Tienda") + "\n" + "\n" * 200_000
    result = parse_revolut_csv(text, PROFILE)
    assert len(result.rows) == 1
    assert result.rows[0].line == 200_001


def test_csv_extra_columns_are_cut() -> None:
    text = f"{CSV_HEADER}\n{csv_row('Tienda')}{',x' * 5000}\n"
    assert len(parse_revolut_csv(text, PROFILE).rows) == 1


@pytest.mark.parametrize("amount", ["1E+50", "1e-999999", "10000000000000000"])
def test_absurd_csv_amount_is_a_skipped_row(amount) -> None:
    result = parse_revolut_csv(f"{CSV_HEADER}\n{csv_row('Tienda', amount)}\n", PROFILE)
    assert result.rows == []
    assert result.skipped[0].reason == "fila no válida: importe no válido"


def test_absurd_xlsx_amount_is_a_skipped_row() -> None:
    rows = [[*ROWS[0][:5], 1e50, *ROWS[0][6:]]]
    result = parse_revolut(make_xlsx([HEADER, *rows]), PROFILE)
    assert result.rows == []
    assert result.skipped[0].reason == "fila no válida: importe no válido"


def test_csv_full_of_blank_lines_stays_small_in_memory() -> None:
    import tracemalloc

    content = (CSV_HEADER + "\n" * (512 * 1024)).encode()
    tracemalloc.start()
    try:
        result = parse_revolut_csv(content, PROFILE)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.rows == []
    # Acumular una lista por línea vacía pasaría de 50 MB; en streaming es el texto y poco más.
    assert peak < 10 * 1024 * 1024
