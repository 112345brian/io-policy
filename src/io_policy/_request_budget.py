"""Response bytes charged per request class in this process."""
from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Generic, TypeVar

from io_policy._class_policy import class_policy

C = TypeVar("C", bound=Enum)


class RequestBudget(Generic[C]):
    """Bytes charged per class, against ``ClassPolicy.process_byte_budget`` (or an explicit per-class override)."""

    def __init__(self, classes: type[C], caps: Mapping[C, int | None] | None = None):
        self._caps: dict[C, int | None] = {c: class_policy(c).process_byte_budget for c in classes}
        self._caps.update(caps or {})
        self._spent: dict[C, int] = {}

    def charge(self, io_class: C, nbytes: int) -> None:
        self._spent[io_class] = self._spent.get(io_class, 0) + max(0, nbytes)

    def spent(self, io_class: C) -> int:
        return self._spent.get(io_class, 0)

    def cap(self, io_class: C) -> int | None:
        return self._caps.get(io_class)
