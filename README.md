# cpp-limit-order-book

`cpp-limit-order-book` is a greenfield C++20 limit-order-book and matching-engine engineering project.

## Current status

Milestone M3 implements and qualifies the deterministic single-writer matching core.

The M3 implementation freeze is commit:

~~~text
41654e89229cf7742cd44a6c6e77b277d5a063b3
~~~

The repository currently provides:

- a C++20 `lob_core` static library target;
- strong domain types for price, quantity, order ID, sequence number and side;
- validated `NewOrder`, `CancelOrder` and `ModifyOrder` command boundaries;
- a deterministic single-writer `MatchingEngine`;
- price-time priority with integer-tick prices and FIFO ordering within a price level;
- maker-price execution and ordered `Trade` output;
- active-order lookup with typed bid/ask locators;
- cancellation and modification semantics, including priority-retaining reductions and
  priority-losing replacements;
- a fail-closed monotonic sequence allocator with explicit exhaustion and no wrap;
- deterministic book snapshots and qualification-only invariant observability;
- target-scoped compiler warnings with warnings treated as errors for first-party code;
- Debug and Release CMake/Ninja presets;
- GoogleTest/CTest integration; and
- Windows/MSVC GitHub Actions qualification.

At the M3 implementation freeze, the test inventory is 74 tests. The exact implementation commit passed
all 74 tests in both Debug and Release locally and in GitHub Actions run `35349811141`.

A separate `BUILD_TESTING=OFF` Release build also passed during local M3 qualification, with the
matching-engine qualification macro absent from the production compile commands.

## Evidence and non-claims

The M3 evidence supports the implemented matching semantics and the tested deterministic state transitions
for the qualified Windows/MSVC configurations.

The repository does **not** currently claim:

- low latency or high throughput;
- any benchmark or profiling result;
- HFT, production-grade or exchange-grade suitability;
- fidelity to the rules of any real exchange;
- reference-model or differential-engine agreement;
- a standalone replay/evidence harness;
- persistence, recovery or networking;
- concurrent matching or thread-safe engine access; or
- cross-platform qualification beyond environments actually tested.

Deterministic replay behaviour has been exercised by qualification tests, but a standalone replay/evidence
harness is deliberately deferred to a later milestone. Performance claims remain prohibited until a
reproducible benchmark baseline exists.

## Build and test

The checked-in presets require CMake 3.25 or newer and use out-of-source Ninja builds.

Debug:

~~~powershell
cmake --preset debug --fresh
cmake --build --preset debug
ctest --preset debug --output-on-failure
~~~

Release:

~~~powershell
cmake --preset release --fresh
cmake --build --preset release
ctest --preset release --output-on-failure
~~~

The current qualified environment uses x64 MSVC. GitHub CI exercises Windows/MSVC Debug and Release
configurations.

## Dependency provenance

GoogleTest is fetched only when testing is enabled.

M1 pins GoogleTest v1.18.0 by release archive and verifies:

~~~text
SHA256=6e3191c1455468b3fc35a417fb565c1c5071aee1b7e7f85e30cf48a98d37d8b5
~~~

A dependency hash mismatch is a configuration failure and must not be bypassed.

## Design records

- [Architecture](docs/ARCHITECTURE.md)
- [Matching semantics](docs/MATCHING_SEMANTICS.md)
- [Domain and matching invariants](docs/INVARIANTS.md)
- [ADR 0001: Integer price ticks](docs/adr/0001-integer-price-ticks.md)
- [ADR 0002: Single-writer deterministic core](docs/adr/0002-single-writer-deterministic-core.md)
- [ADR 0003: Strong domain types and validation boundaries](docs/adr/0003-strong-domain-types-and-validation-boundaries.md)
- [ADR 0004: Deterministic matching-core state architecture](docs/adr/0004-deterministic-matching-core-state-architecture.md)

## Licence

No licence has been selected. Until a licence file is added, all rights are reserved.
