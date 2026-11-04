"""Lector de CSV de cualquier banco, guiado por un perfil (ADR-0020, OF-1105).

El perfil dice dónde está cada dato. Aquí no se adivina nada del contenido: una fila que no
cumple el perfil se descarta con su motivo. Los importes no pasan nunca por ``float``.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from openfinance.domain.csv_profile import DELIMITERS, CsvProfile, CsvSample
from openfinance.domain.imports import (
    ClassificationRules,
    ImportedRow,
    ParseResult,
    SkippedRow,
    check_running_balance,
    fingerprint,
    suggest_kind,
)
from openfinance.domain.shared import Money
from openfinance.infrastructure.importers.common import (
    INVALID_AMOUNT,
    MAX_COLS,
    MAX_ROWS,
    MISSING_AMOUNT,
    ZERO_AMOUNT,
    ImportFormatError,
    to_decimal,
)

_MAX_DESCRIPTION = 500
SAMPLE_ROWS = 12


def _decode(content: bytes, encoding: str) -> str:
    try:
        text = content.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ImportFormatError(
            f"El archivo no está en {encoding}: prueba con otra codificación en el perfil"
        ) from exc
    return text.removeprefix("﻿")


def _read(text: str, delimiter: str) -> list[tuple[int, list[str]]]:
    rows: list[tuple[int, list[str]]] = []
    try:
        for line, cells in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
            if not any(c.strip() for c in cells):
                continue
            if len(cells) > MAX_COLS:
                raise ImportFormatError(f"El archivo tiene demasiadas columnas (máximo {MAX_COLS})")
            rows.append((line, [c.strip() for c in cells]))
            if len(rows) > MAX_ROWS:
                raise ImportFormatError(f"El archivo tiene demasiadas filas (máximo {MAX_ROWS})")
    except csv.Error as exc:
        raise ImportFormatError(f"El CSV no se puede leer: {exc}") from exc
    return rows


def sample(content: bytes) -> CsvSample:
    """Una propuesta de separador y codificación y las primeras filas (no es un perfil)."""
    encoding = "utf-8"
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        encoding, text = "cp1252", content.decode("cp1252", errors="replace")
    text = text.removeprefix("﻿")
    head = [line for line in text.splitlines()[:30] if line.strip()]
    # El separador que da el mismo número de columnas (más de una) en más líneas.
    best, best_score = ",", 0
    for candidate in DELIMITERS:
        counts = [len(next(csv.reader([line], delimiter=candidate))) for line in head]
        multi = [c for c in counts if c > 1]
        score = len(multi) * 1000 + (max(set(multi), key=multi.count) if multi else 0)
        if multi and score > best_score:
            best, best_score = candidate, score
    rows = [cells for _, cells in _read("\n".join(text.splitlines()[:200]), best)[:SAMPLE_ROWS]]
    return CsvSample(best, encoding, rows)


def _cell(cells: list[str], index: int | None) -> str:
    return cells[index] if index is not None and index < len(cells) else ""


def parse_csv(
    content: bytes, account_key: str, rules: ClassificationRules, profile: CsvProfile
) -> ParseResult:
    text = _decode(content, profile.encoding)
    rows = _read(text, profile.delimiter)
    body = rows[profile.skip_rows + (1 if profile.has_header else 0) :]
    # `skip_rows` cuenta líneas del archivo; las vacías no están en `rows`.
    result = ParseResult()
    parsed: list[tuple[datetime, ImportedRow]] = []
    seen: dict[str, int] = {}
    for line, cells in body:
        description = " ".join(
            c for c in (_cell(cells, i) for i in profile.description_columns) if c
        )[:_MAX_DESCRIPTION]
        raw_date = _cell(cells, profile.date_column)
        try:
            booked_at = datetime.strptime(raw_date, profile.date_format)  # noqa: DTZ007 - fecha local
        except ValueError:
            result.skipped.append(SkippedRow(line, "fila no válida: fecha no válida", description))
            continue
        sep = profile.decimal_separator
        try:
            if profile.amount_mode == "single":
                text_amount = _cell(cells, profile.amount_column)
                if not text_amount:
                    result.skipped.append(SkippedRow(line, MISSING_AMOUNT, description))
                    continue
                value = to_decimal(text_amount, decimal_sep=sep)  # type: ignore[arg-type]
                value = -value if profile.invert_sign else value
            else:
                debit = abs(to_decimal(_cell(cells, profile.debit_column), decimal_sep=sep))  # type: ignore[arg-type]
                credit = abs(to_decimal(_cell(cells, profile.credit_column), decimal_sep=sep))  # type: ignore[arg-type]
                if debit and credit:
                    result.skipped.append(
                        SkippedRow(line, "fila no válida: débito y crédito a la vez", description)
                    )
                    continue
                if not debit and not credit:
                    result.skipped.append(SkippedRow(line, MISSING_AMOUNT, description))
                    continue
                value = credit - debit
            amount = Money.of(value, rules.currency)
            balance = None
            if profile.balance_column is not None and _cell(cells, profile.balance_column):
                balance = Money.of(
                    to_decimal(_cell(cells, profile.balance_column), decimal_sep=sep),  # type: ignore[arg-type]
                    rules.currency,
                )
        except ValueError:
            result.skipped.append(SkippedRow(line, INVALID_AMOUNT, description))
            continue
        if amount.is_zero:
            result.skipped.append(SkippedRow(line, ZERO_AMOUNT, description))
            continue
        base = f"{booked_at.isoformat()}|{amount.amount}|{description}|{balance}"
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        kind, member = suggest_kind(description, amount.amount > 0, rules)
        parsed.append(
            (
                booked_at,
                ImportedRow(
                    booked_at=booked_at,
                    value_date=booked_at.date(),
                    description=description or "Movimiento sin concepto",
                    amount=amount,
                    bank_type="",
                    suggested_kind=kind,
                    fingerprint=fingerprint(
                        account_key,
                        booked_at,
                        amount,
                        description,
                        occurrence,
                        discriminator=f"bal:{balance.amount}" if balance else "",
                    ),
                    member=member,
                    balance_after=balance,
                    line=line,
                ),
            )
        )
    # Los bancos dan los movimientos de más nuevo a más viejo o al revés: se deja el orden en
    # que el banco los aplica al saldo (de más viejo a más nuevo).
    if len(parsed) > 1 and parsed[0][0] > parsed[-1][0]:
        parsed.reverse()
    parsed.sort(key=lambda p: p[0])
    result.rows = [row for _, row in parsed]
    result.balance_mismatches = check_running_balance(result.rows)
    return result
