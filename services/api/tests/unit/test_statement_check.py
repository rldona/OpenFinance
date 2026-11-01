"""`openfinance statement-check`: solo recuentos, nunca datos del extracto."""

from openfinance import cli
from tests.unit.test_bankinter_import import FAKE_IBAN, MOVEMENTS, statement
from tests.unit.test_revolut_xlsx import HEADER, ROWS
from tests.xlsx_factory import make_xlsx


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = cli.main(["statement-check", *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_bankinter_summary_has_only_counts(tmp_path, capsys) -> None:
    path = tmp_path / "Movimientos_secreto.xlsx"
    path.write_bytes(statement(MOVEMENTS))
    code, out, _ = run(capsys, "--bank", "bankinter", str(path))
    assert code == 0
    assert "Filas leídas: 7" in out
    assert "Importables: 6" in out
    assert "  pendiente: 1" in out
    assert "Descuadres de saldo: 0" in out
    assert "  contribution: 1" in out
    assert "Aportaciones con persona: 1" in out
    assert "Saldo final del banco: sí" in out
    for leak in (FAKE_IBAN, "secreto", "CAFE", "Revolut**", "BIZUM", "1506", "1.8", "12,50"):
        assert leak not in out


def test_revolut_summary_with_member_pattern(tmp_path, capsys) -> None:
    path = tmp_path / "revolut.xlsx"
    path.write_bytes(make_xlsx([HEADER, *ROWS]))
    code, out, _ = run(capsys, "--bank", "revolut", "--member-pattern", "*1234", str(path))
    assert code == 0
    assert "Aportaciones con persona: 1" in out
    assert "  entradas de tipo recarga: 1" in out
    assert "  entradas de tipo transferencia: 2" in out
    for leak in ("*1234", "Supermercado", "ANA PEREZ", "87.34", "1255"):
        assert leak not in out


def test_unreadable_file(tmp_path, capsys) -> None:
    path = tmp_path / "x.csv"
    path.write_text("Fecha;Concepto\n")
    code, out, err = run(capsys, "--bank", "bankinter", str(path))
    assert code == 1
    assert out == ""
    assert "No es un archivo Excel" in err
    code, _, err = run(capsys, "--bank", "revolut", str(tmp_path / "no-existe.csv"))
    assert code == 1
    assert "no-existe" not in err


def test_unknown_bank_types_are_grouped_as_others(tmp_path, capsys) -> None:
    odd = [*ROWS[:1], ["TIPO-SECRETO-X", *ROWS[1][1:]]]
    path = tmp_path / "revolut.xlsx"
    path.write_bytes(make_xlsx([HEADER, *odd]))
    code, out, _ = run(capsys, "--bank", "revolut", str(path))
    assert code == 0
    assert "  entradas de tipo otros: 1" in out
    assert "SECRETO" not in out.upper()
