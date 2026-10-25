# io-policy

Distribution name: `io-policy-engine` (the name `io-policy` is taken on PyPI by an unrelated project); import name: `io_policy`.

A small, dependency-free engine that decides which I/O requests may reach the network and under which guards and
byte allowance. It knows no vendor, table or storage layout; the standard library is its only import (a test parses
the source and fails on anything else). Licensed under the MIT licence (see `LICENSE`).

```
pip install "io-policy-engine @ git+https://github.com/112345brian/io-policy"
```

## API (`from io_policy import ...`)

- `ClassPolicy`, `Guard`, `class_policy`: describe a request class (guards such as local-first probe, byte ceiling,
  per-process budget, never-stale, return-minimal); self-contradicting combinations fail at construction.
- `RequestFacts`: what is known about one request (method, table, class, prefer header, local answer, bytes spent,
  cap, allowance status).
- `eligibility(facts, advise=None) -> Decision`: the one decision function. `Decision.outcome` is an `Outcome`
  (`ALLOWED`, `SERVED_LOCAL`, `REFUSED`) with a reason and non-blocking findings. `Decision.sends` is true only for
  `ALLOWED`.
- `LocalReadProbe`, `LocalReadQuery`, `LocalAnswer`: the protocol for answering a read from local state. The probe
  gets one `LocalReadQuery` (method, table, params, class, headers, registered read name, and `degraded`: the class is
  over its allowance, so a stale answer beats none).
- `Allowance[C]`, `AllowanceReader[C]`, `AllowanceStatus`, `AllowanceMode`, `allowance_exempt`, `allowance_limited`: a
  rolling byte allowance (total, window, per-class shares, a reserve fraction for unmeasured traffic). The
  `AllowanceReader` you bind supplies `spent_wire_bytes(class, window)`; `RequestFacts.allowance` carries the resulting
  status into `eligibility`. A class is over only when **its own** spend reaches **its own** share: the total (which
  includes spend no class can be blamed for) is a reporting figure, never a trigger. An over class is served locally
  if it has a local answer. With none, `AllowanceMode.WARN` (the default, `RequestFacts.allowance_mode`) allows the
  request with the `ALLOWANCE_EXCEEDED` finding for the caller to record; `AllowanceMode.ENFORCE` refuses it. Only
  *limited* classes are affected: writes and `NEVER_STALE` classes are exempt (`ClassPolicy.allowance_exempt`), and
  small or correctness-critical reads are essential (`ClassPolicy.allowance_essential`): counted, never held back.
- `RequestBudget[C]`: thread-safe per-class byte accounting. `RequestRefused`: exception carrying a refused `Decision`.

## The pattern: a closed Enum whose values are `ClassPolicy`

The caller defines a closed `Enum` of request classes; each member's value is its `ClassPolicy`. The engine is
generic over that enum (`class_policy(member)` reads the value and fails loudly on a wrong-shaped enum), so it never
names a class. The caller also supplies a classifier from a request to a member (or `None`, which is refused as
unclassified) and, optionally, a bound `LocalReadProbe` and `AllowanceReader`. Both are `typing.Protocol`s owned by
this package; you implement them in your infrastructure layer and bind them at your entrypoint.

## Example

`examples/quickstart.py` (run as a test in `tests/test_example.py`):

```python
class Net(Enum):
    LISTING = ClassPolicy("listing", "large read", frozenset({Guard.LOCAL_FIRST_PROBE}), may_serve_local=True)
    WRITE = ClassPolicy("write", "small write", frozenset({Guard.RETURN_MINIMAL}), is_write=True)

class Cache:                      # a LocalReadProbe
    def __init__(self, rows): self.rows = rows
    def answer(self, query):
        rows = self.rows.get(query.table)
        return LocalAnswer(rows) if rows is not None else None

class Meter:                      # an AllowanceReader
    def spent_wire_bytes(self, io_class, window): ...

allowance = Allowance(total_bytes=1000, window=timedelta(days=30), shares={Net.LISTING: 1.0})
status = allowance.status(Net.LISTING, Meter())
facts = RequestFacts("GET", "items", Net.LISTING, local=probe.answer(query), allowance=status)
decision = eligibility(facts)     # ALLOWED, SERVED_LOCAL, or REFUSED
```

## Development

```
python -m pip install -e . pytest ruff build
ruff check . && python -m pytest && python -m build
```

CI (`.github/workflows/ci.yml`) lints, tests and builds on Windows, Linux and macOS; it does not publish.
