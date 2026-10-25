"""The generic request-eligibility engine (``io_policy``), exercised with a toy class enum, not the app's.

Also pins the boundary: the engine imports only the standard library and itself.
"""
from __future__ import annotations

import ast
import sys
from enum import Enum
from pathlib import Path

import pytest

from io_policy import (
    ClassPolicy,
    Guard,
    LocalAnswer,
    Outcome,
    RequestBudget,
    RequestFacts,
    RequestRefused,
    class_policy,
    eligibility,
)

ENGINE_DIR = Path(__file__).resolve().parents[1] / "src" / "io_policy"
G = Guard


class Toy(Enum):
    CHEAP = ClassPolicy("cheap", "local-servable read", frozenset({G.LOCAL_FIRST_PROBE}), may_serve_local=True)
    FRESH = ClassPolicy("fresh", "never stale", frozenset({G.NEVER_STALE}))
    CAPPED = ClassPolicy(
        "capped", "budgeted read", frozenset({G.PROCESS_BUDGET}), process_byte_budget=10,
    )
    PUT = ClassPolicy("put", "write", frozenset({G.RETURN_MINIMAL}), is_write=True)


def test_toy_enum_decisions():
    assert eligibility(RequestFacts("GET", "x", Toy.CHEAP)).outcome is Outcome.ALLOWED
    served = eligibility(RequestFacts("GET", "x", Toy.CHEAP, local=LocalAnswer({"a": 1})))
    assert served.outcome is Outcome.SERVED_LOCAL and served.payload == {"a": 1} and not served.sends
    never = eligibility(RequestFacts("GET", "x", Toy.FRESH, local=LocalAnswer(1)))
    assert never.outcome is Outcome.ALLOWED and never.sends


def test_unclassified_and_budget_refusals():
    unclassified = eligibility(RequestFacts("GET", "mystery", None))
    assert unclassified.outcome is Outcome.REFUSED and unclassified.io_class is None and "unclassified" in unclassified.reason
    spent = eligibility(RequestFacts("GET", "x", Toy.CAPPED, spent_bytes=10, byte_cap=10))
    assert spent.outcome is Outcome.REFUSED and "capped" in spent.reason
    assert eligibility(RequestFacts("GET", "x", Toy.CAPPED, spent_bytes=9, byte_cap=10)).sends
    with pytest.raises(RequestRefused, match="GET x refused"):
        raise RequestRefused(spent, "GET", "x")


def test_advise_attaches_findings_only_to_allowed():
    def advise(facts):
        return [f"saw {facts.table}"]

    assert eligibility(RequestFacts("PUT", "t", Toy.PUT), advise=advise).findings == ("saw t",)
    assert eligibility(RequestFacts("GET", "t", Toy.CHEAP, local=LocalAnswer(1)), advise=advise).findings == ()


def test_budget_generic_over_the_enum_with_overrides():
    budget = RequestBudget(Toy)
    assert budget.cap(Toy.CAPPED) == 10 and budget.cap(Toy.CHEAP) is None
    budget.charge(Toy.CAPPED, 4)
    budget.charge(Toy.CAPPED, -3)  # negative is clamped
    assert budget.spent(Toy.CAPPED) == 4 and budget.spent(Toy.CHEAP) == 0
    assert RequestBudget(Toy, {Toy.CHEAP: 1}).cap(Toy.CHEAP) == 1


@pytest.mark.parametrize("kwargs, message", [
    (dict(guards=frozenset(), is_write=True), "RETURN_MINIMAL"),
    (dict(guards=frozenset({G.RETURN_MINIMAL})), "RETURN_MINIMAL"),
    (dict(guards=frozenset({G.NEVER_STALE, G.LOCAL_FIRST_PROBE}), may_serve_local=True), "NEVER_STALE"),
    (dict(guards=frozenset(), may_serve_local=True), "requires the LOCAL_FIRST_PROBE"),
    (dict(guards=frozenset({G.LOCAL_FIRST_PROBE})), "needs may_serve_local"),
    (dict(guards=frozenset(), process_byte_budget=1), "PROCESS_BUDGET"),
])
def test_class_policy_invariants(kwargs, message):
    with pytest.raises(ValueError, match=message):
        ClassPolicy("bad", "bad", **kwargs)


def test_class_policy_rejects_a_wrong_shaped_enum():
    class Wrong(Enum):
        A = "not a policy"

    with pytest.raises(TypeError):
        class_policy(Wrong.A)
    assert class_policy(Toy.PUT).is_write


def test_engine_imports_only_the_stdlib():
    stdlib = set(sys.stdlib_module_names)
    offenders = []
    for path in sorted(ENGINE_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else []
            )
            for name in names:
                root = name.split(".")[0]
                if root not in stdlib and root != "__future__" and not name.startswith("io_policy"):
                    offenders.append(f"{path.name}: {name}")
    assert not offenders, "the io_policy engine may import only the stdlib and itself:\n" + "\n".join(offenders)


def test_engine_modules_are_underscore_private_except_the_api():
    public = {p.name for p in ENGINE_DIR.glob("*.py") if not p.name.startswith("_")}
    assert not public, f"engine internals must be underscore-private: {sorted(public)}"
