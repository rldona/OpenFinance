"""Importación de formatos estándar: OFX, QIF y CAMT.053 (ADR-0020, OF-1103 y OF-1104).

Reconoce el formato por el contenido, no por el nombre del archivo. Los lectores de Revolut y
Bankinter siguen asociados a su banco; esto es lo que se usa en las cuentas sin banco propio.
"""

from __future__ import annotations

from openfinance.domain.imports import ClassificationRules, ParseResult
from openfinance.infrastructure.importers.common import ImportFormatError, decode_text
from openfinance.infrastructure.importers.ofx import looks_like_ofx, parse_ofx
from openfinance.infrastructure.importers.qif import looks_like_qif, parse_qif


def parse_standard(content: bytes, account_key: str, rules: ClassificationRules) -> ParseResult:
    text = decode_text(content[:65536])
    if looks_like_ofx(text):
        return parse_ofx(content, account_key, rules)
    if looks_like_qif(text):
        return parse_qif(content, account_key, rules)
    raise ImportFormatError(
        "Formato no reconocido. Se admiten OFX, QIF y CAMT.053; para un CSV de otro banco, "
        "crea antes un perfil"
    )
