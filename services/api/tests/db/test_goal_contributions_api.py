"""OF-1206: aportaciones, prioridad y reparto de los objetivos."""

from datetime import date, timedelta
from uuid import uuid4

import pytest

from openfinance.api.v1 import savings as savings_api
from openfinance.domain.ledger import Account, AccountKind, Institution
from openfinance.domain.shared import Currency, Money
from openfinance.domain.shared.ids import AccountId
from openfinance.infrastructure.db.repositories import SqlUnitOfWork

TODAY = date(2026, 11, 15)


@pytest.fixture(autouse=True)
def november(monkeypatch):
    monkeypatch.setattr(savings_api, "local_today", lambda: TODAY)


def eur(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "EUR"}


def goal(client, name="Fondo", target="1000", **kw):
    r = client.post("/api/v1/goals", json={"name": name, "target": target, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def contribute(client, goal_id, amount, **kw):
    return client.post(f"/api/v1/goals/{goal_id}/contributions", json={"amount": amount, **kw})


def saved(client, goal_id):
    return next(g for g in client.get("/api/v1/goals").json() if g["id"] == goal_id)["saved"]


class TestContributions:
    def test_they_add_to_what_is_saved(self, as_raul) -> None:
        g = goal(as_raul, saved="100")
        r = contribute(as_raul, g["id"], "250,50", note="Paga extra")
        assert r.status_code == 201, r.text
        assert r.json()["contribution"]["amount"] == eur("250.50")
        assert saved(as_raul, g["id"]) == eur("350.50")
        listed = as_raul.get(f"/api/v1/goals/{g['id']}/contributions").json()
        assert [(c["amount"], c["note"], c["made_on"]) for c in listed] == [
            (eur("250.50"), "Paga extra", TODAY.isoformat())
        ]

    def test_a_negative_amount_is_a_withdrawal(self, as_raul) -> None:
        g = goal(as_raul, saved="100")
        contribute(as_raul, g["id"], "-30")
        assert saved(as_raul, g["id"]) == eur("70.00")

    def test_most_recent_first(self, as_raul) -> None:
        g = goal(as_raul)
        old = (TODAY - timedelta(days=40)).isoformat()
        contribute(as_raul, g["id"], "1", made_on=old)
        contribute(as_raul, g["id"], "2", made_on=TODAY.isoformat())
        listed = as_raul.get(f"/api/v1/goals/{g['id']}/contributions").json()
        assert [c["amount"]["amount"] for c in listed] == ["2.00", "1.00"]

    def test_the_projection_uses_them(self, as_raul) -> None:
        g = goal(as_raul, target="1000", monthly="100")
        contribute(as_raul, g["id"], "400")
        after = next(x for x in as_raul.get("/api/v1/goals").json() if x["id"] == g["id"])
        assert (after["progress"], after["remaining"], after["months_to_go"]) == (
            40,
            eur("600.00"),
            6,
        )

    def test_undo_and_redo(self, as_raul) -> None:
        g = goal(as_raul)
        op = contribute(as_raul, g["id"], "100").json()["operation_id"]
        assert as_raul.post(f"/api/v1/changes/{op}/undo").json()["applied"] == 1
        assert saved(as_raul, g["id"]) == eur("0.00")
        assert as_raul.post(f"/api/v1/changes/{op}/redo").json()["applied"] == 1
        assert saved(as_raul, g["id"]) == eur("100.00")

    def test_delete_with_undo(self, as_raul) -> None:
        g = goal(as_raul)
        cid = contribute(as_raul, g["id"], "100").json()["contribution"]["id"]
        op = as_raul.delete(f"/api/v1/goals/{g['id']}/contributions/{cid}").json()["operation_id"]
        assert saved(as_raul, g["id"]) == eur("0.00")
        assert as_raul.post(f"/api/v1/changes/{op}/undo").json()["applied"] == 1
        assert saved(as_raul, g["id"]) == eur("100.00")

    def test_deleting_the_goal_deletes_its_contributions(self, as_raul) -> None:
        g = goal(as_raul)
        contribute(as_raul, g["id"], "100")
        assert as_raul.delete(f"/api/v1/goals/{g['id']}").status_code == 204
        assert as_raul.get(f"/api/v1/goals/{g['id']}/contributions").status_code == 404

    def test_a_goal_with_a_pocket_takes_its_savings_from_the_pocket(
        self, as_raul, seed, session_factory
    ) -> None:
        with session_factory() as s:
            uow = SqlUnitOfWork(s)
            pocket = Account(
                id=AccountId(uuid4()),
                household_id=seed.joint.household_id,
                name="Hucha vacaciones",
                institution=Institution.OTHER,
                kind=AccountKind.SAVINGS,
                currency=Currency("EUR"),
                opening_balance=Money.of("0", "EUR"),
            )
            uow.accounts.add(pocket)
            uow.commit()
        g = goal(as_raul, account_id=str(pocket.id))
        r = contribute(as_raul, g["id"], "10")
        assert r.status_code == 422 and "hucha" in r.json()["detail"]

    def test_validation(self, as_raul) -> None:
        g = goal(as_raul)
        assert contribute(as_raul, g["id"], "0").status_code == 422
        assert contribute(as_raul, g["id"], "abc").status_code == 422
        assert contribute(as_raul, g["id"], "5", note="x" * 201).status_code == 422
        gone = "00000000-0000-0000-0000-000000000000"
        assert contribute(as_raul, gone, "5").status_code == 404
        assert as_raul.delete(f"/api/v1/goals/{g['id']}/contributions/{gone}").status_code == 404


class TestPriority:
    def test_goals_are_listed_by_priority(self, as_raul) -> None:
        goal(as_raul, name="Coche", priority=30)
        goal(as_raul, name="Fondo", priority=10)
        goal(as_raul, name="Viaje", priority=60)
        assert [g["name"] for g in as_raul.get("/api/v1/goals").json()] == [
            "Fondo",
            "Coche",
            "Viaje",
        ]

    def test_default_and_patch(self, as_raul) -> None:
        g = goal(as_raul)
        assert g["priority"] == 50
        r = as_raul.patch(f"/api/v1/goals/{g['id']}", json={"priority": 5})
        assert r.json()["priority"] == 5

    def test_bounds(self, as_raul) -> None:
        assert (
            as_raul.post(
                "/api/v1/goals", json={"name": "X", "target": "5", "priority": 0}
            ).status_code
            == 422
        )
        g = goal(as_raul)
        assert as_raul.patch(f"/api/v1/goals/{g['id']}", json={"priority": 100}).status_code == 422


class TestSplit:
    def test_shares_an_amount_by_priority_up_to_what_each_one_misses(self, as_raul) -> None:
        a = goal(as_raul, name="Fondo", target="300", priority=1)
        b = goal(as_raul, name="Viaje", target="800", priority=2)
        contribute(as_raul, a["id"], "100")
        shares = as_raul.get("/api/v1/goals/split", params={"amount": "500"}).json()
        assert [(s["name"], s["amount"], s["remaining"]) for s in shares] == [
            ("Fondo", eur("200.00"), eur("200.00")),
            ("Viaje", eur("300.00"), eur("800.00")),
        ]
        assert b["id"] == shares[1]["goal_id"]

    def test_it_writes_nothing(self, as_raul) -> None:
        g = goal(as_raul)
        as_raul.get("/api/v1/goals/split", params={"amount": "100"})
        assert as_raul.get(f"/api/v1/goals/{g['id']}/contributions").json() == []

    def test_validation(self, as_raul) -> None:
        assert as_raul.get("/api/v1/goals/split", params={"amount": "0"}).status_code == 422
        assert as_raul.get("/api/v1/goals/split", params={"amount": "x"}).status_code == 422


class TestPrivacy:
    def test_other_households_cannot_see_or_touch_a_goal(self, as_raul, as_ana) -> None:
        g = goal(as_raul)
        cid = contribute(as_raul, g["id"], "100").json()["contribution"]["id"]
        assert as_ana.get("/api/v1/goals").json() == []
        assert as_ana.get(f"/api/v1/goals/{g['id']}/contributions").status_code == 404
        assert contribute(as_ana, g["id"], "5").status_code == 404
        assert as_ana.delete(f"/api/v1/goals/{g['id']}/contributions/{cid}").status_code == 404
        assert as_ana.get("/api/v1/goals/split", params={"amount": "100"}).json() == []
        assert saved(as_raul, g["id"]) == eur("100.00")

    def test_other_households_cannot_undo_it(self, as_raul, as_ana) -> None:
        g = goal(as_raul)
        op = contribute(as_raul, g["id"], "100").json()["operation_id"]
        undone = as_ana.post(f"/api/v1/changes/{op}/undo")
        assert undone.status_code in (403, 404) or undone.json()["applied"] == 0
        assert saved(as_raul, g["id"]) == eur("100.00")

    def test_the_partner_shares_the_household_goals(self, as_raul, as_elena) -> None:
        g = goal(as_raul)
        assert contribute(as_elena, g["id"], "40").status_code == 201
        assert saved(as_raul, g["id"]) == eur("40.00")

    def test_anonymous_gets_401(self, client) -> None:
        gone = "00000000-0000-0000-0000-000000000000"
        assert client.get(f"/api/v1/goals/{gone}/contributions").status_code == 401
