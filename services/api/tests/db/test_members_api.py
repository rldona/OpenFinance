"""OF-1601: personas con roles, invitaciones y bajas."""

import re
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from openfinance.infrastructure.db.models import InvitationRow
from openfinance.infrastructure.db.repositories import SqlUnitOfWork
from openfinance.infrastructure.time import utc_now
from tests.db.conftest import CSRF, PASSWORD, login

NEW_PASSWORD = "contraseña-nueva-1"


def invite(client, role="editor"):
    r = client.post("/api/v1/household/invitations", json={"role": role})
    assert r.status_code == 201, r.text
    return r.json()


def accept(app, token, email="nuevo@example.org", name="Nuevo", password=NEW_PASSWORD):
    client = TestClient(app, headers=CSRF)
    r = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "display_name": name, "email": email, "password": password},
    )
    return client, r


def join(app, owner, role, email):
    """Invita, acepta y devuelve el cliente ya con sesión de la persona nueva."""
    client, r = accept(app, invite(owner, role)["token"], email=email)
    assert r.status_code == 201, r.text
    return client


# --- roles -----------------------------------------------------------------------------------


def test_existing_people_are_owners_and_me_says_so(as_raul, as_elena):
    assert as_raul.get("/api/v1/me").json()["role"] == "owner"
    members = as_raul.get("/api/v1/household/members").json()
    assert {(m["display_name"], m["role"]) for m in members} == {
        ("Raúl", "owner"),
        ("Elena", "owner"),
    }
    assert [m["display_name"] for m in members if m["is_me"]] == ["Raúl"]
    assert "email" not in members[0]


def test_only_owners_manage_people(app, as_raul, seed):
    editor = join(app, as_raul, "editor", "editor@example.org")
    viewer = join(app, as_raul, "viewer", "viewer@example.org")
    members = as_raul.get("/api/v1/household/members").json()
    target = next(m["id"] for m in members if m["display_name"] == "Elena")
    pending = invite(as_raul)["invitation"]["id"]
    for client in (editor, viewer):
        assert (
            client.post("/api/v1/household/invitations", json={"role": "viewer"}).status_code == 403
        )
        assert client.get("/api/v1/household/invitations").status_code == 403
        assert client.delete(f"/api/v1/household/invitations/{pending}").status_code == 403
        assert (
            client.put(
                f"/api/v1/household/members/{target}/role", json={"role": "viewer"}
            ).status_code
            == 403
        )
        assert client.delete(f"/api/v1/household/members/{target}").status_code == 403
        assert len(client.get("/api/v1/household/members").json()) == 4  # leer sí


def test_a_viewer_cannot_write_anywhere_but_can_read(app, as_raul, seed):
    viewer = join(app, as_raul, "viewer", "viewer@example.org")
    assert viewer.get("/api/v1/accounts").status_code == 200
    assert viewer.get("/api/v1/insights/month").status_code == 200
    write = {
        "account_id": str(seed.joint.id),
        "booked_on": "2026-11-01",
        "description": "Cena",
        "amount": "10.00",
        "kind": "expense",
    }
    assert viewer.post("/api/v1/transactions", json=write).status_code == 403
    assert viewer.put(f"/api/v1/budgets/{uuid4()}", json={"amount": "10"}).status_code == 403


def test_every_write_route_refuses_a_viewer(app, as_raul, seed):
    """Se recorren todas las rutas que escriben: ninguna se puede olvidar."""
    viewer = join(app, as_raul, "viewer", "viewer@example.org")
    allowed = {
        ("POST", "/api/v1/me/password"),
        ("POST", "/api/v1/me/sessions/revoke-others"),
        ("POST", "/api/v1/alerts/dismiss"),
        ("POST", "/api/v1/notifications/subscriptions"),
        ("POST", "/api/v1/notifications/subscriptions/remove"),
        ("PUT", "/api/v1/notifications/preferences"),
        ("POST", "/api/v1/reports/run"),
        # no usan sesión de hogar
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/auth/invitations/accept"),
    }
    checked = 0
    plain = {"direction", "pattern", "currency", "on", "month", "key", "format"}
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            method = method.upper()
            if method in {"GET", "HEAD", "OPTIONS"} or (method, path) in allowed:
                continue
            url = path
            for name in re.findall(r"{(\w+)}", path):
                url = url.replace("{" + name + "}", "x" if name in plain else str(uuid4()))
            response = viewer.request(method, url, json={})
            assert response.status_code == 403, (method, path, response.status_code)
            checked += 1
    assert checked > 40  # de verdad se han recorrido las rutas de escritura


def test_a_viewer_keeps_what_is_theirs(app, as_raul, seed):
    viewer = join(app, as_raul, "viewer", "viewer@example.org")
    assert viewer.post("/api/v1/reports/run", json={
        "from_month": "2026-10", "to_month": "2026-10", "measure": "spent", "group_by": "category",
    }).status_code == 200  # fmt: skip
    assert (
        viewer.put(
            "/api/v1/notifications/preferences", json={"kinds": ["fee"], "weekly": False}
        ).status_code
        == 200
    )
    changed = viewer.post(
        "/api/v1/me/password",
        json={"current_password": NEW_PASSWORD, "new_password": "otra-contraseña-9"},
    )
    assert changed.status_code == 200, changed.text


def test_an_editor_writes_but_does_not_manage(app, as_raul, seed):
    editor = join(app, as_raul, "editor", "editor@example.org")
    r = editor.post(
        "/api/v1/transactions",
        json={
            "account_id": str(seed.joint.id),
            "booked_on": "2026-11-01",
            "description": "Cena",
            "amount": "10.00",
            "kind": "expense",
        },
    )
    assert r.status_code == 201, r.text
    assert editor.post("/api/v1/household/invitations", json={"role": "viewer"}).status_code == 403


def test_a_role_never_opens_someone_elses_personal_account(app, as_raul, seed):
    owner = join(app, as_raul, "owner", "otro-owner@example.org")
    ids = {a["id"] for a in owner.get("/api/v1/accounts").json()}
    assert str(seed.joint.id) in ids
    assert str(seed.raul_personal.id) not in ids
    assert str(seed.elena_personal.id) not in ids
    assert "Peluquería" not in owner.get("/api/v1/transactions").text


# --- invitaciones ----------------------------------------------------------------------------


def test_the_link_is_shown_once_and_only_its_hash_is_stored(as_raul, session_factory):
    created = invite(as_raul)
    token = created["token"]
    assert len(token) >= 40
    listed = as_raul.get("/api/v1/household/invitations")
    assert token not in listed.text and "token" not in listed.json()[0]
    with session_factory() as s:
        rows = s.query(InvitationRow).all()
    assert [r.token_hash for r in rows] != [token] and token not in rows[0].token_hash
    assert len(rows[0].token_hash) == 64


def test_accepting_creates_the_person_with_the_role_and_a_session(app, as_raul, seed):
    created = invite(as_raul, "viewer")
    client, r = accept(app, created["token"], name="  Marta   Gil ")
    assert r.status_code == 201
    assert r.json()["role"] == "viewer"
    assert r.json()["user"]["display_name"] == "Marta Gil"
    assert "of_session" in client.cookies
    assert client.get("/api/v1/me").status_code == 200
    names = {m["display_name"] for m in as_raul.get("/api/v1/household/members").json()}
    assert names == {"Raúl", "Elena", "Marta Gil"}
    assert as_raul.get("/api/v1/household/invitations").json() == []  # ya no está pendiente


def test_an_invitation_is_single_use_and_every_failure_looks_the_same(
    app, as_raul, session_factory
):
    token = invite(as_raul)["token"]
    assert accept(app, token)[1].status_code == 201
    used = accept(app, token, email="otro@example.org")[1]
    unknown = accept(app, "no-existe", email="otro@example.org")[1]
    revoked_id = invite(as_raul)
    as_raul.delete(f"/api/v1/household/invitations/{revoked_id['invitation']['id']}")
    revoked = accept(app, revoked_id["token"], email="otro@example.org")[1]
    expired = invite(as_raul)
    with session_factory() as s:
        s.execute(
            update(InvitationRow)
            .where(InvitationRow.id == UUID(expired["invitation"]["id"]))
            .values(expires_at=utc_now() - timedelta(minutes=1))
        )
        s.commit()
    late = accept(app, expired["token"], email="otro@example.org")[1]
    bodies = {r.status_code: r.json()["detail"] for r in (used, unknown, revoked, late)}
    assert set(bodies) == {422}
    assert len({r.text for r in (used, unknown, revoked, late)}) == 1


def test_accepting_validates_the_person(app, as_raul, seed):
    token = invite(as_raul)["token"]
    assert accept(app, token, password="corta")[1].status_code == 422
    assert accept(app, token, email="no-es-un-email")[1].status_code == 422
    assert accept(app, token, name="   ")[1].status_code == 422
    taken = accept(app, token, email="raul@example.org")[1]
    assert taken.status_code == 409
    assert accept(app, token)[1].status_code == 201  # los fallos no gastan la invitación


def test_trying_many_tokens_is_throttled(app, as_raul):
    codes = [accept(app, f"adivinando-{i}")[1].status_code for i in range(8)]
    assert 429 in codes and codes[0] == 422


def test_invitations_expire_after_a_week(as_raul):
    created = invite(as_raul)["invitation"]
    from datetime import datetime

    span = datetime.fromisoformat(created["expires_at"]) - datetime.fromisoformat(
        created["created_at"]
    )
    assert span == timedelta(days=7)


def test_limits_on_people_and_pending_invitations(app, as_raul):
    for _ in range(10):
        assert (
            as_raul.post("/api/v1/household/invitations", json={"role": "viewer"}).status_code
            == 201
        )
    assert as_raul.post("/api/v1/household/invitations", json={"role": "viewer"}).status_code == 409


def test_a_household_admits_at_most_ten_people(app, as_raul, seed):
    for i in range(8):  # ya son 2
        join(app, as_raul, "viewer", f"persona{i}@example.org")
    assert len(as_raul.get("/api/v1/household/members").json()) == 10
    assert as_raul.post("/api/v1/household/invitations", json={"role": "viewer"}).status_code == 409


# --- cambiar rol y quitar --------------------------------------------------------------------


def test_changing_a_role_takes_effect_at_once(app, as_raul, seed):
    viewer = join(app, as_raul, "viewer", "viewer@example.org")
    body = {
        "account_id": str(seed.joint.id), "booked_on": "2026-11-01",
        "description": "Cena", "amount": "10.00", "kind": "expense",
    }  # fmt: skip
    assert viewer.post("/api/v1/transactions", json=body).status_code == 403
    uid = viewer.get("/api/v1/me").json()["user"]["id"]
    assert (
        as_raul.put(f"/api/v1/household/members/{uid}/role", json={"role": "editor"}).status_code
        == 204
    )
    assert viewer.post("/api/v1/transactions", json=body).status_code == 201
    as_raul.put(f"/api/v1/household/members/{uid}/role", json={"role": "viewer"})
    assert viewer.post("/api/v1/transactions", json=body).status_code == 403


def test_the_household_always_keeps_an_owner(as_raul, as_elena):
    raul = as_raul.get("/api/v1/me").json()["user"]["id"]
    elena = as_elena.get("/api/v1/me").json()["user"]["id"]
    assert (
        as_raul.put(f"/api/v1/household/members/{elena}/role", json={"role": "editor"}).status_code
        == 204
    )
    # Raúl es el único owner: ni se degrada ni se quita
    assert (
        as_raul.put(f"/api/v1/household/members/{raul}/role", json={"role": "editor"}).status_code
        == 422
    )
    assert as_raul.delete(f"/api/v1/household/members/{raul}").status_code == 422


def test_removing_someone_closes_their_sessions(app, as_raul, seed):
    editor = join(app, as_raul, "editor", "editor@example.org")
    uid = editor.get("/api/v1/me").json()["user"]["id"]
    assert as_raul.delete(f"/api/v1/household/members/{uid}").status_code == 204
    assert editor.get("/api/v1/me").status_code == 401
    assert login(editor, "editor@example.org", NEW_PASSWORD).status_code == 401
    names = {m["display_name"] for m in as_raul.get("/api/v1/household/members").json()}
    assert names == {"Raúl", "Elena"}


def test_someone_with_personal_accounts_cannot_be_removed(as_raul, as_elena):
    elena = as_elena.get("/api/v1/me").json()["user"]["id"]
    r = as_raul.delete(f"/api/v1/household/members/{elena}")
    assert r.status_code == 422 and "cuentas personales" in r.json()["detail"]
    assert as_raul.delete(f"/api/v1/household/members/{uuid4()}").status_code == 404


def test_you_cannot_remove_yourself(as_raul, as_elena):
    raul = as_raul.get("/api/v1/me").json()["user"]["id"]
    as_raul.put(
        f"/api/v1/household/members/{as_elena.get('/api/v1/me').json()['user']['id']}/role",
        json={"role": "owner"},
    )
    assert as_raul.delete(f"/api/v1/household/members/{raul}").status_code == 422


# --- otros hogares ---------------------------------------------------------------------------


def test_another_household_cannot_see_or_touch_ours(as_raul, as_ana, seed):
    pending = invite(as_raul)
    raul = as_raul.get("/api/v1/me").json()["user"]["id"]
    assert [m["display_name"] for m in as_ana.get("/api/v1/household/members").json()] == ["Ana"]
    assert as_ana.get("/api/v1/household/invitations").json() == []
    assert (
        as_ana.delete(f"/api/v1/household/invitations/{pending['invitation']['id']}").status_code
        == 404
    )
    assert (
        as_ana.put(f"/api/v1/household/members/{raul}/role", json={"role": "viewer"}).status_code
        == 404
    )
    assert as_ana.delete(f"/api/v1/household/members/{raul}").status_code == 404
    assert as_raul.get("/api/v1/household/invitations").json() != []


def test_requires_a_session(app, seed):
    anonymous = TestClient(app, headers=CSRF)
    assert anonymous.get("/api/v1/household/members").status_code == 401
    assert anonymous.post("/api/v1/household/invitations", json={}).status_code == 401
    assert PASSWORD and SqlUnitOfWork and pytest
