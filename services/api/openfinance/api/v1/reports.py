"""Informes a medida (ADR-0025, OF-1503)."""

from __future__ import annotations

import csv
import io
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.export_formats import safe_cell
from openfinance.api.v1.schemas import (
    MoneyOut,
    ReportDefinitionIn,
    ReportDefinitionOut,
    ReportOut,
    ReportRowOut,
    SavedReportIn,
    SavedReportOut,
)
from openfinance.application import reports
from openfinance.application.errors import InvalidRequestError
from openfinance.domain.reports import (
    ReportDefinition,
    ReportError,
    SavedReport,
    make_definition,
    to_dict,
)
from openfinance.infrastructure.time import utc_now

router = APIRouter(prefix="/reports", tags=["reports"])

Format = Annotated[Literal["json", "csv"], Query(description="json (por defecto) o csv")]


def _definition(body: ReportDefinitionIn) -> ReportDefinition:
    try:
        return make_definition(
            body.from_month,
            body.to_month,
            body.measure,
            body.group_by,
            account_ids=body.account_ids,
            category_ids=body.category_ids,
            uncategorized=body.uncategorized,
            tags=body.tags,
            min_amount=body.min_amount,
        )
    except ReportError as exc:
        raise InvalidRequestError(str(exc)) from exc


def _result(view: reports.ReportView) -> ReportOut:
    return ReportOut(
        currency=view.currency.code,
        rows=[
            ReportRowOut(
                key=r.key,
                label=view.labels.get(r.key, ""),
                amount=MoneyOut.of(r.amount),
                count=r.count,
            )
            for r in view.result.rows
        ],
        total=MoneyOut.of(view.result.total),
        count=view.result.count,
        hidden_rows=view.result.hidden_rows,
        missing_rates=[m.currency for m in view.missing],
        ignored_accounts=view.ignored_accounts,
    )


def _csv(view: reports.ReportView, name: str) -> Response:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(["grupo", "importe", "moneda", "movimientos"])
    for r in view.result.rows:
        writer.writerow(
            [
                safe_cell(view.labels.get(r.key, "")),
                r.amount.amount,
                r.amount.currency.code,
                r.count,
            ]
        )
    writer.writerow(["Total", view.result.total.amount, view.currency.code, view.result.count])
    return Response(
        out.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="informe.csv"'},
    )


def _saved(report: SavedReport, mine: bool) -> SavedReportOut:
    return SavedReportOut(
        id=report.id,
        name=report.name,
        shared=report.shared,
        mine=mine,
        definition=ReportDefinitionOut(**to_dict(report.definition)),
        created_at=report.created_at,
    )


@router.post("/run", response_model=ReportOut)
def run(
    body: ReportDefinitionIn, actor: ActorDep, uow: UowDep, format: Format = "json"
) -> ReportOut | Response:
    view = reports.run_definition(uow, actor, _definition(body))
    return _csv(view, "informe") if format == "csv" else _result(view)


@router.get("", response_model=list[SavedReportOut])
def list_saved(actor: ActorDep, uow: UowDep) -> list[SavedReportOut]:
    return [_saved(r, r.owner_id == actor.user_id) for r in reports.list_saved(uow, actor)]


@router.post("", response_model=SavedReportOut, status_code=status.HTTP_201_CREATED)
def create_saved(body: SavedReportIn, actor: ActorDep, uow: UowDep) -> SavedReportOut:
    report = reports.create_saved(
        uow, actor, body.name, _definition(body.definition), body.shared, utc_now()
    )
    return _saved(report, True)


@router.put("/{report_id}", response_model=SavedReportOut)
def update_saved(
    report_id: UUID, body: SavedReportIn, actor: ActorDep, uow: UowDep
) -> SavedReportOut:
    report = reports.update_saved(
        uow, actor, report_id, body.name, _definition(body.definition), body.shared
    )
    return _saved(report, True)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved(report_id: UUID, actor: ActorDep, uow: UowDep) -> Response:
    reports.delete_saved(uow, actor, report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{report_id}/run", response_model=ReportOut)
def run_saved(
    report_id: UUID, actor: ActorDep, uow: UowDep, format: Format = "json"
) -> ReportOut | Response:
    report, view = reports.run_saved(uow, actor, report_id)
    return _csv(view, report.name) if format == "csv" else _result(view)
