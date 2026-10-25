"""The rolling byte allowance and its effect on ``eligibility``, with a toy class enum and an in-memory reader."""
from __future__ import annotations

from datetime import timedelta
from enum import Enum

import pytest

from io_policy import (
    ALLOWANCE_EXCEEDED,
    Allowance,
    AllowanceMode,
    AllowanceStatus,
    ClassPolicy,
    Guard,
    LocalAnswer,
    Outcome,
    RequestFacts,
    allowance_exempt,
    allowance_limited,
    eligibility,
)

G = Guard
WINDOW = timedelta(days=30)


class Toy(Enum):
    BULK = ClassPolicy("bulk", "bulk read", frozenset({G.LOCAL_FIRST_PROBE}), may_serve_local=True)
    LOG = ClassPolicy("log", "log read", frozenset({G.LOCAL_FIRST_PROBE}), may_serve_local=True)
    STATE = ClassPolicy("state", "never stale", frozenset({G.NEVER_STALE}))
    PUT = ClassPolicy("put", "write", frozenset({G.RETURN_MINIMAL}), is_write=True)
    LOOKUP = ClassPolicy(
        "lookup", "small essential read", frozenset({G.LOCAL_FIRST_PROBE}), may_serve_local=True, allowance_essential=True,
    )


def default_allowance(total: int = 5_000_000_000, *, reserve_fraction: float = 0.0) -> Allowance[Toy]:
    return Allowance(total, WINDOW, {Toy.BULK: 0.55, Toy.LOG: 0.25}, reserve_fraction)


def _status(spent=0, cap=100, total_spent=0, total_cap=1000) -> AllowanceStatus:
    return AllowanceStatus(spent, cap, total_spent, total_cap, 30)


class FakeReader:
    def __init__(self, per_class: dict[Toy | None, int] | None = None):
        self.per_class = per_class or {}
        self.asked: list[tuple[Toy | None, timedelta]] = []

    def spent_wire_bytes(self, io_class, window):
        self.asked.append((io_class, window))
        if io_class is None:
            return sum(self.per_class.values())
        return self.per_class.get(io_class, 0)


def test_every_limited_class_has_a_share_and_exempt_ones_are_writes_and_never_stale_reads():
    a = default_allowance()
    assert sum(a.shares.values()) <= 1.0
    assert {c for c in Toy if a.cap(c) > 0} == {c for c in Toy if allowance_limited(c)} == {Toy.BULK, Toy.LOG}
    assert {c for c in Toy if allowance_exempt(c)} == {Toy.STATE, Toy.PUT}


def test_the_reserve_shrinks_what_the_reader_is_measured_against():
    a = default_allowance(1000, reserve_fraction=0.2)
    assert a.usable_bytes == 800 and a.cap(Toy.BULK) == int(800 * 0.55)
    status = a.status(Toy.BULK, FakeReader({Toy.BULK: 10}))
    assert status.total_cap == 800 and status.spent == 10


@pytest.mark.parametrize("bad", [
    dict(total_bytes=-1, window=WINDOW, shares={}),
    dict(total_bytes=10, window=timedelta(0), shares={}),
    dict(total_bytes=10, window=WINDOW, shares={Toy.LOG: 0.7, Toy.BULK: 0.7}),
    dict(total_bytes=10, window=WINDOW, shares={Toy.LOG: -0.1}),
    dict(total_bytes=10, window=WINDOW, shares={}, reserve_fraction=1.0),
])
def test_a_nonsensical_allowance_is_refused_at_construction(bad):
    with pytest.raises(ValueError):
        Allowance(**bad)


def test_a_zero_cap_is_over_at_once_and_only_a_class_s_own_spend_trips_it():
    zero = Allowance(0, WINDOW, {Toy.BULK: 1.0})
    assert zero.status(Toy.BULK, FakeReader()).over
    assert not default_allowance(1000).status(Toy.LOG, FakeReader({Toy.BULK: 1000})).over  # the total is no trigger
    assert default_allowance(1000).status(Toy.BULK, FakeReader({Toy.BULK: 550})).over
    assert not default_allowance(1000).status(Toy.LOG, FakeReader({Toy.LOG: 5})).over
    assert _status(spent=100, cap=100).remaining == 0 and _status(spent=500, cap=100).remaining == 0


def test_over_allowance_degrades_to_a_local_answer_else_warns_by_default():
    over = _status(spent=200)
    served = eligibility(RequestFacts("GET", "t", Toy.BULK, local=LocalAnswer([1]), allowance=over))
    assert served.outcome is Outcome.SERVED_LOCAL and served.payload == [1] and "over allowance" in served.reason
    warned = eligibility(RequestFacts("GET", "t", Toy.BULK, allowance=over))
    assert warned.outcome is Outcome.ALLOWED and ALLOWANCE_EXCEEDED in warned.findings
    assert eligibility(RequestFacts("GET", "t", Toy.BULK, allowance=_status(spent=1))).outcome is Outcome.ALLOWED
    assert eligibility(RequestFacts("GET", "t", Toy.BULK)).outcome is Outcome.ALLOWED


def test_enforce_mode_refuses_an_over_allowance_request_with_no_local_answer():
    refused = eligibility(RequestFacts(
        "GET", "t", Toy.BULK, allowance=_status(spent=200), allowance_mode=AllowanceMode.ENFORCE,
    ))
    assert refused.outcome is Outcome.REFUSED and "allowance" in refused.reason


def test_an_essential_class_is_counted_but_never_degraded_or_refused():
    over = _status(spent=10**9)
    decision = eligibility(RequestFacts(
        "GET", "t", Toy.LOOKUP, allowance=over, allowance_mode=AllowanceMode.ENFORCE,
    ))
    assert decision.outcome is Outcome.ALLOWED and ALLOWANCE_EXCEEDED not in decision.findings
    served = eligibility(RequestFacts("GET", "t", Toy.LOOKUP, local=LocalAnswer("x"), allowance=over))
    assert served.outcome is Outcome.SERVED_LOCAL and "over allowance" not in served.reason


@pytest.mark.parametrize("cls,method,prefer", [(Toy.STATE, "GET", None), (Toy.PUT, "POST", "return=minimal")])
def test_exempt_classes_are_never_refused_or_served_local_for_allowance(cls, method, prefer):
    decision = eligibility(RequestFacts(
        method, "t", cls, prefer=prefer, local=LocalAnswer("x"), allowance=_status(spent=10**9),
    ))
    assert decision.outcome is Outcome.ALLOWED
