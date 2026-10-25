"""Guards and the per-class policy. Pure data plus the invariants that keep a policy self-consistent."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Guard(Enum):
    """A protection a class requires. The enforcing code lives with the guard's owner; this names it."""

    LOCAL_FIRST_PROBE = "local_first_probe"        # ask local cache/logs/runtime before the network
    REVISION_SNAPSHOT = "revision_snapshot"        # cross-process disk snapshot validated by a cheap revision probe
    AGE_WINDOW = "age_window"                      # restricted to a recent window
    BYTE_CEILING = "byte_ceiling"                  # per-read response ceiling
    PROCESS_BUDGET = "process_budget"              # per-process bytes for the class (RequestBudget)
    READ_PATIENCE = "read_patience"                # transient failures retried per page, not per read
    NEVER_STALE = "never_stale"                    # may not be answered from a cache or local copy
    RETURN_MINIMAL = "return_minimal"              # a write does not echo its rows back
    SINGLE_ATTEMPT = "single_attempt"              # non-idempotent: never auto-retried


@dataclass(frozen=True)
class ClassPolicy:
    """What a class is allowed to do and must do. Each member of the caller's class enum has one as its value."""

    label: str  # a stable string identifying the class in logs and metrics
    summary: str
    guards: frozenset[Guard]
    is_write: bool = False
    # May a bound LocalReadProbe answer this class without touching the network?
    may_serve_local: bool = False
    # Bytes this class may receive per process before further requests are refused (None: uncapped).
    process_byte_budget: int | None = None

    @property
    def allowance_exempt(self) -> bool:
        """Never refused or degraded for byte allowance: a write, or a class that must not be answered stale."""
        return self.is_write or Guard.NEVER_STALE in self.guards

    def __post_init__(self) -> None:
        # A policy that contradicts itself is refused where it is built, not when a request happens to hit it.
        guards = self.guards
        if self.is_write != (Guard.RETURN_MINIMAL in guards):
            raise ValueError(f"{self.label}: exactly the write classes carry RETURN_MINIMAL")
        if Guard.NEVER_STALE in guards and self.may_serve_local:
            raise ValueError(f"{self.label}: a NEVER_STALE class cannot be answered locally")
        if self.may_serve_local and Guard.LOCAL_FIRST_PROBE not in guards:
            raise ValueError(f"{self.label}: may_serve_local requires the LOCAL_FIRST_PROBE guard")
        if not self.may_serve_local and Guard.LOCAL_FIRST_PROBE in guards:
            raise ValueError(f"{self.label}: LOCAL_FIRST_PROBE needs may_serve_local")
        if self.process_byte_budget is not None and Guard.PROCESS_BUDGET not in guards:
            raise ValueError(f"{self.label}: a byte budget needs the PROCESS_BUDGET guard")


def class_policy(member: Enum) -> ClassPolicy:
    """The ``ClassPolicy`` of a member of a caller's class enum (its value); a wrong-shaped enum fails loudly."""
    policy = member.value
    if not isinstance(policy, ClassPolicy):
        raise TypeError(f"{member!r}: a class enum's member values must be ClassPolicy, got {type(policy).__name__}")
    return policy
