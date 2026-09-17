# ADR 0002: Begin with a single-writer deterministic core

- Status: Accepted
- Date: 2026-08-24

## Context

Matching correctness depends on a total, reproducible event order. Introducing concurrent mutation
before semantics, invariants, replay, and differential qualification exist would expand the state
space and make failures harder to reproduce.

## Decision

The initial matching core will be a single-writer deterministic state machine. An internal monotonic
sequence number, rather than wall-clock timing, will establish arrival order. Identical valid event
streams must produce identical ordered trades and final book state.

Concurrency, including a possible bounded producer queue around one matching thread, is deferred
until after the deterministic baseline is correctness-qualified and benchmarked. Lock-free structures,
custom allocators, and multithreaded mutation are outside the initial scope.

## Consequences

The core can be replayed and compared with an independent reference implementation without scheduler
effects. The design initially limits mutation to one execution context and makes no concurrency or
throughput claim. Later measurements may justify concurrent ingestion while retaining single-writer
book ownership; that would require a separate decision record and qualification plan.
