"""Lectura segura de Excel y utilidades comunes de los lectores."""

# ruff: noqa: DTZ001 - los extractos traen hora local, sin zona

import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal

import openpyxl
import pytest

from openfinance.infrastructure.importers import xlsx
from openfinance.infrastructure.importers.common import (
    ImportFormatError,
    find_header_row,
    repair_mojibake,
    to_decimal,
)
from tests.xlsx_factory import make_xlsx


def test_openpyxl_parses_xml_with_defusedxml() -> None:
    assert openpyxl.DEFUSEDXML is True


def test_reads_cells_as_exact_decimals_and_rounded_datetimes() -> None:
    content = make_xlsx(
        [
            ["Fecha", "Importe", "Texto", "Entero", "Día"],
            [datetime(2026, 10, 1, 9, 59, 59, 999990), -12.3, "Café", 7, date(2026, 10, 2)],
            [datetime(2026, 10, 1, 10, 0, 0, 200_000), 0.1, None, True],
        ]
    )
    rows = xlsx.read_rows(content)
    assert rows[0] == (1, ["Fecha", "Importe", "Texto", "Entero", "Día"])
    line, cells = rows[1]
    assert line == 2
    assert cells == [
        datetime(2026, 10, 1, 10, 0, 0),
        Decimal("-12.3"),
        "Café",
        Decimal(7),
        datetime(2026, 10, 2),
    ]
    assert rows[2][1] == [datetime(2026, 10, 1, 10, 0, 0), Decimal("0.1"), None, "True"]


def test_rejects_non_xlsx_content() -> None:
    with pytest.raises(ImportFormatError, match=r"No es un archivo Excel"):
        xlsx.read_rows(b"Fecha;Concepto\n")


def test_rejects_legacy_xls_with_a_hint() -> None:
    with pytest.raises(ImportFormatError, match=r"\.xlsx"):
        xlsx.read_rows(bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 100)


def _zip(entries: dict[str, bytes], encrypted: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    content = bytearray(buffer.getvalue())
    if encrypted:
        # zipfile no escribe entradas cifradas: se marca el bit en el directorio central.
        central = content.index(b"PK\x01\x02")
        content[central + 8] |= 0x1
    return bytes(content)


def test_rejects_zip_bomb_by_ratio() -> None:
    with pytest.raises(ImportFormatError, match="sospechosa"):
        xlsx.read_rows(_zip({"xl/worksheets/sheet1.xml": b"\x00" * (2 * 1024 * 1024)}))


def test_rejects_too_much_uncompressed_data(monkeypatch) -> None:
    monkeypatch.setattr(xlsx, "MAX_UNCOMPRESSED", 1000)
    with pytest.raises(ImportFormatError, match="demasiado grande"):
        xlsx.read_rows(_zip({"a.xml": b"x" * 600, "b.xml": b"y" * 600}))


def test_rejects_too_many_entries() -> None:
    with pytest.raises(ImportFormatError, match="demasiadas partes"):
        xlsx.read_rows(_zip({f"p{i}.xml": b"x" for i in range(xlsx.MAX_ENTRIES + 1)}))


def test_rejects_encrypted_entries() -> None:
    with pytest.raises(ImportFormatError, match="cifrado"):
        xlsx.read_rows(_zip({"a.xml": b"x"}, encrypted=True))


def test_rejects_too_many_rows(monkeypatch) -> None:
    monkeypatch.setattr(xlsx, "MAX_ROWS", 3)
    with pytest.raises(ImportFormatError, match="supera las 3 filas"):
        xlsx.read_rows(make_xlsx([[i] for i in range(5)]))


def test_corrupt_workbook_is_a_format_error() -> None:
    with pytest.raises(ImportFormatError, match="No se ha podido leer"):
        xlsx.read_rows(_zip({"xl/workbook.xml": b"<roto"}))


def test_truncated_zip_is_a_format_error() -> None:
    with pytest.raises(ImportFormatError, match="No se ha podido leer"):
        xlsx.read_rows(make_xlsx([["a"]])[:200])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DescripciÃ³n", "Descripción"),
        ("Fecha de finalizaciÃ³n", "Fecha de finalización"),
        ("ComisiÃ³n", "Comisión"),
        ("SÃO PAULO", "SÃO PAULO"),
        ("Café", "Café"),
    ],
)
def test_repair_mojibake(raw, expected) -> None:
    assert repair_mojibake(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (Decimal("-1.5"), Decimal("-1.5")),
        (None, Decimal(0)),
        ("", Decimal(0)),
        ("-12,30", Decimal("-12.30")),
        ("1.234,56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
        ("12.30", Decimal("12.30")),
    ],
)
def test_to_decimal(raw, expected) -> None:
    assert to_decimal(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "NaN", datetime(2026, 1, 1)])
def test_to_decimal_rejects_non_amounts(raw) -> None:
    with pytest.raises(ValueError, match="importe no válido"):
        to_decimal(raw)


def test_find_header_row_skips_preamble() -> None:
    rows = [
        (1, ["Título"]),
        (2, []),
        (3, ["Fecha", "Descripción", "Importe"]),
        (4, ["x"]),
    ]
    aliases = {"date": ("fecha",), "description": ("descripcion",), "amount": ("importe",)}
    assert find_header_row(rows, aliases, ["date", "amount"]) == (
        2,
        {"date": 0, "description": 1, "amount": 2},
    )
    assert find_header_row(rows, aliases, ["date", "balance"]) is None


def _replace_part(content: bytes, name: str, data: bytes, stored: bool = False) -> bytes:
    """Reescribe un .xlsx cambiando (o añadiendo) una de sus partes."""
    source = zipfile.ZipFile(io.BytesIO(content))
    buffer = io.BytesIO()
    method = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(buffer, "w", method) as out:
        for item in source.infolist():
            out.writestr(item.filename, data if item.filename == name else source.read(item))
        if name not in source.namelist():
            out.writestr(name, data)
    return buffer.getvalue()


@pytest.fixture
def no_workbook(monkeypatch):
    """Falla si se llega a abrir el libro: los límites tienen que actuar antes."""

    def forbidden(*_args, **_kwargs):
        raise AssertionError("load_workbook no debería llamarse")

    monkeypatch.setattr(xlsx, "load_workbook", forbidden)


def _styles(size: int) -> bytes:
    head = b'<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    return head + b"<numFmts/>" * (size // 10)


def test_huge_compressible_styles_is_rejected_before_opening(no_workbook) -> None:
    # Unos cientos de KB en disco que serían decenas de MB en memoria.
    content = _replace_part(make_xlsx([["a"]]), "xl/styles.xml", _styles(12 * 1024 * 1024))
    assert len(content) < 1024 * 1024
    with pytest.raises(ImportFormatError):
        xlsx.read_rows(content)


def test_styles_over_its_own_limit_is_rejected(no_workbook) -> None:
    content = _replace_part(make_xlsx([["a"]]), "xl/styles.xml", _styles(1100 * 1024), stored=True)
    with pytest.raises(ImportFormatError, match="parte del archivo Excel es demasiado grande"):
        xlsx.read_rows(content)


def test_shared_strings_over_its_own_limit_is_rejected(no_workbook) -> None:
    big = b"<sst>" + b"<si/>" * (1024 * 1024 + 10)
    content = _replace_part(make_xlsx([["a"]]), "xl/sharedStrings.xml", big, stored=True)
    with pytest.raises(ImportFormatError, match="parte del archivo Excel es demasiado grande"):
        xlsx.read_rows(content)


def test_refuses_to_parse_without_defusedxml(monkeypatch, no_workbook) -> None:
    monkeypatch.setattr(openpyxl, "DEFUSEDXML", False)
    with pytest.raises(ImportFormatError, match="no está disponible"):
        xlsx.read_rows(make_xlsx([["a"]]))


def test_wrong_declared_dimension_does_not_cut_rows() -> None:
    content = make_xlsx([["Fecha", "Importe"], ["x", 1], ["y", 2], ["z", 3]])
    sheet = zipfile.ZipFile(io.BytesIO(content)).read("xl/worksheets/sheet1.xml")
    forged = re.sub(rb'<dimension ref="[^"]*"\s*/>', b'<dimension ref="A1"/>', sheet)
    assert forged != sheet
    rows = xlsx.read_rows(_replace_part(content, "xl/worksheets/sheet1.xml", forged))
    assert [line for line, _ in rows] == [1, 2, 3, 4]
    assert rows[-1][1] == ["z", Decimal(3)]


@pytest.mark.parametrize(
    "raw",
    ["1E+50", Decimal("1E+50"), Decimal("1E+300"), "1000000000000000", "-1e15", "1E-999999"],
)
def test_to_decimal_rejects_amounts_that_do_not_fit(raw) -> None:
    with pytest.raises(ValueError, match="importe no válido"):
        to_decimal(raw)


def test_to_decimal_accepts_the_largest_amount_that_fits() -> None:
    assert to_decimal("999999999999999.99") == Decimal("999999999999999.99")
