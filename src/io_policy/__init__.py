"""A generic request-eligibility engine: which I/O may reach the network, under which guards. No app knowledge.

The caller supplies a closed ``Enum`` of request classes whose member values are ``ClassPolicy`` objects, a way to
classify a request into one of those members, and (optionally) a bound ``LocalReadProbe``. The engine turns the
class's policy plus the request's facts into one explicit ``Decision`` (allowed / served local / refused)
and does the arithmetic of a rolling per-class byte allowance.
It knows no table, vendor or storage layout, and imports nothing but the standard library
(``tests/test_engine.py`` enforces that).

This ``__init__`` is the engine's deliberate public API; the implementation lives in the underscore modules.
"""
from io_policy._allowance import (
    Allowance,
    AllowanceMode,
    AllowanceReader,
    AllowanceStatus,
    allowance_exempt,
    allowance_limited,
)
from io_policy._class_policy import ClassPolicy, Guard, class_policy
from io_policy._decision import (
    ALLOWANCE_EXCEEDED,
    Decision,
    LocalAnswer,
    LocalReadProbe,
    LocalReadQuery,
    Outcome,
    RequestFacts,
    RequestRefused,
    eligibility,
)
from io_policy._ordered_lookup import (
    AnswerKind,
    Freshness,
    LookupOutcome,
    LookupPlan,
    LookupResult,
    LookupSource,
    SourceAnswer,
    resolve,
)
from io_policy._request_budget import RequestBudget

__all__ = [
    "ALLOWANCE_EXCEEDED",
    "Allowance",
    "AllowanceMode",
    "AllowanceReader",
    "AllowanceStatus",
    "AnswerKind",
    "ClassPolicy",
    "Decision",
    "Freshness",
    "Guard",
    "LocalAnswer",
    "LocalReadProbe",
    "LocalReadQuery",
    "LookupOutcome",
    "LookupPlan",
    "LookupResult",
    "LookupSource",
    "Outcome",
    "RequestBudget",
    "RequestFacts",
    "RequestRefused",
    "SourceAnswer",
    "class_policy",
    "allowance_exempt",
    "allowance_limited",
    "eligibility",
    "resolve",
]
