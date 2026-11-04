"""Formatos de la exportación del hogar (OF-501): JSON y ZIP con un CSV por entidad.

Los importes salen como texto decimal exacto (``"-12.30"``) y las fechas en ISO 8601. En los
CSV, los textos que una hoja de cálculo interpretaría como fórmula llevan delante un
apóstrofo; los importes y las fechas nunca se tocan.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import re
import zipfile
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from openfinance.application.export import (
    ExportedAccount,
    ExportedBudget,
    ExportedCategory,
    ExportedGoal,
    ExportedMember,
    ExportedPattern,
    ExportedRate,
    ExportedRule,
    ExportedTransaction,
    HouseholdExport,
)

# Una fórmula al principio del texto o tras un separador que una hoja de cálculo pueda usar
# al abrir el CSV (Excel en español separa con «;»), aunque haya espacios delante.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_FORMULA = re.compile(r"(^|[;\t\r\n])\s*[=+\-@]")

CSV_FILES: dict[str, type] = {
    "members": ExportedMember,
    "accounts": ExportedAccount,
    "transactions": ExportedTransaction,
    "categories": ExportedCategory,
    "rules": ExportedRule,
    "budgets": ExportedBudget,
    "goals": ExportedGoal,
    "member_patterns": ExportedPattern,
    "exchange_rates": ExportedRate,
}
"""Un CSV por entidad: el nombre es el campo de ``HouseholdExport`` y las columnas, los
campos de su tipo (aunque no haya filas)."""

MANIFEST = "manifest.json"


def safe_cell(value: str) -> str:
    """Evita que una hoja de cálculo ejecute como fórmula un texto importado del banco."""
    if value.startswith(_FORMULA_PREFIXES) or _FORMULA.search(value):
        return f"'{value}"
    return value


def _plain(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _as_dict(export: HouseholdExport) -> dict[str, object]:
    data = dataclasses.asdict(export)
    return {"format_version": export.meta.format_version, **{k: _plain(v) for k, v in data.items()}}


def render_json(export: HouseholdExport) -> bytes:
    return json.dumps(_as_dict(export), ensure_ascii=False, indent=2).encode("utf-8")


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return safe_cell(value)
    return str(_plain(value))


def _csv(rows: Sequence[object], columns: list[str]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(getattr(row, c)) for c in columns])
    return buffer.getvalue().encode("utf-8-sig")


def render_csv_zip(export: HouseholdExport) -> bytes:
    manifest = json.dumps(_plain(dataclasses.asdict(export.meta)), ensure_ascii=False, indent=2)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, manifest.encode("utf-8"))
        for name, row_type in CSV_FILES.items():
            columns = [f.name for f in dataclasses.fields(row_type)]
            archive.writestr(f"{name}.csv", _csv(getattr(export, name), columns))
    return buffer.getvalue()
