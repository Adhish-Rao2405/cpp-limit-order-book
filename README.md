# cpp-limit-order-book

`cpp-limit-order-book` is a greenfield C++20 limit-order-book and matching-engine engineering project.

## Current status

Milestone M1 establishes the reproducible build and test infrastructure that later matching-engine
work will rely on.

The repository currently provides:

- a C++20 `lob_core` static library target;
- target-scoped compiler warning policy with warnings treated as errors for first-party code;
- Debug and Release CMake/Ninja presets;
- GoogleTest integration using a cryptographically verified release archive;
- CTest discovery and execution;
- Windows/MSVC GitHub Actions configuration for Debug and Release qualification.

No order model, price-level representation, matching engine, trade path, replay implementation,
benchmark harness, concurrency mechanism, or persistence layer exists yet.

## Evidence and non-claims

This repository does not currently claim:

- high performance or low latency;
- production-grade or exchange-grade suitability;
- fidelity to the rules of any real exchange;
- established matching correctness;
- established benchmark or profiling evidence;
- cross-platform qualification beyond environments actually tested.

Correctness, determinism, and performance statements will be introduced only when the relevant
milestones produce reproducible evidence.

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

The current local qualification environment uses x64 MSVC. GitHub CI is configured to exercise Windows
MSVC Debug and Release configurations only.

## Dependency provenance

GoogleTest is fetched only when testing is enabled.

M1 pins GoogleTest v1.18.0 by release archive and verifies:

~~~text
SHA256=6e3191c1455468b3fc35a417fb565c1c5071aee1b7e7f85e30cf48a98d37d8b5
~~~

A dependency hash mismatch is a configuration failure and must not be bypassed.

## Design records

- [Architecture](docs/ARCHITECTURE.md)
- [ADR 0001: Integer price ticks](docs/adr/0001-integer-price-ticks.md)
- [ADR 0002: Single-writer deterministic core](docs/adr/0002-single-writer-deterministic-core.md)

## Licence

No licence has been selected. Until a licence file is added, all rights are reserved.
