# Architecture

## M0 status

This document records proposed top-level boundaries only. None of the components below is implemented
at M0, and the boundaries remain subject to refinement when the domain contract is defined.

```text
Event / Input
      |
      v
Validation
      |
      v
Matching Core --------> Trade Output
      |
      v
Order Book
      |
      v
Replay / Evidence

Benchmark Harness ----> validated event workloads and measured evidence
```

## Proposed component boundaries

| Component | Proposed responsibility | M0 state |
| --- | --- | --- |
| Event / Input | Supply an ordered stream of domain events without owning matching policy. | Not implemented |
| Validation | Reject malformed or invalid requests before state mutation. | Not implemented |
| Matching Core | Apply declared matching semantics as a deterministic single writer. | Not implemented |
| Order Book | Own active orders, price levels, FIFO priority, and locator integrity. | Not implemented |
| Trade Output | Preserve the ordered trade events emitted by matching. | Not implemented |
| Replay / Evidence | Reproduce event streams and capture comparable correctness state. | Not implemented |
| Benchmark Harness | Run fixed workloads and record reproducible measurement metadata. | Not implemented |

## Current constraints

- C++20 is the declared language standard.
- Prices will use integer ticks as recorded in ADR 0001.
- Initial state mutation will be single writer and deterministic as recorded in ADR 0002.
- No container selection, ownership graph, public API, matching contract, or performance property is
  established by M0.
