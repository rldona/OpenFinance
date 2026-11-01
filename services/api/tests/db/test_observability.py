"""Logging, identificador de petición y /ready (OF-904)."""

import logging

import pytest
from fastapi.testclient import TestClient

from openfinance.infrastructure.config import Settings
from openfinance.infrastructure.db.session import get_session_factory
from openfinance.infrastructure.logs import configure_logging, parse_level, sanitize_request_id
from openfinance.main import create_app


class TestRequestId:
    def test_generates_one_and_returns_it(self, client) -> None:
        a = client.get("/health").headers["X-Request-ID"]
        b = client.get("/health").headers["X-Request-ID"]
        assert len(a) == 32 and a != b

    def test_keeps_a_valid_one_from_the_proxy(self, client) -> None:
        r = client.get("/health", headers={"X-Request-ID": "nginx-abc123"})
        assert r.headers["X-Request-ID"] == "nginx-abc123"

    @pytest.mark.parametrize("bad", ["a b", "x" * 65, "linea\nfalsa", "<script>"])
    def test_replaces_an_invalid_one(self, client, bad) -> None:
        r = client.get("/health", headers={"X-Request-ID": bad.replace("\n", " ")})
        assert r.headers["X-Request-ID"] != bad
        assert sanitize_request_id(bad) is None

    def test_error_responses_carry_it_too(self, client) -> None:
        r = client.post("/api/v1/auth/logout", headers={"X-Requested-With": "otra"})  # 403
        assert r.status_code == 403
        assert "X-Request-ID" in r.headers


def _ours(caplog) -> list[str]:
    """Solo lo que escribe la API (no el cliente httpx de las pruebas)."""
    return [r.getMessage() for r in caplog.records if r.name == "openfinance.main"]


class TestAccessLog:
    def test_logs_method_path_status_and_id_but_not_the_query(self, client, seed, caplog) -> None:
        caplog.set_level(logging.INFO)
        r = client.get("/api/v1/transactions?q=secreto-personal&month=2026-10")
        assert r.status_code == 401
        lines = [x for x in _ours(caplog) if "/api/v1/transactions" in x]
        assert lines and "401" in lines[0]
        assert not any("secreto-personal" in x for x in _ours(caplog))

    def test_health_checks_do_not_fill_the_log(self, client, caplog) -> None:
        caplog.set_level(logging.INFO)
        client.get("/health")
        assert not [x for x in _ours(caplog) if "/health" in x]

    def test_lines_include_the_request_id(self, client, caplog) -> None:
        caplog.set_level(logging.INFO)
        r = client.get("/api/v1/me", headers={"X-Request-ID": "traza-1"})
        assert r.status_code == 401
        record = next(x for x in caplog.records if "/api/v1/me" in x.getMessage())
        assert record.name == "openfinance.main"


class TestLoggingConfig:
    def test_level_comes_from_settings_and_is_idempotent(self) -> None:
        configure_logging("WARNING")
        configure_logging("DEBUG")
        root = logging.getLogger()
        ours = [h for h in root.handlers if getattr(h, "_openfinance", False)]
        assert len(ours) == 1
        assert root.level == logging.DEBUG
        configure_logging("INFO")

    def test_rejects_an_unknown_level(self) -> None:
        with pytest.raises(ValueError):
            parse_level("charlatan")
        with pytest.raises(ValueError):
            Settings(log_level="charlatan")


class TestReady:
    def test_ok_when_the_database_answers(self, client) -> None:
        r = client.get("/ready")
        assert r.status_code == 200 and r.json()["status"] == "ok"

    def test_503_without_details_when_it_does_not(self) -> None:
        class Broken:
            def __call__(self):
                raise RuntimeError("password=hunter2 host=db")

        app = create_app()
        app.dependency_overrides[get_session_factory] = lambda: Broken()
        r = TestClient(app).get("/ready")
        assert r.status_code == 503
        assert r.json()["status"] == "unavailable"
        assert "hunter2" not in r.text
