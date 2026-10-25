"""A rolling byte allowance per request class: the arithmetic, and the port that supplies "bytes spent so far".

Pure. The engine does not know where the spent figure comes from; an ``AllowanceReader`` adapter (a log, a
meter, a billing API) supplies it. Exempt classes (writes, never-stale reads) are counted in the total but never
degraded or refused for allowance: losing a user's own state to save bytes is worse than the bytes.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Generic, Protocol, TypeVar

from io_policy._class_policy import class_policy

C = TypeVar("C", bound=Enum)
C_contra = TypeVar("C_contra", bound=Enum, contravariant=True)


class AllowanceReader(Protocol[C_contra]):
    """Bytes that crossed the network (the billed figure) over the trailing ``window``.

    ``io_class`` of ``None`` asks for every class together. Implementations decide how to fail; the caller
    treats an exception as "unknown" and does not refuse on it.
    """

    def spent_wire_bytes(self, io_class: C_contra | None, window: timedelta) -> int:
        ...


@dataclass(frozen=True)
class AllowanceStatus:
    """Where one class stands against its share and the overall total."""

    spent: int
    cap: int
    total_spent: int
    total_cap: int
    window_days: float

    @property
    def over(self) -> bool:
        return self.spent >= self.cap or self.total_spent >= self.total_cap

    @property
    def remaining(self) -> int:
        """Bytes left before either limit trips (never negative)."""
        return max(0, min(self.cap - self.spent, self.total_cap - self.total_spent))

    def describe(self) -> str:
        return (
            f"{self.spent} of {self.cap} bytes of the class share and {self.total_spent} of {self.total_cap} total "
            f"over the last {self.window_days:g} days"
        )


@dataclass(frozen=True)
class Allowance(Generic[C]):
    """``total_bytes`` over a trailing ``window``, split into per-class ``shares`` (fractions of the total)."""

    total_bytes: int
    window: timedelta
    shares: Mapping[C, float]
    # Fraction of ``total_bytes`` held back for traffic the reader cannot see (other clients, a pooler).
    reserve_fraction: float = 0.0

    @property
    def usable_bytes(self) -> int:
        """What the reader's figures are measured against: the total less the reserve."""
        return int(self.total_bytes * (1.0 - self.reserve_fraction))

    def __post_init__(self) -> None:
        if self.total_bytes < 0:
            raise ValueError("an allowance total cannot be negative")
        if self.window <= timedelta(0):
            raise ValueError("an allowance window must be positive")
        if not 0.0 <= self.reserve_fraction < 1.0:
            raise ValueError("an allowance reserve must be at least 0 and less than 1")
        if any(share < 0 for share in self.shares.values()):
            raise ValueError("an allowance share cannot be negative")
        if sum(self.shares.values()) > 1.0 + 1e-9:
            raise ValueError("allowance shares add up to more than the whole")

    def cap(self, io_class: C) -> int:
        """Bytes this class may receive over the window; a class with no share has none."""
        return int(self.usable_bytes * self.shares.get(io_class, 0.0))

    def status(self, io_class: C, reader: AllowanceReader[C]) -> AllowanceStatus:
        return AllowanceStatus(
            spent=reader.spent_wire_bytes(io_class, self.window),
            cap=self.cap(io_class),
            total_spent=reader.spent_wire_bytes(None, self.window),
            total_cap=self.usable_bytes,
            window_days=self.window.total_seconds() / 86400,
        )


def allowance_exempt(io_class: Enum) -> bool:
    """Writes and never-stale classes are never refused or degraded for allowance."""
    return class_policy(io_class).allowance_exempt
