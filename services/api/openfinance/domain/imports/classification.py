from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from openfinance.domain.ledger import TransactionKind
from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.domain.shared.text import normalize_text

MIN_PATTERN_ALNUM = 3
MAX_PATTERN = 60


class PatternError(ValueError):
    pass


class PatternDirection(StrEnum):
    INFLOW = "inflow"
    """Entradas en la conjunta que son aportaciones de esa persona (p. ej. ``RECARGA DE *1234``)."""
    OUTFLOW = "outflow"
    """Salidas de su cuenta personal que son su aportación al hogar."""


def normalize_member_pattern(raw: str) -> str:
    """Patrón en la forma con que se compara: mayúsculas, sin tildes, espacios simples.

    Exige al menos tres letras o cifras para que no reconozca cualquier concepto.
    """
    pattern = normalize_text(raw)
    if not pattern:
        raise PatternError("El patrón está vacío")
    if len(pattern) > MAX_PATTERN:
        raise PatternError(f"El patrón no puede superar {MAX_PATTERN} caracteres")
    if not pattern.isprintable():
        raise PatternError("El patrón contiene caracteres no imprimibles")
    if sum(1 for c in pattern if c.isalnum()) < MIN_PATTERN_ALNUM:
        raise PatternError(f"El patrón necesita al menos {MIN_PATTERN_ALNUM} letras o cifras")
    return pattern


@dataclass(frozen=True, slots=True)
class MemberPattern:
    """Texto que, en el concepto del banco, identifica una aportación de una persona."""

    household_id: WorkspaceId
    user_id: UserId
    pattern: str
    direction: PatternDirection = PatternDirection.INFLOW

    def __post_init__(self) -> None:
        if normalize_member_pattern(self.pattern) != self.pattern:
            raise PatternError("El patrón debe estar normalizado")


@dataclass(frozen=True, slots=True)
class ClassificationRules:
    """Cómo reconocer aportaciones y traspasos a ahorro en los conceptos del banco.

    Los patrones se buscan por palabra completa sobre el concepto normalizado
    (mayúsculas, sin tildes): «ANA» no está en «MARIANA» ni «*1234» en «*12345».
    """

    member_patterns: Mapping[str, Sequence[str]] = field(default_factory=dict)
    """Persona → patrones que identifican sus aportaciones (p. ej. su nombre o IBAN)."""
    savings_patterns: Sequence[str] = ()
    """Patrones de traspasos hacia la hucha o la cuenta de ahorro."""
    internal_patterns: Sequence[str] = ()
    outflow_member_patterns: Mapping[str, Sequence[str]] = field(default_factory=dict)
    """Persona → patrones de salidas de su cuenta que son su aportación al hogar."""
    currency: str = "EUR"
    """Moneda de la cuenta: los formatos que no la traen (QIF, CSV) usan esta (OF-1103)."""


def _contains_word(text: str, pattern: str) -> bool:
    """``pattern`` aparece en ``text`` sin letras ni cifras pegadas a sus extremos.

    Solo se exige frontera en el extremo que es letra o cifra: «REVOLUT**» sigue
    reconociendo «REVOLUT**9876*».
    """
    start = text.find(pattern)
    while start != -1:
        end = start + len(pattern)
        before_ok = start == 0 or not (pattern[0].isalnum() and text[start - 1].isalnum())
        after_ok = end == len(text) or not (pattern[-1].isalnum() and text[end].isalnum())
        if before_ok and after_ok:
            return True
        start = text.find(pattern, start + 1)
    return False


def _matches(description: str, patterns: Sequence[str]) -> bool:
    text = normalize_text(description)
    return any(_contains_word(text, normalize_text(p)) for p in patterns if p.strip())


def _member(description: str, by_member: Mapping[str, Sequence[str]]) -> str | None:
    return next((m for m, patterns in by_member.items() if _matches(description, patterns)), None)


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
        member = _member(description, rules.member_patterns)
        if member is not None:
            return TransactionKind.CONTRIBUTION, member
        return TransactionKind.INCOME, None
    if is_inflow:
        return TransactionKind.EXPENSE, None
    member = _member(description, rules.outflow_member_patterns)
    if member is not None:
        return TransactionKind.CONTRIBUTION, member
    return TransactionKind.EXPENSE, None
