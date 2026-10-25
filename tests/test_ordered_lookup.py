"""The ordered lookup: a walk over sources, local first, that never claims freshness it was not given."""
from __future__ import annotations

from io_policy import (
    Freshness,
    LookupOutcome,
    LookupPlan,
    SourceAnswer,
    resolve,
)


class Fake:
    def __init__(self, name: str, best: Freshness, answer: SourceAnswer) -> None:
        self.name = name
        self.best_freshness = best
        self.answer = answer
        self.calls: list[str] = []

    def find(self, key: str) -> SourceAnswer:
        self.calls.append(key)
        return self.answer


def _found(name: str, fresh: Freshness, value: str = "v", age: float | None = None) -> Fake:
    return Fake(name, fresh, SourceAnswer.found(value, fresh, source=name, age_seconds=age))


def _miss(name: str, fresh: Freshness) -> Fake:
    return Fake(name, fresh, SourceAnswer.miss(fresh, source=name))


def _down(name: str, best: Freshness) -> Fake:
    return Fake(name, best, SourceAnswer.unavailable("down", source=name))


def test_a_satisfying_local_hit_never_consults_the_network():
    local = _found("validated", Freshness.VALIDATED)
    network = _found("network", Freshness.AUTHORITATIVE)
    result = resolve(LookupPlan((local, network)), "k", Freshness.VALIDATED)
    assert result.outcome is LookupOutcome.FOUND and result.source == "validated"
    assert network.calls == []


def test_a_source_weaker_than_required_is_never_consulted():
    stale = _found("stale", Freshness.STALE_OK, age=900.0)
    network = _found("network", Freshness.AUTHORITATIVE)
    result = resolve(LookupPlan((stale, network)), "k", Freshness.VALIDATED)
    assert result.source == "network" and stale.calls == []
    relaxed = resolve(LookupPlan((stale, network)), "k", Freshness.STALE_OK)
    assert relaxed.source == "stale" and relaxed.age_seconds == 900.0 and relaxed.freshness is Freshness.STALE_OK


def test_a_found_answer_weaker_than_it_promised_does_not_satisfy():
    liar = Fake("liar", Freshness.AUTHORITATIVE, SourceAnswer.found("v", Freshness.STALE_OK, source="liar"))
    backup = _found("backup", Freshness.AUTHORITATIVE, value="real")
    result = resolve(LookupPlan((liar, backup)), "k", Freshness.VALIDATED)
    assert result.value == "real"


def test_only_a_validated_or_better_miss_ends_the_walk():
    weak_miss = _miss("weak", Freshness.STALE_OK)
    network = _found("network", Freshness.AUTHORITATIVE)
    assert resolve(LookupPlan((weak_miss, network)), "k", Freshness.STALE_OK).source == "network"
    strong_miss = _miss("strong", Freshness.VALIDATED)
    network = _found("network", Freshness.AUTHORITATIVE)
    result = resolve(LookupPlan((strong_miss, network)), "k", Freshness.VALIDATED)
    assert result.outcome is LookupOutcome.NOT_FOUND and network.calls == []


def test_nothing_settling_it_is_unavailable_with_reasons_never_not_found():
    result = resolve(LookupPlan((_down("a", Freshness.VALIDATED), _miss("b", Freshness.STALE_OK))), "k", Freshness.STALE_OK)
    assert result.outcome is LookupOutcome.UNAVAILABLE and "a: down" in result.reason
    assert resolve(LookupPlan(()), "k", Freshness.STALE_OK).outcome is LookupOutcome.UNAVAILABLE


def test_freshness_is_ordered():
    assert Freshness.STALE_OK < Freshness.VALIDATED < Freshness.AUTHORITATIVE
