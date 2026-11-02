"""Reglas con condiciones, acciones y fases (ADR-0020, OF-1101).

Una regla dice «si pasa esto, haz aquello». El motor es una función pura: recibe lo que se ve de
un movimiento y las reglas, y devuelve lo que hay que cambiar. No lee ni escribe nada.

Reglas de oro:
- **Sin expresiones regulares.** Solo «contiene», «empieza por» e «igual a». Una regla escrita
  por una persona no puede colgar el servidor.
- **La primera que fija, gana.** Cada campo lo fija una sola vez; lo que ya estaba fijado (por
  una persona o por una regla anterior) no se pisa. Las etiquetas se acumulan.
- Una regla nunca toca el importe, la fecha ni el concepto.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from uuid import UUID

from openfinance.domain.categories import CategoryId, merchant_key
from openfinance.domain.ledger import TransactionKind
from openfinance.domain.shared import Money
from openfinance.domain.shared.ids import WorkspaceId
from openfinance.domain.shared.text import normalize_text
from openfinance.domain.tags import TagError, clean_tags

MAX_NAME = 80
MAX_TEXT = 100
MAX_CONDITIONS = 8
MAX_ACTIONS = 6
MAX_NOTE = 200

GENERIC_KINDS = (TransactionKind.EXPENSE, TransactionKind.INCOME)
"""Un tipo que la propia importación decide y una regla puede corregir; los demás (aportación,
hucha, entre cuentas) los fija una persona o una regla de traspasos y no se tocan."""

SETTABLE_KINDS = (
    TransactionKind.EXPENSE,
    TransactionKind.INCOME,
    TransactionKind.INTERNAL_TRANSFER,
    TransactionKind.SAVINGS_TRANSFER,
)


class RuleError(ValueError):
    pass


class Phase(StrEnum):
    BEFORE = "before"
    NORMAL = "normal"
    AFTER = "after"


_PHASE_ORDER = {Phase.BEFORE: 0, Phase.NORMAL: 1, Phase.AFTER: 2}

TEXT_OPS = ("contains", "starts_with", "equals")


@dataclass(frozen=True, slots=True)
class Condition:
    field: str
    """description | merchant | amount | direction | account | bank_type"""
    op: str
    value: Any
    """Texto, ``[mín, máx]``, ``expense``/``income`` o lista de cuentas, según el campo."""

    def as_json(self) -> dict[str, Any]:
        return {"field": self.field, "op": self.op, "value": self.value}


@dataclass(frozen=True, slots=True)
class Action:
    type: str
    """set_category | set_kind | add_tags | set_note | set_merchant"""
    value: Any

    def as_json(self) -> dict[str, Any]:
        return {"type": self.type, "value": self.value}


@dataclass(frozen=True, slots=True)
class AutomationRule:
    id: UUID
    household_id: WorkspaceId
    scope: str
    """Vacío = de todo el hogar; si no, el identificador de su titular (ADR-0013)."""
    name: str
    phase: Phase
    priority: int
    enabled: bool
    conditions: tuple[Condition, ...]
    actions: tuple[Action, ...]

    def definition(self) -> str:
        """El texto canónico de la regla, tal como se guarda en el registro de cambios."""
        return json.dumps(
            {
                "name": self.name,
                "scope": self.scope,
                "phase": self.phase.value,
                "priority": self.priority,
                "enabled": self.enabled,
                "conditions": [c.as_json() for c in self.conditions],
                "actions": [a.as_json() for a in self.actions],
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class RowView:
    """Lo que una regla puede ver de un movimiento (ya guardado o a punto de importarse)."""

    description: str
    merchant: str
    amount: Money
    kind: TransactionKind
    account_id: str
    bank_type: str = ""


@dataclass(frozen=True, slots=True)
class Fixed:
    """Qué campos ya están fijados y una regla no puede cambiar."""

    category: bool = False
    kind: bool = False
    note: bool = False
    merchant: bool = False


@dataclass(frozen=True, slots=True)
class Decision:
    category_id: CategoryId | None = None
    kind: TransactionKind | None = None
    tags: tuple[str, ...] = ()
    note: str | None = None
    merchant: str | None = None
    fired: tuple[UUID, ...] = field(default=())
    """Las reglas que han cambiado algo, en orden."""

    @property
    def is_empty(self) -> bool:
        return not (self.category_id or self.kind or self.tags or self.note or self.merchant)


# --------------------------------------------------------------------------- validación


def _text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuleError(f"{what}: escribe un texto")
    text = " ".join(value.split())
    if len(text) > MAX_TEXT:
        raise RuleError(f"{what}: como máximo {MAX_TEXT} caracteres")
    return text


def _decimal(value: Any, what: str) -> str:
    try:
        number = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise RuleError(f"{what}: no es un número") from exc
    if not number.is_finite() or number < 0 or number > Decimal("999999999"):
        raise RuleError(f"{what}: tiene que estar entre 0 y 999999999")
    return f"{number:f}"


def parse_condition(raw: Mapping[str, Any]) -> Condition:
    field_name, op, value = raw.get("field"), raw.get("op"), raw.get("value")
    if field_name == "description":
        if op not in TEXT_OPS:
            raise RuleError("El concepto: usa «contiene», «empieza por» o «es igual a»")
        return Condition("description", str(op), _text(value, "El concepto"))
    if field_name == "merchant":
        return Condition("merchant", "equals", _text(value, "El comercio"))
    if field_name == "bank_type":
        return Condition("bank_type", "equals", _text(value, "El tipo del banco"))
    if field_name == "amount":
        if op != "between" or not isinstance(value, (list, tuple)) or len(value) != 2:
            raise RuleError("El importe: indica un mínimo y un máximo")
        low, high = _decimal(value[0], "El mínimo"), _decimal(value[1], "El máximo")
        if Decimal(low) > Decimal(high):
            raise RuleError("El importe mínimo no puede ser mayor que el máximo")
        return Condition("amount", "between", [low, high])
    if field_name == "direction":
        if value not in ("expense", "income"):
            raise RuleError("La dirección es «expense» (sale dinero) o «income» (entra)")
        return Condition("direction", "is", value)
    if field_name == "account":
        if not isinstance(value, (list, tuple)) or not value or len(value) > 20:
            raise RuleError("Elige entre 1 y 20 cuentas")
        try:
            ids = sorted({str(UUID(str(v))) for v in value})
        except ValueError as exc:
            raise RuleError("Cuenta no válida") from exc
        return Condition("account", "in", ids)
    raise RuleError(f"Condición desconocida: {field_name}")


def parse_action(raw: Mapping[str, Any]) -> Action:
    kind, value = raw.get("type"), raw.get("value")
    if kind == "set_category":
        try:
            return Action("set_category", str(UUID(str(value))))
        except ValueError as exc:
            raise RuleError("Categoría no válida") from exc
    if kind == "set_kind":
        try:
            parsed = TransactionKind(str(value))
        except ValueError as exc:
            raise RuleError("Tipo no válido") from exc
        if parsed not in SETTABLE_KINDS:
            raise RuleError("Una regla solo puede poner gasto, ingreso o traspaso")
        return Action("set_kind", parsed.value)
    if kind == "add_tags":
        if not isinstance(value, (list, tuple)) or not value:
            raise RuleError("Indica al menos una etiqueta")
        try:
            return Action("add_tags", list(clean_tags([str(v) for v in value])))
        except TagError as exc:
            raise RuleError(str(exc)) from exc
    if kind == "set_note":
        text = _text(value, "La nota")
        if len(text) > MAX_NOTE:
            raise RuleError(f"La nota de una regla admite como máximo {MAX_NOTE} caracteres")
        return Action("set_note", text)
    if kind == "set_merchant":
        key = normalize_text(_text(value, "El comercio"))
        if merchant_key(key) != key:
            raise RuleError("Usa el comercio tal como sale en Comercios, p. ej. MERCADONA")
        return Action("set_merchant", key)
    raise RuleError(f"Acción desconocida: {kind}")


def parse_conditions(raw: Sequence[Mapping[str, Any]]) -> tuple[Condition, ...]:
    if not raw:
        raise RuleError("Una regla necesita al menos una condición")
    if len(raw) > MAX_CONDITIONS:
        raise RuleError(f"Una regla admite como máximo {MAX_CONDITIONS} condiciones")
    return tuple(parse_condition(c) for c in raw)


def parse_actions(raw: Sequence[Mapping[str, Any]]) -> tuple[Action, ...]:
    if not raw:
        raise RuleError("Una regla necesita al menos una acción")
    if len(raw) > MAX_ACTIONS:
        raise RuleError(f"Una regla admite como máximo {MAX_ACTIONS} acciones")
    return tuple(parse_action(a) for a in raw)


def clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > MAX_NAME:
        raise RuleError(f"El nombre tiene entre 1 y {MAX_NAME} caracteres")
    return cleaned


def from_definition(rule_id: UUID, household_id: WorkspaceId, definition: str) -> AutomationRule:
    """Reconstruye una regla desde su texto canónico (base de datos o registro de cambios)."""
    data = json.loads(definition)
    return AutomationRule(
        id=rule_id,
        household_id=household_id,
        scope=data["scope"],
        name=data["name"],
        phase=Phase(data["phase"]),
        priority=int(data["priority"]),
        enabled=bool(data["enabled"]),
        conditions=parse_conditions(data["conditions"]),
        actions=parse_actions(data["actions"]),
    )


# --------------------------------------------------------------------------- motor


def matches(rule: AutomationRule, view: RowView) -> bool:
    """Todas las condiciones a la vez."""
    for c in rule.conditions:
        if c.field == "description":
            text, wanted = normalize_text(view.description), normalize_text(str(c.value))
            ok = (
                wanted in text
                if c.op == "contains"
                else text.startswith(wanted)
                if c.op == "starts_with"
                else text == wanted
            )
        elif c.field == "merchant":
            ok = normalize_text(view.merchant) == normalize_text(str(c.value))
        elif c.field == "bank_type":
            ok = normalize_text(view.bank_type) == normalize_text(str(c.value))
        elif c.field == "amount":
            low, high = (Decimal(v) for v in c.value)
            ok = low <= abs(view.amount.amount) <= high
        elif c.field == "direction":
            ok = view.amount.is_negative == (c.value == "expense")
        elif c.field == "account":
            ok = view.account_id in c.value
        else:  # no debería llegar: parse_condition lo rechaza
            ok = False
        if not ok:
            return False
    return True


def ordered(rules: Sequence[AutomationRule], phase: Phase) -> list[AutomationRule]:
    return sorted(
        (r for r in rules if r.enabled and r.phase is phase), key=lambda r: (r.priority, str(r.id))
    )


def decide(
    rules: Sequence[AutomationRule],
    view: RowView,
    fixed: Fixed = Fixed(),  # noqa: B008 - es inmutable
    learned_category: CategoryId | None = None,
) -> Decision:
    """Qué cambiar de un movimiento según las reglas.

    Orden: fase ``before``, fase ``normal``, la categoría aprendida («comercio → categoría», que
    decide lo que ninguna regla explícita ha decidido) y fase ``after``.
    """
    category: CategoryId | None = None
    kind: TransactionKind | None = None
    note: str | None = None
    merchant: str | None = None
    tags: list[str] = []
    fired: list[UUID] = []
    locked = {
        "category": fixed.category,
        "kind": fixed.kind,
        "note": fixed.note,
        "merchant": fixed.merchant,
    }

    def run(group: list[AutomationRule]) -> None:
        nonlocal category, kind, note, merchant
        for rule in group:
            if not matches(rule, view):
                continue
            changed = False
            for a in rule.actions:
                if a.type == "set_category" and not locked["category"]:
                    category, locked["category"], changed = CategoryId(UUID(a.value)), True, True
                elif a.type == "set_kind" and not locked["kind"]:
                    kind, locked["kind"], changed = TransactionKind(a.value), True, True
                elif a.type == "set_note" and not locked["note"]:
                    note, locked["note"], changed = a.value, True, True
                elif a.type == "set_merchant" and not locked["merchant"]:
                    merchant, locked["merchant"], changed = a.value, True, True
                elif a.type == "add_tags":
                    new = [t for t in a.value if t.casefold() not in {x.casefold() for x in tags}]
                    if new:
                        tags.extend(new)
                        changed = True
            if changed:
                fired.append(rule.id)

    run(ordered(rules, Phase.BEFORE))
    run(ordered(rules, Phase.NORMAL))
    if learned_category is not None and not locked["category"]:
        category, locked["category"] = learned_category, True
    run(ordered(rules, Phase.AFTER))
    return Decision(category, kind, tuple(tags), note, merchant, tuple(fired))


def sort_key(rule: AutomationRule) -> tuple[int, int, str]:
    return _PHASE_ORDER[rule.phase], rule.priority, str(rule.id)
