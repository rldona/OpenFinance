"""Línea de comandos de OpenFinance.

``openfinance bootstrap`` crea el hogar, sus dos personas y sus cuentas. No hay registro
público: el alta se hace una vez desde el servidor.

``openfinance member-patterns`` guarda los textos del banco que identifican la aportación
de cada persona, y ``openfinance statement-check`` comprueba un extracto sin base de datos
mostrando solo recuentos. ``openfinance sessions revoke-all`` cierra todas las sesiones (se
usa tras restaurar una copia).

``openfinance users set-password`` cambia la contraseña de alguien (y cierra sus sesiones) y
``openfinance accounts add`` añade una hucha o una cuenta al hogar ya creado.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from openfinance.application.errors import ApplicationError
from openfinance.application.households import (
    BootstrapRequest,
    NewAccount,
    NewMember,
    add_account,
    bootstrap_household,
)
from openfinance.application.imports import (
    DEFAULT_OUTFLOW_CONTRIBUTION_PATTERNS,
    DEFAULT_SAVINGS_PATTERNS,
)
from openfinance.domain.identity import MIN_PASSWORD_LENGTH
from openfinance.domain.imports import ClassificationRules, ParseResult, PatternDirection
from openfinance.domain.imports.batch import MAX_FILE_BYTES
from openfinance.domain.ledger import AccountKind, AccountType, Institution, TransactionKind
from openfinance.domain.shared.text import normalize_text
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from openfinance.infrastructure.db.session import get_session_factory
from openfinance.infrastructure.security import Argon2PasswordHasher
from openfinance.infrastructure.time import utc_now

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


def _demo(args: argparse.Namespace) -> int:
    from openfinance.demo import create_demo
    from openfinance.infrastructure.config import get_settings
    from openfinance.infrastructure.time import local_today

    if get_settings().is_production and not args.force:
        print(
            "La demostración crea usuarios con una contraseña conocida. No se ejecuta en "
            "producción salvo con --force.",
            file=sys.stderr,
        )
        return 1

    with get_session_factory()() as session:
        try:
            r = create_demo(SqlUnitOfWork(session), Argon2PasswordHasher(), local_today())
        except ApplicationError as exc:
            print(f"No se ha creado la demostración: {exc}", file=sys.stderr)
            return 1
    print(
        f"Hogar «{r.household}» con {r.transactions} movimientos ({r.months[0]} a {r.months[1]})."
    )
    print(f"Entra con {r.emails[0]} o {r.emails[1]} y la contraseña «{r.password}».")
    print("Son datos ficticios: no uses estas cuentas para tus datos reales.")
    return 0


def _member_patterns(args: argparse.Namespace) -> int:
    from openfinance.application import member_patterns as mp

    direction = PatternDirection.OUTFLOW if args.outflow else PatternDirection.INFLOW
    with get_session_factory()() as session:
        uow = SqlUnitOfWork(session)
        try:
            if args.action == "add":
                added = mp.add_member_pattern(uow, args.email, args.pattern, direction, utc_now())
                print(f"Guardado «{added.pattern}» ({added.direction.value}) para {args.email}.")
            elif args.action == "remove":
                mp.remove_member_pattern(uow, args.email, args.pattern, direction)
                print("Patrón eliminado.")
            else:
                listed = mp.list_member_patterns(uow, args.email)
                if not listed:
                    print("El hogar no tiene patrones guardados.")
                for item in listed:
                    p = item.pattern
                    print(f"{p.direction.value:8} {item.member.email:30} {p.pattern}")
        except ApplicationError as exc:
            print(f"No se ha podido completar: {exc}", file=sys.stderr)
            return 1
    return 0


def _imports(_: argparse.Namespace) -> int:
    from openfinance.application.imports import purge_expired_imports

    with get_session_factory()() as session:
        purged = purge_expired_imports(SqlUnitOfWork(session), utc_now())
    print(
        "1 vista previa caducada purgada"
        if purged == 1
        else f"{purged} vistas previas caducadas purgadas"
    )
    return 0


def _sessions(_: argparse.Namespace) -> int:
    from openfinance.application.identity import revoke_all_sessions

    with get_session_factory()() as session:
        revoked = revoke_all_sessions(SqlUnitOfWork(session), utc_now())
    print(revoked)
    return 0


def _users(args: argparse.Namespace) -> int:
    from openfinance.application.identity import set_password

    # Se pide sin eco y nunca como argumento: no queda en el historial de la shell.
    password = _ask_password(getpass.getpass, args.email)
    with get_session_factory()() as session:
        try:
            revoked = set_password(
                SqlUnitOfWork(session), Argon2PasswordHasher(), args.email, password
            )
        except ApplicationError as exc:
            print(f"No se ha cambiado la contraseña: {exc}", file=sys.stderr)
            return 1
    closed = "1 sesión cerrada" if revoked == 1 else f"{revoked} sesiones cerradas"
    print(f"Contraseña cambiada para {args.email} ({closed}).")
    return 0


def _accounts(args: argparse.Namespace) -> int:
    kind = AccountKind(args.kind)
    spec = NewAccount(
        args.name,
        Institution(args.bank),
        kind,
        args.opening_balance,
        owner_email=args.email if kind is AccountKind.PERSONAL else None,
        type=AccountType(args.type),
        currency=args.currency,
    )
    with get_session_factory()() as session:
        try:
            account = add_account(SqlUnitOfWork(session), args.email, spec)
        except ApplicationError as exc:
            print(f"No se ha añadido la cuenta: {exc}", file=sys.stderr)
            return 1
    who = "solo la verá su titular" if kind is AccountKind.PERSONAL else "la ve todo el hogar"
    print(f"Cuenta «{account.name}» añadida ({who}).")
    return 0


_KNOWN_BANK_TYPES = {
    "PAGO CON TARJETA": "pago con tarjeta",
    "CARD_PAYMENT": "pago con tarjeta",
    "TRANSFERIR": "transferencia",
    "TRANSFER": "transferencia",
    "RECARGAS": "recarga",
    "TOPUP": "recarga",
    "CARD_REFUND": "devolución",
    "REFUND": "devolución",
    "ATM": "cajero",
    "EXCHANGE": "cambio de divisa",
}


def _bank_type_group(bank_type: str) -> str:
    """El tipo del banco viene del archivo: solo se muestran los conocidos."""
    return _KNOWN_BANK_TYPES.get(normalize_text(bank_type), "otros")


def _generic_reason(reason: str) -> str:
    """El motivo sin los datos de la fila que a veces lo acompañan."""
    head = reason.split(":", 1)[0].strip()
    return "producto distinto de la cuenta" if head.startswith("producto") else head


def _check_rules(bank: str, patterns: Sequence[str]) -> ClassificationRules:
    if bank == "bankinter":
        return ClassificationRules(
            savings_patterns=DEFAULT_SAVINGS_PATTERNS,
            outflow_member_patterns={
                "titular": [*DEFAULT_OUTFLOW_CONTRIBUTION_PATTERNS, *patterns]
            },
        )
    return ClassificationRules(
        member_patterns={f"patrón {i}": [p] for i, p in enumerate(patterns, start=1)},
        savings_patterns=DEFAULT_SAVINGS_PATTERNS,
    )


def _parse_statement(bank: str, content: bytes, rules: ClassificationRules) -> ParseResult:
    from openfinance.infrastructure.importers.bankinter import parse_bankinter
    from openfinance.infrastructure.importers.revolut import RevolutProfile, parse_revolut

    if bank == "bankinter":
        return parse_bankinter(content, "statement-check", rules)
    return parse_revolut(content, RevolutProfile(account_key="statement-check", rules=rules))


def statement_summary(result: ParseResult) -> list[str]:
    """Solo recuentos: ni conceptos, ni importes, ni números de cuenta."""
    reasons = Counter(_generic_reason(s.reason) for s in result.skipped)
    kinds = Counter(r.suggested_kind.value for r in result.rows)
    contributions = [r for r in result.rows if r.suggested_kind is TransactionKind.CONTRIBUTION]
    inflows_without_member = sum(
        1 for r in result.rows if r.suggested_kind is TransactionKind.INCOME and r.amount.amount > 0
    )
    currencies = Counter(r.amount.currency.code for r in result.rows)
    inflow_types = Counter(
        _bank_type_group(r.bank_type) for r in result.rows if r.amount.amount > 0 and r.bank_type
    )
    lines = [
        f"Filas leídas: {len(result.rows) + len(result.skipped)}",
        f"Importables: {len(result.rows)}",
        f"Descartadas: {len(result.skipped)}",
        *(f"  {reason}: {n}" for reason, n in sorted(reasons.items())),
        f"Descuadres de saldo: {len(result.balance_mismatches)}",
        "Tipo propuesto:",
        *(f"  {kind}: {n}" for kind, n in sorted(kinds.items())),
        f"Aportaciones con persona: {sum(1 for r in contributions if r.member)}",
        f"Aportaciones sin persona: {sum(1 for r in contributions if not r.member)}",
        f"Entradas sin persona (propuestas como ingreso): {inflows_without_member}",
        *(f"  entradas de tipo {t}: {n}" for t, n in sorted(inflow_types.items())),
        "Monedas: " + ", ".join(f"{c} {n}" for c, n in sorted(currencies.items())),
        f"Saldo final del banco: {'sí' if result.closing_balance is not None else 'no'}",
    ]
    return lines


def _statement_check(args: argparse.Namespace) -> int:
    from openfinance.infrastructure.importers.common import ImportFormatError

    path = Path(args.file)
    if not path.is_file():
        print("No se encuentra el archivo.", file=sys.stderr)
        return 1
    content = path.read_bytes()
    if len(content) > MAX_FILE_BYTES:
        print("El archivo es demasiado grande (máximo 5 MB).", file=sys.stderr)
        return 1
    try:
        result = _parse_statement(args.bank, content, _check_rules(args.bank, args.patterns))
    except ImportFormatError as exc:
        print(f"No se puede leer: {exc}", file=sys.stderr)
        return 1
    print("\n".join(statement_summary(result)))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openfinance")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("bootstrap", help="Crear el hogar, sus personas y sus cuentas").set_defaults(
        func=_bootstrap
    )
    demo = sub.add_parser("demo", help="Crear un hogar de demostración con 12 meses de datos")
    demo.add_argument("--force", action="store_true", help="Permitirlo también en producción")
    demo.set_defaults(func=_demo)

    quotes = "Escribe el patrón entre comillas simples para que la shell no lo toque: '*1234'"
    patterns = sub.add_parser(
        "member-patterns",
        help="Patrones del banco que identifican la aportación de cada persona",
        description=quotes,
    )
    actions = patterns.add_subparsers(dest="action", required=True)
    for action, text in (("add", "Guardar un patrón"), ("remove", "Eliminar un patrón")):
        p = actions.add_parser(action, help=text, description=quotes)
        p.add_argument("email", help="Email de la persona que aporta")
        p.add_argument("pattern", help="Texto del concepto, p. ej. '*1234' o 'REVOLUT**'")
        p.add_argument(
            "--outflow",
            action="store_true",
            help="Salida de su cuenta personal (por defecto: entrada en la conjunta)",
        )
    listing = actions.add_parser("list", help="Ver los patrones del hogar")
    listing.add_argument("email", help="Email de alguien del hogar")
    listing.set_defaults(outflow=False)
    patterns.set_defaults(func=_member_patterns)

    sessions = sub.add_parser("sessions", help="Sesiones abiertas")
    session_actions = sessions.add_subparsers(dest="action", required=True)
    session_actions.add_parser(
        "revoke-all", help="Cerrar todas las sesiones e imprimir cuántas había"
    )
    sessions.set_defaults(func=_sessions)

    imports = sub.add_parser("imports", help="Importaciones de extractos")
    import_actions = imports.add_subparsers(dest="action", required=True)
    import_actions.add_parser(
        "purge", help="Borrar el archivo de las vistas previas de más de 24 h sin confirmar"
    )
    imports.set_defaults(func=_imports)

    users = sub.add_parser("users", help="Personas del hogar")
    user_actions = users.add_subparsers(dest="action", required=True)
    set_pw = user_actions.add_parser(
        "set-password",
        help="Cambiar la contraseña de alguien y cerrar sus sesiones",
        description="La contraseña se pide sin eco; nunca se pasa como argumento.",
    )
    set_pw.add_argument("email", help="Email de la persona")
    users.set_defaults(func=_users)

    accounts = sub.add_parser("accounts", help="Cuentas del hogar")
    account_actions = accounts.add_subparsers(dest="action", required=True)
    add = account_actions.add_parser(
        "add",
        help="Añadir una hucha o una cuenta al hogar existente",
        description="Una cuenta personal es de EMAIL y solo la ve esa persona (ADR-0013).",
    )
    add.add_argument("email", help="Email de alguien del hogar (titular si es personal)")
    add.add_argument("name", help="Nombre de la cuenta, p. ej. 'Hucha viaje'")
    add.add_argument("--kind", choices=[k.value for k in AccountKind], default="savings")
    add.add_argument("--bank", choices=[i.value for i in Institution], default="revolut")
    add.add_argument(
        "--currency",
        default=None,
        help="Moneda de la cuenta (código ISO, p. ej. USD); por defecto, la del hogar",
    )
    add.add_argument(
        "--type",
        choices=[t.value for t in AccountType],
        default="bank",
        help="Para qué sirve: bank, cash, card, loan o investment (solo seguimiento)",
    )
    add.add_argument("--opening-balance", default="0", help="Saldo inicial, p. ej. 120.50")
    accounts.set_defaults(func=_accounts)

    check = sub.add_parser(
        "statement-check",
        help="Comprobar un extracto sin guardarlo: solo muestra recuentos",
        description=quotes,
    )
    check.add_argument("--bank", choices=("revolut", "bankinter"), required=True)
    check.add_argument(
        "--member-pattern",
        dest="patterns",
        action="append",
        default=[],
        help="Patrón de aportación (entrada en Revolut, salida en Bankinter). Repetible.",
    )
    check.add_argument("file", help="Extracto (CSV o XLSX)")
    check.set_defaults(func=_statement_check)
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
