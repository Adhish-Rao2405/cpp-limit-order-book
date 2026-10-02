# M5 Differential Qualification

- Status: Preregistered design; implementation not started
- Milestone: M5 - Candidate/Reference Differential Qualification
- Date: 2026-10-02
- Frozen M4 entry commit: `a9f5578360ff0e568d1e5215d812601f16d293c7`
- Frozen M4 entry tree: `e21b44de096f02ea0b6b8040ed9a5fa4f0e6ef39`

## 1. Purpose

M5 establishes bounded differential correctness evidence between the deterministic C++ matching
engine and the independent CPython reference model qualified in M4.

The qualification question is:

> For the preregistered qualification command domain and workload set, do the independently
> implemented candidate and reference producers emit exactly the same canonical-v1 observations
> from exactly the same raw qualification input bytes?

M5 is correctness-only.

M5 does not establish:

- formal verification;
- universal correctness;
- latency or throughput performance;
- HFT capability;
- exchange-grade behaviour;
- production readiness;
- concurrency correctness;
- persistence or recovery correctness;
- networking or venue integration; or
- optimization success.

M7 owns benchmark methodology and baseline performance evidence.
M8 owns profiling-backed optimization.

M6 owns standalone replay, durable evidence packaging, provenance manifests, replay verification,
and correctness freeze after differential qualification.

## 2. Authority

Matching-semantic authority remains:

1. `docs/MATCHING_SEMANTICS.md`;
2. `docs/INVARIANTS.md`;
3. ADR 0001;
4. ADR 0002;
5. ADR 0003;
6. ADR 0004 where it expresses logical behaviour; and
7. ADR 0005.

Reference-model authority remains:

- `docs/REFERENCE_MODEL.md`;
- ADR 0005.

Canonical byte authority remains:

- `docs/CANONICAL_TRACE.md`.

This document does not redefine those contracts.

Candidate implementation behaviour and candidate tests are evidence, not semantic authority.

A disagreement is investigated against the frozen semantic contract rather than resolved by copying
one implementation into the other.

## 3. Differential architecture

The normative M5 flow is:

```text
preregistered workload definition
             |
             v
neutral deterministic generator
             |
             v
frozen raw qualification stream bytes
        /                         \
       v                           v
C++ candidate runner        Python reference runner
       |                           |
       v                           v
candidate domain path       independent reference path
       |                           |
       v                           v
MatchingEngine              reference model
       |                           |
       v                           v
independent C++             independent Python
canonical-v1 producer       canonical-v1 producer
        \                         /
         \                       /
          v                     v
            independent comparator
                     |
             exact bytes or HOLD
```

The same exact raw input bytes are supplied to both producers.

The candidate and reference independently derive their logical observations.

They independently canonicalize those observations.

A third qualification component performs the primary comparison.

## 4. Independence requirements

The candidate must not:

- call Python reference code;
- consume reference-produced expected results;
- use reference snapshots as expected candidate state;
- use reference validation helpers;
- use reference matching helpers; or
- use reference transition logic.

The reference must not:

- call candidate code;
- reuse candidate factories;
- consume candidate snapshots as expected reference state;
- use candidate validation helpers;
- use candidate matching helpers; or
- reuse candidate transition logic.

Candidate and reference must not share one runtime canonical serializer.

The comparator must not use either matching implementation as semantic authority.

## 5. Primary agreement predicate

For a transport-valid qualification stream:

```text
candidate canonical-v1 bytes
==
reference canonical-v1 bytes
```

is the primary predicate.

Comparison is byte-for-byte.

Before the primary decision there is no:

- newline normalization;
- whitespace removal;
- JSON parse-and-reserialize;
- object-member reordering;
- trade reordering;
- book-state repair;
- integer-format normalization; or
- ignored metadata.

A logically equivalent but noncanonical byte stream is not a PASS.

One unexplained candidate/reference mismatch places the active qualification gate on HOLD.

## 6. Qualification transport: LOBQ1

M5 introduces the qualification-only transport:

```text
LOBQ1
```

LOBQ1 is not a production protocol, public matching API, exchange protocol, or networking contract.

A stream begins with exactly one header:

```text
LOBQ1|<allocator>
```

and is followed by zero or more commands.

The only v1 commands are:

```text
N|<order_id>|<side_code>|<price_ticks>|<quantity_units>
C|<order_id>
M|<order_id>|<price_ticks>|<quantity_units>
```

No matching command carries sequence identity.

## 7. Allocator seed

Normal initialization:

```text
LOBQ1|1
```

A qualification stream may seed any positive uint64 `next_sequence`.

Explicit allocator exhaustion is:

```text
LOBQ1|EXHAUSTED
```

Allocator seed is qualification metadata, not command data.

Arbitrary active-order seeding is forbidden in v1.

Initial active state is empty.

Numeric allocator value `0` is malformed qualification input.

## 8. Scalar grammar

Unsigned decimal is exactly:

```text
0
or
[1-9][0-9]*
```

Signed decimal is exactly:

```text
0
or
[1-9][0-9]*
or
-[1-9][0-9]*
```

Forbidden forms include:

```text
+1
01
001
-0
-01
1_000
1.0
1e3
0x10
```

Representation ranges are:

```text
order_id:
0 .. 18446744073709551615

side_code:
0 .. 255

price_ticks:
-9223372036854775808 .. 9223372036854775807

quantity_units:
0 .. 18446744073709551615

numeric allocator seed:
1 .. 18446744073709551615
```

Representation validity is separate from matching-domain validity.

Therefore values such as:

```text
side_code = 2
price_ticks = 0
quantity_units = 0
```

are representation-valid and must reach matching-domain validation.

## 9. LOBQ1 byte contract

LOBQ1 v1 requires:

```text
character repertoire      ASCII subset of UTF-8
UTF-8 BOM                 forbidden
line ending               LF byte 0x0A only
CR                        forbidden
blank lines               forbidden
leading whitespace        forbidden
trailing whitespace       forbidden
comments                  forbidden
mandatory final LF        yes
maximum record content    128 bytes excluding LF
```

Malformed transport includes:

- empty input;
- missing header;
- duplicate header;
- unsupported protocol identifier/version;
- unknown command kind;
- missing field;
- extra field;
- forbidden numeric spelling;
- numeric representation overflow;
- embedded NUL;
- forbidden non-ASCII byte; or
- missing final LF.

## 10. Whole-stream parsing

Both producers validate the complete transport before processing any semantic command.

If any record is malformed:

```text
semantic command execution count = 0
semantic canonical trace = absent
```

A valid prefix followed by malformed input must not produce a partial semantic trace.

Malformed transport is not a `DomainError`.

For example:

```text
N|42|2|100|10
```

is representation-valid and reaches domain validation.

By contrast:

```text
N|42|true|100|10
```

is malformed qualification transport.

## 11. Candidate qualification adapter

The candidate adapter may perform only transport/representation responsibilities:

- read exact LOBQ1 bytes;
- validate framing;
- validate field count;
- validate lexical numeric grammar;
- validate scalar representation ranges;
- produce raw scalar values;
- route those values through the existing candidate domain boundary;
- invoke the existing matching engine;
- expose required logical observations; and
- use the existing narrow qualification allocator seam.

The adapter must not independently implement:

```text
InvalidPrice
InvalidQuantity
InvalidSide
DuplicateOrderId
UnknownOrderId
SequenceExhausted
InvalidModification
```

Those remain candidate matching-domain responsibilities.

M5 must not broaden the normal public production API merely to make qualification easier.

If implementation appears to require arbitrary book mutation, arbitrary active-order seeding,
caller-supplied sequence identity, direct locator mutation, or unrestricted allocator mutation,
implementation stops with an architecture HOLD.

## 12. Reference runner

The reference path is:

```text
LOBQ1 bytes
    |
    v
independent parser
    |
    v
RawNew / RawCancel / RawModify
    |
    v
M4 reference model
    |
    v
M4 canonical-v1 serializer
```

The reference runtime remains:

```text
CPython 3.12.10
64-bit
Python standard library only
```

Qualification uses `python -B`.

Cache hygiene remains mandatory.

Malformed transport must not be converted into `DomainError`.

## 13. Canonical observation surface

M5 consumes canonical trace v1.

It does not introduce canonical trace v2.

The frozen observation surface includes:

- raw qualification command;
- command index;
- accepted/rejected result;
- exact `DomainError` where rejected;
- ordered trades;
- ordered bids;
- ordered asks; and
- allocator state.

State ordering remains:

```text
bids: price descending, then sequence ascending
asks: price ascending, then sequence ascending
```

Trade order is preserved.

Canonicalization must not repair incorrect semantic output.

## 14. Candidate canonical producer

The C++ candidate must independently produce canonical-v1 bytes.

It must not:

- call the Python serializer;
- spawn Python to serialize candidate observations;
- consume Python-produced expected trace records at runtime; or
- share one serializer implementation with the reference.

Integral formatting must be deterministic and locale-independent.

Trace files use exact LF bytes and must avoid platform text-mode newline translation.

## 15. Candidate serializer known-answer gate

Before full differential qualification, the candidate serializer must pass fixed known-answer vectors
derived from `docs/CANONICAL_TRACE.md`.

Required coverage includes:

- trace header;
- accepted command with zero trades;
- one trade;
- multiple trades;
- rejected command;
- empty book;
- ordered bids;
- ordered asks;
- uint64 maximum;
- relevant int64 boundaries;
- available `next_sequence = UINT64_MAX`;
- exhausted allocator;
- exact member ordering;
- compact JSON;
- LF-only output; and
- mandatory final LF.

Expected bytes must not be generated dynamically by the reference serializer during that test.

## 16. File-based semantic transport

Semantic inputs and trace outputs use files, not shell stdout pipelines.

This reduces common-mode risk from:

- Windows CRLF conversion;
- shell encoding;
- terminal encoding;
- PowerShell pipeline behaviour;
- stdout/stderr interleaving; and
- diagnostic contamination.

Diagnostics remain separate from semantic trace bytes.

## 17. Comparator order

For each transport-valid stream the harness:

1. verifies exact input-byte identity;
2. executes candidate;
3. executes reference;
4. checks producer process status;
5. requires candidate trace;
6. requires reference trace;
7. validates candidate canonical-v1 bytes;
8. validates reference canonical-v1 bytes;
9. compares complete raw bytes;
10. returns PASS only on exact equality;
11. otherwise stops with HOLD; and
12. derives diagnostics only from already-produced evidence.

Diagnostic parsing cannot turn a byte mismatch into a PASS.

## 18. No retry and no automatic shrinking

The first unexplained qualification failure stops the active gate.

There is no automatic:

- retry;
- seed replacement;
- workload regeneration;
- denominator reduction;
- failure deletion; or
- continuation followed by percentage-based success.

A later rerun requires an explicitly designed corrective gate.

Automatic property-test shrinking is prohibited during qualification.

The original failing workload remains historical evidence.

## 19. Fixed semantic corpus F01-F32

The fixed semantic corpus contains exactly:

```text
32 streams
79 semantic command positions
```

Required cases are:

```text
F01  single resting buy
F02  single resting sell
F03  buy aggressor crosses sell maker; maker price
F04  sell aggressor crosses buy maker; maker price
F05  partial fill leaves maker residual
F06  exact full fill removes both
F07  aggressor partial fill then residual rests
F08  buy multi-level sweep
F09  sell multi-level sweep
F10  same-price bid FIFO
F11  same-price ask FIFO
F12  duplicate active ID
F13  ID reuse after cancellation
F14  ID reuse after complete fill
F15  unknown cancel
F16  unknown modify
F17  same-price reduction retains priority
F18  no-op modify rejected
F19  same-price increase loses priority
F20  price-changing modify loses priority
F21  replacement matches only after original removal
F22  New invalid price + quantity + side precedence
F23  New valid price, invalid quantity + side precedence
F24  New invalid side only
F25  Modify invalid price + quantity precedence
F26  Modify invalid quantity only
F27  UINT64_MAX allocated exactly once then exhaustion
F28  cancel while exhausted
F29  priority-retaining modify while exhausted
F30  priority-losing modify while exhausted
F31  duplicate rejection atomicity
F32  unknown-modify rejection atomicity
```

The exact raw bytes and command count of every stream must be frozen before differential execution.

If the exact authored corpus cannot satisfy both the required cases and the frozen 79-command total,
qualification stops for preregistration review before execution.

## 20. Scalar-boundary corpus B

The boundary corpus contains exactly:

```text
24 streams
24 semantic command positions
```

Coverage includes:

```text
order_id:
0
1
UINT64_MAX

side_code:
0
1
2
255

price_ticks:
INT64_MIN
-1
0
1
INT64_MAX

quantity_units:
0
1
UINT64_MAX
```

It is a deliberately selected covering set rather than a Cartesian product.

Exact B01-B24 stream bytes are sealed before execution.

## 21. Malformed corpus X01-X24

Exactly 24 malformed transport cases are preregistered:

```text
X01  empty file
X02  missing header
X03  wrong protocol identifier
X04  unsupported protocol version
X05  missing final LF
X06  CRLF
X07  UTF-8 BOM
X08  blank command line
X09  leading whitespace
X10  trailing whitespace
X11  invalid command kind
X12  New missing field
X13  New extra field
X14  Cancel extra field
X15  Modify missing field
X16  Modify extra field
X17  negative value in unsigned field
X18  explicit plus prefix
X19  leading zero
X20  negative zero
X21  uint64 overflow
X22  int64 overflow
X23  nonnumeric scalar
X24  embedded NUL
```

At least one malformed case contains a valid command prefix followed by the malformed record.

Every X case requires:

```text
semantic commands processed = 0
semantic trace emitted = none
classification = malformed qualification input
```

## 22. Generated PRNG

Generated workloads use explicitly implemented SplitMix64.

For each draw:

```text
state = state + 0x9E3779B97F4A7C15
z = state
z = (z xor (z >> 30)) * 0xBF58476D1CE4E5B9
z = (z xor (z >> 27)) * 0x94D049BB133111EB
result = z xor (z >> 31)
```

All arithmetic is modulo `2^64`.

Bounded selection is:

```text
next_u64() % n
```

The generator does not use:

- Python `random`;
- implementation-defined C++ random behaviour;
- wall-clock time;
- environment entropy;
- process IDs; or
- filesystem ordering.

## 23. Frozen base seeds

Exactly these four seeds are preregistered:

```text
0x243F6A8885A308D3
0x13198A2E03707344
0xA4093822299F31D0
0x082EFA98EC4E6C89
```

Seeds are never replaced because a result is inconvenient.

## 24. Generator independence and derivation

The workload generator is not an oracle.

It must not import candidate code, the reference model, the reference canonical serializer, or
candidate/reference expected-result fixtures.

Each generated stream derives an independent PRNG starting state from:

```text
family identifier
base seed
stream index
```

The exact derivation algorithm must be frozen in generator source before any generated corpus is
executed.

State-dependent "draw until usable" loops are prohibited.

The preferred rule is:

```text
one category draw
fixed field draws
deterministic fallback
```

## 25. G1 state-aware valid-intent workload

G1 is:

```text
4 seeds
8 streams per seed
256 commands per stream
32 streams
8192 command positions
active-order cap = 64
```

Nominal command selector:

```text
00-44  New
45-69  Cancel
70-99  Modify
```

Moderate scalar region:

```text
price       1..1000
quantity    1..100
ID pool     0..127
side_code   0 or 1
```

If no active order exists for selected Cancel or Modify, the deterministic fallback emits a
valid-intent New.

At the active-state cap, generation deterministically selects an operation that does not intend to
increase active state.

G1 deliberately includes both resting and crossing New-order patterns.

## 26. G2 hostile generated workload

G2 is:

```text
4 seeds
8 streams per seed
256 commands per stream
32 streams
8192 command positions
active-order cap = 64
```

Category buckets:

```text
00-19  valid-intent New
20-29  valid-intent Cancel
30-39  valid-intent Modify
40-49  duplicate-active-ID New
50-59  invalid-side New
60-69  zero-quantity New
70-79  non-positive-price New or Modify
80-89  unknown Cancel
90-94  unknown Modify
95-99  no-op Modify
```

Unavailable category preconditions use one deterministic preregistered fallback.

There is no random redraw until a category becomes available.

## 27. G3 long mixed churn

G3 is:

```text
4 seeds
4 streams per seed
1024 commands per stream
16 streams
16384 command positions
active-order cap = 128
```

It exercises long state history including:

- price-level creation/removal;
- order-ID reuse;
- repeated partial fills;
- cancellation;
- modification;
- FIFO turnover; and
- alternating liquidity pressure.

G3 is correctness stress, not benchmark evidence.

## 28. G4 allocator-exhaustion churn

G4 is:

```text
4 seeds
4 streams per seed
64 commands per stream
16 streams
1024 command positions
active-order cap = 16
initial next_sequence = UINT64_MAX - 7
```

Each stream deliberately reaches explicit sequence exhaustion.

Post-exhaustion commands include:

- cancellation;
- priority-retaining modify;
- priority-losing modify;
- New;
- unknown cancel; and
- unknown modify.

The family covers both operations that require a fresh sequence and those that do not.

## 29. Frozen base denominator

Before metamorphic derived executions:

```text
F   32 streams       79 command positions
B   24 streams       24 command positions
G1  32 streams     8192 command positions
G2  32 streams     8192 command positions
G3  16 streams    16384 command positions
G4  16 streams     1024 command positions
```

Therefore:

```text
base transport-valid streams = 152
33895 semantic command positions
```

Malformed transport is reported separately:

```text
X = 24 cases
```

Expected `DomainError` observations remain inside semantic qualification.

## 30. M5E0 corpus seal

No full candidate/reference differential execution begins until M5E0 corpus seal is complete.

The manifest records at minimum:

- LOBQ1 version;
- generator version;
- generator source identity;
- PRNG algorithm;
- exact seeds;
- family identifiers;
- stream counts;
- command counts;
- stream IDs;
- stream byte lengths;
- per-stream SHA-256;
- fixed corpus identities;
- malformed case identities; and
- aggregate manifest SHA-256.

Once sealed, the raw qualification bytes are immutable qualification inputs.

A later corrective corpus is versioned separately and never rewrites original evidence history.

## 31. Metamorphic policy

M5 v1 preregisters exactly two relation families:

```text
MR1 deterministic replay
MR2 rejection atomicity
```

No broad permutation invariance is claimed.

M5 v1 does not preregister general ID renaming, arbitrary price translation, quantity scaling, side
inversion, or book mirroring.

### MR1 deterministic replay

Exactly 12 relation instances.

Preconditions include identical producer identity, build/runtime configuration, allocator state, and
raw input bytes.

The exact same sealed input is executed twice.

Required relation:

```text
candidate A == candidate B
reference A == reference B
candidate == reference
```

The second execution is a preregistered relation member, not a retry.

### MR2 rejection atomicity

Exactly 12 relation instances.

A command guaranteed by frozen semantics to reject before mutation is inserted at a known state.

Permitted cases include duplicate active ID, unknown cancel, and no-op modify where their
preconditions have been explicitly established.

Required state relation:

```text
state before guaranteed rejection
==
state after guaranteed rejection
```

Mapped subsequent state evolution must remain equivalent except for the additional rejection
observation.

Total metamorphic denominator:

```text
24 relation instances
```

## 32. Failure taxonomy

Fixed workload IDs already use F01-F32, so failures use Class 1-Class 11:

```text
Class 1   malformed qualification input
Class 2   candidate adapter failure
Class 3   candidate DomainError observation
Class 4   reference qualification failure
Class 5   reference DomainError observation
Class 6   candidate serializer failure
Class 7   reference serializer failure
Class 8   comparator or harness defect
Class 9   canonical byte mismatch
Class 10  logical semantic mismatch
Class 11  process/runtime/resource failure
```

Class 3 and Class 5 are not automatically defects.

An independently matching expected `DomainError` is a valid differential outcome.

Harness defects are not product defects.

Product defects must not be dismissed as harness defects without evidence.

## 33. Mismatch evidence

At minimum record:

- workload family;
- stream ID;
- generator version where applicable;
- seed where applicable;
- stream index;
- command index where localizable;
- input SHA-256;
- candidate process result;
- reference process result;
- candidate trace SHA-256;
- reference trace SHA-256;
- trace byte lengths;
- first differing byte offset;
- first differing record;
- first differing logical field;
- candidate/reference command outcomes;
- candidate/reference trades;
- candidate/reference bids and asks;
- candidate/reference allocator state;
- candidate commit/tree;
- reference manifest identity; and
- corpus manifest identity.

M6 remains responsible for durable standalone evidence packaging.

## 34. Result policy

M5 does not use an agreement percentage.

The following is prohibited:

```text
99.99 percent agreement => PASS
```

Each preregistered category has an independent denominator.

Every required category must pass in full.

A failed stream remains in its denominator.

## 35. Cross-platform matrix

Final M5 qualification requires:

```text
P01  Windows / C++ Debug   / CPython normal
P02  Windows / C++ Debug   / CPython -O
P03  Windows / C++ Release / CPython normal
P04  Windows / C++ Release / CPython -O

P05  Linux   / C++ Debug   / CPython normal
P06  Linux   / C++ Debug   / CPython -O
P07  Linux   / C++ Release / CPython normal
P08  Linux   / C++ Release / CPython -O
```

Each cell consumes the exact same sealed raw workload bytes.

Per-stream SHA-256 must agree with the corpus seal.

For each stream:

```text
candidate == reference
```

must hold inside every matrix cell.

Corresponding candidate traces must also be deterministic across Windows/Linux and Debug/Release.

Corresponding reference traces must be deterministic across Windows/Linux and normal/`-O`.

Toolchain identities are recorded; toolchain equality is not claimed.

## 36. CI boundary

M5A performs no CI mutation.

When M5 CI is eventually authorized it must:

- retain existing C++ qualification;
- retain CPython 3.12.10 reference qualification;
- add rather than replace M5 jobs;
- pin actions immutably;
- use least privilege;
- verify sealed workload identities;
- preserve exact denominators; and
- introduce no unreviewed third-party Python dependency.

A green CI summary cannot override contradictory evidence.

## 37. Threat model

| Threat | Control |
| --- | --- |
| Candidate/reference share matching logic | Independent implementations and state strategies |
| Adapter hides candidate validation defect | Representation-only adapter |
| Shared serializer creates common-mode bug | Independent serializers |
| Comparator repairs bad output | Raw-byte equality first |
| Seeds changed after mismatch | Frozen seeds and corpus seal |
| Platform input drift | Per-stream SHA-256 verification |
| Shell newline transformation | File-based byte transport |
| Malformed input becomes DomainError | Whole-stream transport parse first |
| State growth becomes benchmark | Active-state caps |
| Retry hides nondeterminism | No automatic retry |
| Shrinking rewrites failure evidence | No automatic shrinking |
| Large generated corpus hides fixed failure | Independent categorical denominators |
| Harness defect blamed on candidate | Explicit failure taxonomy |
| Candidate defect dismissed as harness | Evidence-required attribution |
| Performance claim leaks into M5 | Correctness-only scope |

## 38. M5 decomposition

The planned sequence is:

```text
M5A  architecture, threat model, preregistration
M5B  raw candidate qualification adapter
M5C  independent candidate canonical producer
M5D  deterministic differential harness/comparator
M5E  fixed, boundary, malformed corpus and M5E0 seal
M5F  deterministic generated workloads
M5G  differential and metamorphic qualification
M5H  cross-platform CI qualification
M5I  integrated M5 closure
```

No later milestone is authorized merely because it is documented here.

## 39. M5 completion condition

M5 closes only if:

```text
F       complete PASS
B       complete PASS
G1      complete PASS
G2      complete PASS
G3      complete PASS
G4      complete PASS
X       complete PASS
MR1     complete PASS
MR2     complete PASS
P01-P08 complete PASS

unexplained differential mismatches = 0
unresolved harness defects = 0
corpus identity drift = 0
unresolved provenance inconsistency = 0
```

Anything less is partial evidence or HOLD, not completed M5 qualification.

## 40. Claim boundary after M5A

After M5A documentation alone the project may claim that:

- M5 architecture is preregistered;
- LOBQ1 is specified;
- comparison policy is preregistered;
- workload families and denominators are preregistered;
- seeds are preregistered;
- mismatch policy is preregistered;
- metamorphic relations are preregistered;
- cross-platform matrix is preregistered; and
- threat controls are documented.

It must not yet claim that:

- a candidate adapter exists;
- a C++ canonical producer exists;
- a differential comparator exists;
- the corpus is sealed;
- generated workloads exist;
- candidate/reference agreement exists;
- metamorphic qualification passed;
- cross-platform M5 qualification passed; or
- M5 is complete.

Only after M5A documentation closure may M5B candidate-adapter implementation begin.
