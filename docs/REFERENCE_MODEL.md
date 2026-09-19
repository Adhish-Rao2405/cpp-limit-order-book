# M4 Independent Reference Model

- Status: Architecture implementation contract
- Runtime: CPython 3.12.10, standard library only
- Authority: ADR 0005 plus the frozen matching semantics, invariants, and ADRs 0001 through 0004

## 1. Purpose

This document defines the required behaviour, state model, qualification boundary, and evidence obligations for the primary M4 independent reference model.

The reference model is a correctness oracle. It is not a production matching engine, a performance model, a benchmark target, or semantic authority independent of the frozen project contract.

Acceptance of this document does not establish that the reference implementation exists, is correct, agrees with the C++ candidate, or has passed M5 differential qualification.

## 2. Authority and precedence

The reference implementation must be derived from:

- `docs/MATCHING_SEMANTICS.md`;
- `docs/INVARIANTS.md`;
- ADR 0001;
- ADR 0002;
- ADR 0003;
- ADR 0004 where ADR 0004 expresses logical behaviour rather than M3-specific storage mechanics; and
- ADR 0005.

The M3 C++ implementation and M3 tests are evidence about the candidate. They are not sources from which the reference algorithm, state topology, validation logic, or expected results are copied.

If candidate behaviour conflicts with the frozen semantic contract, the discrepancy is evidence to investigate. Candidate behaviour does not silently redefine the oracle.

## 3. Runtime and dependency contract

The primary reference implementation uses:

```text
CPython 3.12.10
64-bit runtime
Python standard library only
```

Third-party Python packages are prohibited for the primary oracle.

The runtime choice exists to increase implementation-language and arithmetic independence from the C++20 candidate. It is not a performance choice.

## 4. Qualification command envelope

The qualification boundary carries raw scalar values within the representation domains frozen by ADR 0005.

The v1 command forms are:

```text
RawNew:
    order_id       unsigned uint64
    side_code      unsigned uint8
    price_ticks    signed int64
    quantity_units unsigned uint64

RawCancel:
    order_id       unsigned uint64

RawModify:
    order_id       unsigned uint64
    price_ticks    signed int64
    quantity_units unsigned uint64
```

There is no sequence field in any matching command.

The v1 command envelope is closed. For each command kind, only the payload fields listed above and any expressly defined command-kind discriminator are permitted. Any other field is malformed qualification input.

A command kind outside `new`, `cancel`, or `modify`, a missing required field, or a scalar outside its representation domain is malformed qualification input.

At the Python qualification API boundary, every scalar field must have exact runtime type `int`. `bool` is malformed even though CPython defines `bool` as a subclass of `int`. Other scalar types are malformed and must not be coerced into integers by the reference model.

Malformed qualification input is not a `DomainError` and must fail the qualification or trace boundary.

Within the representation domain:

```text
side_code 0 -> Buy
side_code 1 -> Sell
side_code 2..255 -> invalid logical Side
```

The qualification envelope does not introduce textual prices, decimal-price conversion, network framing, arbitrary-precision external order values, timestamps, venue identifiers, or externally supplied sequence identity into the matching contract.

## 5. Domain error set

Expected matching-domain rejection is represented as data using exactly:

```text
InvalidPrice
InvalidQuantity
InvalidSide
DuplicateOrderId
UnknownOrderId
SequenceExhausted
InvalidModification
```

Expected domain rejection must not be represented by Python exception control flow.

Python exceptions are reserved for malformed qualification input, programming defects, failed internal assertions, or runtime/resource failures. Such exceptions must not be translated into `DomainError`.

## 6. Command result

Each processed matching command produces one logical command result.

An accepted command result contains:

```text
accepted = true
error = absent
```

A rejected command result contains:

```text
accepted = false
error = exact DomainError
```

Ordered trades and post-command state are not nested inside `command_result`. They are sibling fields of the command observation defined in Section 22.

For an expected rejection, the sibling ordered-trades field is empty and the post-command logical state equals the pre-command logical state.

The allocator state is part of that logical state and therefore must also remain unchanged on expected rejection.

## 7. Reference state

The reference engine owns only:

```text
active_orders
next_sequence
```

`active_orders` is a flat Python collection of immutable reference-order values.

Each reference order contains:

```text
order_id
side
price_ticks
remaining_quantity
sequence
```

The allocator is represented logically as either:

```text
positive uint64 next_sequence
```

or:

```text
exhausted
```

Normal construction starts with an empty active-order collection and `next_sequence = 1`.

Qualification-only construction may replace the normal allocator state with any valid logical allocator state: a positive uint64 `next_sequence` or exhausted.

The qualification allocator seed is not a matching command, is not command data, must not permit a command to choose sequence identity, and must not become matching authority.

Non-empty active state is reached through matching commands in v1. The v1 reference constructor does not accept arbitrary externally supplied active orders.

## 8. Independence requirements

The reference implementation must not reproduce the M3 candidate topology:

```text
map<Price, FIFO list<RestingOrder>>
unordered_map<OrderId, Locator>
BidLocator / AskLocator
persistent container iterators
price-level ownership as semantic authority
```

Active-ID resolution is a linear scan of the flat active-order collection.

Maker selection is a fresh linear semantic search over active orders on every matching iteration.

Flat-collection position is never execution-priority authority.

The reference implementation must not call or wrap `MatchingEngine`, reuse C++ command factories, derive expected state from a candidate snapshot, invoke candidate matching helpers, or import candidate state-transition logic.

The reference may share the frozen semantic vocabulary. It must not share candidate implementation mechanisms that differential qualification is intended to check.

## 9. Reference invariants

At every command boundary, valid reference state must satisfy:

- each active `OrderId` identifies exactly one active order;
- each active remaining quantity is positive;
- each active price is positive;
- each active side is exactly Buy or Sell;
- every active sequence is positive and within uint64;
- sequence wrap and sequence reuse are forbidden;
- equal-price execution priority is determined by lower sequence;
- an inactive `OrderId` does not resolve as active;
- no active order has zero remaining quantity; and
- after accepted processing from an invariant-compliant uncrossed pre-state, the quiescent book is uncrossed.

If both sides are populated at quiescence:

```text
best_bid < best_ask
```

The reference implementation must not claim to repair arbitrary malformed or crossed initial active state. V1 does not accept externally seeded active orders.

## 10. Scalar validation

Representation validity is established before matching-domain validation.

For `RawNew`, scalar domain validation order is:

```text
1. price_ticks <= 0     -> InvalidPrice
2. quantity_units == 0  -> InvalidQuantity
3. side_code not 0 or 1 -> InvalidSide
```

For `RawModify`, scalar domain validation order is:

```text
1. price_ticks <= 0    -> InvalidPrice
2. quantity_units == 0 -> InvalidQuantity
```

`RawCancel` contains only a representationally valid uint64 `order_id` and therefore has no scalar matching-domain rejection before active-ID resolution.

OrderId value `0` is valid.

Quantity `0` is invalid and is never implicit cancellation.

## 11. New-order rejection precedence

After representation validity, `RawNew` uses exactly this rejection precedence:

```text
1. InvalidPrice
2. InvalidQuantity
3. InvalidSide
4. DuplicateOrderId
5. SequenceExhausted
```

A duplicate check considers active lifetime only.

An `OrderId` may be reused after its prior order has been fully filled or successfully cancelled.

A rejected new order:

```text
emits no trade
consumes no sequence
changes no active state
changes no allocator state
```

## 12. New-order accepted transition

For an accepted new order:

1. scalar validation has passed;
2. no active order has the same `OrderId`;
3. a fresh sequence is available;
4. exactly one fresh sequence is assigned before matching begins;
5. the incoming order matches as a taker using the algorithm in this document; and
6. any positive residual rests at the incoming limit with the sequence already assigned.

An accepted new order consumes exactly one fresh sequence even if it fully fills and leaves no resting residual.

No expected `DomainError` may arise after the accepted transition has entered matching.

## 13. Cancellation

For `RawCancel`:

```text
active order_id   -> accepted cancellation
inactive order_id -> UnknownOrderId
```

A successful cancellation:

- removes the active order;
- emits no trade;
- consumes no sequence; and
- leaves all unrelated active orders unchanged.

An unknown cancellation:

- emits no trade;
- consumes no sequence;
- changes no active state; and
- changes no allocator state.

Cancellation remains available when the sequence allocator is exhausted.

## 14. Modify rejection precedence

After representation validity, `RawModify` uses exactly this rejection precedence:

```text
1. InvalidPrice
2. InvalidQuantity
3. UnknownOrderId
4. InvalidModification
5. SequenceExhausted, only when the valid modification requires requeue
```

The modification quantity is target remaining quantity.

Side cannot change through Modify and is not present in `RawModify`.

A rejected modification:

```text
emits no trade
consumes no sequence
changes no allocator state
leaves the original order exactly unchanged
```

Exact original state includes price, side, remaining quantity, sequence, and execution priority.

## 15. Priority-retaining modification

If the target price equals the active order price and the target remaining quantity is lower but positive:

- accept the modification;
- retain the same `OrderId`;
- retain side;
- retain price;
- retain sequence;
- retain execution priority;
- change only remaining quantity;
- perform no matching; and
- consume no sequence.

This transition remains valid when the sequence allocator is exhausted.

If the target price and target remaining quantity both equal the active values, reject with `InvalidModification`.

## 16. Priority-losing modification

A modification loses priority when either:

- target remaining quantity increases at the same price; or
- target price changes, regardless of whether quantity increases, decreases, or remains equal.

A priority-losing modification:

- retains the same `OrderId`;
- retains immutable side;
- requires exactly one fresh sequence;
- must establish fresh-sequence availability before destructive state mutation;
- must reject with `SequenceExhausted` without changing the original order when no sequence is available;
- removes the original order before processing the replacement as incoming;
- processes the replacement using normal incoming matching semantics; and
- rests any positive residual with the fresh sequence.

Because the original order is absent before replacement matching begins, the replacement cannot match against its previous incarnation.

## 17. Sequence allocator algorithm

Normal allocator state begins at `1`.

When a command requires a fresh sequence:

```text
if allocator is exhausted:
    reject the fresh-sequence requirement with SequenceExhausted
else if next_sequence < UINT64_MAX:
    assigned = next_sequence
    next_sequence = next_sequence + 1
else:
    assigned = UINT64_MAX
    allocator becomes exhausted
```

`UINT64_MAX` is therefore allocatable exactly once.

Sequence value `0` is never allocated.

Sequence wrap and reuse are forbidden.

Accepted new orders and accepted priority-losing modifications consume exactly one fresh sequence.

Successful cancellations, accepted priority-retaining reductions, and rejected commands consume no sequence.

The qualification-only allocator seed may be used to exercise the boundary without processing an infeasible number of commands. It must not alter these allocation semantics.

## 18. Maker selection

For an incoming Buy with limit `P`, eligible makers are active Sell orders with:

```text
maker.price_ticks <= P
```

Choose the maker with:

```text
lowest price_ticks
then lowest sequence
```

For an incoming Sell with limit `P`, eligible makers are active Buy orders with:

```text
maker.price_ticks >= P
```

Choose the maker with:

```text
highest price_ticks
then lowest sequence
```

Price priority therefore precedes sequence priority.

A better price beats an older order at a worse price.

At equal price, lower sequence executes first.

A fresh semantic search is performed after every maker update or removal.

## 19. Trade formation and matching loop

For each selected maker:

```text
trade_price = maker.price_ticks
trade_quantity = min(incoming_remaining, maker.remaining_quantity)
```

`trade_quantity` must be positive.

Each trade contains exactly:

```text
maker_order_id
taker_order_id
price_ticks
quantity_units
```

The trade price is the resting maker price, not the incoming limit.

Trades are appended in exact execution order.

After a trade:

- reduce incoming remaining quantity by trade quantity;
- reduce maker remaining quantity by trade quantity;
- remove a fully filled maker immediately;
- otherwise replace the maker value with the reduced positive remaining quantity while retaining maker ID, side, price, sequence, and priority.

Continue until either:

```text
incoming remaining quantity == 0
```

or:

```text
no executable maker exists
```

If positive incoming residual remains, rest it with its already assigned incoming sequence.

No active zero-quantity order is permitted.

## 20. Conservation

For accepted incoming quantity `Q0`:

```text
Q0 = mathematical sum of emitted trade quantities + final incoming residual
```

For each maker execution:

```text
maker_before = trade_quantity + maker_after
```

when the maker remains active.

For a fully filled maker:

```text
maker_before = trade_quantity
```

and no active maker residual remains.

Qualification and proof arithmetic must use Python arbitrary-precision integers or an equivalently non-wrapping method.

Proof arithmetic does not expand the uint64 order-quantity domain.

## 21. Determinism

Given identical:

- valid initial logical state;
- allocator state;
- configuration; and
- ordered qualification command stream;

the reference model must produce identical:

- accepted/rejected command results;
- exact `DomainError` values;
- sequence evolution;
- ordered trades;
- active orders;
- remaining quantities;
- prices;
- priority ordering; and
- final logical state.

Wall-clock time, host identity, hash-table order, Python object identity, memory address, scheduler behaviour, and container position are not semantic authority.

## 22. Canonical logical observation

After every command, the reference exposes a storage-independent logical observation containing:

```text
command_result
ordered trades
bids
asks
next_sequence
```

Each exposed command observation is a point-in-time logical value for that completed command. Once exposed, its logical contents must not change when later commands are processed.

The implementation may use immutable containers, defensive copies, or another mechanism, but retained historical observations must preserve the same logical values they had when emitted.

Canonical bids are ordered:

```text
price descending
then sequence ascending
```

Canonical asks are ordered:

```text
price ascending
then sequence ascending
```

Each resting-order observation contains:

```text
order_id
side
price_ticks
remaining_quantity
sequence
```

The allocator observation distinguishes:

```text
next_sequence = UINT64_MAX
```

from:

```text
allocator exhausted
```

These are different logical states.

The exact byte serialization of these observations belongs to `docs/CANONICAL_TRACE.md`.

## 23. Expected rejection atomicity

Every expected `DomainError` must satisfy:

```text
logical post-state == logical pre-state
allocator post-state == allocator pre-state
ordered trades == empty
```

All expected rejection conditions must therefore be determined before any destructive logical mutation required by the accepted transition.

This requirement does not claim transactional recovery from arbitrary Python runtime/resource failures.

## 24. Implementation strategy

Reference-order values are immutable, as required by Section 7.

State transitions may create replacement values rather than mutate object graphs.

The implementation should favour obvious semantic code over abstraction density.

The implementation should keep:

- representation validation;
- domain validation;
- active-ID resolution;
- sequence allocation;
- maker selection;
- matching;
- canonical observation; and
- qualification-only state seeding

as reviewable responsibilities with clear boundaries.

This does not require a particular Python module layout. File layout is an implementation-scope decision and must not weaken the independence rules in ADR 0005.

## 25. Qualification obligations

M4 reference qualification must cover, at minimum:

### Representation boundary

- int64 minimum and maximum price representations are accepted by the envelope;
- uint64 minimum and maximum quantity representations are accepted by the envelope;
- uint64 minimum and maximum OrderId representations are accepted by the envelope;
- uint8 side codes `0` and `1` map to Buy and Sell;
- uint8 side codes `2` through `255` are representationally valid but domain-invalid;
- values outside any representation range fail as malformed qualification input rather than `DomainError`;
- Python `bool` scalar values fail as malformed qualification input; and
- non-`int` scalar values fail as malformed qualification input without numeric coercion.
- each command kind rejects every unlisted payload field as malformed qualification input.

### New-order precedence

Adversarial combinations must prove:

```text
invalid price + invalid quantity + invalid side + duplicate + exhausted -> InvalidPrice
valid price + invalid quantity + invalid side + duplicate + exhausted   -> InvalidQuantity
valid price + valid quantity + invalid side + duplicate + exhausted     -> InvalidSide
valid scalar values + duplicate + exhausted                             -> DuplicateOrderId
valid scalar values + unique ID + exhausted                             -> SequenceExhausted
```

### Modify precedence

Adversarial combinations must prove:

```text
invalid price + other defects                       -> InvalidPrice
valid price + zero quantity + other defects         -> InvalidQuantity
valid scalar values + unknown ID + exhausted        -> UnknownOrderId
active exact no-op + exhausted                      -> InvalidModification
same-price positive reduction + exhausted           -> accepted
priority-losing valid modification + exhausted      -> SequenceExhausted
```

For the final case the original active order must remain exactly unchanged.

### Cancellation under exhaustion

Qualification must prove:

```text
unknown ID + exhausted allocator -> UnknownOrderId
active ID + exhausted allocator  -> accepted cancellation
```

### Price-time matching

Qualification must cover:

- better price before older worse price;
- lower sequence first at equal price;
- multi-level sweeps;
- maker-price execution;
- partial maker retention;
- full maker removal;
- incoming residual resting;
- exact ordered trade sequence.

### Physical-order independence

Reference-only qualification must build a valid non-empty state through matching commands, then compare logically identical states whose flat active-order collections differ only in physical element order.

At least one equal-price case must place the lower-sequence maker after the higher-sequence maker physically. Qualification must exercise the independence property for both bid and ask maker selection.

Maker selection and canonical logical observation must remain identical.

Any test-only physical reordering mechanism is qualification-only. It is not a matching command, must not be exposed as the v1 external active-state constructor, must not change any logical order field or allocator state, and must not become semantic authority.

### Modification behaviour

Qualification must cover:

- same-price reduction retains priority and sequence;
- same-price no-op rejects;
- same-price increase loses priority;
- any price change loses priority;
- priority-losing replacement may match immediately;
- original order is absent before replacement matching;
- replacement residual uses the fresh sequence.

### Sequence boundary

Qualification must prove:

- normal first allocation is `1`;
- `UINT64_MAX` is allocated exactly once;
- the next fresh-sequence requirement rejects with `SequenceExhausted`;
- no wrap occurs;
- cancellations and priority-retaining reductions still work after exhaustion;
- rejected commands do not consume sequence.

### ID lifetime

Qualification must prove:

- duplicate active ID rejects;
- ID reuse after successful cancellation is allowed;
- ID reuse after full fill is allowed.

### Conservation and quiescence

Qualification must prove:

- incoming conservation with non-wrapping proof arithmetic;
- maker conservation;
- positive trade quantity;
- no active zero quantity;
- valid execution price bounds; and
- uncrossed quiescent state after accepted processing from a valid uncrossed pre-state.

### Determinism

Repeated execution of the same qualified initial allocator state and ordered command stream must produce exactly equal logical observations.

### Observation stability

Qualification must retain at least one exposed observation across a later accepted state-changing command and prove that the retained observation remains logically unchanged.

## 26. Qualification independence

Reference qualification cases must be derived from the frozen semantic requirements and this contract.

It is acceptable for a semantic case to resemble a candidate test because both test the same requirement. Expected results must not be generated by calling the candidate engine.

The reference test suite must not treat candidate output as an oracle.

M5 owns candidate-versus-reference comparison.

## 27. Canonical-trace boundary

The reference model must expose enough logical information for the canonical serializer to produce producer-neutral trace bytes.

The reference model itself must not add producer-specific metadata such as:

- Python executable path;
- host identity;
- wall-clock time;
- Git commit;
- CI run identifier; or
- implementation name

to the semantic observation supplied to canonical trace serialization.

Provenance belongs outside semantic canonical trace bytes.

## 28. Complexity and performance

The reference algorithm is intentionally allowed to be asymptotically poor.

Linear ID scans and repeated linear maker searches are accepted.

No latency, throughput, allocation, cache-locality, or HFT claim may be derived from reference-model execution time.

Performance optimization is not a valid reason to introduce M3 map/list or locator topology into the primary oracle.

## 29. M4, M5, and M6 boundary

M4 owns:

- implementation and qualification of this independent reference model;
- canonical trace contract and serializer qualification; and
- local plus CI qualification of the M4 evidence surface.

M5 owns:

- candidate-versus-reference differential execution;
- adversarial and generated differential workloads;
- mismatch evidence; and
- metamorphic differential qualification.

M6 owns:

- standalone replay;
- durable evidence packaging;
- provenance manifests;
- replay verification; and
- correctness freeze after differential qualification.

Passing M4 must not be described as M5 differential agreement or M6 replay/evidence closure.

## 30. Non-claims

This document and the M4 reference model do not establish:

- universal correctness over all possible command streams;
- formal verification;
- production readiness;
- benchmark performance;
- low latency;
- high throughput;
- HFT capability;
- concurrency;
- persistence;
- recovery;
- fidelity to a real exchange; or
- exchange-grade behaviour.

## 31. Change control

After this document is accepted, changes that alter:

- reference language or dependency model;
- qualification-envelope representation domains;
- domain-error set or rejection precedence;
- allocator authority or exhaustion semantics;
- reference-state topology in a way that materially reduces independence;
- active-ID resolution strategy;
- maker-selection semantics;
- expected-rejection atomicity;
- canonical logical observation authorities; or
- the M4/M5/M6 responsibility boundary

require explicit architecture review and qualification-impact analysis.

Implementation convenience and performance are not sufficient reasons to weaken independence or evidence requirements.
