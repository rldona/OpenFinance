"""Categorías de gasto y reglas aprendidas por comercio (OF-201, OF-202)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NewType
from uuid import UUID

from openfinance.domain.shared.ids import WorkspaceId
from openfinance.domain.shared.text import normalize_text

CategoryId = NewType("CategoryId", UUID)

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_NAME = 50
MAX_ICON = 8
MAX_MERCHANT = 100


class CategoryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Category:
    id: CategoryId
    household_id: WorkspaceId
    name: str
    icon: str
    color: str
    hidden: bool = False
    slug: str | None = None
    """Identificador estable de las categorías de serie (p. ej. ``super``); None si es propia."""
    position: int = 0

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > MAX_NAME:
            raise CategoryError(f"El nombre debe tener entre 1 y {MAX_NAME} caracteres")
        if self.name != self.name.strip():
            raise CategoryError("El nombre no puede empezar ni acabar con espacios")
        if not self.icon.strip() or len(self.icon) > MAX_ICON:
            raise CategoryError("Icono no válido")
        if not _COLOR.match(self.color):
            raise CategoryError("El color debe tener el formato #rrggbb")

    @property
    def key(self) -> str:
        """Nombre normalizado: dos categorías del mismo hogar no pueden compartirlo."""
        return normalize_text(self.name)


@dataclass(frozen=True, slots=True)
class DefaultCategory:
    slug: str
    name: str
    icon: str
    color: str


DEFAULT_CATEGORIES: tuple[DefaultCategory, ...] = (
    DefaultCategory("vivienda", "Vivienda", "🏠", "#0f766e"),
    DefaultCategory("super", "Supermercado", "🛒", "#16a34a"),
    DefaultCategory("suministros", "Luz, agua, gas e internet", "💡", "#ca8a04"),
    DefaultCategory("restaurantes", "Restaurantes", "🍽️", "#ea580c"),
    DefaultCategory("transporte", "Transporte", "🚗", "#2563eb"),
    DefaultCategory("suscripciones", "Suscripciones", "📺", "#7c3aed"),
    DefaultCategory("salud", "Salud y deporte", "💪", "#db2777"),
    DefaultCategory("ocio", "Ocio", "🎟️", "#0891b2"),
    DefaultCategory("ropa", "Ropa", "👕", "#9333ea"),
    DefaultCategory("hogar", "Hogar", "🛋️", "#65a30d"),
    DefaultCategory("viajes", "Viajes", "✈️", "#0284c7"),
    DefaultCategory("regalos", "Regalos", "🎁", "#e11d48"),
    DefaultCategory("otros", "Otros", "📦", "#64748b"),
)


HOUSEHOLD_SCOPE = ""


@dataclass(frozen=True, slots=True)
class CategoryRule:
    household_id: WorkspaceId
    merchant: str
    """Comercio normalizado (``merchant_key``)."""
    category_id: CategoryId
    scope: str = HOUSEHOLD_SCOPE
    """``""`` = regla del hogar (cuentas compartidas). El id de una persona = regla aprendida en
    su cuenta personal: solo se aplica a sus cuentas personales (ADR-0013)."""


# Prefijos que los bancos añaden delante del comercio (se aplican repetidamente).
_PREFIXES = re.compile(
    r"^(?:COMPRA(?: EN| CON TARJETA| TARJETA)?|PAGO(?: CON TARJETA| EN| A)?|"
    r"RECIBO(?: DE)?|ADEUDO(?: DE)?|CARGO(?: DE| EN)?|CARD PAYMENT(?: TO)?|PAYMENT (?:TO|FROM)|"
    r"TRANSFERENCIA (?:A|DE)|TRANSFER (?:FROM|TO)|BIZUM (?:A|DE)|CASH AT|TARJETA|TO)(?:\s+|$)"
)
_TOKEN_NOISE = re.compile(r"\d")
_STOP = frozenset(
    {"SL", "SA", "SLU", "SAU", "SARL", "SAS", "GMBH", "LTD", "INC", "BV", "COM", "ES", "EU", "WWW"}
)
# Palabras que por sí solas no identifican un comercio.
_GENERIC = frozenset({"PAGO", "COMPRA", "TARJETA", "RECIBO", "CARGO", "ADEUDO", "TRANSFERENCIA"})
# Intermediarios de pago o tiendas generalistas: una regla con solo esta palabra
# clasificaría compras muy distintas.
_BROAD = frozenset(
    {"PAYPAL", "SUMUP", "STRIPE", "ZETTLE", "AMAZON", "AMZN", "GOOGLE", "APPLE", "ALIEXPRESS"}
)
_MIN_SINGLE_WORD = 4


def merchant_key(description: str) -> str:
    """Comercio normalizado a partir del concepto del banco.

    «COMPRA TARJETA 4821 MERCADONA 1234 VALENCIA» → «MERCADONA VALENCIA»;
    «MERCADONA 0087» → «MERCADONA». Quita prefijos, números de tarjeta o terminal,
    referencias con dígitos y sufijos societarios, y se queda con hasta tres palabras.
    Devuelve ``""`` si no queda nada que identifique al comercio.
    """
    text = normalize_text(description)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    words = [w for w in text.split() if not _TOKEN_NOISE.search(w)]
    text = " ".join(words)
    previous = None
    while previous != text:
        previous, text = text, _PREFIXES.sub("", text)
    words = [w for w in text.split() if len(w) > 1 and w not in _STOP]
    if all(w in _GENERIC for w in words):
        return ""
    return " ".join(words[:3])[:MAX_MERCHANT]


def can_learn(merchant: str) -> bool:
    """Si un comercio es lo bastante específico para aprender una regla de él."""
    words = merchant.split()
    if not words:
        return False
    if len(words) == 1:
        return len(words[0]) >= _MIN_SINGLE_WORD and words[0] not in _BROAD
    return True


def merchant_label(key: str) -> str:
    """Versión legible del comercio para mostrar: «MERCADONA» → «Mercadona»."""
    return " ".join(w.capitalize() for w in key.split())


def rule_matches(rule_merchant: str, merchant: str) -> bool:
    """La regla aplica si sus palabras son el principio del comercio.

    «MERCADONA» → «MERCADONA VALENCIA»: sí. «MERCADONA VALENCIA» → «MERCADONA»: no.
    Las reglas de una palabra demasiado corta o genérica solo aplican al comercio exacto.
    """
    if not rule_merchant or not merchant:
        return False
    if rule_merchant == merchant:
        return True
    rule_words, words = rule_merchant.split(), merchant.split()
    if len(rule_words) >= len(words) or not can_learn(rule_merchant):
        return False
    return words[: len(rule_words)] == rule_words


def best_rule(rules: list[CategoryRule], merchant: str) -> CategoryRule | None:
    """La regla más específica que aplica; a igualdad, la personal antes que la del hogar."""
    matching = [r for r in rules if rule_matches(r.merchant, merchant)]
    if not matching:
        return None
    return max(matching, key=lambda r: (len(r.merchant.split()), r.scope != HOUSEHOLD_SCOPE))
