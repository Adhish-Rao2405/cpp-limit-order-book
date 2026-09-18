# Architecture

## Current status

Milestone M3 implements and qualifies the deterministic single-writer matching core described by
ADR 0004.

The current logical boundary is:

```text
Validated NewOrder / CancelOrder / ModifyOrder
                     |
                     v
              MatchingEngine
             /      |       \
            v       v        v
       bids/asks  active_   sequence state
            \       |        /
             \      |       /
              v     v      v
           ExecutionReport + EngineSnapshot

Future Replay / Evidence Harness
              |
              v
       deterministic workloads

Future Benchmark Harness
              |
              v
       measured evidence only
```

The matching engine owns the current book state directly. There is no separate runtime order-book
service or concurrent mutation layer.

## Component boundaries

| Component | Responsibility | Current state |
| --- | --- | --- |
| Event / Input | Supply typed commands without owning matching policy. | No standalone protocol/event-stream component; callers provide validated command objects. |
| Validation | Reject invalid scalar/command input and state-dependent command errors before unauthorized mutation. | Implemented for the current command set through strong domain types, command factories and matching-engine checks. |
| Matching Core | Apply the declared matching semantics as a deterministic single writer. | Implemented and qualified in M3. |
| Order Book | Own active orders, price levels, FIFO priority and locator integrity. | Implemented internally by `MatchingEngine` using side books plus an active-ID index. |
| Trade Output | Preserve ordered maker/taker executions. | Implemented as ordered `Trade` values in `ExecutionReport`. |
| Snapshot / Observability | Expose canonical deterministic logical state for qualification and comparison. | Implemented as `EngineSnapshot`; invariant checking is private and used through a build-gated qualification seam. |
| Replay / Evidence | Reproduce fixed command streams and emit standalone comparable evidence. | Not yet implemented as a standalone harness; deterministic replay equivalence is covered by M3 tests. |
| Benchmark Harness | Run fixed workloads and record reproducible measurement metadata. | Not implemented. |
| Persistence / Recovery | Persist and restore matching state. | Not implemented. |
| Networking / Exchange adapters | Connect external protocols or venues. | Not implemented. |
| Concurrent matching | Permit concurrent engine mutation. | Not implemented; engine access must be externally serialized. |

## M3 state architecture

The engine uses:

```text
bids_:   ascending map<Price, FIFO list<RestingOrder>>
asks_:   ascending map<Price, FIFO list<RestingOrder>>
active_: unordered_map<OrderId, Locator, OrderIdHash>
```

The best ask is the first ask level. The best bid is the last bid level.

Price and side are structural properties of the owning book/price level. Resting nodes store only
order ID, remaining quantity and sequence. The active hash index is lookup support and is not
matching, trade-order, snapshot-order or replay authority.

The internal sequence allocator starts at `1`, permits `UINT64_MAX` exactly once and then enters an
explicit exhausted state. Sequence wrap is forbidden.

Copy and move of `MatchingEngine` are disabled because its locator graph contains iterators into its
own book state.

## Current constraints and claim boundary

- C++20 is the declared language standard.
- Prices use integer ticks as recorded in ADR 0001.
- State mutation is single writer and deterministic as recorded in ADR 0002.
- Strong domain types and validation boundaries follow ADR 0003.
- Matching-core ownership and public API follow ADR 0004.
- Expected domain rejection uses typed `DomainError` results rather than normal exception control
  flow.
- The engine is not thread-safe; concurrent access is outside the current contract.
- Resource-exception strong recovery is not claimed.
- No latency, throughput, HFT, production-readiness or exchange-fidelity property is established by
  the current architecture.
- Replay/evidence and benchmark harnesses remain future milestones.
