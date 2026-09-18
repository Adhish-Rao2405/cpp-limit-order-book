# Domain and Matching Invariants

## Status

Specification origin: **M2 — Domain Model + Formal Matching Contract + Invariants**

Current implementation status: **M3-r1 — Deterministic Single-Writer Matching Core qualified**

This document remains the normative invariant contract. Historical `M2B status` and `Future enforcement`
subsections are retained as specification provenance; they describe the state when M2B was authored and are
not the current implementation-status summary.

The original M3 implementation freeze is commit
`41654e89229cf7742cd44a6c6e77b277d5a063b3`. Its qualification suite contained 74 tests and passed in both
Debug and Release locally and in GitHub Actions run `35349811141`.

A post-freeze audit identified F-01: `MatchingEngine::invariants_hold()` did not detect non-increasing sequence
order within one price-level FIFO as required by ADR 0004 section 24. The finding established an invariant-checker
conformance defect; it did not establish a production matching-behaviour defect.

Corrective commit `5e037546aed7abbe751fa2178b2dd426517d86e4` added the missing strict per-level sequence-order check and
adversarial qualification coverage. It was merged to `main` at
`afaf6f4466d47811593d66ddc96d5eb30921159d`, tree
`172e396f46b007d8c3fe0442b74144f0c5db57f4`. The current suite contains 77 tests and post-merge GitHub
Actions run `35386634152` passed Debug and Release. Annotated tag `m3-matching-core-qualified-r1` freezes this
corrective qualified state; the original `m3-matching-core-qualified` tag remains unchanged as historical
qualification provenance.

M3 provides explicit implementation and qualification evidence for active-ID uniqueness, positive active
state, structural side/price ownership, FIFO/sequence behaviour, locator consistency, maker-price execution,
limit-boundary matching, rejection atomicity, sequence exhaustion/no-wrap behaviour, modification priority,
quiescent uncrossed state and deterministic replay equivalence for the tested command stream.

The qualification suite is evidence for the covered state transitions; it is not a mathematical proof over
all possible input streams. A standalone replay/reference evidence harness and exhaustive differential oracle
remain future work.

The matching semantics in `docs/MATCHING_SEMANTICS.md` are normative and this document must remain
consistent with them.

---

## 1. Status terminology

### SPECIFIED

The property is formally defined, but no implementation claim is made.

### DOMAIN-ENFORCEABLE

The property, or a scalar portion of it, may be enforceable by strong domain types.

### BOOK-ENFORCEABLE

The property requires active order-book state.

### MATCHING-ENFORCEABLE

The property requires matching behaviour.

### QUALIFIED

The relevant implementation exists and explicit test/evidence qualification has passed.

The per-invariant M2B status markers below are historical provenance. Current M3 implementation and qualification status is summarized in Section 18.

---

# I1 — Active Order ID Uniqueness

For every `OrderId x`:

```text
count(active_orders where order.id == x) <= 1
```

Equivalently:

> No two simultaneously active orders may share one `OrderId`.

This is an active-lifetime property.

It does not prohibit reuse of an ID after the previous order with that ID has become inactive through complete fill or cancellation.

Because active-lifetime reuse is permitted, historical event consumers must not assume that `OrderId` alone is a globally unique lifetime identifier.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Requires active-order state and therefore belongs to a later book implementation.

---

# I2 — Positive Active Quantity

For every active resting order `o`:

```text
o.remaining_quantity > 0
```

An order whose remaining quantity becomes zero must leave active state immediately.

A zero-quantity active order is invalid.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Positive scalar `Quantity` validity may become domain-enforceable during M2.

Active-state enforcement requires a later book and matcher.

---

# I3 — Valid Resting Price

For every active resting limit order `o`:

```text
o.price_ticks > 0
```

No active limit order may rest at zero or a negative tick price.

Floating-point values do not participate in matching price ordering.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Positive scalar `Price` validity may become domain-enforceable during M2.

Resting-state enforcement requires a later book.

---

# I4 — Side Consistency

For every active order `o`:

```text
o.side ∈ {Buy, Sell}
```

and the order may belong only to the logical side represented by that value.

An active order cannot simultaneously be a bid and an ask.

The only valid logical side values are `Buy` and `Sell`.

If an out-of-range underlying enumeration value reaches `NewOrder` command
validation, it must be rejected as:

```text
InvalidSide
```

M2C may instead make invalid side construction impossible at the public command
boundary. It must not silently map an invalid value to either valid side.

An accepted modification does not change side.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Strong enum representation can constrain the scalar domain during M2.

Book membership consistency is deferred.

---

# I5 — Price-Level Consistency

Once price-level storage exists, for every active resting order `o` contained in price level `L`:

```text
o.price == L.price
```

An order must never be stored under a price level different from its logical price.

This invariant specifies logical consistency only.

It does not select a container, price-level representation, ownership graph, or locator strategy.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Deferred until a price-level representation exists.

---

# I6 — FIFO / Sequence Consistency

For active resting orders `a` and `b` on the same side and at the same price:

```text
a.sequence < b.sequence
```

implies:

```text
a has execution priority over b
```

unless `a` leaves the active set before execution.

A partial fill does not change sequence.

A same-price positive quantity reduction does not change sequence.

A priority-losing modification receives a fresh sequence.

The initial allocatable sequence is:

```text
1
```

A successfully allocated sequence is never reissued by the same continuing allocator state.

Sequence `UINT64_MAX` may be allocated once if reached legitimately.

After `UINT64_MAX` has been allocated, any later command requiring a fresh sequence is rejected with:

```text
SequenceExhausted
```

The allocator must never wrap to `0` or any previously allocated sequence.

An accepted new order consumes exactly one fresh sequence even if it fully executes and never rests.

A priority-losing accepted modification consumes exactly one fresh sequence even if its replacement fully executes and never rests.

Rejected commands consume no sequence.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Requires engine sequence state and, for resting priority, book ordering.

---

# I7 — Locator Integrity

Once active-ID lookup exists, for every active order `o`:

```text
lookup(o.id) resolves to exactly o
```

and for every inactive `OrderId x`:

```text
lookup(x) does not resolve to an inactive order as active
```

There must be a one-to-one relationship between active IDs and active orders.

No active locator may:

- point to an inactive order;
- point to the wrong active order;
- represent two active orders for one ID.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Deferred until a locator/index structure exists.

---

# I8 — Positive Trade Quantity

For every emitted trade `t`:

```text
t.quantity > 0
```

Immediately before execution:

```text
t.quantity <= taker.remaining_quantity
```

and:

```text
t.quantity <= maker.remaining_quantity
```

Therefore no trade may consume more quantity than either participant possesses immediately before that trade.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Requires matching and trade emission.

---

# I9 — Matching Price Validity

Every trade must satisfy the incoming order's limit constraint.

For incoming BUY order `b` and trade `t`:

```text
t.price <= b.limit_price
```

For incoming SELL order `s` and trade `t`:

```text
t.price >= s.limit_price
```

An incoming order must never execute outside its own limit.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Requires matching implementation.

---

# I10 — Resting-Price Execution

For every trade `t` between incoming/taker order `i` and resting/maker order `r`:

```text
t.price == r.price
```

The incoming limit determines executability.

It does not replace the maker price as the execution price.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Requires matching implementation.

---

# I11 — Quantity Conservation

For an accepted incoming order with original incoming quantity `Q0`, let:

```text
T = mathematical sum of all quantities executed by that incoming order
R = final positive resting residual for that order, or 0 if no residual rests
```

Then:

```text
Q0 = T + R
```

For every individual execution against maker `m`:

if the maker remains active after the trade:

```text
maker_quantity_before =
    trade_quantity + maker_quantity_after
```

If the maker is completely filled:

```text
maker_quantity_before = trade_quantity
```

and no active maker residual exists.

Matching may transfer quantity from active state into emitted trade events, but it must not create or destroy quantity.

### Arithmetic qualification requirement

A future test or reference implementation must not attempt to prove conservation using unchecked fixed-width accumulation that can itself silently overflow.

Qualification must use checked arithmetic, a wider proof representation where appropriate, or equivalent state-transition reasoning that cannot silently wrap.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Requires matching implementation and qualification.

---

# I12 — Determinism

Let:

```text
S0
```

be an identical valid initial logical state.

Let:

```text
A0
```

be an identical initial sequence-allocator state.

Let:

```text
C = [c1, c2, ..., cn]
```

be an identical ordered command stream.

Let all configuration relevant to logical semantics also be identical.

Then repeated processing must produce identical:

```text
command acceptance/rejection outcomes
rejection categories
allocated sequences
final sequence-allocator state
ordered trade stream
active orders
remaining quantities
prices
queue ordering
final logical state
```

Formally, the logical transition system can be described as:

```text
F(S0, A0, C, configuration)
    =
(results, trades, Sfinal, Afinal)
```

and must be deterministic.

Wall-clock timing, scheduler behaviour and thread interleaving are not matching authority.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Requires state-machine implementation plus replay and/or differential qualification.

---

# I13 — No Executable Cross After Processing

Preconditions:

```text
the initial resting state is invariant-compliant
```

and:

```text
the initial resting state contains no executable bid/ask cross
```

After an accepted command has been processed completely to quiescence, there must not exist an active bid `b` and active ask `a` such that:

```text
b.price >= a.price
```

Equivalently, when both sides are non-empty:

```text
best_bid < best_ask
```

must hold after processing completes.

This applies after processing:

- an accepted new order;
- a priority-losing modification that is processed as an atomic replacement.

A same-price priority-retaining quantity reduction cannot itself introduce a cross.

This invariant does not claim that the engine repairs arbitrary externally corrupted state.

### M2B status

```text
SPECIFIED
```

### Future enforcement

Requires matching and order-book implementation.

---

# 14. Command rejection atomicity

The following normative property applies to every rejected command:

```text
logical_post_state == logical_pre_state
```

and:

```text
sequence_allocator_post_state ==
    sequence_allocator_pre_state
```

Additionally:

```text
no trade is emitted
```

This applies to expected rejection categories including:

```text
InvalidPrice
InvalidQuantity
InvalidSide
DuplicateOrderId
UnknownOrderId
SequenceExhausted
InvalidModification
```

A rejected priority-losing modification must therefore leave the original order completely intact, including its sequence and queue position.

---

# 15. Sequence allocation property

The sequence allocator obeys all of the following:

- allocation begins at `1`;
- allocation is internal to deterministic engine state;
- each accepted new order consumes exactly one fresh sequence;
- each accepted priority-losing modification consumes exactly one fresh sequence;
- accepted priority-retaining same-price quantity reductions consume no fresh sequence;
- successful cancellations consume no fresh sequence;
- rejected commands consume no sequence;
- allocated values increase monotonically;
- allocated values are never reused by the same continuing allocator state;
- `UINT64_MAX` may be allocated once;
- allocation after `UINT64_MAX` is exhausted;
- exhaustion is reported as `SequenceExhausted`;
- sequence wrap is forbidden.

The existence of a sequence does not imply that the corresponding order must rest.

A new order or replacement can consume its sequence, fully execute, and leave no active residual.

---

# 16. Modification priority property

For an active order with current price `P` and current remaining quantity `Q`:

### Same price and lower positive remaining quantity

If:

```text
new_P == P
0 < new_Q < Q
```

then:

```text
priority retained
sequence retained
```

### Same price and unchanged remaining quantity

If:

```text
new_P == P
new_Q == Q
```

then:

```text
InvalidModification
```

and no state or allocator mutation occurs.

### Quantity increase

If:

```text
new_Q > Q
```

then:

```text
priority lost
fresh sequence required
```

### Any price change

If:

```text
new_P != P
```

then:

```text
priority lost
fresh sequence required
```

The priority-losing operation is logically an atomic cancel-and-replacement while retaining the same `OrderId`.

The replacement is processed under normal incoming-order matching semantics.

If the replacement cannot obtain a fresh sequence, the original order remains unchanged.

---

# 17. Rejection precedence property

Rejection precedence is normative because deterministic behaviour must not depend on incidental implementation order.

For `NewOrder`:

```text
1. InvalidPrice
2. InvalidQuantity
3. InvalidSide
4. DuplicateOrderId
5. SequenceExhausted
```

For `ModifyOrder`:

```text
1. InvalidPrice
2. InvalidQuantity
3. UnknownOrderId
4. InvalidModification
5. SequenceExhausted
```

where `SequenceExhausted` applies only when the otherwise-valid modification requires a fresh sequence.

For `CancelOrder`:

```text
UnknownOrderId
```

is the expected rejection for an ID that is not currently active.

---

# 18. Enforcement matrix

| Invariant | M2B specification | M3 implementation | M3 qualification evidence |
| --- | --- | --- | --- |
| I1 Active ID uniqueness | Specified | Active-ID index plus lifecycle checks | Duplicate-ID, fill/cancel reuse, cardinality and locator tests |
| I2 Positive active quantity | Specified | Strong `Quantity` plus zero-residual removal | Lifecycle, partial-fill and invariant-checker tests |
| I3 Valid resting price | Specified | Strong positive `Price` and structural price levels | Domain validation plus matching-state tests |
| I4 Side consistency | Specified | Validated side plus side-book ownership | Buy/sell symmetry, modify-side immutability and invariant checks |
| I5 Price-level consistency | Specified | Price is represented by the owning map level | Snapshot, remove/recreate-level and invariant checks |
| I6 FIFO/sequence consistency | Specified | FIFO lists plus monotonic sequence allocation | FIFO, partial-fill retention, reductions, requeue and exhaustion tests |
| I7 Locator integrity | Specified | Typed bid/ask locators in the active index | Locator consistency and active-cardinality invariant checks |
| I8 Positive trade quantity | Specified | Positive `Quantity` construction and bounded matching subtraction | Partial/full-fill and maximum-quantity tests |
| I9 Matching price validity | Specified | Matching loops enforce incoming limit boundaries | Buy/sell limit-boundary and multi-level sweep tests |
| I10 Resting-price execution | Specified | Trade price is the maker/resting level price | Buy/sell and multi-level maker-price tests |
| I11 Quantity conservation | Specified | Matching transitions subtract the same bounded trade quantity from participants | Scenario and extreme-quantity tests; no standalone exhaustive conservation oracle yet |
| I12 Determinism | Specified | Single-writer canonical state and deterministic snapshot ordering | Repeated-engine replay-equivalence test; standalone replay harness not yet implemented |
| I13 No executable cross | Specified | Matching drains executable prices to quiescence | Boundary tests plus invariant checker requiring `best_bid < best_ask` |

M3 qualification is bounded evidence for the implemented transition system. It does not convert this matrix
into a universal proof over arbitrary corrupted state, resource-exception paths or all possible command streams.

---

# 19. Specification versus runtime checking

An invariant may be preserved structurally without a dedicated runtime assertion.

M3 does not perform a whole-book invariant scan after every production command. The engine instead combines:

1. strong scalar/domain validation;
2. structural ownership in canonical bid/ask books;
3. a typed active-ID locator index;
4. deterministic matching transitions;
5. a private `invariants_hold()` checker used by qualification tests through a build-gated friend seam; and
6. targeted and adversarial tests, including allocator-exhaustion and deterministic-replay cases.

The canonical bid/ask books are invariant authority. Iteration over the unordered active-ID index is not
semantic authority.

Reference/differential testing and a standalone replay/evidence harness are not yet implemented.

No performance-oriented omission is permitted to weaken correctness evidence silently.

---

# 20. Non-claims

The M3 implementation and qualification evidence do not establish:

- universal correctness for every possible or externally corrupted state;
- strong recovery after arbitrary resource-allocation exceptions;
- reference-model or differential-engine agreement;
- a standalone replay/evidence harness;
- exchange fidelity;
- benchmark evidence;
- latency characteristics;
- throughput characteristics;
- HFT capability;
- thread-safe concurrent matching;
- persistence, recovery or networking;
- production readiness; or
- exchange-grade suitability.

Those properties require separate architecture decisions and explicit qualification evidence.

---

# 21. M2B adversarial review questions

Before M2B may be frozen, the specification must answer all of the following without relying on unstated assumptions:

1. Can two active orders ever share an ID?
2. Can a zero-quantity order remain active?
3. Can a non-positive limit price enter active state?
4. What happens if an out-of-range `Side` value reaches command validation?
5. Can an order change side through modification?
6. Can an order be stored under the wrong price level?
7. What exactly establishes FIFO priority?
8. What is the initial sequence number?
9. Can `UINT64_MAX` be allocated?
10. What happens after `UINT64_MAX` has been allocated?
11. Can sequence allocation wrap?
12. Does a fully executed incoming order still consume an arrival sequence?
13. Can a locator refer to an inactive or wrong order?
14. Can a zero-quantity trade be emitted?
15. Can a BUY execute above its limit?
16. Can a SELL execute below its limit?
17. Why is the maker price the execution price?
18. How is quantity conservation established without overflow in the test oracle?
19. Which initial state, allocator state, command stream and configuration define determinism?
20. Under what preconditions is an uncrossed post-state guaranteed?
21. What happens if sequence allocation fails during modify?
22. Which invariants are only specified today and which are genuinely enforced?
23. Does active-lifetime `OrderId` reuse imply global historical uniqueness? It does not.

If any answer depends on an unstated assumption or contradicts `docs/MATCHING_SEMANTICS.md`, M2B is not ready to pass.
