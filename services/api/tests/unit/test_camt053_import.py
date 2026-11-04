"""OF-1104: lector de CAMT.053 con un archivo sintético."""

from pathlib import Path

import pytest

from openfinance.domain.imports import ClassificationRules
from openfinance.domain.ledger import TransactionKind
from openfinance.infrastructure.importers.camt import parse_camt053
from openfinance.infrastructure.importers.common import ImportFormatError
from openfinance.infrastructure.importers.universal import parse_standard

FILE = (Path(__file__).parents[1] / "fixtures" / "synthetic_camt053.xml").read_bytes()
RULES = ClassificationRules()


def parse(content: bytes = FILE):
    return parse_camt053(content, "acc", RULES)


def test_debits_are_negative_and_credits_positive_in_date_order() -> None:
    r = parse()
    got = [(x.booked_at.date().isoformat(), str(x.amount.amount), x.description) for x in r.rows]
    assert got == [
        ("2026-10-01", "1600.00", "EMPRESA SINTETICA SL NOMINA OCTUBRE"),
        ("2026-10-03", "-87.34", "MERCADONA SA COMPRA TARJETA"),
        ("2026-10-10", "-12.00", "PROVEEDOR UNO"),
        ("2026-10-10", "-18.00", "PROVEEDOR DOS"),
        ("2026-10-12", "-10.00", "DEVOLUCION DE RECIBO"),
    ]
    assert r.rows[0].suggested_kind is TransactionKind.INCOME


def test_an_entry_with_several_transactions_becomes_one_row_each() -> None:
    rows = [x for x in parse().rows if x.booked_at.day == 10]
    assert [str(x.amount.amount) for x in rows] == ["-12.00", "-18.00"]
    assert rows[0].fingerprint != rows[1].fingerprint


def test_a_reversal_flips_the_sign() -> None:
    reversal = next(x for x in parse().rows if "DEVOLUCION" in x.description)
    assert str(reversal.amount.amount) == "-10.00"  # un crédito anulado resta


def test_pending_and_zero_entries_are_skipped_with_a_reason() -> None:
    reasons = {s.description: s.reason for s in parse().skipped}
    assert "pendiente" in reasons["PENDIENTE DE CONTABILIZAR"]
    assert "importe cero" in reasons["VERIFICACION"]


def test_the_closing_balance_goes_on_the_last_row() -> None:
    r = parse()
    assert r.closing_balance is not None and str(r.closing_balance.amount) == "1427.66"


def test_fingerprints_are_stable_and_per_account() -> None:
    assert [x.fingerprint for x in parse().rows] == [x.fingerprint for x in parse().rows]
    other = parse_camt053(FILE, "otra", RULES)
    assert other.rows[0].fingerprint != parse().rows[0].fingerprint


def test_the_format_is_recognised_by_content() -> None:
    assert len(parse_standard(FILE, "acc", RULES).rows) == 5


def test_other_namespace_versions_work() -> None:
    text = FILE.decode().replace("camt.053.001.02", "camt.053.001.08")
    assert len(parse(text.encode()).rows) == 5


def test_two_accounts_in_one_file_are_refused() -> None:
    text = FILE.decode()
    second = text[text.index("<Stmt>") : text.index("</Stmt>") + len("</Stmt>")].replace(
        "ES0000000000000000000000", "ES1111111111111111111111"
    )
    text = text.replace("</BkToCstmrStmt>", second + "</BkToCstmrStmt>")
    with pytest.raises(ImportFormatError, match="cuentas distintas"):
        parse(text.encode())


class TestHostileXml:
    def test_external_entities_are_refused_and_never_read(self) -> None:
        evil = (
            b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
            b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
            b"<BkToCstmrStmt><Stmt><Ntry><AddtlNtryInf>&e;</AddtlNtryInf></Ntry></Stmt>"
            b"</BkToCstmrStmt></Document>"
        )
        with pytest.raises(ImportFormatError, match="no permitidas"):
            parse(evil)

    def test_entity_expansion_bombs_are_refused(self) -> None:
        bomb = (
            b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaaaaaaaa">'
            b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
            b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
            b"<BkToCstmrStmt><Stmt>&b;</Stmt></BkToCstmrStmt></Document>"
        )
        with pytest.raises(ImportFormatError):
            parse(bomb)

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            (b"no es xml", "no es válido"),
            (b"<Document/>", "No parece"),
            (b'<Document xmlns="x"><BkToCstmrStmt/></Document>', "ningún extracto"),
        ],
    )
    def test_other_bad_files(self, content, message) -> None:
        with pytest.raises(ImportFormatError, match=message):
            parse(content)
