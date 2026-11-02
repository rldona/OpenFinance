"""OF-1105: perfiles de CSV y lector guiado por perfil (archivos sintéticos)."""

from uuid import uuid4

import pytest

from openfinance.domain.csv_profile import ProfileError, build, from_definition
from openfinance.domain.imports import ClassificationRules
from openfinance.domain.shared.ids import WorkspaceId
from openfinance.infrastructure.importers.common import ImportFormatError
from openfinance.infrastructure.importers.csv_profile import parse_csv, sample

HOUSEHOLD = WorkspaceId(uuid4())
RULES = ClassificationRules()

SPANISH = (
    "Extracto de cuenta;;;;\n"
    "Titular;SINTETICO;;;\n"
    "Fecha;Descripción;Detalle;Debe;Haber;Saldo\n"
    "03/10/2026;COMPRA;MERCADONA;87,34;;1.512,66\n"
    "01/10/2026;NOMINA;EMPRESA SINTETICA;;1.600,00;1.600,00\n"
    "07/10/2026;COMPRA;GLOVO;25,40;;1.487,26\n"
).encode("cp1252")


def profile(**kw):
    config = {
        "delimiter": ";",
        "encoding": "cp1252",
        "skip_rows": 2,
        "has_header": True,
        "date_column": 0,
        "date_format": "%d/%m/%Y",
        "description_columns": [1, 2],
        "amount_mode": "debit_credit",
        "debit_column": 3,
        "credit_column": 4,
        "decimal_separator": ",",
        "balance_column": 5,
        **kw,
    }
    return build(uuid4(), HOUSEHOLD, kw.pop("name", "Banco sintético"), config)


class TestParse:
    def test_reads_a_spanish_debit_credit_csv_in_the_banks_order(self) -> None:
        r = parse_csv(SPANISH, "acc", RULES, profile())
        got = [
            (x.booked_at.date().isoformat(), x.description, str(x.amount.amount)) for x in r.rows
        ]
        assert got == [
            ("2026-10-01", "NOMINA EMPRESA SINTETICA", "1600.00"),
            ("2026-10-03", "COMPRA MERCADONA", "-87.34"),
            ("2026-10-07", "COMPRA GLOVO", "-25.40"),
        ]
        assert r.balance_mismatches == []
        assert r.closing_balance is not None and str(r.closing_balance.amount) == "1487.26"

    def test_a_balance_that_does_not_add_up_is_reported(self) -> None:
        bad = SPANISH.replace(b"1.512,66", b"1.500,00")
        assert len(parse_csv(bad, "acc", RULES, profile()).balance_mismatches) == 2

    def test_single_column_with_inverted_sign(self) -> None:
        text = "fecha,concepto,importe\n2026-10-03,CAFE,3.50\n2026-10-04,DEVOLUCION,-3.50\n"
        p = profile(
            delimiter=",", encoding="utf-8", skip_rows=0, date_format="%Y-%m-%d",
            description_columns=[1], amount_mode="single", amount_column=2,
            decimal_separator=".", invert_sign=True, balance_column=None,
        )  # fmt: skip
        r = parse_csv(text.encode(), "acc", RULES, p)
        assert [str(x.amount.amount) for x in r.rows] == ["-3.50", "3.50"]

    def test_descending_files_come_out_oldest_first(self) -> None:
        text = "d;c;i\n05/10/2026;B;-2,00\n04/10/2026;A;-1,00\n"
        p = profile(
            skip_rows=0, encoding="utf-8", description_columns=[1], amount_mode="single",
            amount_column=2, balance_column=None,
        )  # fmt: skip
        assert [x.description for x in parse_csv(text.encode(), "acc", RULES, p).rows] == ["A", "B"]

    def test_bad_rows_are_skipped_with_a_reason_and_never_guessed(self) -> None:
        text = (
            "d;c;i\n"
            "no-fecha;A;-1,00\n"
            "04/10/2026;B;mucho\n"
            "04/10/2026;C;\n"
            "04/10/2026;D;0,00\n"
            "04/10/2026;E;1.234\n"  # dos lecturas posibles con «,» decimal: miles
            "04/10/2026;F;-2,50\n"
        )
        p = profile(
            skip_rows=0, encoding="utf-8", description_columns=[1], amount_mode="single",
            amount_column=2, balance_column=None,
        )  # fmt: skip
        r = parse_csv(text.encode(), "acc", RULES, p)
        assert [x.description for x in r.rows] == ["E", "F"]
        assert str(r.rows[0].amount.amount) == "1234.00"
        assert {s.description for s in r.skipped} == {"A", "B", "C", "D"}

    def test_debit_and_credit_at_once_is_refused(self) -> None:
        text = "d;c;x;y\n04/10/2026;A;1,00;2,00\n"
        p = profile(
            skip_rows=0,
            encoding="utf-8",
            description_columns=[1],
            debit_column=2,
            credit_column=3,
            balance_column=None,
        )
        r = parse_csv(text.encode(), "acc", RULES, p)
        assert r.rows == [] and "a la vez" in r.skipped[0].reason

    def test_fingerprints_are_stable_distinct_and_per_account(self) -> None:
        text = "d;c;i\n04/10/2026;CAFE;-1,00\n04/10/2026;CAFE;-1,00\n"
        p = profile(
            skip_rows=0,
            encoding="utf-8",
            description_columns=[1],
            amount_mode="single",
            amount_column=2,
            balance_column=None,
        )
        a = parse_csv(text.encode(), "acc", RULES, p)
        assert len({x.fingerprint for x in a.rows}) == 2
        assert [x.fingerprint for x in a.rows] == [
            x.fingerprint for x in parse_csv(text.encode(), "acc", RULES, p).rows
        ]
        assert (
            parse_csv(text.encode(), "otra", RULES, p).rows[0].fingerprint != a.rows[0].fingerprint
        )

    def test_the_wrong_encoding_is_a_clear_error(self) -> None:
        with pytest.raises(ImportFormatError, match="utf-8"):
            parse_csv(SPANISH, "acc", RULES, profile(encoding="utf-8"))

    def test_the_account_currency_is_used(self) -> None:
        r = parse_csv(SPANISH, "acc", ClassificationRules(currency="GBP"), profile())
        assert {x.amount.currency.code for x in r.rows} == {"GBP"}

    def test_too_many_rows_or_columns_are_refused(self) -> None:
        many = "d;c;i\n" + "04/10/2026;A;-1,00\n" * 20_001
        p = profile(
            skip_rows=0,
            encoding="utf-8",
            description_columns=[1],
            amount_mode="single",
            amount_column=2,
            balance_column=None,
        )
        with pytest.raises(ImportFormatError, match="demasiadas filas"):
            parse_csv(many.encode(), "acc", RULES, p)
        wide = ";".join(str(i) for i in range(31)) + "\n"
        with pytest.raises(ImportFormatError, match="demasiadas columnas"):
            parse_csv(wide.encode(), "acc", RULES, p)


class TestSample:
    def test_proposes_the_separator_and_encoding(self) -> None:
        s = sample(SPANISH)
        assert (s.delimiter, s.encoding) == (";", "cp1252")
        assert s.rows[2][0] == "Fecha" and len(s.rows) <= 12

    def test_utf8_comma_file(self) -> None:
        s = sample(b"a,b,c\n1,2,3\n")
        assert (s.delimiter, s.encoding, s.rows[1]) == (",", "utf-8", ["1", "2", "3"])


class TestProfileValidation:
    @pytest.mark.parametrize(
        "change",
        [
            {"delimiter": "x"},
            {"encoding": "ebcdic"},
            {"skip_rows": 51},
            {"skip_rows": -1},
            {"date_format": "%d/%m/%Y %H:%M:%S%z"},  # solo formatos de la lista
            {"date_column": None},
            {"date_column": 99},
            {"description_columns": []},
            {"description_columns": [1, 2, 3, 4, 5]},
            {"amount_mode": "raro"},
            {"debit_column": 3, "credit_column": 3},
            {"decimal_separator": ";"},
            {"balance_column": -2},
        ],
    )
    def test_invalid_profiles(self, change) -> None:
        with pytest.raises(ProfileError):
            profile(**change)

    def test_round_trip_through_the_definition(self) -> None:
        p = profile()
        again = from_definition(p.id, HOUSEHOLD, p.definition())
        assert again == p and again.definition() == p.definition()

    def test_single_mode_needs_an_amount_column(self) -> None:
        with pytest.raises(ProfileError):
            profile(amount_mode="single", amount_column=None)
