"""Find one value by key through an ordered list of sources, cheapest and least fresh first.

Generic: it knows no key, value, store or vendor. A caller supplies the sources (a local snapshot, a change-token
validated snapshot, a network read) and the order; this module only fixes how a walk over them ends.

* A source declares the best ``Freshness`` it can ever give and answers ``find(key)`` with an explicit
  ``SourceAnswer``: FOUND (with the freshness and age of *that* answer), MISS, or UNAVAILABLE (could not tell).
* ``resolve(plan, key, require)`` walks the plan in order. A source whose best freshness is below ``require`` is
  never consulted. It stops at the first FOUND that meets ``require``. A MISS ends the walk (NOT_FOUND) only when
  the answer itself was at least VALIDATED and meets ``require``; a weaker MISS proves nothing, so the walk goes
  on. When nothing settles it, the result is UNAVAILABLE with the reasons, never a silent "not found".
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Generic, Protocol, TypeVar

K = TypeVar("K", contravariant=True)
V = TypeVar("V")


class Freshness(IntEnum):
    """How current an answer is. Ordered: a stronger answer satisfies a weaker requirement."""

    STALE_OK = 1       # may be old; fine for a read-only view that says how old it is
    VALIDATED = 2      # checked against the authority's own change token, so current as of that check
    AUTHORITATIVE = 3  # read from the authority itself just now


class AnswerKind(Enum):
    FOUND = "found"
    MISS = "miss"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SourceAnswer(Generic[V]):
    kind: AnswerKind
    value: V | None = None
    freshness: Freshness = Freshness.STALE_OK
    age_seconds: float | None = None
    source: str = ""
    reason: str = ""

    @classmethod
    def found(cls, value: V, freshness: Freshness, *, source: str, age_seconds: float | None = None) -> SourceAnswer[V]:
        return cls(AnswerKind.FOUND, value, freshness, age_seconds, source)

    @classmethod
    def miss(cls, freshness: Freshness, *, source: str) -> SourceAnswer[V]:
        return cls(AnswerKind.MISS, None, freshness, None, source)

    @classmethod
    def unavailable(cls, reason: str, *, source: str) -> SourceAnswer[V]:
        return cls(AnswerKind.UNAVAILABLE, None, Freshness.STALE_OK, None, source, reason)


class LookupSource(Protocol[K, V]):
    name: str
    best_freshness: Freshness

    def find(self, key: K) -> SourceAnswer[V]: ...


@dataclass(frozen=True)
class LookupPlan(Generic[V]):
    """The sources in the order they are tried."""

    sources: tuple[LookupSource, ...]


class LookupOutcome(Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class LookupResult(Generic[V]):
    outcome: LookupOutcome
    value: V | None = None
    freshness: Freshness | None = None
    age_seconds: float | None = None
    source: str = ""
    reason: str = ""

    @property
    def is_found(self) -> bool:
        return self.outcome is LookupOutcome.FOUND


def resolve(plan: LookupPlan[V], key: object, require: Freshness) -> LookupResult[V]:
    """Walk ``plan`` for ``key`` and return what the first source that can settle it says."""
    reasons: list[str] = []
    for source in plan.sources:
        if source.best_freshness < require:
            continue
        answer = source.find(key)
        if answer.kind is AnswerKind.FOUND:
            if answer.freshness >= require:
                return LookupResult(LookupOutcome.FOUND, answer.value, answer.freshness, answer.age_seconds, source.name)
            reasons.append(f"{source.name}: answer too old for this caller")
        elif answer.kind is AnswerKind.MISS:
            if answer.freshness >= Freshness.VALIDATED and answer.freshness >= require:
                return LookupResult(LookupOutcome.NOT_FOUND, None, answer.freshness, None, source.name)
        else:
            reasons.append(f"{source.name}: {answer.reason or 'unavailable'}")
    return LookupResult(LookupOutcome.UNAVAILABLE, reason="; ".join(reasons) or "no source could answer")
