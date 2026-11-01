"""Comercios con nombre propio (OF-1001).

El banco escribe un mismo comercio de muchas formas («MERCADONA», «MERCADONA VALENCIA»).
Cada forma normalizada es una *variante* (`merchant_key`); un comercio agrupa una o varias y
tiene el nombre con el que se enseña. Un comercio sin tocar no tiene fila: su nombre es la
variante legible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType
from uuid import UUID

from openfinance.domain.shared.ids import WorkspaceId

MerchantId = NewType("MerchantId", UUID)

MAX_NAME = 60
KEYS_SEPARATOR = "|"
"""Las variantes solo llevan letras, cifras y espacios: «|» no puede aparecer en ellas."""


class MerchantError(ValueError):
    pass


def clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise MerchantError("El nombre del comercio no puede estar vacío")
    if len(cleaned) > MAX_NAME:
        raise MerchantError(f"El nombre del comercio admite como máximo {MAX_NAME} caracteres")
    return cleaned


@dataclass(frozen=True, slots=True)
class Merchant:
    id: MerchantId
    household_id: WorkspaceId
    name: str
    keys: tuple[str, ...]


def join_keys(keys: tuple[str, ...] | list[str] | set[str]) -> str:
    return KEYS_SEPARATOR.join(sorted(keys))


def split_keys(joined: str) -> list[str]:
    return [k for k in joined.split(KEYS_SEPARATOR) if k]
