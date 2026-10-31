from datetime import UTC, datetime, timedelta

from openfinance.api import deps
from tests.db.conftest import PASSWORD, login


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
