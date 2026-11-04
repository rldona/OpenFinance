"""Perfil de CSV: cómo leer el extracto de cualquier banco (ADR-0020, OF-1105).

Un perfil es solo datos: qué columna es la fecha, cuál el concepto, cuál el importe y con qué
formato. No ejecuta nada. Las columnas se cuentan desde 0; el formato de fecha es uno de una lista
cerrada (nunca un texto libre de ``strptime``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from openfinance.domain.shared.ids import WorkspaceId

MAX_NAME = 80
MAX_COLUMNS = 30
MAX_SKIP = 50
DELIMITERS = {",": "coma", ";": "punto y coma", "\t": "tabulador", "|": "barra vertical"}
ENCODINGS = ("utf-8", "cp1252", "latin-1")
DATE_FORMATS = (
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m/%d/%y",
)
AMOUNT_MODES = ("single", "debit_credit")


class ProfileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CsvProfile:
    id: UUID
    household_id: WorkspaceId
    name: str
    delimiter: str
    encoding: str
    skip_rows: int
    """Líneas antes de la cabecera (títulos, número de cuenta…)."""
    has_header: bool
    date_column: int
    date_format: str
    description_columns: tuple[int, ...]
    amount_mode: str
    amount_column: int | None
    debit_column: int | None
    credit_column: int | None
    decimal_separator: str
    invert_sign: bool
    """En modo ``single``: el banco da los gastos en positivo."""
    balance_column: int | None

    def config(self) -> dict[str, Any]:
        return {
            "delimiter": self.delimiter,
            "encoding": self.encoding,
            "skip_rows": self.skip_rows,
            "has_header": self.has_header,
            "date_column": self.date_column,
            "date_format": self.date_format,
            "description_columns": list(self.description_columns),
            "amount_mode": self.amount_mode,
            "amount_column": self.amount_column,
            "debit_column": self.debit_column,
            "credit_column": self.credit_column,
            "decimal_separator": self.decimal_separator,
            "invert_sign": self.invert_sign,
            "balance_column": self.balance_column,
        }

    def definition(self) -> str:
        """El texto canónico (registro de cambios y base de datos)."""
        return json.dumps(
            {"name": self.name, **self.config()},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )


def _column(value: Any, what: str, *, required: bool = True) -> int | None:
    if value is None or value == "":
        if required:
            raise ProfileError(f"Falta la columna de {what}")
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < MAX_COLUMNS:
        raise ProfileError(f"La columna de {what} no es válida (0 a {MAX_COLUMNS - 1})")
    return value


def build(
    profile_id: UUID, household_id: WorkspaceId, name: str, config: dict[str, Any]
) -> CsvProfile:
    """Un perfil validado a partir de datos del cliente."""
    cleaned = " ".join(str(name).split())
    if not cleaned or len(cleaned) > MAX_NAME:
        raise ProfileError(f"El nombre tiene entre 1 y {MAX_NAME} caracteres")
    delimiter = config.get("delimiter", ",")
    if delimiter not in DELIMITERS:
        raise ProfileError("Separador de columnas no admitido")
    encoding = config.get("encoding", "utf-8")
    if encoding not in ENCODINGS:
        raise ProfileError("Codificación no admitida")
    skip = config.get("skip_rows", 0)
    if isinstance(skip, bool) or not isinstance(skip, int) or not 0 <= skip <= MAX_SKIP:
        raise ProfileError(f"Las líneas a saltar van de 0 a {MAX_SKIP}")
    date_format = config.get("date_format", "")
    if date_format not in DATE_FORMATS:
        raise ProfileError("Formato de fecha no admitido")
    raw_description = config.get("description_columns") or []
    if not isinstance(raw_description, list) or not 1 <= len(raw_description) <= 4:
        raise ProfileError("Elige de 1 a 4 columnas para el concepto")
    description = tuple(_column(c, "concepto") for c in raw_description)
    mode = config.get("amount_mode", "single")
    if mode not in AMOUNT_MODES:
        raise ProfileError("Modo de importe no admitido")
    amount = debit = credit = None
    if mode == "single":
        amount = _column(config.get("amount_column"), "importe")
    else:
        debit = _column(config.get("debit_column"), "débito")
        credit = _column(config.get("credit_column"), "crédito")
        if debit == credit:
            raise ProfileError("Débito y crédito tienen que ser columnas distintas")
    separator = config.get("decimal_separator", ",")
    if separator not in (",", "."):
        raise ProfileError("El separador decimal es «,» o «.»")
    return CsvProfile(
        id=profile_id,
        household_id=household_id,
        name=cleaned,
        delimiter=delimiter,
        encoding=encoding,
        skip_rows=skip,
        has_header=bool(config.get("has_header", True)),
        date_column=_column(config.get("date_column"), "fecha"),  # type: ignore[arg-type]
        date_format=date_format,
        description_columns=description,  # type: ignore[arg-type]
        amount_mode=mode,
        amount_column=amount,
        debit_column=debit,
        credit_column=credit,
        decimal_separator=separator,
        invert_sign=bool(config.get("invert_sign", False)),
        balance_column=_column(config.get("balance_column"), "saldo", required=False),
    )


def from_definition(profile_id: UUID, household_id: WorkspaceId, definition: str) -> CsvProfile:
    data = json.loads(definition)
    name = data.pop("name")
    return build(profile_id, household_id, name, data)


@dataclass(frozen=True, slots=True)
class CsvSample:
    """Una propuesta de separador y codificación y las primeras filas, para elegir columnas."""

    delimiter: str
    encoding: str
    rows: list[list[str]]
