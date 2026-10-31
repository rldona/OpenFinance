"""Línea de comandos de OpenFinance.

``openfinance bootstrap`` crea el hogar, sus dos personas y sus cuentas. No hay registro
público: el alta se hace una vez desde el servidor.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from openfinance.application.errors import ApplicationError
from openfinance.application.households import (
    BootstrapRequest,
    NewAccount,
    NewMember,
    bootstrap_household,
)
from openfinance.domain.identity import MIN_PASSWORD_LENGTH
from openfinance.domain.ledger import AccountKind, Institution
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from openfinance.infrastructure.db.session import get_session_factory
from openfinance.infrastructure.security import Argon2PasswordHasher

Prompt = Callable[[str], str]


def _ask(prompt: Prompt, label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = prompt(f"{label}{suffix}: ").strip() or default
        if value:
            return value


def _ask_password(secret: Prompt, name: str) -> str:
    while True:
        first = secret(f"Contraseña de {name} (mín. {MIN_PASSWORD_LENGTH} caracteres): ")
        if len(first) < MIN_PASSWORD_LENGTH:
            print("Demasiado corta.")
            continue
        if secret("Repítela: ") == first:
            return first
        print("No coinciden.")


def _yes(prompt: Prompt, label: str) -> bool:
    return _ask(prompt, f"{label} (s/n)", "s").lower().startswith("s")


def collect_request(prompt: Prompt = input, secret: Prompt = getpass.getpass) -> BootstrapRequest:
    print("Alta del hogar en OpenFinance\n")
    household = _ask(prompt, "Nombre del hogar", "Nuestra casa")
    members: list[NewMember] = []
    for n in (1, 2):
        print(f"\nPersona {n}")
        name = _ask(prompt, "  Nombre")
        email = _ask(prompt, "  Email")
        members.append(NewMember(name, email, _ask_password(secret, name)))

    print("\nCuentas")
    accounts = [
        NewAccount(
            _ask(prompt, "  Nombre de la cuenta conjunta", "Cuenta conjunta"),
            Institution.REVOLUT,
            AccountKind.JOINT,
            _ask(prompt, "  Saldo inicial de la conjunta", "0"),
        )
    ]
    for m in members:
        if _yes(prompt, f"  ¿Añadir la cuenta personal de Bankinter de {m.display_name}?"):
            accounts.append(
                NewAccount(
                    f"Bankinter {m.display_name}",
                    Institution.BANKINTER,
                    AccountKind.PERSONAL,
                    _ask(prompt, "    Saldo inicial", "0"),
                    owner_email=m.email,
                )
            )
    return BootstrapRequest(household, members, accounts)


def _bootstrap(_: argparse.Namespace) -> int:
    request = collect_request()
    with get_session_factory()() as session:
        try:
            household = bootstrap_household(SqlUnitOfWork(session), Argon2PasswordHasher(), request)
        except ApplicationError as exc:
            print(f"\nNo se ha creado el hogar: {exc}", file=sys.stderr)
            return 1
    print(f"\nHogar «{household.name}» creado con {len(request.accounts)} cuentas.")
    print("Las cuentas personales solo las verá su titular.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openfinance")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("bootstrap", help="Crear el hogar, sus personas y sus cuentas").set_defaults(
        func=_bootstrap
    )
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
