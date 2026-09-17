# ADR 0003: Use strong domain types with explicit validation boundaries

- Status: Accepted
- Date: 2026-09-17

## Context

M2B defines the normative matching contract before matching implementation. The C++ domain model must now
encode that contract without introducing an order book, matching loop, locator, benchmark harness, allocator
strategy, concurrency model, networking layer, or performance claim.

The project currently exposes only the `lob` public include namespace and has no existing order-domain API.
This gives M2 a clean opportunity to make invalid scalar states difficult to construct and to prevent accidental
mixing of identifiers, prices, quantities, and sequence numbers.

The design must remain C++20. `std::expected` is therefore unavailable as a standard C++20 facility, and M2
will not add a third-party result dependency merely for domain construction.

This ADR refines ADR 0001 (integer price ticks) and ADR 0002 (single-writer deterministic core). It must remain
consistent with `docs/MATCHING_SEMANTICS.md` and `docs/INVARIANTS.md`.

## Decision

### 1. Namespace and public header layout

All M2 domain types live in namespace:

```cpp
lob
```

M2D will add exactly these public headers:

```text
include/lob/domain/price.hpp
include/lob/domain/quantity.hpp
include/lob/domain/order_id.hpp
include/lob/domain/sequence_number.hpp
include/lob/domain/side.hpp
include/lob/domain/error.hpp
include/lob/domain/commands.hpp
```

No umbrella `types.hpp` header is introduced in M2.

Each header must be self-contained: it includes every standard/project header required by its own declarations
and must not depend on accidental transitive includes.

The M2D primitives are header-only. M2D therefore does not require a new `.cpp` file and does not modify
`CMakeLists.txt`. M2E may later modify the test target to add genuine domain tests.

This header-only decision is a scope/minimality decision, not a performance claim.

### 2. Shared implementation rules

For every class type introduced by M2D:

- no default constructor is exposed unless this ADR explicitly permits one;
- no implicit conversion to the underlying integer representation is exposed;
- no implicit construction from a different numeric domain type is exposed;
- copy/move operations use normal compiler-generated value semantics;
- expected validation paths are `noexcept`;
- public accessors are `[[nodiscard]]`, `constexpr`, and `noexcept` where specified below.

M2 does not add generic arithmetic merely because the underlying representation is numeric.

### 3. Price

`Price` is a strong class type with underlying representation:

```cpp
std::int64_t
```

The underlying value is an integer count of ticks.

A valid `Price` satisfies:

```text
ticks > 0
```

`price.hpp` includes the standard headers required for:

```text
std::int64_t
std::optional
three-way comparison
```

The exact M2D public API is:

```cpp
class Price final {
public:
    using rep = std::int64_t;

    [[nodiscard]] static constexpr std::optional<Price>
    from_ticks(rep ticks) noexcept;

    [[nodiscard]] constexpr rep ticks() const noexcept;

    friend constexpr bool operator==(Price, Price) noexcept = default;
    friend constexpr auto operator<=>(Price, Price) noexcept = default;

private:
    explicit constexpr Price(rep ticks) noexcept;

    rep ticks_;
};
```

`from_ticks` returns `std::nullopt` for:

```text
ticks <= 0
```

and returns a `Price` for:

```text
ticks > 0
```

There is no public default constructor.

`Price` does not provide:

- implicit integer construction;
- implicit integer conversion;
- `+`;
- `-`;
- `*`;
- `/`;
- `%`;
- `++`;
- `--`.

Natural equality and ordering are permitted because price comparison has direct domain meaning.

### 4. Quantity

`Quantity` is a strong class type with underlying representation:

```cpp
std::uint64_t
```

A valid `Quantity` satisfies:

```text
units > 0
```

The exact M2D public API is:

```cpp
class Quantity final {
public:
    using rep = std::uint64_t;

    [[nodiscard]] static constexpr std::optional<Quantity>
    from_units(rep units) noexcept;

    [[nodiscard]] constexpr rep units() const noexcept;

    friend constexpr bool operator==(Quantity, Quantity) noexcept = default;
    friend constexpr auto operator<=>(Quantity, Quantity) noexcept = default;

private:
    explicit constexpr Quantity(rep units) noexcept;

    rep units_;
};
```

`from_units(0)` returns `std::nullopt`.

There is no public default constructor.

M2 does not add general public quantity arithmetic:

- `+`;
- `-`;
- `*`;
- `/`;
- `%`;
- `++`;
- `--`.

Future matching code will require quantity reduction. That operation must be introduced deliberately with
underflow and quantity-conservation evidence rather than as convenience arithmetic in this scalar type.

Natural equality and ordering are permitted because matching requires quantity comparison.

`Quantity::rep` is the canonical already-integer domain representation. This factory is not a protocol parser.
If an external signed or textual value is later accepted, that future boundary must reject negatives and
conversion overflow before converting to `std::uint64_t`; M2 must not claim that information lost by an earlier
unsafe cast can be recovered here.

### 5. OrderId

`OrderId` is a strong class type with underlying representation:

```cpp
std::uint64_t
```

Every `std::uint64_t` value, including `0`, is valid under the M2 contract.

The exact M2D public API is:

```cpp
class OrderId final {
public:
    using rep = std::uint64_t;

    explicit constexpr OrderId(rep value) noexcept;

    [[nodiscard]] constexpr rep value() const noexcept;

    friend constexpr bool operator==(OrderId, OrderId) noexcept = default;

private:
    rep value_;
};
```

There is no public default constructor.

No numeric ordering operator is provided because numeric `OrderId` ordering has no matching meaning.

No arithmetic operator is provided.

The type does not encode active-lifetime uniqueness. That property requires future book state.

The type does not encode lifetime-global uniqueness because M2B explicitly permits reuse after the previous
order with that ID becomes inactive.

### 6. SequenceNumber

`SequenceNumber` is a strong class type with underlying representation:

```cpp
std::uint64_t
```

A representationally valid allocated sequence satisfies:

```text
value >= 1
```

Sequence `0` is invalid as an allocated `SequenceNumber`.

The exact M2D public API is:

```cpp
class SequenceNumber final {
public:
    using rep = std::uint64_t;

    [[nodiscard]] static constexpr std::optional<SequenceNumber>
    from_value(rep value) noexcept;

    [[nodiscard]] constexpr rep value() const noexcept;

    friend constexpr bool operator==(SequenceNumber, SequenceNumber) noexcept = default;
    friend constexpr auto operator<=>(SequenceNumber, SequenceNumber) noexcept = default;

private:
    explicit constexpr SequenceNumber(rep value) noexcept;

    rep value_;
};
```

`from_value(0)` returns `std::nullopt`.

There is no public default constructor.

The type enforces only scalar validity. It does not claim allocator authority.

The following remain future allocator/engine responsibilities:

- first allocation is `1`;
- monotonic allocation;
- no reuse by one continuing allocator state;
- `UINT64_MAX` may be allocated once;
- allocation after `UINT64_MAX` yields `SequenceExhausted`;
- no wrap to `0`;
- rejected commands do not consume a sequence;
- priority-retaining modify does not consume a sequence;
- accepted new orders and priority-losing modifies consume exactly one fresh sequence.

No public sequence arithmetic or increment/decrement operator is provided.

Natural equality and ordering are permitted because lower sequence establishes earlier equal-price priority.

### 7. Side

`Side` is exactly:

```cpp
enum class Side : std::uint8_t {
    Buy = 0,
    Sell = 1
};
```

The only valid logical values are `Side::Buy` and `Side::Sell`.

`side.hpp` provides exactly:

```cpp
[[nodiscard]] constexpr bool is_valid(Side side) noexcept;
```

Its logical definition is:

```text
side == Side::Buy OR side == Side::Sell
```

C++ permits an explicit cast or unsafe external boundary to place an unnamed underlying value in fixed-underlying
enum storage. Such a value is not a valid logical side.

An invalid side value must never be silently mapped to BUY or SELL.

At the `NewOrder` command-validation boundary it maps to:

```text
InvalidSide
```

`Side` has equality semantics only. M2 introduces no side ordering.

### 8. DomainError and DomainResult

`error.hpp` defines exactly:

```cpp
enum class DomainError {
    InvalidPrice,
    InvalidQuantity,
    InvalidSide,
    DuplicateOrderId,
    UnknownOrderId,
    SequenceExhausted,
    InvalidModification
};
```

`DomainError` is the primary machine-testable rejection identity.

`error.hpp` also defines the M2 C++20 result alias:

```cpp
template <typename T>
using DomainResult = std::variant<T, DomainError>;
```

M2 does not add a custom `Result<T, E>` class and does not add a third-party expected/result dependency.

The M2 alternatives used with `DomainResult` have non-throwing ordinary value operations. Expected rejection is
represented by the `DomainError` alternative rather than by exceptions.

Consumers must inspect the active alternative through normal `std::variant` facilities. Deliberately requesting
the wrong alternative with a throwing accessor is caller misuse and is not the domain rejection mechanism.

Free-form diagnostic strings may be added later, but they are not authoritative error identity.

### 9. NewOrder

`NewOrder` is a validated command object.

Its logical data is:

```text
OrderId
Side
Price
Quantity
```

It is not an aggregate and has no public constructor that can bypass command validation.

The exact M2D public API is:

```cpp
class NewOrder final {
public:
    [[nodiscard]] static constexpr DomainResult<NewOrder> create(
        OrderId order_id,
        Side side,
        Price::rep price_ticks,
        Quantity::rep quantity_units) noexcept;

    [[nodiscard]] constexpr OrderId order_id() const noexcept;
    [[nodiscard]] constexpr Side side() const noexcept;
    [[nodiscard]] constexpr Price price() const noexcept;
    [[nodiscard]] constexpr Quantity quantity() const noexcept;

private:
    constexpr NewOrder(
        OrderId order_id,
        Side side,
        Price price,
        Quantity quantity) noexcept;

    OrderId order_id_;
    Side side_;
    Price price_;
    Quantity quantity_;
};
```

There is no public default constructor.

The factory performs scalar validation in exactly this order:

```text
1. Price::from_ticks
   failure -> InvalidPrice

2. Quantity::from_units
   failure -> InvalidQuantity

3. is_valid(side)
   false -> InvalidSide
```

Only after all three checks succeed may the validated `NewOrder` be created.

The factory does not check:

```text
DuplicateOrderId
SequenceExhausted
```

because those require future engine state.

A future engine receiving a validated `NewOrder` continues the normative M2B precedence with:

```text
4. DuplicateOrderId
5. SequenceExhausted
```

`SequenceNumber` is not a `NewOrder` field and is never externally supplied.

### 10. CancelOrder

`CancelOrder` contains exactly:

```text
OrderId
```

All `OrderId` values are representationally valid, so no scalar rejection is possible during command
construction.

The exact M2D public API is:

```cpp
class CancelOrder final {
public:
    explicit constexpr CancelOrder(OrderId order_id) noexcept;

    [[nodiscard]] constexpr OrderId order_id() const noexcept;

private:
    OrderId order_id_;
};
```

There is no public default constructor.

`CancelOrder` does not check `UnknownOrderId`; that rejection requires future active-order state.

### 11. ModifyOrder

`ModifyOrder` is a validated command object containing:

```text
OrderId
new Price
new remaining Quantity
```

It contains no side field because side is immutable.

It is not an aggregate and has no public constructor that can bypass scalar validation.

The exact M2D public API is:

```cpp
class ModifyOrder final {
public:
    [[nodiscard]] static constexpr DomainResult<ModifyOrder> create(
        OrderId order_id,
        Price::rep new_price_ticks,
        Quantity::rep new_quantity_units) noexcept;

    [[nodiscard]] constexpr OrderId order_id() const noexcept;
    [[nodiscard]] constexpr Price price() const noexcept;
    [[nodiscard]] constexpr Quantity quantity() const noexcept;

private:
    constexpr ModifyOrder(
        OrderId order_id,
        Price price,
        Quantity quantity) noexcept;

    OrderId order_id_;
    Price price_;
    Quantity quantity_;
};
```

There is no public default constructor.

The quantity accessor represents target remaining quantity, not original submitted quantity.

The factory performs scalar validation in exactly this order:

```text
1. Price::from_ticks
   failure -> InvalidPrice

2. Quantity::from_units
   failure -> InvalidQuantity
```

The factory does not check:

```text
UnknownOrderId
InvalidModification
SequenceExhausted
```

because those depend on future active order and allocator state.

A future engine continues the M2B precedence with:

```text
3. UnknownOrderId
4. InvalidModification
5. SequenceExhausted
```

### 12. Header dependency direction

The intended dependency direction is:

```text
price.hpp
quantity.hpp
order_id.hpp
sequence_number.hpp
side.hpp
        |
        v
error.hpp
        |
        v
commands.hpp
```

More precisely:

- each scalar type header depends only on required standard headers;
- `side.hpp` depends only on required standard headers;
- `error.hpp` depends on the standard library required for `DomainError` and `DomainResult`;
- `commands.hpp` includes the scalar/error headers it directly uses.

No domain header includes `version.hpp`.

No domain header includes a test header.

No domain header introduces a dependency on book, matching, benchmark, networking, persistence, or concurrency
code.

### 13. Trade representation

The M2 semantic shape of a future trade remains:

```text
maker OrderId
taker OrderId
Price
Quantity
```

All price and quantity members must use validated strong types.

`Trade` is not implemented in M2D.

Trade construction is an internal future matching concern, not an untrusted external-input boundary. Constructor
visibility and any additional invariant enforcement will be frozen when matching output is implemented.

M2 does not introduce:

- `TradeId`;
- timestamps;
- venue codes;
- fees;
- settlement fields.

### 14. Active/resting order representation

M2C deliberately does not introduce a concrete public `RestingOrder`.

A future active/resting representation will logically require:

```text
OrderId
Side
Price
remaining Quantity
SequenceNumber
```

but ownership, mutability, locator stability, queue linkage, and price-level membership are order-book design
decisions.

Freezing a concrete mutable resting-order class during M2 would prematurely constrain later container and
locator architecture.

Therefore:

```text
logical shape = specified
concrete RestingOrder type = deferred
```

### 15. Invalid-state strategy

The M2 domain model follows these rules:

- `Price` cannot represent non-positive prices through its supported construction API.
- `Quantity` cannot represent zero through its supported construction API.
- `SequenceNumber` cannot represent zero through its supported construction API.
- `OrderId` accepts every `std::uint64_t` value because that is the domain contract.
- `Side` remains an enum, but every untrusted command boundary validates it explicitly.
- `NewOrder` cannot be created through its supported API with invalid price, quantity, or side.
- `ModifyOrder` cannot be created through its supported API with invalid price or quantity.
- `CancelOrder` contains only a representationally valid `OrderId`.
- state-dependent invariants are not falsely claimed to be encoded in scalar types.

The goal is not to claim that every future book invariant is encoded by the C++ type system. Each invariant must
live at the narrowest boundary that can actually enforce it.

### 16. Exception policy

All M2 scalar construction and expected command validation paths are non-throwing.

Expected invalid scalar input is represented by:

```text
std::optional
```

because each scalar factory owns one validation category.

Expected invalid command input requiring a typed reason is represented by:

```text
DomainResult<T>
```

Expected domain rejection does not use exception-based control flow.

This ADR does not make a project-wide claim that no C++ operation can ever throw. The non-throwing contract is
limited to these domain construction and expected-validation paths.

### 17. Comparison policy

M2 permits only comparisons with actual domain meaning:

```text
Price          equality + ordering
Quantity       equality + ordering
OrderId        equality only
SequenceNumber equality + ordering
Side           equality only
DomainError    equality
```

Numeric `OrderId` ordering is intentionally absent.

No cross-type comparison is introduced.

M2 does not add ordering to command objects.

### 18. Conversion policy

No strong domain type provides implicit conversion to or from its underlying integer representation.

Raw accessors are explicit and named:

```text
Price::ticks()
Quantity::units()
OrderId::value()
SequenceNumber::value()
```

These accessors support deterministic diagnostics, future serialization boundaries, and tests without weakening
type separation through implicit conversion.

External decimal, textual, signed-to-unsigned, or protocol conversion is outside M2D. Future conversion code must
perform range and sign checks before values are narrowed into the canonical raw representation.

### 19. Hashing, formatting and streaming

M2 does not add:

- `std::hash` specializations;
- `operator<<`;
- formatter specializations;
- generic `to_string`;
- generic string parsing.

Those capabilities are introduced only when a real container, diagnostic surface, test requirement, or protocol
boundary justifies them.

### 20. Performance and representation claims

The strong types are small value abstractions, but M2 makes no claim about:

- zero-cost abstraction;
- object size;
- ABI layout;
- cache behaviour;
- latency;
- throughput;
- allocation behaviour.

M2 does not add `sizeof` assertions merely to manufacture a performance claim.

Performance evidence belongs to later benchmark milestones.

### 21. Exact M2D implementation boundary

M2D may add only:

```text
include/lob/domain/price.hpp
include/lob/domain/quantity.hpp
include/lob/domain/order_id.hpp
include/lob/domain/sequence_number.hpp
include/lob/domain/side.hpp
include/lob/domain/error.hpp
include/lob/domain/commands.hpp
```

M2D implements exactly:

```text
Price
Quantity
OrderId
SequenceNumber
Side
is_valid(Side)
DomainError
DomainResult<T>
NewOrder
CancelOrder
ModifyOrder
```

M2D does not modify:

```text
CMakeLists.txt
CMakePresets.json
src/
tests/
.github/
cmake/
```

M2D must not implement:

- a production order book;
- price-level containers;
- active-ID locator structures;
- matching loops;
- sequence allocator state;
- trade matching;
- cancellation against book state;
- modification against book state;
- reference engines;
- benchmark harnesses;
- allocators or pools;
- concurrency primitives;
- networking;
- protocol parsing;
- persistence;
- exchange adapters.

### 22. M2E qualification boundary

M2E will add genuine tests for only the properties owned by the implemented M2 types.

Required test categories include:

- positive `Price` accepted;
- zero `Price` rejected;
- negative `Price` rejected;
- positive `Quantity` accepted;
- zero `Quantity` rejected;
- `OrderId{0}` accepted;
- maximum `OrderId` representationally accepted;
- positive `SequenceNumber` accepted;
- zero `SequenceNumber` rejected;
- `Side::Buy` valid;
- `Side::Sell` valid;
- unnamed underlying side value invalid;
- invalid side maps to `InvalidSide` through `NewOrder::create`;
- `NewOrder` rejects invalid price before invalid quantity or side;
- `NewOrder` rejects invalid quantity before invalid side;
- `ModifyOrder` rejects invalid price before invalid quantity;
- validated command accessors expose the exact typed values supplied after validation;
- no domain class is publicly default-constructible;
- raw integer values are not implicitly convertible to `Price`, `Quantity`, or `SequenceNumber`;
- `Price`, `Quantity`, `OrderId`, and `SequenceNumber` are distinct C++ types;
- expected scalar and command validation operations are `noexcept`.

Compile-time type-trait assertions should be used where they prove API properties more directly than runtime
tests.

M2E must not simulate or duplicate a matching engine merely to manufacture coverage.

### 23. Explicit deferrals

The following remain deliberately unresolved after M2C:

```text
Trade concrete API
RestingOrder concrete API
book ownership model
price-level container type
active-ID locator type
sequence allocator class
matching-loop structure
trade collection/output type
hashing policy
formatting policy
external parser/protocol boundary
benchmark representation
allocation strategy
concurrency strategy
```

These are not omissions from the M2D implementation. They belong to later design gates.

## Consequences

The type system prevents accidental interchange of price, quantity, identifiers, and sequence numbers through
the supported API.

Invalid scalar prices, quantities, and allocated sequence values are rejected before they become validated
domain objects.

The command factories preserve the scalar portion of deterministic M2B rejection precedence without forcing
invalid scalar states into future matching code.

The architecture now gives M2D exact constructor, factory, accessor, comparison, conversion, and header
boundaries rather than leaving those decisions to implementation.

Some invariants necessarily remain state-dependent. Active ID uniqueness, unknown-order detection, sequence
allocation monotonicity, queue priority, locator integrity, quantity conservation across actual matching, and
uncrossed post-state cannot honestly be claimed by scalar types alone.

The design adds seven small public headers, avoids a custom result framework, and avoids premature hashing,
generic arithmetic, matching state, or order-book container architecture.

This decision does not establish a working order book, matching correctness, runtime book invariant enforcement,
latency performance, production readiness, or exchange fidelity.
