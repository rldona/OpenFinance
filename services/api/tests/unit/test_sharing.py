"""OF-1602: el reparto suma exactamente y los saldos suman cero."""

import random
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from openfinance.domain.shared import Currency, Money
from openfinance.domain.sharing import (
    Balance,
    Guest,
    Settlement,
    SettlementStatus,
    SharedExpense,
    SharingError,
    SplitMethod,
    balances,
    split_amount,
    suggest_transfers,
    to_minor,
)

EUR = Currency("EUR")
A, B, C, D = (UUID(int=i) for i in (1, 2, 3, 4))
NOW = datetime(2026, 11, 3, tzinfo=UTC)


def eur(x):
    return Money.of(x, "EUR")


def minor(parts):
    return {k: to_minor(v) for k, v in parts.items()}


def test_equal_split_gives_the_leftover_cents_to_the_first_in_order():
    parts = split_amount(eur("10.00"), SplitMethod.EQUAL, [A, B, C])
    assert minor(parts) == {A: 334, B: 333, C: 333}
    reordered = split_amount(eur("10.00"), SplitMethod.EQUAL, [C, A, B])
    assert minor(reordered) == {C: 334, A: 333, B: 333}


def test_one_person_gets_everything():
    assert minor(split_amount(eur("7.77"), SplitMethod.EQUAL, [A])) == {A: 777}


def test_percentages_must_add_up_to_exactly_100():
    parts = split_amount(
        eur("100.00"),
        SplitMethod.PERCENTAGE,
        [A, B, C],
        {A: Decimal("50"), B: Decimal("30"), C: Decimal("20")},
    )
    assert minor(parts) == {A: 5000, B: 3000, C: 2000}
    for bad in ({A: "50", B: "30", C: "19.99"}, {A: "50", B: "30", C: "20.01"}):
        with pytest.raises(SharingError):
            split_amount(
                eur("100.00"),
                SplitMethod.PERCENTAGE,
                [A, B, C],
                {k: Decimal(v) for k, v in bad.items()},
            )


def test_percentages_that_do_not_divide_evenly_still_sum_exactly():
    parts = split_amount(
        eur("0.10"), SplitMethod.PERCENTAGE, [A, B, C],
        {A: Decimal("33.33"), B: Decimal("33.33"), C: Decimal("33.34")},
    )  # fmt: skip
    assert sum(minor(parts).values()) == 10


def test_exact_amounts_must_sum_to_the_total():
    parts = split_amount(
        eur("30.00"), SplitMethod.EXACT, [A, B], {A: Decimal("12.50"), B: Decimal("17.50")}
    )
    assert minor(parts) == {A: 1250, B: 1750}
    with pytest.raises(SharingError):
        split_amount(
            eur("30.00"), SplitMethod.EXACT, [A, B], {A: Decimal("12.50"), B: Decimal("17.49")}
        )
    with pytest.raises(SharingError):
        split_amount(eur("30.00"), SplitMethod.EXACT, [A, B], {A: Decimal("-5"), B: Decimal("35")})


def test_shares_are_weights_two_to_one_to_one():
    parts = split_amount(
        eur("100.00"), SplitMethod.SHARES, [A, B, C], {A: Decimal(2), B: Decimal(1), C: Decimal(1)}
    )
    assert minor(parts) == {A: 5000, B: 2500, C: 2500}
    odd = split_amount(
        eur("0.05"), SplitMethod.SHARES, [A, B, C], {A: Decimal(1), B: Decimal(1), C: Decimal(1)}
    )
    assert sum(minor(odd).values()) == 5


def test_a_zero_decimal_currency_splits_in_whole_units():
    yen = Money.of("100", "JPY")
    parts = split_amount(yen, SplitMethod.EQUAL, [A, B, C])
    assert sorted(int(v.amount) for v in parts.values()) == [33, 33, 34]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"participants": []},
        {"participants": [A, A]},
        {"participants": [A, B], "method": SplitMethod.SHARES, "values": {A: Decimal(1)}},
        {
            "participants": [A, B],
            "method": SplitMethod.SHARES,
            "values": {A: Decimal(1), B: Decimal(0)},
        },
        {
            "participants": [A],
            "method": SplitMethod.SHARES,
            "values": {A: Decimal(1), B: Decimal(1)},
        },
    ],
)
def test_invalid_splits_are_rejected(kwargs):
    kwargs = {"method": SplitMethod.EQUAL, **kwargs}
    with pytest.raises(SharingError):
        split_amount(
            eur("10.00"), kwargs.pop("method"), kwargs.pop("participants"), kwargs.get("values")
        )


def test_non_positive_totals_are_rejected():
    for bad in ("0", "-5.00"):
        with pytest.raises(SharingError):
            split_amount(eur(bad), SplitMethod.EQUAL, [A, B])


def test_the_sum_of_the_parts_is_always_the_amount_property():
    rng = random.Random(1602)
    ids = [UUID(int=i) for i in range(1, 9)]
    for _ in range(400):
        total = eur(Decimal(rng.randint(1, 2_000_000)).scaleb(-2))
        who = rng.sample(ids, rng.randint(1, len(ids)))
        method = rng.choice(list(SplitMethod))
        if method is SplitMethod.EXACT:
            cents = to_minor(total)
            cuts = sorted(rng.randint(0, cents) for _ in range(len(who) - 1))
            pieces = [b - a for a, b in zip([0, *cuts], [*cuts, cents], strict=True)]
            values = {p: Decimal(c).scaleb(-2) for p, c in zip(who, pieces, strict=True)}
        elif method is SplitMethod.PERCENTAGE:
            cuts = sorted(rng.randint(0, 10_000) for _ in range(len(who) - 1))
            pieces = [b - a for a, b in zip([0, *cuts], [*cuts, 10_000], strict=True)]
            values = {p: Decimal(c).scaleb(-2) for p, c in zip(who, pieces, strict=True)}
        elif method is SplitMethod.SHARES:
            values = {p: Decimal(rng.randint(1, 9)) for p in who}
        else:
            values = None
        parts = split_amount(total, method, who, values)
        assert sum(to_minor(v) for v in parts.values()) == to_minor(total)
        assert set(parts) == set(who) and all(v.amount >= 0 for v in parts.values())


# --- gastos, liquidaciones y saldos -----------------------------------------------------------


def expense(amount, payers, parts, voided=False):
    return SharedExpense(
        id=uuid4(),
        household_id=uuid4(),
        on=date(2026, 11, 1),
        description="Luz",
        amount=eur(amount),
        payers=tuple((p, eur(v)) for p, v in payers),
        method=SplitMethod.EXACT,
        parts=tuple((p, eur(v)) for p, v in parts),
        created_by=uuid4(),
        created_at=NOW,
        voided=voided,
    )


def test_an_expense_refuses_payers_or_parts_that_do_not_add_up():
    with pytest.raises(SharingError):
        expense("90.00", [(A, "89.99")], [(A, "30"), (B, "30"), (C, "30")])
    with pytest.raises(SharingError):
        expense("90.00", [(A, "90")], [(A, "30"), (B, "30"), (C, "29.99")])
    with pytest.raises(SharingError):
        expense("90.00", [(A, "45"), (A, "45")], [(A, "90")])  # pagador repetido
    with pytest.raises(SharingError):
        expense("0", [(A, "0")], [(A, "0")])


def settlement(frm, to, amount, status=SettlementStatus.CONFIRMED):
    return Settlement(
        uuid4(), uuid4(), frm, to, eur(amount), date(2026, 11, 2), uuid4(), NOW, status
    )


def test_balances_sum_to_exactly_zero_and_follow_the_example_of_the_adr():
    # Ana (A) paga 90 de la luz; le toca un tercio a cada una de las tres
    e = expense("90.00", [(A, "90")], [(A, "30"), (B, "30"), (C, "30")])
    result = balances([e], [], EUR)
    assert (result[A].net, result[B].net, result[C].net) == (
        eur("60.00"),
        eur("-30.00"),
        eur("-30.00"),
    )
    assert sum(b.net.amount for b in result.values()) == 0


def test_confirmed_settlements_move_balances_and_pending_ones_do_not():
    e = expense("90.00", [(A, "90")], [(A, "30"), (B, "30"), (C, "30")])
    pending = settlement(B, A, "30.00", SettlementStatus.PENDING)
    cancelled = settlement(C, A, "30.00", SettlementStatus.CANCELLED)
    assert balances([e], [pending, cancelled], EUR)[B].net == eur("-30.00")
    done = settlement(B, A, "30.00")
    result = balances([e], [done], EUR)
    assert result[B].net == eur("0.00") and result[A].net == eur("30.00")
    assert sum(b.net.amount for b in result.values()) == 0


def test_voided_expenses_do_not_count():
    e = expense("90.00", [(A, "90")], [(A, "30"), (B, "30"), (C, "30")], voided=True)
    assert all(b.net.is_zero for b in balances([e], [], EUR, [A, B, C]).values())


def test_a_paid_by_several_people_expense():
    e = expense("100.00", [(A, "60"), (B, "40")], [(A, "25"), (B, "25"), (C, "25"), (D, "25")])
    nets = {k: v.net for k, v in balances([e], [], EUR).items()}
    assert nets == {A: eur("35.00"), B: eur("15.00"), C: eur("-25.00"), D: eur("-25.00")}


def test_suggestions_settle_everyone_with_few_transfers():
    nets = {A: eur("60.00"), B: eur("-30.00"), C: eur("-30.00")}
    transfers = suggest_transfers(nets, EUR)
    assert [(t.from_id, t.to_id, t.amount) for t in transfers] == [
        (B, A, eur("30.00")),
        (C, A, eur("30.00")),
    ]


def test_suggestions_zero_out_every_balance_with_at_most_n_minus_one_transfers():
    rng = random.Random(7)
    for _ in range(300):
        people = [UUID(int=i) for i in range(1, rng.randint(2, 9))]
        cents = [rng.randint(-50_000, 50_000) for _ in people[:-1]]
        cents.append(-sum(cents))
        nets = {
            p: Money.of(Decimal(c).scaleb(-2), "EUR") for p, c in zip(people, cents, strict=True)
        }
        transfers = suggest_transfers(nets, EUR)
        left = {p: to_minor(m) for p, m in nets.items()}
        for t in transfers:
            assert t.amount.amount > 0 and t.from_id != t.to_id
            left[t.from_id] += to_minor(t.amount)
            left[t.to_id] -= to_minor(t.amount)
        assert all(v == 0 for v in left.values())
        assert len(transfers) <= max(0, len([c for c in cents if c]) - 1)


def test_settlements_and_guests_validate():
    with pytest.raises(SharingError):
        settlement(A, A, "5")
    with pytest.raises(SharingError):
        settlement(A, B, "0")
    with pytest.raises(SharingError):
        Guest(uuid4(), uuid4(), "   ")
    assert Balance  # exported


# --- eventos ----------------------------------------------------------------------------------


def test_the_summary_of_an_event_only_counts_active_expenses():
    from openfinance.domain.sharing import Event, summarize_event

    cat = uuid4()
    kept = expense("60.00", [(A, "60")], [(A, "30"), (B, "30")])
    kept = replace(kept, category_id=cat)
    gone = expense("40.00", [(A, "40")], [(A, "20"), (B, "20")], voided=True)
    summary = summarize_event([kept, gone], EUR)
    assert (summary.total, summary.count) == (eur("60.00"), 1)
    assert summary.by_category == {cat: eur("60.00")}
    assert summary.balances[B].net == eur("-30.00")
    assert sum(b.net.amount for b in summary.balances.values()) == 0
    empty = summarize_event([], EUR)
    assert empty.total.is_zero and empty.count == 0 and empty.balances == {}
    assert Event


def test_events_validate_their_name_icon_and_dates():
    from openfinance.domain.sharing import Event

    ok = Event(
        uuid4(), uuid4(), "Roma", NOW, starts_on=date(2026, 12, 1), ends_on=date(2026, 12, 1)
    )
    assert ok.closed is False
    for kwargs in (
        {"name": " "},
        {"name": "x" * 81},
        {"name": "Roma", "icon": " "},
        {"name": "Roma", "starts_on": date(2026, 12, 2), "ends_on": date(2026, 12, 1)},
    ):
        with pytest.raises(SharingError):
            Event(uuid4(), uuid4(), created_at=NOW, **kwargs)
