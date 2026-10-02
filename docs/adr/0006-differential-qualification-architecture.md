# ADR 0006: Independent differential qualification architecture

- Status: Accepted
- Date: 2026-10-02
- Milestone: M5 - Candidate/Reference Differential Qualification
- Detailed protocol: `docs/M5_DIFFERENTIAL_QUALIFICATION.md`

## Context

M3 qualified the deterministic single-writer C++20 matching core.

M4 added and qualified an independent CPython 3.12.10 reference model together with canonical
trace v1.

Those milestones establish two independently implemented semantic producers and a common
producer-neutral observation format, but they do not establish that the C++ candidate and Python
reference agree when processing the same qualification workloads.

M5 therefore introduces differential qualification.

The purpose of M5 is deliberately narrow:

> feed the same preregistered raw qualification bytes to two independently implemented semantic
> systems, independently serialize their observations to canonical trace v1, and require exact
> byte agreement.

M5 is a correctness milestone.

It does not establish latency, throughput, HFT suitability, exchange fidelity, production
readiness, concurrency correctness, persistence/recovery correctness, or formal verification.

The detailed workload, transport, comparator, denominator, mismatch and cross-platform rules are
defined normatively by `docs/M5_DIFFERENTIAL_QUALIFICATION.md`.

This ADR records the architectural decisions behind that protocol.

---

## Decision summary

M5 will use:

1. a qualification-only raw byte transport named `LOBQ1`;
2. the same exact raw stream bytes for candidate and reference;
3. a narrow C++ qualification adapter that performs representation parsing but does not duplicate
   matching-domain validation;
4. the already-independent CPython reference model as oracle;
5. independently implemented candidate and reference canonical-v1 producers;
6. a third comparator whose primary predicate is exact canonical byte equality;
7. whole-stream transport validation before semantic processing;
8. file-based semantic input/output rather than stdout pipelines;
9. deterministic preregistered fixed and generated workloads;
10. explicitly implemented SplitMix64 for generation;
11. fixed seeds and fixed denominators;
12. bounded active-state sizes;
13. corpus sealing before full differential execution;
14. fail-closed mismatch handling;
15. no automatic retry or shrinking;
16. two narrowly justified metamorphic relation families;
17. the same sealed workload bytes across Windows/Linux qualification surfaces; and
18. strict separation between M5 correctness work and M6/M7/M8 responsibilities.

---

## 1. Authority hierarchy

M5 does not redefine matching semantics.

Semantic authority remains:

- `docs/MATCHING_SEMANTICS.md`;
- `docs/INVARIANTS.md`;
- ADR 0001;
- ADR 0002;
- ADR 0003;
- ADR 0004 where it expresses logical behaviour; and
- ADR 0005.

Reference-model authority remains:

- ADR 0005; and
- `docs/REFERENCE_MODEL.md`.

Canonical byte authority remains:

- `docs/CANONICAL_TRACE.md`.

The C++ implementation and its tests remain evidence about the candidate.

They are not semantic authority.

The Python reference is an independent oracle implementation derived from the semantic contract.
Its implementation is also not permitted to silently redefine that contract.

A disagreement must therefore be investigated against the frozen specification hierarchy.

---

## 2. Why differential qualification is required

Candidate-only testing can show that the C++ implementation behaves consistently with its test
suite.

Reference-only testing can show that the Python oracle satisfies its own independently designed
qualification suite.

Neither alone establishes cross-implementation agreement.

Differential qualification adds a new evidence surface:

```text
same raw input
    |
    +--> candidate --> candidate observation
    |
    +--> reference --> reference observation
```

Agreement between independently implemented systems reduces the risk that one implementation and
its local tests share the same defect.

This remains bounded empirical qualification rather than formal proof.

---

## 3. Same raw bytes are the shared input boundary

The candidate and reference will consume the same exact qualification input bytes.

They will not consume merely equivalent in-memory command objects constructed by one shared parser.

This decision preserves independence at the qualification boundary.

If one shared semantic parser produced already-validated command objects for both implementations,
parser or validation defects could become common-mode failures.

Therefore M5 shares the wire specification and the immutable raw bytes, not one runtime parser
implementation.

---

## 4. LOBQ1 is qualification-only

M5 introduces `LOBQ1` as a minimal deterministic qualification transport.

Its role is only to encode the raw scalar command envelope already established by M4.

It is not:

- a production API;
- an exchange protocol;
- a network protocol;
- a market-data protocol;
- a persistence format; or
- a claim about future external interfaces.

The command forms are limited to qualification representations of New, Cancel and Modify.

No matching command carries sequence identity.

The allocator seed is stream qualification metadata and remains outside matching commands.

Arbitrary active-book injection remains forbidden.

---

## 5. Representation validity is separate from domain validity

The LOBQ1 parser owns representation concerns only.

Examples of representation concerns are:

- framing;
- field count;
- canonical decimal lexical form;
- int64/uint64/uint8 representation bounds;
- LF requirements; and
- forbidden bytes.

Examples of matching-domain concerns are:

- positive price;
- positive quantity;
- valid logical side;
- duplicate active ID;
- unknown active ID;
- modification policy; and
- allocator exhaustion semantics.

A representation-valid value such as:

```text
side_code = 2
```

must reach the candidate's actual matching-domain validation boundary.

The qualification adapter must not convert such a value into `InvalidSide` itself.

This decision prevents qualification infrastructure from masking defects in production validation.

---

## 6. Whole-stream parsing precedes semantic execution

LOBQ1 transport validation is performed for the complete stream before semantic processing begins.

If any transport record is malformed, no semantic command is processed and no semantic canonical
trace is emitted.

This decision avoids an ambiguous state where:

- a valid prefix has already mutated one producer;
- a later transport defect terminates parsing; and
- the resulting partial semantic trace could be mistaken for a legitimate matching observation.

Malformed transport remains harness/qualification failure classification rather than `DomainError`.

---

## 7. Candidate adapter remains narrow

The C++ candidate qualification adapter exists only to bridge raw qualification representations to
the already-defined candidate domain boundary.

It must not become a second implementation of matching policy.

It may:

- parse transport;
- enforce scalar representation ranges;
- construct raw values;
- call existing domain factories/validation paths;
- invoke the existing matching engine;
- expose qualification observations; and
- use a narrow build-gated allocator qualification seam.

It must not expose arbitrary production-state mutation merely to simplify testing.

If M5 implementation requires broad public access to internal book state, sequence identity,
locators, or mutation controls, that is an architecture failure requiring explicit redesign.

---

## 8. Arbitrary active-state seeding is rejected

M5 v1 permits an empty initial active book plus qualification-only allocator state control.

It does not permit arbitrary active-order injection.

Allowing arbitrary active state would require qualification infrastructure to manufacture states
that might be unreachable through legal matching commands.

It would also expand the trusted harness surface and could bypass invariants the differential test
is intended to exercise.

Interesting non-empty states are therefore reached through actual matching commands.

---

## 9. Independent serializers are required

Candidate and reference must independently implement canonical trace v1 production.

A shared runtime serializer was rejected because it could create false confidence:

```text
candidate logical observation
         \
          shared defective serializer
         /
reference logical observation
```

could cause both outputs to contain the same serialization defect.

The reference retains its M4 Python serializer.

The candidate implements canonical-v1 serialization independently in C++.

The candidate serializer receives its own known-answer qualification before full differential use.

---

## 10. A third comparator is required

The comparator is logically separate from both semantic producers.

It does not use either matching engine as authority.

Its primary operation is exact byte comparison after validating that both claimed outputs are
canonical-v1 traces.

Diagnostic parsing may identify the first differing record or logical field, but those diagnostics
cannot weaken the primary result.

This avoids circular comparison in which the reference serializer is reused to normalize candidate
output before deciding equality.

---

## 11. Exact canonical byte equality is primary

M5 uses exact canonical-v1 byte equality rather than only logical JSON equality.

This is possible because M4 already defines canonical trace v1 precisely.

Exact bytes detect both:

- semantic disagreement; and
- producer failure to obey the canonical observation contract.

The comparator does not:

- reorder members;
- sort arrays;
- normalize numeric strings;
- normalize whitespace;
- normalize line endings; or
- reserialize parsed JSON before the primary decision.

A byte mismatch is therefore visible rather than silently repaired.

---

## 12. File-based transport is selected

Semantic workload input and canonical trace output use files rather than shell pipelines.

This reduces risk from:

- CRLF translation;
- terminal encoding;
- shell encoding;
- PowerShell pipeline semantics;
- stdout/stderr interleaving; and
- diagnostic contamination.

Diagnostic output is kept separate from semantic bytes.

This decision is especially important because final M5 qualification spans Windows and Linux.

---

## 13. Deterministic generation uses SplitMix64

Generated workloads require a PRNG whose exact behaviour can be specified independently of
language/library implementation.

M5 therefore uses an explicitly implemented SplitMix64 algorithm.

Built-in language generators such as Python `random` or implementation-specific C++ random
behaviour are not used as the qualification identity.

The goal is deterministic workload identity, not statistical simulation quality.

Modulo reduction for bounded selection is accepted because deterministic qualification is the goal,
not unbiased Monte Carlo inference.

---

## 14. Seeds are frozen before execution

The preregistered base seeds are:

```text
0x243F6A8885A308D3
0x13198A2E03707344
0xA4093822299F31D0
0x082EFA98EC4E6C89
```

A seed cannot be removed or replaced because it reveals a mismatch.

A later supplemental diagnostic seed may be added under a separate corrective gate, but it cannot
replace original evidence.

This is a direct control against workload cherry-picking.

---

## 15. Generator state is not oracle state

State-aware generation may track enough abstract information to select active or inactive IDs and
construct meaningful commands.

That state is generation machinery only.

It does not define expected matching outcomes.

It must not be used to declare a producer wrong merely because an intended generated category did
not behave as anticipated.

Candidate/reference comparison remains authoritative for the M5 differential result, subject to the
frozen semantic specification.

---

## 16. Random redraw-until-valid is rejected

State-dependent repeated draws would consume a variable number of PRNG values.

A small state difference could therefore change the complete remainder of a generated stream.

M5 instead requires deterministic decision consumption and deterministic fallback rules.

This makes workload derivation auditable and reproducible.

---

## 17. Active-state size is bounded

Canonical observations include book state.

If generated tests allow the active book to grow without bound, trace volume can grow sharply and
M5 may accidentally become a memory/throughput stress benchmark.

M5 therefore freezes active-state caps:

```text
G1 = 64
G2 = 64
G3 = 128
G4 = 16
```

The caps preserve substantial state interaction while keeping M5's purpose correctness-focused.

Performance methodology remains M7 responsibility.

---

## 18. Corpus sealing precedes full differential execution

M5E0 freezes the qualification corpus before full candidate/reference differential execution.

The seal includes identities such as:

- generator version;
- generator source identity;
- seeds;
- stream IDs;
- command counts;
- byte lengths;
- per-stream SHA-256; and
- aggregate manifest SHA-256.

Once sealed, those raw bytes are the qualification inputs.

A discovered defect does not authorize silently changing the corpus.

A corrected corpus requires an explicit versioned corrective history.

---

## 19. Denominators are categorical

M5 does not use one aggregate agreement percentage.

The fixed corpus, scalar boundary corpus, generated families, malformed transport corpus,
metamorphic relations and platform matrix are reported separately.

This avoids a large generated denominator numerically hiding failure of a small but critical
contract-directed case.

There is no acceptance rule equivalent to:

```text
99.99% agreement is good enough
```

Every required category must pass completely.

---

## 20. One unexplained mismatch causes HOLD

A single unexplained differential mismatch is qualification-significant.

The active gate stops rather than continuing to accumulate a percentage.

The original failing workload and produced evidence are preserved.

No automatic retry is performed.

A later rerun requires root-cause analysis and an explicitly defined corrective gate.

This preserves failure history and prevents transient success from overwriting contradictory
evidence.

---

## 21. Automatic shrinking is rejected during qualification

Property-testing frameworks often shrink failing workloads automatically.

That behaviour is useful during ordinary development but is inappropriate for the primary
qualification evidence path because it creates new executions after the original failure.

M5 preserves the original failing stream.

A minimized reproducer may be created later under an explicitly authorized diagnostic gate.

---

## 22. Metamorphic scope is deliberately narrow

M5 v1 preregisters only:

- deterministic replay; and
- rejection atomicity.

These relations have strong support in the frozen semantics.

Broader transformations such as arbitrary command permutation, order-ID renaming, price
translation, quantity scaling, side inversion or book mirroring are not included in v1.

A smaller set of defensible metamorphic claims is preferable to a larger set of weakly justified
properties.

---

## 23. Cross-platform qualification uses identical input bytes

Final M5 qualification covers Windows and Linux.

It is insufficient for each platform to use only the same nominal seed.

Every platform must consume the same sealed stream bytes identified by SHA-256.

This prevents generator or newline differences from creating superficially similar but nonidentical
qualification workloads.

---

## 24. Cross-platform canonical determinism is required

For the same stream:

```text
candidate == reference
```

must hold inside every required matrix cell.

Corresponding candidate traces are also expected to agree across Windows/Linux and Debug/Release.

Corresponding reference traces are expected to agree across Windows/Linux and CPython normal/`-O`.

The project records actual toolchain identities.

It does not claim compiler or operating-system equivalence.

---

## 25. M5 does not own standalone evidence packaging

M5 records enough structured evidence to support qualification and mismatch diagnosis.

M6 remains responsible for:

- standalone replay;
- durable evidence bundles;
- provenance manifests;
- packaged replay verification; and
- correctness freeze.

This prevents M5 from expanding into a larger replay/evidence subsystem before the differential
architecture itself is qualified.

---

## 26. M5 does not own performance claims

M5 may encounter runtimes and resource limits operationally, but those measurements do not become
benchmark evidence.

M5 must not claim:

- low latency;
- high throughput;
- HFT suitability;
- performance superiority;
- cache efficiency;
- allocation efficiency; or
- optimization success.

M7 defines benchmark methodology and baseline evidence.

M8 defines profiling-backed optimization.

---

## 27. Failure attribution remains evidence-based

The M5 failure taxonomy distinguishes:

- malformed qualification input;
- candidate adapter failure;
- candidate `DomainError` observation;
- reference qualification failure;
- reference `DomainError` observation;
- candidate serializer failure;
- reference serializer failure;
- comparator/harness defect;
- canonical mismatch;
- logical semantic mismatch; and
- process/runtime/resource failure.

A harness defect is not automatically a candidate defect.

A candidate mismatch is not dismissed as a harness defect without evidence.

Expected `DomainError` is data and may be correct differential agreement.

---

## 28. Rejected alternatives

### Shared semantic parser

Rejected because it would create common-mode qualification-boundary behaviour.

### Candidate pre-validation

Rejected because it could mask defects in the actual candidate validation boundary.

### Shared canonical serializer

Rejected because candidate and reference could agree on the same serializer defect.

### JSON normalization before comparison

Rejected because normalization can hide canonical-contract violations.

### Stdout as semantic transport

Rejected because shell/platform text behaviour increases avoidable cross-platform ambiguity.

### Built-in language PRNGs

Rejected because deterministic identity across implementations is more important than convenience.

### Unbounded generated workloads

Rejected because M5 is correctness qualification rather than performance/resource benchmarking.

### Retry-until-pass

Rejected because it destroys fail-closed evidence history.

### Automatic shrinking in the primary gate

Rejected because it generates follow-on executions after a failure without explicit qualification
authorization.

### Agreement percentage

Rejected because it can hide critical categorical failures.

### Large metamorphic catalogue

Rejected because every relation itself becomes a theorem the harness must justify.

### Arbitrary active-order seeding

Rejected because it expands harness authority and can manufacture unreachable candidate states.

---

## 29. Consequences

The selected architecture increases implementation work because:

- the candidate needs its own qualification parser;
- the candidate needs its own canonical producer;
- a separate comparator is required;
- workload generation must be deterministic and audited;
- corpus identity must be sealed before execution; and
- failure handling is intentionally strict.

Those costs are accepted because they reduce common-mode failure and make the resulting evidence
more defensible.

The architecture also deliberately favours:

- narrow claims;
- explicit provenance;
- deterministic reproducibility;
- independent implementation;
- preserved failure history; and
- fail-closed qualification

over convenience or headline test volume.

---

## 30. Implementation boundary

This ADR authorizes architecture only.

It does not itself authorize:

- M5B implementation;
- builds;
- tests;
- generated workload execution;
- corpus sealing;
- CI changes;
- staging;
- committing;
- pushing;
- tagging;
- PR creation; or
- merging.

Repository mutation remains governed by the active explicit qualification gate.

---

## 31. Acceptance consequence

Once M5A documentation is closed, M5 may proceed to M5B under a new explicit implementation gate.

At that point the project may claim that the M5 differential architecture and experimental
protocol were preregistered before implementation and differential execution.

It may not claim candidate/reference agreement until the later M5 qualification gates actually
produce that evidence.
