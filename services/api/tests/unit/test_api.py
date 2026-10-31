from fastapi.testclient import TestClient

from openfinance import __version__
from openfinance.domain import BOUNDED_CONTEXTS
from openfinance.main import create_app

client = TestClient(create_app())


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_meta_lists_bounded_contexts() -> None:
    body = client.get("/api/v1/meta").json()
    assert body["name"] == "OpenFinance"
    assert body["api_version"] == "v1"
    assert body["contexts"] == list(BOUNDED_CONTEXTS)


def test_openapi_is_published() -> None:
    schema = client.get("/openapi.json").json()
    assert "/health" in schema["paths"]
    assert "/api/v1/meta" in schema["paths"]
