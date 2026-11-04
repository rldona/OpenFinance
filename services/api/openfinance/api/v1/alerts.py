"""Avisos del hogar (ADR-0023, OF-1301)."""

from fastapi import APIRouter, Response, status

from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.v1.schemas import AlertDismissIn, AlertOut
from openfinance.application import alerts
from openfinance.infrastructure.time import local_today, utc_now

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(actor: ActorDep, uow: UowDep) -> list[AlertOut]:
    """Los avisos de hoy que no has descartado, lo más grave primero."""
    return [AlertOut.of(a) for a in alerts.list_alerts(uow, actor, local_today())]


@router.post("/alerts/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_alert(body: AlertDismissIn, actor: ActorDep, uow: UowDep) -> Response:
    alerts.dismiss_alert(uow, actor, body.key, local_today(), utc_now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
