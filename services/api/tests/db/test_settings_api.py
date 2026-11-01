"""Ajustes: contraseña, sesiones y tarjetas de recarga desde la web (OF-704)."""

from fastapi.testclient import TestClient

from .conftest import CSRF, PASSWORD, login
from .test_imports_api import upload

NEW = "una-clave-nueva-larga"


def change(client, current: str = PASSWORD, new: str = NEW):
    return client.post(
        "/api/v1/me/password", json={"current_password": current, "new_password": new}
    )


def second_session(app, email: str = "raul@example.org", password: str = PASSWORD) -> TestClient:
    c = TestClient(app, headers=CSRF)
    assert login(c, email, password).status_code == 200
    return c


class TestPassword:
    def test_change_revokes_the_other_sessions_but_keeps_this_one(
        self, app, as_raul, as_elena
    ) -> None:
        phone = second_session(app)
        r = change(as_raul)
        assert (r.status_code, r.json()["revoked"]) == (200, 1)
        assert as_raul.get("/api/v1/me").status_code == 200
        assert phone.get("/api/v1/me").status_code == 401
        assert as_elena.get("/api/v1/me").status_code == 200
        assert login(TestClient(app, headers=CSRF), "raul@example.org", NEW).status_code == 200

    def test_wrong_current_password_is_422_not_401(self, as_raul) -> None:
        r = change(as_raul, current="no-es-esta-clave")
        assert r.status_code == 422
        assert as_raul.get("/api/v1/me").status_code == 200

    def test_weak_or_equal_new_password(self, as_raul) -> None:
        assert change(as_raul, new="corta").status_code == 422
        assert change(as_raul, new=PASSWORD).status_code == 422

    def test_repeated_wrong_attempts_are_throttled(self, as_raul) -> None:
        codes = [change(as_raul, current=f"mala-{i}-clave").status_code for i in range(6)]
        assert codes[-1] == 429

    def test_requires_session_and_csrf(self, client, app, seed) -> None:
        assert change(client).status_code == 401
        plain = TestClient(app)
        login(plain, "raul@example.org")
        r = plain.post(
            "/api/v1/me/password", json={"current_password": PASSWORD, "new_password": NEW}
        )
        assert r.status_code == 403


class TestSessions:
    def test_revoke_others(self, app, as_raul) -> None:
        phone, laptop = second_session(app), second_session(app)
        r = as_raul.post("/api/v1/me/sessions/revoke-others")
        assert r.json()["revoked"] == 2
        assert phone.get("/api/v1/me").status_code == 401
        assert laptop.get("/api/v1/me").status_code == 401
        assert as_raul.get("/api/v1/me").status_code == 200


class TestPatterns:
    def test_each_person_manages_only_their_own(self, as_raul, as_elena, as_ana) -> None:
        r = as_raul.post("/api/v1/me/patterns", json={"pattern": "*1234"})
        assert (r.status_code, r.json()) == (201, {"pattern": "*1234", "direction": "inflow"})
        assert as_elena.get("/api/v1/me/patterns").json() == []
        assert as_ana.get("/api/v1/me/patterns").json() == []
        # La pareja no puede borrar el patrón del otro.
        assert as_elena.delete("/api/v1/me/patterns/inflow/*1234").status_code == 404
        assert as_raul.get("/api/v1/me/patterns").json() == [
            {"pattern": "*1234", "direction": "inflow"}
        ]
        assert as_raul.delete("/api/v1/me/patterns/inflow/*1234").status_code == 204
        assert as_raul.get("/api/v1/me/patterns").json() == []

    def test_weak_pattern(self, as_raul) -> None:
        assert as_raul.post("/api/v1/me/patterns", json={"pattern": "***"}).status_code == 422

    def test_import_into_the_joint_warns_who_has_no_recharge_card(
        self, as_raul, as_elena, seed
    ) -> None:
        def missing() -> set[str]:
            return set(upload(as_raul, seed.joint.id).json()["members_without_recharge"])

        assert missing() == {str(seed.raul.id), str(seed.elena.id)}
        as_elena.post("/api/v1/me/patterns", json={"pattern": "*9876"})
        assert missing() == {str(seed.raul.id)}

    def test_personal_accounts_do_not_warn(self, as_raul, seed) -> None:
        from .test_xlsx_imports_api import bankinter_xlsx

        r = as_raul.post(
            "/api/v1/imports",
            data={"account_id": str(seed.raul_personal.id)},
            files={"file": ("b.xlsx", bankinter_xlsx(), "application/octet-stream")},
        )
        assert r.json()["members_without_recharge"] == []
