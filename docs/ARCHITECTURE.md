# Architecture

## Current status

Milestone M3 implements and qualifies the deterministic single-writer matching core described by
ADR 0004.

M4 currently establishes the specification boundary for an independent reference model and a
canonical trace/evidence contract through [ADR 0005](adr/0005-independent-reference-model-and-canonical-trace.md),
[REFERENCE_MODEL.md](REFERENCE_MODEL.md) and [CANONICAL_TRACE.md](CANONICAL_TRACE.md).
The executable reference model, canonical trace writer and validator are not yet implemented or
qualified. The specifications do not establish a differential harness or standalone replay harness.

The logical boundaries distinguish implemented components from specified and future work:

```text
M3 - implemented and qualified
Validated NewOrder / CancelOrder / ModifyOrder
                     |
                     v
              MatchingEngine
                     |
                     v
     ordered ExecutionReport + deterministic EngineSnapshot
     (expected rejection is a typed DomainError)

M4 - specified qualification boundary; not executable yet
Raw qualification commands
          |
          v
Independent reference-model contract
          |
          v
Logical command observations
          |
          v
Canonical-trace contract

Future milestones - not implemented or qualified here
M5: candidate/reference differential qualification
M6: standalone replay/evidence
M7: benchmark methodology and baseline evidence
M8: profiling-backed optimization
```

The matching engine owns the current book state directly. There is no separate runtime order-book
service or concurrent mutation layer.

## Semantic authority

[MATCHING_SEMANTICS.md](MATCHING_SEMANTICS.md) and [INVARIANTS.md](INVARIANTS.md) remain
matching-semantic authority. ADRs 0001 through 0004 remain authoritative for their accepted M3
decisions. ADR 0005 defines the independent-reference and evidence boundary; the M4 contracts do
not redefine matching policy.

Candidate implementation behavior and candidate tests are not semantic authority for the reference
model. A disagreement must be investigated against the frozen contract, not resolved by copying the
candidate's behavior.

## Component boundaries

| Component | Responsibility | Current state |
| --- | --- | --- |
| Event / Input | Supply commands without owning matching policy or sequence identity. | M3 callers provide validated typed commands; M4 specifies a separate raw qualification envelope, not a public matching protocol. |
| Validation | Reject invalid scalar/command input and state-dependent command errors before unauthorized mutation. | M3 implements strong domain types, command factories and engine checks. M4 specifies independent reference validation; it is not yet implemented. |
| Matching Core | Apply the declared matching semantics as a deterministic single writer. | Implemented and qualified in M3. |
| Order Book | Own active orders, price levels, FIFO priority and locator integrity. | Implemented internally by `MatchingEngine` using side books plus an active-ID index. |
| Trade Output | Preserve ordered maker/taker executions. | Implemented as ordered `Trade` values in `ExecutionReport`. |
| Snapshot / Observability | Expose canonical deterministic logical state for qualification and comparison. | Implemented as `EngineSnapshot`; invariant checking is private and used through a build-gated qualification seam. |
| Independent Reference Model | Apply frozen semantics with independent validation and state representation. | M4 contract specified; executable implementation and qualification not yet established. |
| Canonical Trace | Represent command observations as producer-neutral bytes and validate canonicality. | M4 contract specified; writer/validator implementation and qualification not yet established. |
| Differential Qualification | Compare candidate and reference behavior and retain mismatch evidence. | Future M5; no differential harness or agreement established. |
| Replay / Evidence | Reproduce fixed command streams and package verifiable standalone evidence. | Future M6; no standalone harness or closure established. M3 tests cover deterministic replay equivalence only. |
| Benchmark Harness | Run fixed workloads and record reproducible measurement metadata. | Future M7 methodology and baseline evidence; not implemented. |
| Profiling / Optimization | Use profiling and measurement to justify changes while preserving correctness. | Future M8; no profiling-backed optimization evidence established. |
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

## Independent reference-model contract

ADR 0005 and REFERENCE_MODEL.md specify CPython 3.12.10 with the standard library only. The
reference is intended as a correctness oracle, not a performance peer. Its algorithmic complexity
is not an M4 qualification objective.

The specified reference architecture uses:

- a flat collection of immutable active-order values and scalar next-sequence state with explicit
  exhaustion;
- linear order-ID lookup;
- a fresh linear search for an executable maker after each fill, selecting best executable price
  before lowest sequence;
- sequence value, never Python container position, as equal-price time-priority authority; and
- derived sorted snapshots only: bids by descending price then ascending sequence, asks by
  ascending price then ascending sequence. Snapshot ordering does not make physical collection
  position matching authority.

Candidate map/list topology, iterator behavior, unordered-map/hash iteration, typed locators and
validation helpers are not reference-model authority and must not be reused as its matching or
validation mechanism. Incidental Python behavior is not semantic authority either.

The qualification-only raw envelope preserves representation-valid input, including domain-invalid
values, for independent validation and evidence. It is not a new public matching protocol and gives
the caller no sequence authority. The allocator seed is qualification-only, outside matching
commands; normal initialization and sequence semantics remain unchanged. Dedicated contracts
define the exact input domains and qualification obligations.

## Canonical trace contract

CANONICAL_TRACE.md specifies evidence representation, not matching policy. Each command record
preserves the raw qualification command and its zero-based trace index, exact acceptance or
`DomainError` result, ordered trades, canonical logical bids/asks and allocator observation.
Rejected commands still include complete post-state and allocator state, with empty trades.
Available-at-`UINT64_MAX` and exhausted remain observably distinct.

The producer supplies canonical logical observations. The serializer must preserve trade emission
order and must not sort or rewrite trades into correctness. It must not sort, deduplicate or repair
incorrect book state into correctness; supplied book arrays that fail the contract's ordering or
field constraints fail serialization. Canonical validation is fail-closed and does not certify
matching correctness or restore rejected-command pre-state.

`EngineSnapshot` is a logical state view, not the canonical byte format. Candidate and reference
are not required to share a serializer implementation. For the same raw command, command index
and logical post-command observation, conforming producers must be capable of identical bytes.

Provenance is excluded from semantic trace bytes. An external SHA-256 identifies the exact complete
bytes for integrity checking; it does not establish semantic correctness, completeness, provenance
authenticity or differential agreement. CANONICAL_TRACE.md owns the normative byte schema,
validation rules and known-answer qualification requirements.

## Error boundary

The candidate uses typed `DomainError` results for expected domain rejection. The reference
contract specifies the same seven-error vocabulary as comparison data: `InvalidPrice`,
`InvalidQuantity`, `InvalidSide`, `DuplicateOrderId`, `UnknownOrderId`, `SequenceExhausted` and
`InvalidModification`. The frozen rejection precedence and rejection atomicity remain unchanged.

Malformed qualification input is not a matching `DomainError` result and does not produce a
semantic command record. Serializer failures, programming defects and resource/runtime failures
are also outside expected matching-domain rejection. These are reference/evidence contract
requirements, not claims that executable M4 components already enforce them.

## Milestone boundary

| Milestone | Responsibility | Evidence at this checkpoint |
| --- | --- | --- |
| M3 | Deterministic matching implementation and qualification. | Established within the documented M3 scope. |
| M4 | Independent reference model and canonical trace, including their implementation and qualification. | Contracts specified only; executable reference and writer/validator qualification are not yet established. |
| M5 | Candidate/reference differential qualification and agreement. | Future work; no agreement claimed. |
| M6 | Standalone replay and durable evidence closure. | Future work; no closure claimed. |
| M7 | Benchmark methodology and baseline evidence. | Future work; no benchmark results claimed. |
| M8 | Profiling-backed optimization. | Future work; no optimization results claimed. |

The current M4 specification checkpoint does not close M4 implementation qualification. No
milestone inherits a stronger claim merely because a later component is planned.

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
- Differential agreement, standalone replay/evidence closure, benchmark results and profiling-backed
  optimization remain future evidence obligations.
- No concurrent-matching, persistence/recovery or networking/exchange-adapter capability is claimed.
- The specifications and bounded qualification evidence are not formal verification or universal
  correctness proof.
