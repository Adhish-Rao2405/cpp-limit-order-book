# Matching Semantics

## Status

Specification origin: **M2 — Domain Model + Formal Matching Contract + Invariants**

Current implementation status: **M3 — Deterministic Single-Writer Matching Core qualified**

This document defines the normative logical matching contract for the project.

M3 implements this contract in `MatchingEngine` at implementation-freeze commit
`41654e89229cf7742cd44a6c6e77b277d5a063b3`. The exact commit passed 74 tests in both Debug and Release
locally and in GitHub Actions run `35349811141`.

The implementation includes the active order books, locator index, matching loops, sequence allocator,
ordered trade output, modification/cancellation paths, deterministic snapshots and qualification-only
invariant observability described by ADR 0004.

This status does not claim a standalone replay/reference harness, benchmark harness, concurrency,
persistence/recovery, networking, performance characteristics, production readiness or exchange fidelity.

The governing rule remains:

> Specify correctness before implementing matching; claim only what explicit evidence supports.

---

## 1. Scope

The initial system models a deterministic, single-writer limit-order book.

Supported logical commands are:

- `NewOrder`
- `CancelOrder`
- `ModifyOrder`

The initial system supports limit orders only.

The following are deliberately outside this contract:

- market orders;
- stop orders;
- hidden or iceberg orders;
- pegged orders;
- auction behaviour;
- self-trade prevention;
- exchange-specific order attributes;
- time-in-force variants;
- multi-instrument matching;
- networking;
- persistence;
- recovery;
- exchange adapters;
- concurrency;
- benchmark or latency semantics.

This document specifies this project's behaviour and does not claim fidelity to
the rules of any real exchange.

---

## 2. Terminology

### Incoming / taker order

The order currently being processed against resting liquidity.

An accepted incoming order may:

1. execute against one or more resting counterparties;
2. be completely filled;
3. be partially filled and leave a positive residual;
4. execute nothing and rest in full.

### Resting / maker order

An active order already present in the book before the current matching
interaction.

The resting order supplies the execution price.

### Bid

A resting BUY order.

### Ask

A resting SELL order.

### Price-time priority

Resting liquidity is selected by:

1. better executable price;
2. earlier sequence number at equal price.

---

## 3. Domain values

### 3.1 Price

`Price` represents an integer number of ticks.

Conceptual underlying representation:

```text
std::int64_t
```

A valid limit price satisfies:

```text
price_ticks > 0
```

Zero and negative limit prices are invalid.

Floating-point values do not participate in order-book price ordering or
matching.

Any future conversion from external decimal prices must occur at a validation
boundary before matching-core use.

The tick-size configuration mechanism is outside M2.

### 3.2 Quantity

`Quantity` represents an integral number of units.

Conceptual underlying representation:

```text
std::uint64_t
```

A valid submitted or active remaining quantity satisfies:

```text
quantity > 0
```

Zero is not a valid active quantity.

Zero quantity is not an implicit cancellation instruction. Cancellation is
expressed through `CancelOrder`.

### 3.3 OrderId

Conceptual underlying representation:

```text
std::uint64_t
```

`OrderId` is an identity value and has no arithmetic meaning.

The M2 domain contract reserves no numeric sentinel value. In particular,
numeric value `0` is not inherently invalid.

At most one active order may exist for a particular `OrderId`.

This is active-lifetime uniqueness, not lifetime-global uniqueness. Once an
order has become inactive through cancellation or complete fill, reuse of the
same ID is permitted by this project-level contract.

A future external protocol may impose a stricter rule.

Because reuse is permitted, `OrderId` alone is not promised to be a globally
unique historical event key. Any later standalone audit format that requires
historical disambiguation must carry sufficient additional context.

### 3.4 Side

The logical domain is:

```cpp
enum class Side {
    Buy,
    Sell
};
```

Boolean side representation is not part of the contract.

The only valid logical side values are `Side::Buy` and `Side::Sell`.

C++ enumeration storage can be forced to contain an out-of-range underlying
value through an explicit cast or an unsafe external boundary. Such a value is
not a valid `Side` under this contract.

If an invalid side value reaches `NewOrder` command validation, the command is
rejected with:

```text
InvalidSide
```

M2C may instead make invalid side construction impossible at the public command
boundary, but it must not silently interpret an invalid underlying value as
BUY or SELL.

An order's side is immutable during its active lifetime.

### 3.5 SequenceNumber

Conceptual underlying representation:

```text
std::uint64_t
```

Sequence numbers are assigned internally by deterministic engine state.

They are not supplied by external commands.

Wall-clock time does not establish matching priority.

For equal-price resting orders:

```text
lower sequence number = earlier priority
```

The initial allocator state has sequence `1` as the first allocatable value.
Sequence `0` is not allocated as an arrival sequence by this engine contract.
Whether the C++ wrapper type can represent `0` is a separate M2C design decision.

Every accepted new order receives exactly one sequence number before matching
begins, even if it fully executes and never rests.

If an unfilled residual later rests, it retains that arrival sequence.

An accepted priority-losing modification receives exactly one fresh sequence,
even if its replacement fully executes and never rests.

Rejected commands consume no sequence.

---

## 4. Sequence exhaustion

Sequence allocation must never wrap.

`std::uint64_t` maximum is an allocatable sequence value. Once that value has
been allocated, the allocator is exhausted and no later command requiring a
fresh sequence may be accepted.

If a command requires a new sequence and no next representable sequence is
available, the command is rejected with:

```text
SequenceExhausted
```

The rejection occurs before state mutation.

Sequence exhaustion is therefore fail-closed.

A command that does not require a fresh sequence may still succeed when no
further sequence can be allocated. For example, a valid same-price quantity
reduction retains its existing sequence.

---

## 5. New order validity

A logical `NewOrder` contains:

```text
OrderId
Side
Price
Quantity
```

Acceptance requires:

```text
Price > 0
Quantity > 0
Side is exactly Buy or Sell
OrderId not currently active
fresh sequence available
```

A rejected new order causes no state mutation, emits no trade and consumes no
sequence.

Normative new-order rejection precedence is:

1. `InvalidPrice`
2. `InvalidQuantity`
3. `InvalidSide`
4. `DuplicateOrderId`
5. `SequenceExhausted`

The precedence is part of the contract rather than an accidental consequence
of implementation order.

---

## 6. BUY matching

For an incoming BUY limit order with limit `P`, select the lowest-priced
resting ask.

Execution is permitted while:

```text
resting_ask_price <= P
```

At an executable price level, the lowest sequence number executes first.

Matching continues until either:

- incoming remaining quantity becomes zero; or
- no executable resting ask remains.

---

## 7. SELL matching

For an incoming SELL limit order with limit `P`, select the highest-priced
resting bid.

Execution is permitted while:

```text
resting_bid_price >= P
```

At an executable price level, the lowest sequence number executes first.

Matching continues until either:

- incoming remaining quantity becomes zero; or
- no executable resting bid remains.

---

## 8. Execution price

Every trade executes at the resting / maker order's price:

```text
trade_price = maker_price
```

The incoming limit defines the maximum acceptable price for a BUY and the
minimum acceptable price for a SELL.

The incoming limit does not replace the resting price as the execution price.

---

## 9. Execution quantity

For the incoming order and selected resting counterparty:

```text
trade_quantity =
    min(incoming_remaining_quantity,
        resting_remaining_quantity)
```

Every emitted trade therefore satisfies:

```text
trade_quantity > 0
```

and cannot exceed either participant's remaining quantity immediately before
the trade.

---

## 10. Trade representation

ADR 0004 freezes the public M3 trade representation as:

```text
maker OrderId
taker OrderId
execution Price
execution Quantity
```

Accepted commands return an `ExecutionReport` containing ordered `Trade` values. Trades are emitted in
exact matching order.

The current contract does not define:

- a `TradeId`;
- timestamps;
- venue codes;
- fees; or
- settlement metadata.

---

## 11. Partial fills

### 11.1 Resting order partially consumed

If the incoming quantity is smaller than the selected resting quantity, the
resting order remains active with:

```text
new_resting_quantity =
    old_resting_quantity - trade_quantity
```

Its:

- `OrderId`;
- side;
- price;
- sequence

remain unchanged.

It therefore retains its queue priority.

### 11.2 Resting order completely filled

If a resting order's remaining quantity becomes zero:

- it immediately leaves active state;
- it no longer participates in matching;
- active-ID lookup must eventually cease resolving it.

No active zero-quantity order is permitted.

### 11.3 Incoming residual

If executable counterparties are exhausted while incoming quantity remains
positive, that positive residual rests at the incoming limit price.

The residual retains the sequence assigned when the incoming new order was
accepted.

---

## 12. Price priority

For resting BUY orders:

```text
higher price = better priority
```

For resting SELL orders:

```text
lower price = better priority
```

Price priority is evaluated before sequence priority.

A later order at a better price therefore has priority over an earlier order
at a worse price.

---

## 13. FIFO priority

Within one price:

```text
lower sequence number executes first
```

A partial fill does not change sequence.

A valid priority-retaining modification does not change sequence.

A priority-losing modification receives a fresh sequence.

---

## 14. Cancel semantics

`CancelOrder(OrderId)` removes the identified active order.

A successful cancellation:

- removes the order from active state;
- emits no trade;
- allocates no sequence.

Cancelling an inactive or unknown ID is rejected with:

```text
UnknownOrderId
```

A rejected cancellation leaves logical state unchanged.

---

## 15. Modify semantics

A modification identifies an existing active order and proposes:

```text
new Price
new remaining Quantity
```

The quantity supplied to `ModifyOrder` means **target remaining quantity**,
not historical/original submitted quantity.

This distinction is normative after partial fills.

Side modification is not permitted.

### 15.1 Same price and lower remaining quantity

If:

```text
new_price == current_price
and
0 < new_quantity < current_remaining_quantity
```

the modification is accepted and:

- retains the same `OrderId`;
- retains side;
- retains price;
- retains sequence;
- retains queue position;
- changes only remaining quantity.

This is a priority-retaining modification.

### 15.2 No-op modification

If both price and remaining quantity are unchanged, the command is rejected
with:

```text
InvalidModification
```

No sequence is consumed and no state changes.

### 15.3 Quantity increase

If:

```text
new_quantity > current_remaining_quantity
```

the order loses priority.

The operation is semantically equivalent to an atomic cancel-and-replacement:

1. validate the replacement completely;
2. establish that a fresh sequence is available;
3. remove the current active order;
4. create the replacement under the same `OrderId`;
5. assign a fresh sequence;
6. process the replacement using normal incoming-order matching semantics.

The priority loss is not itself a rejection.

### 15.4 Price change

Any price change loses priority.

The replacement retains the same `OrderId`, receives a fresh sequence and is
processed under normal incoming-order matching semantics.

A marketable price change may therefore execute against opposite-side resting
orders before any positive residual rests.

### 15.5 Price and quantity change

Any price change loses priority regardless of whether remaining quantity:

- increases;
- decreases;
- remains equal.

The replacement quantity is the new target remaining quantity.

### 15.6 Zero resulting quantity

A modification requesting:

```text
new_quantity == 0
```

is rejected with:

```text
InvalidQuantity
```

Explicit `CancelOrder` must be used for cancellation.

### 15.7 Unknown order

Modification of an inactive or unknown ID is rejected with:

```text
UnknownOrderId
```

### 15.8 Failure atomicity

All validation required to determine whether a modification can proceed occurs
before destructive mutation.

For a priority-losing modification this includes confirming fresh-sequence
availability.

If modification is rejected:

- the original order remains active;
- remaining quantity is unchanged;
- price is unchanged;
- sequence is unchanged;
- queue position is unchanged;
- no trade is emitted;
- no sequence is consumed.

---

## 16. Modify rejection precedence

Normative precedence is:

1. `InvalidPrice`
2. `InvalidQuantity`
3. `UnknownOrderId`
4. `InvalidModification`
5. `SequenceExhausted`, when the valid modification requires requeueing

A priority-retaining quantity reduction does not require sequence allocation.

---

## 17. Expected domain rejection

Expected domain failure is represented by explicit machine-testable result values.

The current C++ result boundary is `DomainResult<T> = std::variant<T, DomainError>` as established by
ADR 0003 and used by the M3 matching API.

Logical rejection categories are:

```text
InvalidPrice
InvalidQuantity
InvalidSide
DuplicateOrderId
UnknownOrderId
SequenceExhausted
InvalidModification
```

Free-form text is not the primary error contract.

Expected domain rejection does not use exception-based control flow. Internal invariant violations or
resource-allocation failures remain outside the expected-domain-error contract.

---

## 18. Rejection atomicity

For every rejected command:

```text
logical_post_state == logical_pre_state
```

Additionally:

```text
no trade is emitted
no sequence is consumed
```

M2 defines no exception to this rule.

---

## 19. Determinism

Given:

- identical valid initial logical state, including sequence-allocator state;
- identical semantic configuration;
- identical ordered command stream;

processing must produce identical:

- acceptance/rejection outcomes;
- rejection categories;
- sequence evolution;
- ordered trade events;
- active orders;
- remaining quantities;
- prices;
- queue ordering;
- final logical state.

Wall-clock timing and thread scheduling are not matching authority.

---

## 20. Quantity conservation

For an accepted incoming order with original quantity `Q0`, let:

```text
T = mathematical sum of all quantities executed by that incoming order
R = final resting residual, or 0 if no residual rests
```

Then:

```text
Q0 = T + R
```

Matching may transfer quantity between active state and trade output, but may
not create or destroy quantity.

Future tests must not attempt to prove this invariant using unchecked
fixed-width accumulation that can itself silently overflow.

---

## 21. Post-processing quiescence

Precondition:

- processing begins from an invariant-compliant resting state; and
- that resting state contains no executable bid/ask cross.

After an accepted command is processed completely to quiescence, there must
not exist active bid `b` and active ask `a` satisfying:

```text
b.price >= a.price
```

Equivalently, when both sides are non-empty:

```text
best_bid < best_ask
```

This does not claim that the engine repairs arbitrary externally corrupted
state.

---

## 22. Deterministic examples

## Example 1 — Non-crossing BUY rests

Initial state:

```text
empty
```

Command:

```text
NewOrder(id=1, side=Buy, price=100, quantity=10)
```

Result:

```text
accepted
sequence=1
trades=none
```

Final active state:

```text
id=1 Buy price=100 quantity=10 sequence=1
```

---

## Example 2 — Non-crossing SELL rests

Initial state:

```text
id=1 Buy price=100 quantity=10 sequence=1
```

Command:

```text
NewOrder(id=2, side=Sell, price=105, quantity=4)
```

Result:

```text
accepted
sequence=2
trades=none
```

Final state:

```text
id=1 Buy  price=100 quantity=10 sequence=1
id=2 Sell price=105 quantity=4  sequence=2
```

---

## Example 3 — BUY crosses one ask

Initial state:

```text
id=10 Sell price=101 quantity=5 sequence=1
```

Command:

```text
NewOrder(id=20, side=Buy, price=103, quantity=5)
```

Trade:

```text
maker=10
taker=20
price=101
quantity=5
```

Final state:

```text
empty
```

The execution price is the resting ask price `101`, not incoming limit `103`.

---

## Example 4 — SELL crosses one bid

Initial state:

```text
id=10 Buy price=100 quantity=7 sequence=1
```

Command:

```text
NewOrder(id=20, side=Sell, price=98, quantity=7)
```

Trade:

```text
maker=10
taker=20
price=100
quantity=7
```

Final state:

```text
empty
```

---

## Example 5 — Resting order partially consumed

Initial state:

```text
id=10 Sell price=100 quantity=10 sequence=1
```

Command:

```text
NewOrder(id=20, side=Buy, price=100, quantity=4)
```

Trade:

```text
maker=10
taker=20
price=100
quantity=4
```

Final state:

```text
id=10 Sell price=100 quantity=6 sequence=1
```

The resting order retains priority.

---

## Example 6 — Multiple resting orders consumed

Initial state:

```text
id=10 Sell price=100 quantity=3 sequence=1
id=11 Sell price=101 quantity=4 sequence=2
id=12 Sell price=102 quantity=8 sequence=3
```

Command:

```text
NewOrder(id=20, side=Buy, price=101, quantity=6)
```

Trades:

```text
1. maker=10 taker=20 price=100 quantity=3
2. maker=11 taker=20 price=101 quantity=3
```

Final state:

```text
id=11 Sell price=101 quantity=1 sequence=2
id=12 Sell price=102 quantity=8 sequence=3
```

---

## Example 7 — Equal-price FIFO

Initial state:

```text
id=10 Sell price=100 quantity=5 sequence=1
id=11 Sell price=100 quantity=5 sequence=2
```

Command:

```text
NewOrder(id=20, side=Buy, price=100, quantity=6)
```

Trades:

```text
1. maker=10 taker=20 price=100 quantity=5
2. maker=11 taker=20 price=100 quantity=1
```

Final state:

```text
id=11 Sell price=100 quantity=4 sequence=2
```

---

## Example 8 — Better price beats earlier sequence

Initial state:

```text
id=10 Sell price=101 quantity=5 sequence=1
id=11 Sell price=100 quantity=5 sequence=2
```

Command:

```text
NewOrder(id=20, side=Buy, price=101, quantity=5)
```

Trade:

```text
maker=11
taker=20
price=100
quantity=5
```

The later order executes first because `100` is the better ask price.

---

## Example 9 — Duplicate active ID

Initial state:

```text
id=7 Buy price=100 quantity=5 sequence=1
```

Command:

```text
NewOrder(id=7, side=Sell, price=110, quantity=2)
```

Result:

```text
DuplicateOrderId
```

State and sequence allocator remain unchanged.

---

## Example 10 — Zero quantity

Command:

```text
NewOrder(id=1, side=Buy, price=100, quantity=0)
```

Result:

```text
InvalidQuantity
```

No state mutation occurs.

---

## Example 11 — Invalid price

Command:

```text
NewOrder(id=1, side=Buy, price=0, quantity=10)
```

Result:

```text
InvalidPrice
```

No state mutation occurs.

---

## Example 12 — Unknown cancellation

Initial state:

```text
id=1 Buy price=100 quantity=10 sequence=1
```

Command:

```text
CancelOrder(id=999)
```

Result:

```text
UnknownOrderId
```

State remains unchanged.

---

## Example 13 — Quantity reduction retains priority

Initial state:

```text
id=1 Buy price=100 quantity=10 sequence=1
id=2 Buy price=100 quantity=10 sequence=2
```

Command:

```text
ModifyOrder(id=1, price=100, quantity=6)
```

Final queue:

```text
id=1 Buy price=100 quantity=6  sequence=1
id=2 Buy price=100 quantity=10 sequence=2
```

No fresh sequence is allocated.

---

## Example 14 — Quantity increase loses priority

Initial state:

```text
id=1 Buy price=100 quantity=5 sequence=1
id=2 Buy price=100 quantity=5 sequence=2
```

Command:

```text
ModifyOrder(id=1, price=100, quantity=8)
```

Assuming fresh sequence `3`, final queue is:

```text
id=2 Buy price=100 quantity=5 sequence=2
id=1 Buy price=100 quantity=8 sequence=3
```

The same ID is retained but priority is lost.

---

## Example 15 — Price change may execute

Initial state:

```text
id=1  Buy  price=99  quantity=5 sequence=1
id=10 Sell price=101 quantity=3 sequence=2
```

Command:

```text
ModifyOrder(id=1, price=102, quantity=5)
```

Assuming fresh sequence `3`, the replacement BUY is marketable.

Trade:

```text
maker=10
taker=1
price=101
quantity=3
```

Residual:

```text
id=1 Buy price=102 quantity=2 sequence=3
```

---

## Example 16 — Modify after partial fill uses remaining quantity

Suppose order `1` originally submitted quantity `10` but now has:

```text
id=1 Buy price=100 quantity=6 sequence=1
```

after `4` units have executed.

Command:

```text
ModifyOrder(id=1, price=100, quantity=3)
```

The requested `3` means:

```text
target remaining quantity = 3
```

The same-price reduction retains sequence `1`.

---

## Example 17 — Invalid side is rejected

Conceptually, if an unsafe boundary supplies an underlying side value that is
neither `Buy` nor `Sell`:

```text
NewOrder(id=1, side=invalid, price=100, quantity=10)
```

the result is:

```text
InvalidSide
```

No state changes, no trade is emitted and no sequence is consumed.

---

## 23. Design decisions resolved after M2B

ADR 0003 and ADR 0004 subsequently resolved the following M2B-deferred decisions:

- public domain header layout;
- the typed C++ result boundary;
- matching-core public API;
- side-book and price-level storage;
- active-order locator representation;
- deterministic matching-loop structure; and
- internal sequence-allocation state and exhaustion behaviour.

The following remain deliberately deferred:

- a standalone reference/differential engine;
- a standalone replay/evidence harness and durable evidence format;
- benchmark workload and result formats;
- custom memory-allocation or container optimisations;
- concurrency;
- persistence and recovery;
- networking and exchange adapters; and
- performance claims.

---

## 24. Claim boundary

After M3 it is permissible to claim that the project has:

- a documented normative matching contract;
- an implemented deterministic single-writer matching core;
- implemented price-time FIFO matching, cancellation and modification semantics;
- fail-closed sequence exhaustion with no wrap;
- deterministic snapshots and qualification-only invariant checking; and
- explicit local and Windows/MSVC CI qualification for the M3 implementation freeze.

The evidence does **not** establish:

- universal proof over every possible command stream or corrupted state;
- reference-engine agreement;
- a standalone replay/evidence system;
- low latency or high throughput;
- HFT capability;
- concurrent matching;
- persistence or recovery;
- production readiness;
- fidelity to a real exchange; or
- exchange-grade behaviour.
