"""OF-1303: resumen semanal, su envío y privacidad."""

from datetime import timedelta

from openfinance.domain.weekly import last_full_week
from openfinance.infrastructure.time import local_today
from tests.db.test_notifications_api import FakeSender, run, subscribe

TODAY = local_today()
START, END = last_full_week(TODAY)
PREVIOUS_START, _ = last_full_week(START)


def spend(client, account, amount, on, description="Compra", category=None):
    body = {
        "booked_on": on.isoformat(),
        "description": description,
        "amount": amount,
        "kind": "expense",
        "account_id": str(account.id),
    }
    if category:
        body["category_id"] = category
    r = client.post("/api/v1/transactions", json=body)
    assert r.status_code == 201, r.text


def category(client, slug):
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["slug"] == slug)


class TestSummary:
    def test_compares_with_the_week_before_and_ranks_categories(self, as_raul, seed) -> None:
        super_, ocio = category(as_raul, "super"), category(as_raul, "ocio")
        spend(as_raul, seed.joint, "100.00", PREVIOUS_START + timedelta(days=1))
        spend(as_raul, seed.joint, "80.00", START + timedelta(days=1), category=super_)
        spend(as_raul, seed.joint, "40.00", START + timedelta(days=2), category=ocio)
        spend(as_raul, seed.joint, "999.00", TODAY)  # esta semana no entra
        body = as_raul.get("/api/v1/summary/weekly").json()
        assert (body["start"], body["end"]) == (START.isoformat(), END.isoformat())
        assert body["spent"] == {"amount": "120.00", "currency": "EUR"}
        assert body["previous"]["amount"] == "100.00" and body["change_percent"] == 20
        assert [(t["category_id"], t["amount"]["amount"]) for t in body["top"]] == [
            (super_, "80.00"),
            (ocio, "40.00"),
        ]

    def test_without_a_base_there_is_no_percentage(self, as_raul, seed) -> None:
        spend(as_raul, seed.joint, "10.00", START)
        assert as_raul.get("/api/v1/summary/weekly").json()["change_percent"] is None

    def test_upcoming_payments_in_the_next_seven_days(self, as_raul, seed) -> None:
        for name, days in (("Gimnasio", 3), ("Seguro", 30)):
            as_raul.post(
                "/api/v1/schedule",
                json={
                    "name": name,
                    "amount": "-30.00",
                    "account_id": str(seed.joint.id),
                    "frequency": "once",
                    "first_due": (TODAY + timedelta(days=days)).isoformat(),
                },
            )
        upcoming = as_raul.get("/api/v1/summary/weekly").json()["upcoming"]
        assert [u["name"] for u in upcoming] == ["Gimnasio"]

    def test_a_personal_account_only_counts_for_its_owner(self, as_raul, as_elena, seed) -> None:
        spend(as_elena, seed.elena_personal, "55.00", START + timedelta(days=1))
        assert as_elena.get("/api/v1/summary/weekly").json()["spent"]["amount"] == "55.00"
        assert as_raul.get("/api/v1/summary/weekly").json()["spent"]["amount"] == "0.00"

    def test_another_household_sees_nothing(self, as_raul, as_ana, seed) -> None:
        spend(as_raul, seed.joint, "70.00", START)
        assert as_ana.get("/api/v1/summary/weekly").json()["spent"]["amount"] == "0.00"

    def test_requires_login(self, client) -> None:
        assert client.get("/api/v1/summary/weekly").status_code == 401


class TestWeeklyNotification:
    def weekly(self, sender):
        return [m for _, m in sender.sent if m.tag == "semana"]

    def test_sent_once_per_iso_week(self, as_raul, session_factory) -> None:
        subscribe(as_raul)
        first = FakeSender()
        run(session_factory, first)
        assert len(self.weekly(first)) == 1
        again = FakeSender()
        run(session_factory, again)
        assert self.weekly(again) == []

    def test_the_text_has_no_figures(self, as_raul, seed, session_factory) -> None:
        subscribe(as_raul)
        spend(as_raul, seed.joint, "123.45", START)
        sender = FakeSender()
        run(session_factory, sender)
        (message,) = self.weekly(sender)
        assert "123" not in f"{message.title} {message.body}" and message.url == "/#semana"

    def test_it_can_be_turned_off_per_person(self, as_raul, as_elena, session_factory) -> None:
        subscribe(as_raul)
        subscribe(as_elena, "https://updates.push.services.mozilla.com/wpush/v2/e")
        as_raul.put("/api/v1/notifications/preferences", json={"kinds": [], "weekly": False})
        sender = FakeSender()
        run(session_factory, sender)
        targets = {s.endpoint for s, m in sender.sent if m.tag == "semana"}
        assert targets == {"https://updates.push.services.mozilla.com/wpush/v2/e"}
