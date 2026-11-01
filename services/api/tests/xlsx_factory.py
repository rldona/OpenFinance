"""Genera extractos .xlsx sintéticos para los tests (nunca datos reales)."""

from __future__ import annotations

import io
from collections.abc import Iterable, Sequence

from openpyxl import Workbook


def make_xlsx(rows: Iterable[Sequence[object]], sheet: str = "Sheet1") -> bytes:
    workbook = Workbook()
    ws = workbook.active
    assert ws is not None
    ws.title = sheet
    for row in rows:
        ws.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
