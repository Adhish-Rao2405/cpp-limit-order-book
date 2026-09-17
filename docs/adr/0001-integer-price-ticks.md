# ADR 0001: Represent prices as integer ticks

- Status: Accepted
- Date: 2026-08-24

## Context

The order book will compare prices to determine ordering and whether incoming orders cross resting
orders. Binary floating-point types cannot exactly represent many decimal prices, so equality and
ordering at a declared tick boundary can become dependent on representation artefacts.

## Decision

Prices will be represented by a strong domain type whose underlying value is a signed integer count
of ticks. A price such as GBP 100.01 can therefore be represented as 10,001 ticks when the configured
tick size is GBP 0.01. Floating-point values will not participate in book ordering or matching.

Conversion from external decimal representations will occur at a validation boundary that is not yet
implemented. The matching core will receive already validated tick values.

## Consequences

Integer comparison gives deterministic ordering and makes the permitted price grid explicit. The
representation has a finite range, so validation must reject non-positive prices and detect overflow
during future parsing or conversion. Instruments with different tick sizes need explicit metadata or
pre-normalisation; M0 does not define that configuration mechanism.

This decision does not by itself establish matching correctness or fidelity to any real exchange.
