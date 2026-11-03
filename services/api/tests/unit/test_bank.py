"""OF-1401..1404: dominio de la conexión bancaria y el cliente de Enable Banking."""

import base64
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from openfinance.domain.bank import (
    BankAccountRef,
    BankConnection,
    BankError,
    ConsentStatus,
    RemoteTransaction,
    to_rows,
)
from openfinance.domain.imports import ClassificationRules
from openfinance.domain.ledger import TransactionKind
from openfinance.domain.shared import Currency
from openfinance.infrastructure.enablebanking import parse_balance, parse_transaction, sign_jwt

NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)
EUR = Currency("EUR")


def pending() -> BankConnection:
    return BankConnection(
        id=uuid4(),
        household_id=uuid4(),
        owner_id=uuid4(),
        aspsp="Bankinter",
        country="ES",
        status=ConsentStatus.PENDING,
        created_at=NOW,
        state="abc",
    )


def active(valid_days: int = 100) -> BankConnection:
    return pending().activate(
        "sess",
        [
            BankAccountRef("u1", "1234", "Corriente", "EUR"),
            BankAccountRef("u2", "5678", "Ahorro", "EUR"),
        ],
        NOW + timedelta(days=valid_days),
    )


def test_activate_clears_the_state_and_keeps_the_session():
    c = active()
    assert (c.status, c.state, c.session_id) == (ConsentStatus.ACTIVE, "", "sess")
    assert [link.iban_tail for link in c.links] == ["1234", "5678"]
    with pytest.raises(BankError):
        c.activate("again", [], NOW)


def test_expiry_and_warning_window():
    assert active(100).current(NOW).status is ConsentStatus.ACTIVE
    assert not active(100).expires_soon(NOW)
    assert active(10).expires_soon(NOW)
    assert active(14).expires_soon(NOW)
    assert not active(15).expires_soon(NOW)
    expired = active(-1)
    assert expired.current(NOW).status is ConsentStatus.EXPIRED
    assert not expired.expires_soon(NOW)


def test_revoked_forgets_the_session():
    r = active().revoked()
    assert (r.status, r.session_id, r.state) == (ConsentStatus.REVOKED, None, "")


def test_sync_window():
    c = active()
    assert c.sync_start(NOW) == date(2026, 8, 5)
    assert c.synced(NOW).sync_start(NOW + timedelta(days=30)) == date(2026, 10, 27)


def test_link_rules():
    c = active()
    account = uuid4()
    linked = c.link_to("u1", account)
    assert linked.links[0].account_id == account
    with pytest.raises(BankError):
        linked.link_to("u2", account)
    assert linked.link_to("u1", None).links[0].account_id is None
    with pytest.raises(BankError):
        c.link_to("nope", account)
    with pytest.raises(BankError):
        c.revoked().link_to("u1", account)


def tx(entry, amount, day=1, desc="Mercadona", currency="EUR"):
    return RemoteTransaction(entry, date(2026, 10, day), Decimal(amount), currency, desc)


RULES = ClassificationRules(currency="EUR")


def test_rows_use_the_bank_id_so_syncing_twice_does_not_duplicate():
    cid = uuid4()
    first, _ = to_rows(cid, "u1", [tx("A1", "-10.00"), tx("A2", "-10.00")], RULES, EUR)
    again, _ = to_rows(cid, "u1", [tx("A2", "-10.00"), tx("A1", "-10.00")], RULES, EUR)
    assert len({r.fingerprint for r in first}) == 2
    assert {r.fingerprint for r in first} == {r.fingerprint for r in again}
    other, _ = to_rows(uuid4(), "u1", [tx("A1", "-10.00")], RULES, EUR)
    assert other[0].fingerprint not in {r.fingerprint for r in first}


def test_rows_without_bank_id_tell_identical_charges_apart_but_are_stable():
    cid = uuid4()
    rows, _ = to_rows(
        cid, "u1", [tx(None, "-3.50", desc="Café"), tx(None, "-3.50", desc="café")], RULES, EUR
    )
    again, _ = to_rows(
        cid, "u1", [tx(None, "-3.50", desc="Café"), tx(None, "-3.50", desc="café")], RULES, EUR
    )
    assert len({r.fingerprint for r in rows}) == 2
    assert [r.fingerprint for r in rows] == [r.fingerprint for r in again]


def test_rows_skip_other_currencies_and_zero_and_classify_by_sign():
    rows, skipped = to_rows(
        uuid4(),
        "u1",
        [
            tx("A", "-5.00"),
            tx("B", "20.00", desc="Nómina"),
            tx("C", "-1.00", currency="USD"),
            tx("D", "0"),
        ],
        RULES,
        EUR,
    )
    assert skipped == 2
    assert [(r.amount.amount, r.suggested_kind) for r in rows] == [
        (Decimal("-5.00"), TransactionKind.EXPENSE),
        (Decimal("20.00"), TransactionKind.INCOME),
    ]
    assert all(r.bank_type == "PSD2" for r in rows)


# --- Enable Banking ---------------------------------------------------------------------------


def _unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def test_jwt_is_rs256_with_the_application_id_and_a_one_hour_life():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = sign_jwt("app-123", key, 1_000_000)
    head, claims, signature = token.split(".")
    assert json.loads(_unb64(head)) == {"typ": "JWT", "alg": "RS256", "kid": "app-123"}
    assert json.loads(_unb64(claims)) == {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": 1_000_000,
        "exp": 1_003_600,
    }
    key.public_key().verify(
        _unb64(signature), f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256()
    )


def test_parse_transaction_signs_by_direction_and_joins_the_text():
    debit = parse_transaction(
        {
            "entry_reference": "E1",
            "booking_date": "2026-10-05",
            "transaction_amount": {"amount": "12.30", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "creditor": {"name": "Mercadona"},
            "remittance_information": ["Compra tarjeta"],
        }
    )
    assert debit is not None
    assert (debit.entry_id, debit.booked_on, debit.amount) == (
        "E1",
        date(2026, 10, 5),
        Decimal("-12.30"),
    )
    assert debit.description == "Mercadona · Compra tarjeta"
    credit = parse_transaction(
        {
            "transaction_id": "T9",
            "value_date": "2026-10-06",
            "transaction_amount": {"amount": "100", "currency": "EUR"},
            "credit_debit_indicator": "CRDT",
            "debtor": {"name": "Empresa SL"},
        }
    )
    assert credit is not None
    assert (credit.entry_id, credit.amount, credit.description) == (
        "T9",
        Decimal("100"),
        "Empresa SL",
    )


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"booking_date": "2026-10-05", "transaction_amount": {"amount": "x", "currency": "EUR"}},
        {"booking_date": "no-date", "transaction_amount": {"amount": "1", "currency": "EUR"}},
        {"booking_date": "2026-10-05", "transaction_amount": {"amount": "1"}},
    ],
)
def test_parse_transaction_rejects_what_it_cannot_read(raw):
    assert parse_transaction(raw) is None


def test_parse_balance_prefers_the_closing_booked_balance():
    balance = parse_balance(
        {
            "balances": [
                {"balance_type": "ITAV", "balance_amount": {"amount": "5", "currency": "EUR"}},
                {
                    "balance_type": "CLBD",
                    "balance_amount": {"amount": "1234.56", "currency": "EUR"},
                    "reference_date": "2026-11-02",
                },
            ]
        }
    )
    assert balance is not None
    assert balance.amount.amount == Decimal("1234.56")
    assert parse_balance({"balances": []}) is None
