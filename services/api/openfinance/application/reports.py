"""Informes a medida: ejecutar una definición y guardarla (ADR-0025, OF-1503).

Una definición se ejecuta siempre con los permisos de quien la ejecuta: solo ve las cuentas
que ve él (ADR-0013). Filtrar por una cuenta que no ve es 404, no un resultado vacío. Un
informe compartido comparte la definición, nunca los datos.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from openfinance.application.conversion import MissingRate, missing_rates, report_transactions
from openfinance.application.errors import ConflictError, InvalidRequestError, NotFoundError
from openfinance.application.ledger import visible_accounts
from openfinance.application.ports import UnitOfWork
from openfinance.domain.categories import merchant_label
from openfinance.domain.ledger import AccountKind
from openfinance.domain.reports import (
    MAX_SAVED_PER_PERSON,
    GroupBy,
    ReportDefinition,
    ReportError,
    ReportResult,
    SavedReport,
    aggregate,
    clean_name,
)
from openfinance.domain.shared import Currency
from openfinance.domain.shared.ids import AccountId, TransactionId
from openfinance.domain.workspaces import Actor


@dataclass(frozen=True, slots=True)
class ReportView:
    currency: Currency
    result: ReportResult
    labels: dict[str | None, str]
    missing: list[MissingRate]
    ignored_accounts: int = 0
    """Cuentas del filtro que quien ejecuta no ve (solo en informes compartidos ajenos)."""


def _report_accounts(uow: UnitOfWork, actor: Actor) -> dict[AccountId, str]:
    return {a.id: a.name for a in visible_accounts(uow, actor) if a.type.counts_in_reports}


def _labels(
    uow: UnitOfWork,
    actor: Actor,
    group_by: GroupBy,
    accounts: dict[AccountId, str],
    keys: list[str | None],
) -> dict[str | None, str]:
    if group_by is GroupBy.CATEGORY:
        names = {str(c.id): c.name for c in uow.categories.for_household(actor.household_id)}
        return {k: names.get(k, "Categoría") if k else "Sin categoría" for k in keys}
    if group_by is GroupBy.ACCOUNT:
        return {k: accounts.get(AccountId(UUID(k)), "Cuenta") if k else "Cuenta" for k in keys}
    if group_by is GroupBy.MERCHANT:
        return {k: merchant_label(k) if k else "Sin comercio" for k in keys}
    return {k: k or "" for k in keys}


def _check_filters(
    uow: UnitOfWork, actor: Actor, d: ReportDefinition, accounts: dict[AccountId, str]
) -> None:
    if any(AccountId(i) not in accounts for i in d.account_ids):
        raise NotFoundError("Cuenta no encontrada")
    if d.category_ids:
        known = {c.id for c in uow.categories.for_household(actor.household_id)}
        if any(i not in known for i in d.category_ids):
            raise NotFoundError("Categoría no encontrada")


def run_definition(
    uow: UnitOfWork, actor: Actor, d: ReportDefinition, *, lenient: bool = False
) -> ReportView:
    household = uow.households.get(actor.household_id)
    if household is None:
        raise NotFoundError("Hogar no encontrado")
    accounts = _report_accounts(uow, actor)
    ignored = 0
    if lenient and d.account_ids:
        seen = tuple(i for i in d.account_ids if AccountId(i) in accounts)
        ignored = len(d.account_ids) - len(seen)
        if not seen:
            empty = aggregate(d, [], household.currency, {})
            return ReportView(household.currency, empty, {}, [], ignored)
        d = replace(d, account_ids=seen)
    else:
        _check_filters(uow, actor, d, accounts)
    ids = [AccountId(i) for i in d.account_ids] if d.account_ids else list(accounts)
    txns = (
        report_transactions(uow, actor.household_id, ids, d.from_month.start, d.to_month.end)
        if ids
        else []
    )
    tags = (
        uow.tags.for_transactions(actor.household_id, [TransactionId(t.id) for t in txns])
        if d.tags and txns
        else {}
    )
    result = aggregate(d, txns, household.currency, tags)
    labels = _labels(uow, actor, d.group_by, accounts, [r.key for r in result.rows])
    return ReportView(household.currency, result, labels, missing_rates(uow, actor), ignored)


# --- informes guardados ----------------------------------------------------------------------


def _check_shareable(uow: UnitOfWork, actor: Actor, d: ReportDefinition, shared: bool) -> None:
    """Un informe compartido no puede filtrar por cuentas personales: enseñaría sus ids."""
    if not shared or not d.account_ids:
        return
    personal = {
        a.id
        for a in uow.accounts.for_household(actor.household_id)
        if a.kind is AccountKind.PERSONAL
    }
    if any(AccountId(i) in personal for i in d.account_ids):
        raise InvalidRequestError("Un informe compartido no puede filtrar por cuentas personales")


def list_saved(uow: UnitOfWork, actor: Actor) -> list[SavedReport]:
    return uow.reports.visible_to(actor.household_id, actor.user_id)


def _owned(uow: UnitOfWork, actor: Actor, report_id: UUID) -> SavedReport:
    report = uow.reports.get(actor.household_id, report_id)
    # Los personales ajenos no existen para nadie más; los compartidos se ven pero no se tocan.
    if report is None or (report.owner_id != actor.user_id and not report.shared):
        raise NotFoundError("Informe no encontrado")
    if report.owner_id != actor.user_id:
        raise InvalidRequestError("Solo quien creó el informe puede cambiarlo")
    return report


def create_saved(
    uow: UnitOfWork,
    actor: Actor,
    name: str,
    definition: ReportDefinition,
    shared: bool,
    now: datetime,
) -> SavedReport:
    _check_filters(uow, actor, definition, _report_accounts(uow, actor))
    _check_shareable(uow, actor, definition, shared)
    if uow.reports.count_owned(actor.household_id, actor.user_id) >= MAX_SAVED_PER_PERSON:
        raise ConflictError(f"Puedes guardar hasta {MAX_SAVED_PER_PERSON} informes; borra alguno")
    try:
        report = SavedReport(
            uuid4(), actor.household_id, actor.user_id, clean_name(name), definition, shared, now
        )
    except ReportError as exc:
        raise InvalidRequestError(str(exc)) from exc
    uow.reports.add(report)
    uow.commit()
    return report


def update_saved(
    uow: UnitOfWork,
    actor: Actor,
    report_id: UUID,
    name: str,
    definition: ReportDefinition,
    shared: bool,
) -> SavedReport:
    current = _owned(uow, actor, report_id)
    _check_filters(uow, actor, definition, _report_accounts(uow, actor))
    _check_shareable(uow, actor, definition, shared)
    try:
        updated = replace(current, name=clean_name(name), definition=definition, shared=shared)
    except ReportError as exc:
        raise InvalidRequestError(str(exc)) from exc
    uow.reports.save(updated)
    uow.commit()
    return updated


def delete_saved(uow: UnitOfWork, actor: Actor, report_id: UUID) -> None:
    report = _owned(uow, actor, report_id)
    uow.reports.delete(actor.household_id, report.id)
    uow.commit()


def run_saved(uow: UnitOfWork, actor: Actor, report_id: UUID) -> tuple[SavedReport, ReportView]:
    report = uow.reports.get(actor.household_id, report_id)
    if report is None or (report.owner_id != actor.user_id and not report.shared):
        raise NotFoundError("Informe no encontrado")
    mine = report.owner_id == actor.user_id
    return report, run_definition(uow, actor, report.definition, lenient=not mine)
