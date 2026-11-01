"""Piezas comunes a los lectores de extractos: celdas, importes y cabeceras."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation

from openfinance.domain.shared.text import normalize_text

Cell = str | Decimal | datetime | None
Rows = list[tuple[int, list[Cell]]]
"""Filas de un extracto con su número de línea en el archivo (1 = primera)."""

_MOJIBAKE_MARKS = ("Ã", "Â", "â€")
MAX_ROWS = 20_000
"""Filas con contenido que se leen de un extracto, sea CSV o Excel."""
MAX_COLS = 30
MAX_AMOUNT = Decimal(10) ** 15
"""Las columnas de importe son ``Numeric(19, 4)``: 15 cifras enteras."""
_MIN_EXPONENT = -20
INVALID_AMOUNT = "fila no válida: importe no válido"


class ImportFormatError(ValueError):
    """El archivo no tiene el formato esperado."""


def to_decimal(value: Cell) -> Decimal:
    """Importe exacto de una celda. Nunca pasa por ``float``.

    - ``None`` o texto vacío → 0.
    - ``Decimal`` → tal cual (el lector de Excel ya lo convirtió desde ``repr`` del número).
    - Texto: se quitan espacios. Si lleva ``,`` y ``.``, el que aparece el último es el
      separador decimal y el otro, el de miles. Si solo lleva ``,``, es el decimal. Si solo
      lleva ``.``, también (``1.234`` se lee como 1,234).
    - Una fecha, un texto que no es un número, un valor no finito, una magnitud de
      ``MAX_AMOUNT`` o más, o un exponente absurdo dan ``ValueError("importe no válido")``.
    """
    if value is None:
        return Decimal(0)
    if isinstance(value, datetime):
        raise ValueError("importe no válido")
    if isinstance(value, Decimal):
        result = value
    else:
        text = value.strip().replace(" ", "").replace("\u00a0", "")
        if not text:
            return Decimal(0)
        if "," in text and "." in text:
            decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
            thousands = "." if decimal_sep == "," else ","
            text = text.replace(thousands, "").replace(decimal_sep, ".")
        elif "," in text:
            text = text.replace(",", ".")
        try:
            result = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("importe no válido") from exc
    if not result.is_finite():
        raise ValueError("importe no válido")
    exponent = result.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < _MIN_EXPONENT or abs(result) >= MAX_AMOUNT:
        raise ValueError("importe no válido")
    return result


def repair_mojibake(text: str) -> str:
    """Arregla texto UTF-8 leído como Latin-1 (``DescripciÃ³n`` → ``Descripción``).

    Solo actúa si aparecen las marcas típicas y la reparación es UTF-8 válido; si no,
    devuelve el texto tal cual (``SÃO PAULO`` es legítimo).
    """
    if not any(mark in text for mark in _MOJIBAKE_MARKS):
        return text
    for codec in ("cp1252", "latin-1"):
        try:
            return text.encode(codec).decode("utf-8")
        except UnicodeError:
            continue
    return text


def repair_text_cells(rows: Rows) -> Rows:
    """Repara la codificación de las celdas de texto (solo para formatos que la rompen)."""
    return [
        (line, [repair_mojibake(c) if isinstance(c, str) else c for c in cells])
        for line, cells in rows
    ]


def cell_text(value: Cell) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value).strip()


def _key(value: Cell) -> str:
    return normalize_text(cell_text(value)).lower()


def find_header_row(
    rows: Rows,
    aliases: Mapping[str, Sequence[str]],
    required: Sequence[str],
    max_scan: int = 50,
) -> tuple[int, dict[str, int]] | None:
    """Busca la primera fila que contiene todas las columnas requeridas.

    Devuelve su posición en ``rows`` y qué columna ocupa cada clave encontrada. Las
    cabeceras se comparan tal cual; si su codificación puede venir rota, repáralas antes
    con ``repair_text_cells``.
    """
    targets = {k: [normalize_text(a).lower() for a in names] for k, names in aliases.items()}
    for position, (_, cells) in enumerate(rows[:max_scan]):
        header = [_key(c) for c in cells]
        found: dict[str, int] = {}
        for key, names in targets.items():
            index = next((header.index(n) for n in names if n in header), None)
            if index is not None:
                found[key] = index
        if all(k in found for k in required):
            return position, found
    return None
