# cpp-limit-order-book

`cpp-limit-order-book` is a greenfield C++20 limit-order-book and matching-engine project.

## Current status

The project is under construction. Milestone M0 establishes tooling, repository structure,
build configuration, and initial architectural decisions only. No order model, order book,
matching engine, trade path, replay implementation, tests, or benchmarks exist yet.

## Evidence and non-claims

This repository does not currently claim:

- high performance or low latency;
- production-grade or exchange-grade suitability;
- fidelity to the rules of any real exchange;
- established matching correctness;
- established benchmark or profiling evidence.

Correctness, determinism, and performance statements will be introduced only when the relevant
milestones produce reproducible test and benchmark evidence.

## M0 configuration

The checked-in CMake presets use out-of-source Ninja builds and require CMake 3.25 or newer.

```powershell
cmake --preset debug
cmake --build --preset debug
```

The M0 project deliberately contains no production library or executable target. The
`lob_project_options` interface target exists only to declare the C++20 language requirement for
future targets.

## Design records

- [Architecture](docs/ARCHITECTURE.md)
- [ADR 0001: Integer price ticks](docs/adr/0001-integer-price-ticks.md)
- [ADR 0002: Single-writer deterministic core](docs/adr/0002-single-writer-deterministic-core.md)

## Licence

No licence has been selected during M0. Until a licence file is added, all rights are reserved.
