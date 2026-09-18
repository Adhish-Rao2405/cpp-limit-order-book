# ADR 0004: Deterministic matching-core state architecture

- Status: Accepted
- Date: 2026-09-18
- Milestone: M3 — Deterministic Single-Writer Matching Core

## Context

M2 established the normative matching contract, invariants, strong domain types, and command-validation boundaries.
It deliberately deferred the concrete order-book representation, matching-loop state, active-order locator,
sequence allocator, trade output representation, and matching-core public API.

M3 introduces the first stateful matching implementation. The architecture must preserve the existing semantics
without silently weakening rejection atomicity, price-time priority, sequence allocation, sequence exhaustion,
active-order uniqueness, locator integrity, quantity conservation, deterministic replayability, or
post-processing quiescence.

This ADR refines, and must remain consistent with:

- ADR 0001 — integer price ticks;
- ADR 0002 — single-writer deterministic core;
- ADR 0003 — strong domain types and validation boundaries;
- `docs/MATCHING_SEMANTICS.md`;
- `docs/INVARIANTS.md`.

This is a correctness-first architecture decision. It does not establish a latency, throughput, HFT,
production-readiness, or exchange-fidelity claim.

## Decision summary

M3 will use a deterministic, single-writer `MatchingEngine` with:

```text
bids_:   ascending map<Price, FIFO list<RestingOrder>>
asks_:   ascending map<Price, FIFO list<RestingOrder>>
active_: unordered map<OrderId, Locator, OrderIdHash>
```

The logical best prices are:

```text
best ask = asks_.begin()
best bid = previous element before bids_.end()
```

`RestingOrder` stores only:

```text
OrderId
remaining Quantity
SequenceNumber
```

Price is implied by the owning price level. Side is implied by the owning side book.

The active-ID hash index is lookup support only. Hash-table iteration order is never matching authority,
trade-order authority, snapshot-order authority, or replay authority.

The engine owns an internal monotonic sequence allocator with an explicit exhausted state. Copy and move of the
engine are disabled in M3 because active locators contain iterators into the engine's own book graph.

Expected domain rejection is represented by `DomainError`. Accepted commands return an `ExecutionReport`
containing the ordered trades emitted by that command.

## 1. Public logical API boundary

The M3 public logical API is frozen to the following types and signatures. Only non-semantic implementation
details behind these declarations may vary:

```cpp
namespace lob {

struct Trade final {
    OrderId maker;
    OrderId taker;
    Price price;
    Quantity quantity;

    friend bool operator==(const Trade&, const Trade&) = default;
};

struct ExecutionReport final {
    std::vector<Trade> trades;

    friend bool operator==(const ExecutionReport&, const ExecutionReport&) = default;
};

struct RestingOrderView final {
    OrderId order_id;
    Side side;
    Price price;
    Quantity remaining;
    SequenceNumber sequence;

    friend bool operator==(const RestingOrderView&, const RestingOrderView&) = default;
};

struct EngineSnapshot final {
    std::vector<RestingOrderView> bids;
    std::vector<RestingOrderView> asks;
    std::optional<SequenceNumber> next_sequence;

    friend bool operator==(const EngineSnapshot&, const EngineSnapshot&) = default;
};

class MatchingEngine final {
public:
    MatchingEngine();

    MatchingEngine(const MatchingEngine&) = delete;
    MatchingEngine& operator=(const MatchingEngine&) = delete;
    MatchingEngine(MatchingEngine&&) = delete;
    MatchingEngine& operator=(MatchingEngine&&) = delete;

    [[nodiscard]] DomainResult<ExecutionReport> process(const NewOrder& command);
    [[nodiscard]] DomainResult<ExecutionReport> process(const CancelOrder& command);
    [[nodiscard]] DomainResult<ExecutionReport> process(const ModifyOrder& command);

    [[nodiscard]] EngineSnapshot snapshot() const;
};

}  // namespace lob
```

The semantic result contract remains:

```text
accepted command -> ExecutionReport
rejected command -> DomainError
```

Expected domain rejection is not exception-driven control flow.

No public command may accept an externally supplied `SequenceNumber`.

Normal public construction begins with `next_sequence = 1`. No public constructor or public method accepts an
initial sequence or allocator state.

The three `process(...)` overloads and `snapshot()` are not declared `noexcept` in M3 because their
implementations may allocate through standard-library containers or result storage.

## 2. Trade representation

M3 introduces a `Trade` value with exactly:

```text
maker OrderId
taker OrderId
Price
Quantity
```

The maker is the resting order. The taker is the currently processed incoming order or priority-losing
replacement. Execution price is always the resting maker price.

M3 does not introduce trade IDs, timestamps, venues, fees, settlement fields, or exchange-generated
identifiers.

Trade ordering inside one `ExecutionReport` is the deterministic order in which matching occurs.

## 3. ExecutionReport

A successful command produces an `ExecutionReport` containing an ordered sequence of `Trade` values.

A successful command that emits no trades returns an accepted report with an empty trade sequence. Examples
include cancellation, same-price quantity reduction, and a new order that rests without execution.

The report does not duplicate complete engine state. State observation is provided separately through a logical
snapshot boundary.

## 4. MatchingEngine ownership

`MatchingEngine` exclusively owns:

- bid price levels;
- ask price levels;
- all active resting-order nodes;
- the active-ID locator index;
- sequence-allocation state.

No external object owns or mutates a resting-order node.

M3 is single writer and `MatchingEngine` is not thread-safe.

All `process(...)` and `snapshot()` calls on one engine instance must be externally serialized. Concurrent
mutation is unsupported. Concurrent observation racing with mutation is unsupported.

A future concurrent-ingestion or concurrent-observation model requires a separate architecture decision and
qualification.

The engine is not copyable or movable in M3:

```text
copy construction: deleted
copy assignment: deleted
move construction: deleted
move assignment: deleted
```

Reason: `active_` stores locators containing iterators into the engine's own map/list graph. Compiler-generated
copy or move semantics must not create an unqualified locator graph.

Any later move support requires an explicit architecture decision and qualification of locator preservation or
reconstruction.

## 5. Side-book representation

Both sides use the same ascending price-map representation:

```text
map<Price, FIFO list<RestingOrder>>
```

Best-price access is explicit:

```text
ASK: best level = first ascending level
BID: best level = last ascending level
```

For an incoming BUY with limit `P`, execution is permitted only while:

```text
best_ask <= P
```

For an incoming SELL with limit `P`, execution is permitted only while:

```text
best_bid >= P
```

If the current best opposite level is not executable, no worse opposite level can be executable.

## 6. Price levels and FIFO

Each populated price level owns a FIFO list of `RestingOrder` nodes.

Within one price level:

```text
front = earliest execution priority
back  = latest execution priority
```

A positive residual that newly rests at a level is appended at the back.

A partial fill retains list position and sequence. A same-price positive remaining-quantity reduction also
retains list position and sequence.

A priority-losing modification never reuses the old list position. If its replacement leaves a positive
residual, that residual rests with the replacement's fresh sequence.

Sequence values remain the semantic priority identity. FIFO list position is the maintained storage
representation of that priority.

Sequences at one level must be strictly increasing in execution-priority order. They need not be contiguous.

## 7. RestingOrder state

The concrete M3 resting node stores:

```text
OrderId id
Quantity remaining
SequenceNumber sequence
```

It does not duplicate `Price` or `Side`.

For every active resting node:

```text
price = owning map key
side  = owning side book
```

This makes price-level consistency and side membership structural properties of the storage graph rather than
duplicated mutable state.

A zero remaining quantity is never a valid active `RestingOrder`.

## 8. Active-ID index

The engine maintains conceptually:

```text
active_: unordered_map<OrderId, Locator, OrderIdHash>
```

`OrderIdHash` hashes only the representational value of `OrderId`.

The index exists solely to resolve an active `OrderId` to its exact live book node.

It must satisfy:

```text
one active OrderId -> exactly one Locator
inactive OrderId   -> no active Locator
```

Iteration over `active_` has no semantic meaning.

No matching decision, trade ordering, snapshot ordering, replay ordering, or invariant definition may depend on
hash-table iteration order.

## 9. Typed Locator

Because both side books use the same concrete side-book type, raw iterator types alone do not encode side.

M3 therefore uses a typed locator variant conceptually equivalent to:

```text
BidLocator {
    bid-level iterator
    FIFO-node iterator
}

AskLocator {
    ask-level iterator
    FIFO-node iterator
}

Locator = variant<BidLocator, AskLocator>
```

The owning bid/ask book is the semantic authority for `Side`.

The `Locator` variant alternative is type-safe routing metadata used by active-ID lookup and must agree with the
owning side book. A disagreement between locator alternative and book ownership is an invariant violation; it
does not create a second semantic authority for side.

A locator must never refer to an inactive order, the wrong active order, an erased FIFO node, or an erased price
level.

## 10. Iterator and lifetime protocol

The architecture relies on the standard iterator-stability properties of node-based map and list containers for
unrelated insertions and erasures.

Persistent locator removal must precede destruction of the locator's referenced FIFO node.

For cancellation, complete maker fill, priority-losing replacement removal, and any other active-order removal,
the required logical destruction protocol is:

```text
1. locate the active-ID entry;
2. obtain the command-local iterator information required for erasure;
3. erase the persistent active-ID entry;
4. erase the exact FIFO node;
5. if the FIFO is now empty, erase the exact price level;
6. never dereference the erased node or level iterator again.
```

A command-local copy of an iterator may exist only long enough to perform the corresponding erase. Once that
element is erased, that iterator is dead and must not be dereferenced.

No empty price-level iterator may remain in `active_`. The final node's persistent locator is removed before an
empty level is erased.

## 11. unordered_map rehash discipline

`active_` may rehash as IDs are inserted.

Locators stored as mapped values point into the separate map/list book graph. Rehash of `active_` therefore does
not define the lifetime of those book iterators.

However, iterators into `active_` itself are not stable across an insertion that may rehash.

Therefore no iterator into `active_` may be retained across an operation that can insert into `active_` and
therefore trigger rehash.

Active-ID lookup iterators are command-local and short-lived. Hash iteration is never used to derive
deterministic logical order.

## 12. Sequence allocator

Sequence allocation is internal deterministic engine state.

The logical allocator state is:

```text
optional<SequenceNumber> next_sequence
```

Meaning:

```text
populated -> one fresh sequence is available
empty     -> allocator exhausted
```

Normal initial state is:

```text
next_sequence = 1
```

If `next_sequence` is empty, allocation fails with `SequenceExhausted`.

If the available value is less than `UINT64_MAX`:

```text
return current value
next_sequence = current + 1
```

If the available value is exactly `UINT64_MAX`:

```text
return UINT64_MAX exactly once
next_sequence = empty
```

The allocator must never increment `UINT64_MAX`. The allocator must never wrap to zero. The allocator must never
reissue an allocated sequence in one continuing allocator state.

## 13. Sequence-consumption rules

An accepted `NewOrder` consumes exactly one fresh sequence before matching, even if it fully executes and never
rests.

An accepted priority-losing `ModifyOrder` consumes exactly one fresh sequence before destructive replacement,
even if its replacement fully executes and never rests.

A same-price positive quantity reduction that retains priority consumes no fresh sequence.

A successful cancellation consumes no fresh sequence.

A rejected command consumes no sequence.

After allocator exhaustion, commands that do not require a fresh sequence may still succeed when otherwise
valid.

## 14. Sequence-exhaustion qualification seam

M3 qualification must exercise the `UINT64_MAX` boundary without processing an infeasible number of commands.

The implementation therefore uses internal test/qualification support to construct allocator state near
exhaustion. This seam is not part of the public `MatchingEngine` API.

Normal public `MatchingEngine` construction always begins with `next_sequence = 1`.

No public constructor, public method, or production command accepts an initial `SequenceNumber`, allocator state,
or caller-selected sequence identity.

The qualification seam must not become matching authority and must not weaken the production command-validation
contract.

Production commands can never supply or directly influence sequence identity.

## 15. NewOrder processing

`NewOrder` has already passed scalar validation in its command factory.

State-dependent processing is:

```text
1. if OrderId is active:
       reject DuplicateOrderId

2. request one fresh sequence:
       if unavailable:
           reject SequenceExhausted

3. process the order as incoming against the opposite book

4. emit trades in deterministic execution order

5. if positive incoming residual remains:
       append one resting node to the appropriate price level
       create exactly one active-ID locator

6. if no residual remains:
       do not create active resting state
```

`DuplicateOrderId` therefore precedes `SequenceExhausted`.

Once matching begins, no later expected `DomainError` path is permitted for this accepted transition.

## 16. CancelOrder processing

`CancelOrder` processing is:

```text
1. resolve OrderId in active_

2. if absent:
       reject UnknownOrderId

3. retain command-local iterator information required for erasure

4. erase the persistent active-ID locator

5. erase the exact resting node

6. erase its price level if the level became empty

7. return an accepted ExecutionReport with no trades
```

Cancellation consumes no sequence.

## 17. ModifyOrder classification

`ModifyOrder` has already passed scalar price and quantity validation in its command factory.

State-dependent processing is:

```text
1. resolve active OrderId
       absent -> UnknownOrderId

2. compare requested values with current active state

3. classify modification

4. apply normative rejection / priority semantics
```

Classification uses current remaining quantity, not historical or original submitted quantity.

Same price and lower positive remaining quantity:

```text
priority retained
sequence retained
FIFO position retained
no fresh sequence
no matching
```

Same price and unchanged remaining quantity:

```text
InvalidModification
```

Quantity increase:

```text
priority lost
fresh sequence required
atomic replacement path
```

Any price change:

```text
priority lost
fresh sequence required
atomic replacement path
```

## 18. Priority-losing ModifyOrder protocol

A priority-losing modification is an atomic domain-level cancel-and-replacement retaining the same `OrderId` and
same immutable `Side`.

The required ordering is:

```text
1. locate original active order;
2. classify the requested modification;
3. establish and consume one fresh sequence;
4. capture immutable replacement data required after removal:
       OrderId
       Side
       replacement Price
       replacement Quantity
       fresh SequenceNumber
5. retain command-local iterator information required for old-node erasure;
6. erase the persistent active-ID entry;
7. erase the original FIFO node;
8. erase the old price level if now empty;
9. process the replacement using normal incoming matching semantics;
10. if positive replacement residual remains:
        append it as a new resting node with the fresh sequence;
        create one new active-ID locator.
```

Sequence exhaustion is resolved before destructive removal.

Therefore `SequenceExhausted` leaves the original `OrderId`, price, remaining quantity, sequence, FIFO position,
and active locator unchanged.

The original node is absent before the replacement becomes an incoming taker. The replacement therefore cannot
match against its previous incarnation.

## 19. Matching loop

Matching always consumes the current best executable opposite price level first. Within that level, it consumes
FIFO front first.

Each trade quantity is logically:

```text
min(incoming_remaining, maker_remaining)
```

Matching continues until either incoming remaining quantity is zero or no executable opposite best level
remains.

When a maker is partially filled:

```text
maker remains in place
maker sequence unchanged
maker locator unchanged
```

When a maker is completely filled:

```text
retain command-local erasure iterators
erase maker active-ID entry
erase maker FIFO node
erase empty maker price level if required
```

After processing reaches quiescence, an invariant-compliant initially uncrossed book remains uncrossed.

When both sides remain populated:

```text
best_bid < best_ask
```

## 20. Quantity arithmetic

M3 does not add generic public arithmetic operators to `Quantity`.

Transient matching arithmetic may use `Quantity::rep` only after required bounds are established.

For each execution:

```text
trade_units = min(incoming_units, maker_units)
```

Given valid positive quantities:

```text
incoming_units > 0
maker_units > 0
```

therefore:

```text
trade_units > 0
trade_units <= incoming_units
trade_units <= maker_units
```

The subtractions:

```text
incoming_units - trade_units
maker_units - trade_units
```

cannot underflow.

A positive residual is reconstructed as `Quantity`. A zero residual is a completion/removal condition and is
never reconstructed as active `Quantity`.

Qualification of aggregate quantity conservation must use arithmetic or state-transition reasoning that cannot
silently overflow the proof representation itself.

## 21. Rejection atomicity

For every expected `DomainError` rejection:

```text
logical post-state == logical pre-state
allocator post-state == allocator pre-state
no trade is emitted
```

All expected rejection decisions must occur before irreversible matching mutation.

M3 does not introduce a later expected-domain rejection after matching has begun for an accepted transition.

This includes the state-dependent errors:

```text
DuplicateOrderId
UnknownOrderId
SequenceExhausted
InvalidModification
```

Scalar validation errors remain resolved by the existing command factories before the engine receives a
validated command.

## 22. Exception boundary

Engine processing is not declared `noexcept` in M3.

The selected standard containers and trade result storage may allocate.

M3 distinguishes:

```text
expected domain rejection
    -> typed DomainError
    -> domain rejection atomicity required

allocation/resource/runtime exception
    -> not DomainError
    -> strong transactional recovery is not claimed by M3
```

M3 does not claim continued engine usability after an arbitrary allocation or resource exception interrupts a
mutating operation.

A later milestone may strengthen this boundary through preallocation, object pools, custom allocators,
transactional construction, or another explicit architecture decision.

## 23. Deterministic logical snapshot

Qualification requires storage-independent observation of logical engine state.

The canonical active-order state appears exactly once in the snapshot: `bids` and `asks`. Their union is the
complete active set. No separate `active_orders` collection exists.

`EngineSnapshot` contains exactly these logical authorities:

```text
bids
asks
optional<SequenceNumber> next_sequence
```

Snapshot ordering is deterministic.

Bids are exposed:

```text
best price -> worst price
FIFO within equal price
```

Asks are exposed:

```text
best price -> worst price
FIFO within equal price
```

Each `RestingOrderView` contains `OrderId`, `Side`, `Price`, remaining `Quantity`, and `SequenceNumber`.

Price and side in a resting-order view are reconstructed from structural ownership rather than duplicated
internal node state.

Allocator snapshot state is logically:

```text
optional<SequenceNumber> next_sequence
```

Therefore `next_sequence = UINT64_MAX` and `next_sequence = empty` are observably different states.

The snapshot never obtains semantic ordering by iterating `active_`.

## 24. Invariant strategy

M3 distinguishes structural invariants, direct checks, and qualification evidence.

Structural support includes:

- side membership through the owning side book;
- price-level membership through the owning map key;
- FIFO storage through list position;
- one active locator entry per active ID;
- positive active quantity through `Quantity`;
- positive prices through `Price`.

Debug and qualification invariant checking must be capable of detecting at least:

```text
active locator count != active resting-order count
missing active locator for a resting order
locator resolving to wrong node
locator resolving to wrong side
duplicate active OrderId
zero/inactive residual represented as active
non-increasing sequence order within one price-level FIFO
crossed quiescent book
```

Whole-book scans are qualification/debug evidence. They are not required on a future performance-critical hot
path.

Removing an expensive runtime scan later must not silently weaken correctness qualification.

## 25. Complexity and performance boundary

The selected standard containers are chosen for clarity of ownership, iterator stability, deterministic ordered
price access, arbitrary active-order removal, and testability.

Expected characteristics include:

```text
price-level insertion/search:
    logarithmic in populated price levels

best ask:
    constant-time iterator access

best bid:
    constant-time from end iterator

FIFO front/back:
    constant time

list-node erase with known iterator:
    constant time

active-ID lookup:
    average constant time
    standard hash-table worst-case behaviour applies
```

These are algorithm/container characteristics, not benchmark evidence.

M3 makes no claim of low latency, high throughput, cache efficiency, zero allocation, lock freedom, HFT
readiness, production readiness, or exchange-grade suitability.

The selected containers establish a correctness baseline against which later measured optimization can be
compared.

## 26. Alternatives considered

### map<Price, deque<RestingOrder>>

Not selected for M3 because arbitrary cancellation and modification make stable locator semantics substantially
more awkward. Middle erasure and invalidation behaviour would enlarge the correctness surface.

### Central unordered_map<OrderId, RestingOrder> with price-level queues of IDs

Not selected for M3 because ownership and execution order would be split across a central object store and
secondary queues, increasing indirection and consistency obligations.

### Flat, intrusive, pooled, dense-price, or custom cache-aware structures

Deferred rather than permanently rejected. They may offer better measured latency or locality, but adopting them
before a correctness-qualified baseline would enlarge implementation and qualification complexity without
evidence that the added complexity is necessary.

### Concurrent mutation

Not selected for M3 under ADR 0002. Concurrency may be reconsidered only after deterministic single-writer
correctness and benchmark evidence exist.

## 27. Qualification obligations before M3 closure

Implementation of this ADR is not qualified merely because it compiles.

M3 qualification must include explicit evidence for at least:

- new order resting without crossing;
- incoming BUY selecting the lowest executable ask;
- incoming SELL selecting the highest executable bid;
- FIFO ordering at equal price;
- maker/resting execution price;
- one incoming order consuming multiple makers;
- partial maker fill retaining priority;
- complete maker fill removing locator and empty level correctly;
- duplicate active ID rejection;
- ID reuse after cancellation;
- ID reuse after complete fill;
- successful cancellation;
- unknown cancellation rejection;
- same-price quantity reduction retaining sequence and queue position;
- unchanged modify rejection;
- quantity increase losing priority;
- price change losing priority;
- marketable price-changing replacement;
- sequence consumed by fully executed incoming order;
- sequence consumed by fully executed priority-losing replacement;
- rejected command consuming no sequence;
- `UINT64_MAX` allocated exactly once;
- post-`UINT64_MAX` sequence exhaustion;
- cancellation after sequence exhaustion;
- priority-retaining reduction after sequence exhaustion;
- new-order rejection after sequence exhaustion without book mutation;
- priority-losing modify rejection after sequence exhaustion with original intact;
- replacement unable to self-match;
- quantity conservation;
- no zero-quantity trade;
- deterministic ordered trades;
- deterministic final snapshot;
- no executable cross after quiescence;
- locator integrity after mixed new/cancel/modify/fill workloads.

Where safely possible through internal qualification support, invariant-checking tests should demonstrate
detection of deliberately malformed internal states.

Debug and Release configurations must both remain qualified.

## 28. Consequences

Benefits include deterministic state ownership, stable book-node locators, direct FIFO representation,
structural price/side consistency, explicit sequence exhaustion, separation between hash lookup and semantic
order, storage-independent snapshots, and a credible baseline for profiling.

Costs include node-based allocation and pointer indirection, non-optimized cache locality, potentially allocating
trade storage, intentionally unavailable engine copy/move, and no claim of arbitrary allocation-failure
recovery.

These costs are accepted because M3 is a correctness milestone.

## 29. Deferred decisions

M3B does not decide custom allocator design, object-pool design, intrusive queue design, dense/flat price-ladder
representation, concurrent ingestion, lock-free structures, persistence, networking, external protocol parsing,
replay-file format, reference-engine implementation language, benchmark workload design, latency percentile
methodology, or production resource-exhaustion recovery.

These require later evidence. Architecture-changing decisions require a separate decision record.

## 30. Claim boundary

After this ADR is accepted, it is permissible to claim only that the project has frozen a concrete architecture
for implementing the deterministic matching core.

Acceptance of this ADR does not establish implemented matching correctness, a working production order book,
runtime invariant preservation, reference-engine agreement, differential agreement, benchmark performance, low
latency, high throughput, HFT capability, production readiness, or exchange-grade behaviour.

Those claims require subsequent implementation and explicit qualification evidence.

## 31. Architecture freeze rule

Production matching implementation may begin only after:

1. this ADR is reviewed against ADR 0001 through ADR 0003;
2. this ADR is reviewed against `docs/MATCHING_SEMANTICS.md`;
3. this ADR is reviewed against `docs/INVARIANTS.md`;
4. the M3B.3R corrections are confirmed present;
5. no unresolved semantic contradiction remains;
6. the ADR is accepted only after review;
7. the accepted ADR is committed with exact provenance;
8. the resulting committed repository is clean;
9. the architecture-freeze gate is explicitly declared PASS.

Any later implementation discovery that contradicts this ADR or the normative M2 semantics must stop
progression.

Implementation must not silently redefine the architecture or weaken the specification.
