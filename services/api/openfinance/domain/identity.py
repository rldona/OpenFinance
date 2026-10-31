"""Personas que usan OpenFinance."""

from __future__ import annotations

import re
from dataclasses import dataclass

from openfinance.domain.shared.ids import UserId

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 10


class InvalidUserError(ValueError):
    pass


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if not _EMAIL.match(value):
        raise InvalidUserError(f"Email no válido: {email!r}")
    return value


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidUserError(
            f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres"
        )


@dataclass(frozen=True, slots=True)
class User:
    id: UserId
    email: str
    display_name: str
    password_hash: str

    def __post_init__(self) -> None:
        if normalize_email(self.email) != self.email:
            raise InvalidUserError("El email debe estar normalizado")
        if not self.display_name.strip():
            raise InvalidUserError("El nombre no puede estar vacío")
