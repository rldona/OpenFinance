from typing import Literal

from fastapi import APIRouter, Response

from openfinance import __version__
from openfinance.api.deps import ActorDep, UowDep
from openfinance.api.export_formats import render_csv_zip, render_json
from openfinance.application.export import export_household
from openfinance.infrastructure.time import local_today, utc_now

router = APIRouter(tags=["export"])

_MEDIA = {"json": "application/json", "csv": "application/zip"}
_EXTENSION = {"json": "json", "csv": "zip"}


@router.get(
    "/export",
    response_class=Response,
    responses={
        200: {
            "description": "Archivo con los datos del hogar que ve quien lo pide",
            "content": {"application/json": {}, "application/zip": {}},
        }
    },
)
def export(actor: ActorDep, uow: UowDep, format: Literal["json", "csv"] = "json") -> Response:
    """Descarga los datos del hogar: JSON o ZIP con un CSV por entidad (OF-501).

    Incluye lo que ve quien la pide; la cuenta personal de la otra persona no sale.
    """
    data = export_household(uow, actor, utc_now(), __version__)
    body = render_json(data) if format == "json" else render_csv_zip(data)
    filename = f"openfinance-{local_today().isoformat()}.{_EXTENSION[format]}"
    return Response(
        content=body,
        media_type=_MEDIA[format],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
