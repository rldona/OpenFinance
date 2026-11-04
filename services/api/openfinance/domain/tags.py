"""Etiquetas de un movimiento (OF-1002): palabras libres del hogar, sin jerarquía."""

from __future__ import annotations

from collections.abc import Iterable

MAX_TAG = 40
MAX_TAGS = 10
SEPARATOR = "|"


class TagError(ValueError):
    pass


def tag_key(tag: str) -> str:
    return tag.casefold()


def clean_tags(raw: Iterable[str]) -> tuple[str, ...]:
    """Etiquetas limpias, sin repetidas (sin distinguir mayúsculas) y en orden alfabético.

    Se quita el «#» inicial y los espacios sobrantes. Una etiqueta no puede estar vacía, pasar
    de 40 caracteres ni llevar «|» o caracteres de control; un movimiento admite hasta 10.
    """
    seen: dict[str, str] = {}
    for item in raw:
        tag = " ".join(item.split()).lstrip("#").strip()
        if not tag:
            raise TagError("Una etiqueta no puede estar vacía")
        if len(tag) > MAX_TAG:
            raise TagError(f"Una etiqueta admite como máximo {MAX_TAG} caracteres")
        if SEPARATOR in tag or not tag.isprintable():
            raise TagError("Una etiqueta no puede llevar «|» ni caracteres de control")
        seen.setdefault(tag_key(tag), tag)
    if len(seen) > MAX_TAGS:
        raise TagError(f"Un movimiento admite como máximo {MAX_TAGS} etiquetas")
    return tuple(seen[k] for k in sorted(seen))


def join_tags(tags: Iterable[str]) -> str:
    return SEPARATOR.join(sorted(tags, key=tag_key))


def split_tags(joined: str) -> tuple[str, ...]:
    return tuple(t for t in joined.split(SEPARATOR) if t)
