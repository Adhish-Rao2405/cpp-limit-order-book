# Domain and Matching Invariants

## Status

Milestone: **M2 — Domain Model + Formal Matching Contract + Invariants**

Subgate: **M2B — Formal Semantic Specification**

This document defines logical invariants that future implementations must preserve.

The existence of an invariant in this document does **not** mean runtime enforcement already exists.

M2 distinguishes:

1. specification;
2. domain-type enforcement;
3. order-book enforcement;
4. matching-engine enforcement;
5. qualification evidence.

Claims must correspond to the strongest stage actually completed.

The matching semantics in `docs/MATCHING_SEMANTICS.md` are normative and this document must remain consistent with them.

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

At M2B, all invariants below are **SPECIFIED**. Some scalar portions may later become domain-enforceable during M2 implementation.

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

| Invariant | M2B | M2 domain types | Future book | Future matcher | Qualification required |
| --- | --- | --- | --- | --- | --- |
| I1 Active ID uniqueness | Specified | No | Yes | Indirect | Yes |
| I2 Positive active quantity | Specified | Scalar portion | Yes | Yes | Yes |
| I3 Valid resting price | Specified | Scalar portion | Yes | Yes | Yes |
| I4 Side consistency | Specified | Partial / boundary validation | Yes | Yes | Yes |
| I5 Price-level consistency | Specified | No | Yes | Indirect | Yes |
| I6 FIFO/sequence consistency | Specified | Partial | Yes | Yes | Yes |
| I7 Locator integrity | Specified | No | Yes | Indirect | Yes |
| I8 Positive trade quantity | Specified | Partial | No | Yes | Yes |
| I9 Matching price validity | Specified | No | No | Yes | Yes |
| I10 Resting-price execution | Specified | No | No | Yes | Yes |
| I11 Quantity conservation | Specified | No | Partial | Yes | Yes |
| I12 Determinism | Specified | No | Partial | Yes | Yes |
| I13 No executable cross | Specified | No | Partial | Yes | Yes |

“Scalar portion” means only that a strong scalar type may prevent invalid individual values.

“Partial” means some supporting representation or state may exist without establishing the complete invariant.

Neither term establishes runtime matching correctness.

---

# 19. Specification versus runtime checking

An invariant may be preserved structurally without a dedicated runtime assertion.

M2B does not require a future implementation to perform an expensive whole-book invariant scan after every command.

Instead, later milestones must establish:

1. which invariants are enforced by construction;
2. which invariants are checked directly;
3. which invariants are established through targeted tests;
4. which invariants are established through reference/differential testing;
5. which checks, if any, are debug-only or qualification-only.

No performance-oriented omission is permitted to weaken correctness evidence silently.

---

# 20. Non-claims

The existence of this document does not establish:

- a working order book;
- matching correctness;
- runtime invariant checking;
- reference-model agreement;
- exchange fidelity;
- benchmark evidence;
- latency characteristics;
- throughput characteristics;
- HFT capability;
- production readiness;
- exchange-grade suitability.

These claims require later implementation and explicit qualification gates.

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
