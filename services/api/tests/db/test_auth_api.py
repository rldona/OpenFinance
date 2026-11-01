from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from openfinance.api import deps
from openfinance.infrastructure.config import Settings, get_settings
from tests.db.conftest import CSRF, PASSWORD, login


def test_login_sets_http_only_session_cookie(client, seed) -> None:
    response = login(client, "Raul@Example.org")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["display_name"] == "Raúl"
    assert body["household"]["name"] == "Nuestra casa"
    assert [m["display_name"] for m in body["members"]] == ["Elena", "Raúl"]
    cookie = response.headers["set-cookie"]
    assert "of_session=" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()


def test_wrong_password_and_unknown_email_look_the_same(client, seed) -> None:
    wrong = login(client, "raul@example.org", "otra-contraseña")
    unknown = login(client, "nadie@example.org", PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_protected_endpoints_require_session(client, seed) -> None:
    for path in ("/api/v1/me", "/api/v1/accounts", "/api/v1/transactions"):
        assert client.get(path).status_code == 401


def test_forged_cookie_is_rejected(client, seed) -> None:
    client.cookies.set("of_session", "inventada")
    assert client.get("/api/v1/me").status_code == 401


def test_logout_invalidates_session(as_raul) -> None:
    assert as_raul.get("/api/v1/me").status_code == 200
    token = as_raul.cookies.get("of_session")
    assert as_raul.post("/api/v1/auth/logout").status_code == 204
    as_raul.cookies.set("of_session", token)  # reutilizar el token ya no sirve
    assert as_raul.get("/api/v1/me").status_code == 401


def test_expired_session_is_rejected(as_raul, monkeypatch) -> None:
    future = datetime.now(UTC) + timedelta(days=31)
    monkeypatch.setattr(deps, "utc_now", lambda: future)
    assert as_raul.get("/api/v1/me").status_code == 401


def _secure_cookie(app) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(session_cookie_secure=True)


def test_secure_cookie_over_http_logs_a_warning(app, seed, caplog) -> None:
    _secure_cookie(app)
    client = TestClient(app, base_url="http://192.168.1.20:8080", headers=CSRF)
    with caplog.at_level("WARNING", logger="openfinance.api.v1.auth"):
        assert login(client, "raul@example.org").status_code == 200
    assert "Secure sobre http" in caplog.text
    assert PASSWORD not in caplog.text
    assert "raul@example.org" not in caplog.text


def test_secure_cookie_over_https_or_localhost_is_quiet(app, seed, caplog) -> None:
    _secure_cookie(app)
    with caplog.at_level("WARNING", logger="openfinance.api.v1.auth"):
        for base in ("https://casa.example.org", "http://localhost:8080"):
            assert (
                login(TestClient(app, base_url=base, headers=CSRF), "raul@example.org").status_code
                == 200
            )
    assert "Secure sobre http" not in caplog.text
