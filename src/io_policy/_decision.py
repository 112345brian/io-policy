"""The decision: may this request reach the network? One pure function, explicit result."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Protocol, TypeVar

from io_policy._allowance import AllowanceStatus
from io_policy._class_policy import Guard, class_policy

C = TypeVar("C", bound=Enum)
C_contra = TypeVar("C_contra", bound=Enum, contravariant=True)


class Outcome(Enum):
    ALLOWED = "allowed"
    SERVED_LOCAL = "served_local"
    REFUSED = "refused"


@dataclass(frozen=True)
class Decision(Generic[C]):
    """The answer to "may this request reach the network?". ``payload`` is set only for ``SERVED_LOCAL``."""

    outcome: Outcome
    io_class: C | None
    reason: str
    guards: frozenset[Guard] = frozenset()
    findings: tuple[str, ...] = ()
    payload: Any = field(default=None, compare=False)

    @property
    def sends(self) -> bool:
        return self.outcome is Outcome.ALLOWED


class RequestRefused(RuntimeError):
    """A request was refused by policy before it was sent. Carries the ``Decision``."""

    def __init__(self, decision: Decision[Any], method: str, table: str):
        self.decision = decision
        super().__init__(f"{method} {table} refused: {decision.reason}")


@dataclass(frozen=True)
class LocalAnswer:
    """What a ``LocalReadProbe`` returns when local state can answer a request."""

    payload: Any


@dataclass(frozen=True)
class LocalReadQuery(Generic[C]):
    """What a ``LocalReadProbe`` is asked: the request, plus whether the class is over its allowance.

    ``degraded`` means the network is closed to this class for now, so a stale local answer is better than none;
    when it is false the probe should answer only from state it knows is current.
    """

    method: str
    table: str
    params: Mapping[str, str] | None
    io_class: C
    headers: Mapping[str, str] | None = None
    read: str | None = None
    degraded: bool = False


class LocalReadProbe(Protocol[C_contra]):
    """The local-first port: answer a read from local state, or return ``None``.

    Owned by the engine (the inner ring); an adapter binds one. Only classes whose policy has ``may_serve_local``
    consult it, and never a ``NEVER_STALE`` one.
    """

    def answer(self, query: LocalReadQuery[C_contra]) -> LocalAnswer | None:
        ...


@dataclass(frozen=True)
class RequestFacts(Generic[C]):
    """Everything ``eligibility`` needs to know about one request; no I/O."""

    method: str
    table: str
    io_class: C | None
    prefer: str | None = None
    local: LocalAnswer | None = None
    spent_bytes: int = 0
    byte_cap: int | None = None
    allowance: AllowanceStatus | None = None


def eligibility(
    facts: RequestFacts[C],
    *,
    advise: Callable[[RequestFacts[C]], Sequence[str]] | None = None,
) -> Decision[C]:
    """Decide from the request's class whether it may reach the network. The one decision function.

    ``advise`` lets the caller attach non-blocking findings to an ALLOWED decision (guard violations that do not
    refuse yet); the engine knows no class by name, so anything class-specific lives there.
    """
    io_class = facts.io_class
    if io_class is None:
        return Decision(Outcome.REFUSED, None, f"unclassified request {facts.method} {facts.table}: no class covers it")
    policy = class_policy(io_class)
    guards = policy.guards
    over = facts.allowance if facts.allowance is not None and facts.allowance.over and not policy.allowance_exempt else None
    if policy.may_serve_local and facts.local is not None and Guard.NEVER_STALE not in guards:
        reason = "answered from local state" if over is None else f"over allowance, degraded to local state ({over.describe()})"
        return Decision(Outcome.SERVED_LOCAL, io_class, reason, guards, payload=facts.local.payload)
    if over is not None:
        return Decision(
            Outcome.REFUSED, io_class,
            f"{policy.label} is over its byte allowance and has no local answer ({over.describe()})", guards,
        )
    if facts.byte_cap is not None and facts.spent_bytes >= facts.byte_cap:
        return Decision(
            Outcome.REFUSED, io_class,
            f"{policy.label} byte budget spent ({facts.spent_bytes} of {facts.byte_cap} bytes this process)",
            guards,
        )
    findings = tuple(advise(facts)) if advise is not None else ()
    return Decision(Outcome.ALLOWED, io_class, "eligible", guards, findings)
