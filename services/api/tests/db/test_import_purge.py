"""El contenido de una vista previa caducada no se conserva (OF-607)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from openfinance import cli
from openfinance.api.v1 import auth as auth_api
from openfinance.infrastructure.db.repositories import SqlUnitOfWork

from .conftest import CSRF, login
from .test_imports_api import upload

LATER = datetime.now(UTC) + timedelta(hours=25)


def content(session_factory, batch_id: str) -> bytes | None:
    with session_factory() as s:
        return SqlUnitOfWork(s).imports.content(UUID(batch_id))


def test_a_preview_older_than_24h_is_purged_on_the_next_login(
    app, as_raul, seed, session_factory, monkeypatch
) -> None:
    preview = upload(as_raul, seed.joint.id).json()
    assert content(session_factory, preview["id"]) is not None
    monkeypatch.setattr(auth_api, "utc_now", lambda: LATER)
    # Entra otra persona del hogar: la purga no depende de quién subió el extracto.
    assert login(TestClient(app, headers=CSRF), "elena@example.org").status_code == 200
    assert content(session_factory, preview["id"]) is None


def test_a_recent_preview_survives_the_login(app, as_raul, seed, session_factory) -> None:
    preview = upload(as_raul, seed.joint.id).json()
    assert login(TestClient(app, headers=CSRF), "elena@example.org").status_code == 200
    assert content(session_factory, preview["id"]) is not None


def test_the_api_purges_when_it_starts(app, as_raul, seed, session_factory, monkeypatch) -> None:
    from openfinance import main

    preview = upload(as_raul, seed.joint.id).json()
    monkeypatch.setattr(main, "utc_now", lambda: LATER)
    with TestClient(app):  # arranca la aplicación (lifespan)
        pass
    assert content(session_factory, preview["id"]) is None


class TestCli:
    @pytest.fixture(autouse=True)
    def database(self, monkeypatch, session_factory):
        monkeypatch.setattr(cli, "get_session_factory", lambda: session_factory)

    def test_imports_purge(self, as_raul, seed, session_factory, monkeypatch, capsys) -> None:
        preview = upload(as_raul, seed.joint.id).json()
        monkeypatch.setattr(cli, "utc_now", lambda: LATER)
        assert cli.main(["imports", "purge"]) == 0
        assert "1 vista previa" in capsys.readouterr().out
        assert content(session_factory, preview["id"]) is None
