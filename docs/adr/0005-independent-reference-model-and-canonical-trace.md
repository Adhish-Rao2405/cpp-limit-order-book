# ADR 0005: Independent Python reference model and canonical trace contract

- Status: Accepted
- Date: 2026-09-18

## Context

M3 qualified a deterministic single-writer C++20 matching core against the frozen matching semantics,
invariants, and ADRs 0001 through 0004. That evidence establishes the candidate baseline, but it does
not establish agreement with an independent implementation.

M4 introduces an independent reference model and a producer-neutral canonical trace contract. The
reference model is a correctness oracle, not a second production matching engine. Performance,
allocation behaviour, cache locality, and concurrency are not design goals for the oracle.

## Decision summary

The primary M4 reference model will use CPython 3.12.10 and the Python standard library only.

It will:

- implement the frozen project semantics independently rather than call or wrap `MatchingEngine`;
- validate matching-domain inputs independently rather than reuse C++ command factories;
- use a flat collection of active reference orders rather than the M3 map/list book graph;
- resolve active IDs by linear search rather than a locator index;
- select makers by linear semantic search over active orders;
- use sequence number, not container position, as execution-priority authority;
- use Python arbitrary-precision integers for proof arithmetic while enforcing the frozen int64/uint64
  representation bounds at the qualification boundary;
- represent expected domain rejection as data rather than Python exceptions; and
- expose storage-independent logical observations for canonical comparison.

The exact trace byte contract is defined in `docs/CANONICAL_TRACE.md`.

## 1. Authority hierarchy

Semantic authority remains:

- `docs/MATCHING_SEMANTICS.md`;
- `docs/INVARIANTS.md`;
- ADR 0001;
- ADR 0002;
- ADR 0003; and
- ADR 0004 where it expresses logical behaviour rather than M3-specific storage mechanics.

The C++ implementation is not semantic authority for M4.

Existing M3 tests are qualification evidence for the candidate implementation. They are not the source
from which the Python reference algorithm is copied.

If candidate behaviour and the frozen semantic contract disagree, M4 follows the frozen semantic
contract and the disagreement must be investigated explicitly.

## 2. Runtime and dependency decision

The qualified reference runtime is:

```text
CPython 3.12.10
64-bit
standard library only
```

The reference implementation must not depend on third-party Python packages.

Later CI integration must select CPython 3.12.10 explicitly rather than rely on whichever interpreter
happens to be present on the runner.

Any CI action used to select Python must be pinned by immutable commit identity under the same
supply-chain discipline used elsewhere in this repository.

## 3. Qualification input boundary

M4 distinguishes representation validity from matching-domain validity.

A qualification command envelope may carry raw scalar representations so differential qualification can
exercise the public domain-validation boundary without sharing C++ command factories.

The v1 representation domains are:

```text
price_ticks:    signed int64 range
quantity_units: unsigned uint64 range
order_id:       unsigned uint64 range
side_code:      unsigned uint8 range
```

Logical side mapping is:

```text
0 -> Buy
1 -> Sell
2..255 -> representationally valid side_code but invalid logical Side
```

A scalar outside its representation range is not a `DomainError`. It is malformed qualification input
and must fail the harness or trace boundary.

Within the representation domain, matching validation follows the frozen contract, including:

```text
price_ticks <= 0 -> InvalidPrice
quantity_units == 0 -> InvalidQuantity
side_code not in {0, 1} -> InvalidSide
```

This does not introduce textual, decimal-price, network-protocol, or arbitrary-precision external input
into the matching contract.

## 4. Independent reference state

The logical reference state consists of:

```text
active_orders
next_sequence
```

Each active reference order contains:

```text
order_id
side
price_ticks
remaining_quantity
sequence
```

The intended implementation is a flat Python collection of immutable reference-order values.

The reference model must not reproduce:

```text
map<Price, FIFO list<RestingOrder>>
unordered_map<OrderId, Locator>
BidLocator / AskLocator
persistent container iterators
M3 price-level ownership as semantic authority
```

This restriction exists to reduce common-mode structural failure between candidate and oracle.

## 5. Active-ID resolution

The reference model resolves an active `OrderId` by scanning the flat active-order collection.

The semantic requirement is:

```text
active ID   -> exactly one active order
inactive ID -> no active order
```

M3 locator mechanics are not reproduced.

## 6. Matching algorithm

For an incoming BUY with limit `P`, eligible makers are active SELL orders satisfying:

```text
maker.price <= P
```

The selected maker has:

```text
minimum price
then minimum sequence
```

For an incoming SELL with limit `P`, eligible makers are active BUY orders satisfying:

```text
maker.price >= P
```

The selected maker has:

```text
maximum price
then minimum sequence
```

A fresh semantic search is performed for each matching iteration.

Matching continues until incoming remaining quantity is zero or no executable maker exists.

Trade price is maker price.

Trade quantity is:

```text
min(incoming_remaining, maker_remaining)
```

Flat-collection position has no semantic priority meaning.

## 7. Sequence allocator

The logical allocator state is:

```text
positive uint64 next_sequence
or
exhausted
```

Normal initial state is `1`.

If the available value is below `UINT64_MAX`, allocate it and advance by one.

If the available value is exactly `UINT64_MAX`, allocate it exactly once and enter exhausted state.

If exhausted, a command requiring a fresh sequence is rejected with `SequenceExhausted`.

Sequence wrap and reuse are forbidden.

Normal reference construction begins with `next_sequence = 1`.

Qualification-only support may initialize the allocator to any valid logical allocator state: a
positive uint64 `next_sequence` or exhausted. This permits the `UINT64_MAX` boundary to be exercised
without processing an infeasible number of commands.

That qualification support is not a matching command, is not part of the matching command contract,
must not permit a command to choose sequence identity, and must not become matching authority.

Accepted new orders and accepted priority-losing modifications consume exactly one fresh sequence.
Successful cancellations and accepted priority-retaining quantity reductions consume no sequence.
Rejected commands consume no sequence.

## 8. Modification semantics

Modify quantity means target remaining quantity.

After representation and scalar validation:

```text
unknown active ID:
    UnknownOrderId

same price and same remaining quantity:
    InvalidModification

same price and lower positive remaining quantity:
    retain side, price, sequence, and execution priority
    perform no matching

quantity increase:
    lose priority
    require fresh sequence
    process as atomic replacement

any price change:
    lose priority
    require fresh sequence
    process as atomic replacement
```

A priority-losing replacement retains the same `OrderId` and immutable side.

Fresh-sequence availability must be established before destructive state mutation.

The original order must be absent before its replacement is processed as an incoming order.

## 9. Expected rejection and atomicity

Expected domain rejection is represented as data using:

```text
InvalidPrice
InvalidQuantity
InvalidSide
DuplicateOrderId
UnknownOrderId
SequenceExhausted
InvalidModification
```

Expected domain rejection must not use Python exception control flow.

For every expected rejection:

```text
logical post-state == logical pre-state
allocator post-state == allocator pre-state
ordered trades == empty
```

Python exceptions are reserved for malformed qualification input, programming defects, failed internal
assertions, or runtime/resource failures. They are not converted into `DomainError`.

## 10. Quantity arithmetic

Order quantities remain bounded by the unsigned uint64 domain.

Reference matching must preserve those bounds.

Qualification and proof arithmetic may use Python arbitrary-precision integers so conservation evidence
cannot silently wrap at 64 bits.

For accepted incoming quantity `Q0`:

```text
Q0 = mathematical sum of emitted trade quantities + final resting residual
```

This proof arithmetic does not expand the order quantity domain.

## 11. Canonical logical observation

The reference model exposes these storage-independent logical authorities:

```text
ordered command outcome
ordered trades
bids
asks
next_sequence
```

Canonical active-state ordering is:

```text
bids: price descending, then sequence ascending
asks: price ascending, then sequence ascending
```

Each resting-order observation contains:

```text
order_id
side
price_ticks
remaining_quantity
sequence
```

`next_sequence = UINT64_MAX` and allocator exhaustion are observably distinct states.

## 12. Canonical trace direction

The canonical trace is producer-neutral.

Candidate and reference executions that agree semantically must be capable of producing identical
canonical trace bytes for the same qualified initial state and ordered command stream.

Producer-specific metadata such as implementation name, executable path, Git commit, workflow run,
wall-clock time, or host identity must not appear inside semantic canonical trace bytes.

The v1 trace uses:

```text
UTF-8
no BOM
LF line endings
JSON Lines
one mandatory final LF
fixed object field order
compact JSON with no insignificant whitespace
canonical decimal strings for integral values
```

The exact schema, decimal grammar, record ordering, field ordering, and digest rule are defined in
`docs/CANONICAL_TRACE.md`.

## 13. Trace digest

Trace integrity uses SHA-256 over the exact canonical trace bytes.

The digest is stored separately from those bytes so the trace does not contain a self-referential digest.

The digest is an integrity aid, not proof of semantic correctness.

## 14. M4, M5, and M6 responsibility boundary

M4 owns the independent reference model, its qualification, the canonical trace contract, and trace
serialization qualification.

M5 owns candidate-versus-reference differential execution, adversarial/generated differential workloads,
mismatch evidence, and metamorphic differential checks.

M6 owns standalone replay, durable evidence packaging, provenance manifests, replay verification, and the
correctness freeze after differential qualification.

M4 must not claim M5 differential agreement or M6 replay/evidence closure.

## 15. CI and reproducibility boundary

The Python reference implementation must be qualified locally and in CI before M4 closes.

CI must explicitly select CPython 3.12.10, run the standard-library-only reference qualification, and
retain the existing C++ Debug and Release qualification.

Introducing Python must not silently weaken or replace the existing C++ qualification matrix.

CI workflow mutation requires a later controlled implementation gate and is not part of this
architecture-documentation change.

## 16. Alternatives considered

### Reuse C++ domain types and command factories

Rejected for the primary oracle because candidate and reference would share validation code and could
share common-mode defects at the boundary differential testing is intended to check.

### Independent C++ reference model

Technically viable, but not selected for the primary oracle because Python provides greater
implementation-language and arithmetic independence with a smaller reference implementation.

### Python with third-party packages

Rejected because external dependencies enlarge the supply-chain and qualification surface without
providing a necessary semantic capability.

### Reproduce M3 map/list plus locator architecture in Python

Rejected because structural similarity would weaken differential independence.

### Use container position as FIFO authority

Rejected. Sequence number is the frozen semantic priority identity.

### Include producer provenance in canonical trace bytes

Rejected because producer-specific metadata would prevent byte equality between semantically agreeing
candidate and reference traces.

## 17. Consequences

Benefits are stronger independence from the C++ candidate, independent validation, a different
maker-selection algorithm, arbitrary-precision proof arithmetic, and a producer-neutral byte-stable
observation format.

Costs are a second language/runtime, an additional CI qualification path, explicit candidate/reference
adapters, and deliberately poor asymptotic performance in the oracle.

Those costs are accepted because M4 is a correctness-evidence milestone, not a performance milestone.

## 18. Claim boundary

Acceptance of this ADR establishes an architecture decision only.

It does not establish:

- that the Python reference implementation exists or is correct;
- candidate/reference differential agreement;
- universal correctness over all command streams;
- formal verification;
- benchmark performance;
- low latency or high throughput;
- HFT capability;
- concurrency;
- persistence or recovery;
- production readiness;
- fidelity to a real exchange; or
- exchange-grade behaviour.

Those claims require later implementation and qualification gates.

## 19. Freeze rule

After acceptance, changing the primary reference language, reference-state topology in a way that
materially reduces independence from M3, qualification-envelope scalar domains, sequence authority,
maker-selection semantics, expected-rejection representation, canonical observation authorities,
canonical trace byte contract, digest algorithm, or M4/M5/M6 responsibility boundary requires explicit
architecture review and qualification-impact analysis.

Performance optimization is not a valid reason to weaken reference-model independence or canonical
evidence requirements.
