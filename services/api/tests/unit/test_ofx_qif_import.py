"""OF-1103: lectores de OFX y QIF con archivos sintéticos."""

from decimal import Decimal
from pathlib import Path

import pytest

from openfinance.domain.imports import ClassificationRules
from openfinance.domain.ledger import TransactionKind
from openfinance.infrastructure.importers.common import ImportFormatError
from openfinance.infrastructure.importers.ofx import parse_ofx
from openfinance.infrastructure.importers.qif import parse_qif
from openfinance.infrastructure.importers.universal import parse_standard

FIX = Path(__file__).parents[1] / "fixtures"
RULES = ClassificationRules()


def read(name: str) -> bytes:
    return (FIX / name).read_bytes()


class TestOfx:
    def test_reads_rows_in_date_order_with_exact_amounts(self) -> None:
        r = parse_ofx(read("synthetic.ofx"), "acc", RULES)
        assert [
            (x.description, str(x.amount.amount), x.booked_at.date().isoformat()) for x in r.rows
        ] == [
            ("NOMINA EMPRESA SINTETICA", "1600.00", "2026-10-01"),
            ("MERCADONA VALENCIA COMPRA TARJETA", "-87.34", "2026-10-03"),
            ("GLOVO", "-25.40", "2026-10-07"),
            ("GLOVO", "-25.40", "2026-10-07"),
        ]
        assert all(isinstance(x.amount.amount, Decimal) for x in r.rows)
        assert r.rows[0].suggested_kind is TransactionKind.INCOME
        assert r.rows[1].bank_type == "DEBIT"

    def test_skips_zero_and_broken_rows_with_a_reason(self) -> None:
        r = parse_ofx(read("synthetic.ofx"), "acc", RULES)
        reasons = {s.description: s.reason for s in r.skipped}
        assert "importe cero" in reasons["VERIFICACION"]
        assert "fecha no válida" in reasons["FECHA ROTA"]

    def test_identical_rows_keep_distinct_fingerprints_and_are_stable(self) -> None:
        a = parse_ofx(read("synthetic.ofx"), "acc", RULES)
        b = parse_ofx(read("synthetic.ofx"), "acc", RULES)
        assert [x.fingerprint for x in a.rows] == [x.fingerprint for x in b.rows]
        assert len({x.fingerprint for x in a.rows}) == len(a.rows)
        assert (
            parse_ofx(read("synthetic.ofx"), "otra", RULES).rows[0].fingerprint
            != a.rows[0].fingerprint
        )

    def test_the_bank_closing_balance_goes_on_the_last_row(self) -> None:
        r = parse_ofx(read("synthetic.ofx"), "acc", RULES)
        assert r.closing_balance is not None and str(r.closing_balance.amount) == "1461.92"

    def test_a_ledger_balance_older_than_the_last_row_is_not_used(self) -> None:
        text = read("synthetic.ofx").decode().replace("<DTASOF>20261031", "<DTASOF>20261002")
        assert parse_ofx(text.encode(), "acc", RULES).closing_balance is None

    def test_reads_ofx_v2_xml(self) -> None:
        r = parse_ofx(read("synthetic_v2.ofx"), "acc", RULES)
        assert [(x.description, str(x.amount.amount)) for x in r.rows] == [
            ("Cafetería Sintética", "-12.50")
        ]

    def test_reads_windows_1252(self) -> None:
        text = read("synthetic_v2.ofx").decode().replace("Cafetería", "Cafetería").encode("cp1252")
        assert parse_ofx(text, "acc", RULES).rows[0].description == "Cafetería Sintética"

    def test_the_currency_comes_from_the_file(self) -> None:
        text = read("synthetic_v2.ofx").decode().replace("<CURDEF>EUR", "<CURDEF>usd")
        assert parse_ofx(text.encode(), "acc", RULES).rows[0].amount.currency.code == "USD"

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            (b"esto no es un OFX", "No parece"),
            (b"<OFX><BANKTRANLIST></BANKTRANLIST></OFX>", "moneda"),
            (b"<OFX><CURDEF>EUR</CURDEF></OFX>", "no trae movimientos"),
            (b"<OFX><STMTRS><CURDEF>EUR<STMTRS></OFX>", "más de una cuenta"),
        ],
    )
    def test_rejects_what_is_not_usable(self, content, message) -> None:
        with pytest.raises(ImportFormatError, match=message):
            parse_ofx(content, "acc", RULES)

    def test_external_entities_are_not_a_thing(self) -> None:
        evil = (
            b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
            b"<OFX><STMTRS><CURDEF>EUR</CURDEF><STMTTRN><DTPOSTED>20261001</DTPOSTED>"
            b"<TRNAMT>-1.00</TRNAMT><NAME>&e;</NAME></STMTTRN></STMTRS></OFX>"
        )
        r = parse_ofx(evil, "acc", RULES)
        assert "root:" not in r.rows[0].description and r.rows[0].description == "&e;"

    def test_too_many_rows_are_refused(self) -> None:
        row = (
            b"<STMTTRN><DTPOSTED>20261001</DTPOSTED><TRNAMT>-1.00</TRNAMT><NAME>x</NAME></STMTTRN>"
        )
        content = (
            b"<OFX><STMTRS><CURDEF>EUR</CURDEF><BANKTRANLIST>"
            + row * 20_001
            + b"</BANKTRANLIST></STMTRS></OFX>"
        )
        with pytest.raises(ImportFormatError, match="demasiados"):
            parse_ofx(content, "acc", RULES)


class TestQif:
    def test_reads_rows_with_the_accounts_currency(self) -> None:
        r = parse_qif(read("synthetic.qif"), "acc", ClassificationRules(currency="USD"))
        assert [(x.description, str(x.amount.amount), x.amount.currency.code) for x in r.rows] == [
            ("SUPERMERCADO SINTETICO Compra semanal", "-45.90", "USD"),
            ("NOMINA EMPRESA SINTETICA", "1250.00", "USD"),
            ("CAFE", "-3.50", "USD"),
            ("CAFE", "-3.50", "USD"),
        ]
        assert len({x.fingerprint for x in r.rows}) == 4

    def test_dd_mm_is_deduced_when_a_day_is_over_12(self) -> None:
        r = parse_qif(read("synthetic.qif"), "acc", RULES)
        assert r.rows[0].booked_at.date().isoformat() == "2026-10-25"

    def test_mm_dd_is_deduced_the_same_way(self) -> None:
        text = b"!Type:Bank\nD10/25/2026\nT-1.00\nPX\n^\n"
        assert parse_qif(text, "acc", RULES).rows[0].booked_at.date().isoformat() == "2026-10-25"

    def test_ambiguous_dates_are_refused_not_guessed(self) -> None:
        with pytest.raises(ImportFormatError, match="ambiguas"):
            parse_qif(read("synthetic_ambiguous.qif"), "acc", RULES)

    def test_mixed_orders_are_refused(self) -> None:
        text = b"!Type:Bank\nD25/10/2026\nT-1.00\nPX\n^\nD10/25/2026\nT-1.00\nPY\n^\n"
        with pytest.raises(ImportFormatError, match="mezclan"):
            parse_qif(text, "acc", RULES)

    def test_iso_dates_never_need_guessing(self) -> None:
        text = b"!Type:Bank\nD2026-10-03\nT-1.00\nPX\n^\n"
        assert parse_qif(text, "acc", RULES).rows[0].booked_at.date().isoformat() == "2026-10-03"

    def test_bad_rows_are_skipped_with_a_reason(self) -> None:
        text = b"!Type:Bank\nD25/10/2026\nTmucho\nPX\n^\nD25/10/2026\nT0.00\nPY\n^\nD25/10/2026\nPZ\n^\n"
        r = parse_qif(text, "acc", RULES)
        assert r.rows == [] and len(r.skipped) == 3

    def test_rejects_other_files(self) -> None:
        with pytest.raises(ImportFormatError):
            parse_qif(b"fecha;importe\n", "acc", RULES)


class TestSniffing:
    def test_chooses_the_reader_by_content_not_by_name(self) -> None:
        assert parse_standard(read("synthetic.ofx"), "a", RULES).rows
        assert parse_standard(read("synthetic.qif"), "a", RULES).rows

    def test_an_unknown_file_gets_a_helpful_message(self) -> None:
        with pytest.raises(ImportFormatError, match="Formato no reconocido"):
            parse_standard(b"a;b;c\n1;2;3\n", "a", RULES)
