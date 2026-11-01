"""Lectura segura de hojas Excel (.xlsx). Es el único módulo que usa ``openpyxl``.

Un .xlsx es un zip con XML dentro: antes de abrirlo se comprueba que no sea una bomba
de descompresión ni esté cifrado, y ``openpyxl`` usa ``defusedxml`` para el XML.
"""

from __future__ import annotations

import io
import warnings
import zipfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import openpyxl
from openpyxl import load_workbook

from openfinance.infrastructure.importers.common import (
    MAX_COLS,
    MAX_ROWS,
    Cell,
    ImportFormatError,
    Rows,
)

XLSX_MAGIC = b"PK\x03\x04"
LEGACY_XLS_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
MAX_ENTRIES = 100
MAX_UNCOMPRESSED = 10 * 1024 * 1024
MAX_RATIO = 100
_RATIO_MIN_SIZE = 64 * 1024
MAX_PART = 8 * 1024 * 1024
"""Tope por parte; las que openpyxl carga enteras en memoria tienen uno menor."""
PART_LIMITS = {
    "xl/styles.xml": 1024 * 1024,
    "xl/sharedstrings.xml": 5 * 1024 * 1024,
}

_UNREADABLE = "No se ha podido leer el archivo Excel"


def is_xlsx(content: bytes) -> bool:
    return content.startswith(XLSX_MAGIC)


def is_legacy_xls(content: bytes) -> bool:
    """Excel 97-2003 o un .xlsx protegido con contraseña (ambos son OLE)."""
    return content.startswith(LEGACY_XLS_MAGIC)


def _check_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise ImportFormatError(_UNREADABLE) from exc
    if len(entries) > MAX_ENTRIES:
        raise ImportFormatError("El archivo Excel tiene demasiadas partes")
    if any(e.flag_bits & 0x1 for e in entries):
        raise ImportFormatError("El archivo Excel está cifrado; expórtalo sin contraseña")
    if sum(e.file_size for e in entries) > MAX_UNCOMPRESSED:
        raise ImportFormatError("El archivo Excel es demasiado grande al descomprimirlo")
    for e in entries:
        if e.file_size > PART_LIMITS.get(e.filename.lower(), MAX_PART):
            raise ImportFormatError("Una parte del archivo Excel es demasiado grande")
        if e.file_size > _RATIO_MIN_SIZE and e.file_size > MAX_RATIO * max(e.compress_size, 1):
            raise ImportFormatError("El archivo Excel está comprimido de forma sospechosa")


def _round_to_second(value: datetime) -> datetime:
    """Excel guarda la hora como fracción de día: 10:00:00 puede leerse como 09:59:59.99999."""
    rounded = value.replace(microsecond=0)
    return rounded + timedelta(seconds=1) if value.microsecond >= 500_000 else rounded


def to_cell(value: object) -> Cell:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, datetime):
        return _round_to_second(value)
    if isinstance(value, date):
        return datetime.combine(value, time())
    return str(value)


def _read(content: bytes) -> Rows:
    rows: Rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        workbook = load_workbook(
            io.BytesIO(content), read_only=True, data_only=True, keep_links=False
        )
        try:
            sheet = workbook.worksheets[0]
            # La dimensión declarada en la hoja puede ser falsa y cortaría filas.
            reset = getattr(sheet, "reset_dimensions", None)
            if reset is not None:
                reset()
            for line, values in enumerate(
                sheet.iter_rows(values_only=True, max_col=MAX_COLS), start=1
            ):
                if line > MAX_ROWS:
                    raise ImportFormatError(f"El archivo Excel supera las {MAX_ROWS} filas")
                cells = [to_cell(v) for v in values]
                while cells and (cells[-1] is None or cells[-1] == ""):
                    cells.pop()
                rows.append((line, cells))
        finally:
            workbook.close()
    return rows


def read_rows(content: bytes) -> Rows:
    """Filas de la primera hoja, con su número de fila de Excel."""
    if is_legacy_xls(content):
        raise ImportFormatError(
            "Es un Excel antiguo (.xls) o protegido con contraseña: expórtalo en .xlsx"
        )
    if not is_xlsx(content):
        raise ImportFormatError("No es un archivo Excel (.xlsx)")
    if not getattr(openpyxl, "DEFUSEDXML", False):
        # Sin defusedxml, openpyxl parsea XML no confiable sin protección.
        raise ImportFormatError("La lectura de Excel no está disponible en este servidor")
    _check_archive(content)
    try:
        return _read(content)
    except ImportFormatError:
        raise
    except Exception as exc:
        # openpyxl puede fallar de muchas formas con un archivo dañado; ninguna es un 500.
        raise ImportFormatError(_UNREADABLE) from exc
