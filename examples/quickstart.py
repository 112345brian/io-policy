"""Quickstart: a closed enum of request classes, a bound LocalReadProbe, and an AllowanceReader."""
from __future__ import annotations

from datetime import timedelta
from enum import Enum

from io_policy import (
    Allowance,
    AllowanceMode,
    ClassPolicy,
    Guard,
    LocalAnswer,
    LocalReadProbe,
    LocalReadQuery,
    RequestFacts,
    eligibility,
)


class Net(Enum):
    """The caller's closed set of request classes. Each member's value is its ClassPolicy."""

    LISTING = ClassPolicy("listing", "large read", frozenset({Guard.LOCAL_FIRST_PROBE}), may_serve_local=True)
    WRITE = ClassPolicy("write", "small write", frozenset({Guard.RETURN_MINIMAL}), is_write=True)


class Cache:
    """A LocalReadProbe: answers a read from local state, or returns None for a miss."""

    def __init__(self, rows: dict[str, list[dict]]) -> None:
        self.rows = rows

    def answer(self, query: LocalReadQuery[Net]) -> LocalAnswer | None:
        rows = self.rows.get(query.table)
        return LocalAnswer(rows) if rows is not None else None


class Meter:
    """An AllowanceReader: bytes that crossed the network in the trailing window (here a fixed figure)."""

    def __init__(self, spent: int) -> None:
        self.spent = spent

    def spent_wire_bytes(self, io_class: Net | None, window: timedelta) -> int:
        return self.spent


probe: LocalReadProbe[Net] = Cache({"items": [{"id": 1}]})
allowance = Allowance(total_bytes=1000, window=timedelta(days=30), shares={Net.LISTING: 1.0})


def decide(table: str, spent: int, mode: AllowanceMode = AllowanceMode.WARN) -> str:
    query = LocalReadQuery("GET", table, None, Net.LISTING)
    status = allowance.status(Net.LISTING, Meter(spent))
    facts = RequestFacts("GET", table, Net.LISTING, local=probe.answer(query), allowance=status, allowance_mode=mode)
    return eligibility(facts).outcome.value


results = [decide("other", 0), decide("items", 2000), decide("other", 2000, AllowanceMode.ENFORCE)]

if __name__ == "__main__":
    print(results)
