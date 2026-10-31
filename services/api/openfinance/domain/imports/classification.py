from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from openfinance.domain.imports.model import TransactionKind, normalize_text


@dataclass(frozen=True, slots=True)
class ClassificationRules:
    """Cómo reconocer aportaciones y traspasos a ahorro en los conceptos del banco.

    Los patrones se comparan como subcadenas sobre el concepto normalizado
    (mayúsculas, sin tildes).
    """

    member_patterns: Mapping[str, Sequence[str]] = field(default_factory=dict)
    """Persona → patrones que identifican sus aportaciones (p. ej. su nombre o IBAN)."""
    savings_patterns: Sequence[str] = ()
    """Patrones de traspasos hacia la hucha o la cuenta de ahorro."""
    internal_patterns: Sequence[str] = ()


def _matches(description: str, patterns: Sequence[str]) -> bool:
    text = normalize_text(description)
    return any(normalize_text(p) in text for p in patterns if p.strip())


def suggest_kind(
    description: str, is_inflow: bool, rules: ClassificationRules, *, is_refund: bool = False
) -> tuple[TransactionKind, str | None]:
    """Propone el tipo de movimiento y, si es una aportación, de quién.

    Una devolución (``is_refund``) es un gasto con importe positivo: resta gasto.
    """
    if _matches(description, rules.savings_patterns):
        return TransactionKind.SAVINGS_TRANSFER, None
    if _matches(description, rules.internal_patterns):
        return TransactionKind.INTERNAL_TRANSFER, None
    if is_inflow and not is_refund:
        for member, patterns in rules.member_patterns.items():
            if _matches(description, patterns):
                return TransactionKind.CONTRIBUTION, member
        return TransactionKind.INCOME, None
    return TransactionKind.EXPENSE, None
