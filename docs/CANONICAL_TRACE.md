# M4 Canonical Trace Contract

- Status: Architecture implementation contract
- Milestone: M4 - Independent Reference Model + Canonical Trace
- Schema name: `lob.canonical_trace`
- Schema version: `1`

## 1. Purpose

This document defines the exact producer-neutral byte representation used to serialize the logical command observations defined by `docs/REFERENCE_MODEL.md`.

The contract exists so that independently implemented producers can represent the same logical observation as exactly the same bytes.

The canonical trace is an evidence and comparison surface. It is not matching authority. Matching semantics remain defined by:

- `docs/MATCHING_SEMANTICS.md`;
- `docs/INVARIANTS.md`; and
- accepted architecture decisions, including ADR 0005.

The M3 C++ candidate implementation and its tests are not sources of canonical-trace semantics.

A canonical trace does not establish that the producer was correct. It establishes only that a producer represented a supplied logical observation according to this byte contract.

---

## 2. Milestone boundary

M4 owns:

- this canonical-trace contract;
- a producer-neutral serializer;
- a validator for this contract;
- reference-model integration with that serializer; and
- explicit qualification of the serializer and validator.

M5 owns:

- candidate/reference differential execution;
- byte or logical comparison of independently produced observations;
- generated and adversarial differential workloads;
- mismatch evidence; and
- metamorphic differential checks.

M6 owns:

- standalone replay;
- durable evidence packaging;
- provenance manifests;
- replay verification; and
- correctness freeze.

Passing M4 must not be described as M5 differential agreement or M6 replay/evidence closure.

---

## 3. Trace-level byte contract

A v1 canonical trace is a sequence of UTF-8 JSON objects encoded as JSON Lines.

The exact byte rules are:

```text
encoding                 UTF-8
UTF-8 BOM                forbidden
line ending              LF byte 0x0A only
CR byte                   forbidden
blank lines               forbidden
leading/trailing spaces   forbidden
inter-token whitespace    forbidden
JSON layout               compact
top-level value per line  exactly one object
final line                terminated by LF
mandatory final LF        yes
```

A zero-command run is represented by the required header record followed by one LF. Therefore every valid canonical trace contains at least one line and ends with exactly the LF terminating its final record.

The byte stream begins with the first `{` byte of the header record. No preamble is permitted.

The canonical serializer must not emit a trailing space or tab before LF.

---

## 4. JSON canonicalization scope

This project does not adopt a general-purpose external JSON canonicalization standard.

Instead, v1 defines a closed schema whose values come from a restricted set of ASCII field names, ASCII enumerated strings, JSON booleans, JSON null, arrays, objects, and canonical decimal strings.

Canonical object member order is part of the byte contract.

A JSON object with the same logical members in a different member order is valid JSON but is not a canonical v1 trace record.

A consumer validating claimed canonical bytes must reject duplicate member names. It must not apply a first-value-wins or last-value-wins rule.

Unknown members are forbidden.

Missing required members are forbidden.

Unknown record types are forbidden.

No optional object member exists in v1. Where absence is semantically required, the schema uses JSON `null`.

Because all v1 string values come from closed ASCII vocabularies or canonical decimal strings, Unicode normalization does not participate in v1 canonicalization.

---

## 5. Canonical decimal strings

All semantic integral values are encoded as JSON strings containing canonical ASCII decimal text.

They are not encoded as JSON numbers.

This prevents precision loss in consumers whose native JSON number type cannot represent all int64 or uint64 values exactly.

### 5.1 Unsigned canonical decimal grammar

The lexical grammar is:

```text
0
or
[1-9][0-9]*
```

Therefore the following are forbidden:

```text
+1
00
01
0007
<SPACE>1
1<SPACE>
1.0
1e3
```

`<SPACE>` denotes one ASCII U+0020 space for display only; it is not part of the decimal text.

Only ASCII digits `0` through `9` are permitted.

Field-specific numeric ranges still apply after lexical validation.

### 5.2 Signed canonical decimal grammar

The lexical grammar is:

```text
0
or
[1-9][0-9]*
or
-[1-9][0-9]*
```

The representation `-0` is forbidden.

The representations `+1`, `01`, `-01`, decimal fractions, and exponent forms are forbidden.

### 5.3 Field ranges

The following ranges are normative:

```text
order_id                 uint64: 0 .. 18446744073709551615
quantity_units           uint64: 0 .. 18446744073709551615
remaining_quantity_units uint64: 1 .. 18446744073709551615
sequence                 uint64: 1 .. 18446744073709551615
available next_sequence  uint64: 1 .. 18446744073709551615
side_code                uint8:  0 .. 255
price_ticks              int64: -9223372036854775808 .. 9223372036854775807
```

`command_index` is a zero-based non-negative canonical decimal string. It is a trace position, not a matching-domain value, so v1 does not assign it a uint64 matching-domain limit.

Schema `version` is the fixed ASCII string `"1"`. It is schema metadata, not a semantic integer field.

---

## 6. Record sequence

A valid v1 trace contains:

1. exactly one header record as line 1; then
2. zero or more command records.

No second header record is permitted.

No record may precede the header.

Each command record corresponds to exactly one processed matching command.

Command records are ordered by processing order.

`command_index` begins at `"0"` and increments by exactly one for each subsequent command record.

Gaps, duplicate indexes, decreasing indexes, or non-canonical indexes are invalid.

A malformed qualification input does not become a processed matching command and therefore produces no semantic command record.

Evidence about malformed qualification inputs belongs to qualification evidence outside the canonical semantic trace.

---

## 7. Header record

The header record has exactly three members in this exact order:

```text
record_type
schema
version
```

Its exact v1 bytes before the terminating LF are:

```json
{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1"}
```

Therefore a zero-command trace is exactly:

```text
{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1"}\n
```

The header contains no:

- producer name;
- candidate/reference marker;
- hostname;
- username;
- process ID;
- executable path;
- repository path;
- Git commit or tree ID;
- branch or tag;
- runtime version;
- timestamp;
- test name;
- random seed;
- command count;
- digest; or
- other provenance metadata.

Those values may be useful evidence, but they are not semantic canonical-trace bytes.

---

## 8. Command record

Every command record is one JSON object with exactly these members in this exact order:

```text
record_type
command_index
command
command_result
trades
bids
asks
next_sequence
```

The `record_type` value is exactly:

```json
"command"
```

The structural shape is:

```json
{"record_type":"command","command_index":"0","command":{...},"command_result":{...},"trades":[...],"bids":[...],"asks":[...],"next_sequence":{...}}
```

No producer-specific field may be added.

---

## 9. Raw command representation

The `command` object preserves the representation-valid qualification input for the processed command.

It must not normalize an invalid logical side into a valid side.

It must not replace the incoming limit price with an execution price.

It must not add a caller-controlled sequence.

The v1 command envelope is closed.

### 9.1 New command

A New command object has exactly these members in this exact order:

```text
kind
order_id
side_code
price_ticks
quantity_units
```

`kind` is exactly `"new"`.

Example:

```json
{"kind":"new","order_id":"20","side_code":"0","price_ticks":"103","quantity_units":"5"}
```

`side_code` preserves the representation-valid uint8 input:

```text
"0"     logical Buy
"1"     logical Sell
"2".. "255" representation-valid but logically invalid Side
```

A representation-valid invalid side is therefore observable in a rejected command record.

### 9.2 Cancel command

A Cancel command object has exactly these members in this exact order:

```text
kind
order_id
```

`kind` is exactly `"cancel"`.

Example:

```json
{"kind":"cancel","order_id":"20"}
```

### 9.3 Modify command

A Modify command object has exactly these members in this exact order:

```text
kind
order_id
price_ticks
quantity_units
```

`kind` is exactly `"modify"`.

Example:

```json
{"kind":"modify","order_id":"20","price_ticks":"101","quantity_units":"7"}
```

Modify contains no side field because side is not mutable through the matching command contract.

---

## 10. Command result

The `command_result` object has exactly these members in this exact order:

```text
accepted
error
```

### 10.1 Accepted result

For an accepted command the exact shape is:

```json
{"accepted":true,"error":null}
```

### 10.2 Rejected result

For an expected matching-domain rejection the exact shape is:

```json
{"accepted":false,"error":"InvalidPrice"}
```

The only permitted non-null error strings are:

```text
InvalidPrice
InvalidQuantity
InvalidSide
DuplicateOrderId
UnknownOrderId
SequenceExhausted
InvalidModification
```

The following result combinations are invalid:

```text
accepted=true  with non-null error
accepted=false with null error
accepted value other than JSON true/false
error string outside the closed DomainError set
```

Malformed qualification input is not encoded as a `command_result` error because it is not a DomainError and does not produce a semantic command record.

---

## 11. Trade array

`trades` is a JSON array.

Array position is the exact semantic trade-emission order.

The serializer must preserve the producer's supplied ordered trade sequence.

The serializer must not sort trades by:

- maker ID;
- taker ID;
- price;
- quantity; or
- any other key.

Each trade object has exactly these members in this exact order:

```text
maker_order_id
taker_order_id
price_ticks
quantity_units
```

Example:

```json
{"maker_order_id":"10","taker_order_id":"20","price_ticks":"101","quantity_units":"5"}
```

Ranges are:

```text
maker_order_id  uint64
taker_order_id  uint64
price_ticks     positive int64 matching-domain price
quantity_units  positive uint64
```

A canonical trace does not add trade IDs, timestamps, venue codes, fees, or settlement metadata.

For a rejected command, `trades` must be the empty array:

```json
[]
```

---

## 12. Resting-order arrays

`bids` and `asks` are the post-command logical resting state.

Each resting-order object has exactly these members in this exact order:

```text
order_id
side
price_ticks
remaining_quantity_units
sequence
```

Example bid:

```json
{"order_id":"7","side":"Buy","price_ticks":"100","remaining_quantity_units":"5","sequence":"1"}
```

Example ask:

```json
{"order_id":"8","side":"Sell","price_ticks":"105","remaining_quantity_units":"4","sequence":"2"}
```

The only permitted `side` strings are:

```text
Buy
Sell
```

Every entry in `bids` must have `"side":"Buy"`.

Every entry in `asks` must have `"side":"Sell"`.

Resting `price_ticks`, `remaining_quantity_units`, and `sequence` must satisfy the active-state domains defined by the matching contract.

### 12.1 Bid order

The producer must supply bids in canonical logical order:

```text
price descending
then sequence ascending
```

### 12.2 Ask order

The producer must supply asks in canonical logical order:

```text
price ascending
then sequence ascending
```

### 12.3 No serializer repair

The serializer must not sort, deduplicate, rewrite, or otherwise repair the supplied resting-order arrays.

Before emission, it must verify that the supplied arrays already satisfy the required canonical logical ordering and field constraints.

If they do not, canonical serialization fails qualification.

A producer defect must not be hidden by serializer normalization.

---

## 13. Sequence allocator representation

`next_sequence` is always an object with exactly these members in this exact order:

```text
state
value
```

### 13.1 Available

When a fresh sequence remains available:

```json
{"state":"available","value":"1"}
```

The `value` is a canonical positive uint64 decimal string.

The state in which `UINT64_MAX` remains the next allocatable value is:

```json
{"state":"available","value":"18446744073709551615"}
```

### 13.2 Exhausted

After `UINT64_MAX` has been allocated:

```json
{"state":"exhausted","value":null}
```

The following representations are invalid:

```text
state=available with null value
state=exhausted with non-null value
state outside available/exhausted
available value 0
available value outside uint64
```

Available-at-maximum and exhausted are distinct logical states and must produce different canonical bytes.

---

## 14. Rejection-state observability

A rejected command record contains the producer's post-command observation.

For an expected DomainError, the reference-model contract requires:

```text
logical post-state == logical pre-state
allocator post-state == allocator pre-state
ordered trades == empty
```

The canonical trace does not omit rejected-command state.

Therefore a rejection record still contains:

```text
trades
bids
asks
next_sequence
```

This makes the resulting post-state observable rather than treating rejection as an error-only line.

The serializer does not invent or restore the pre-state. It serializes the supplied post-command observation after validating canonical representation requirements.

State-equality qualification remains a semantic responsibility of the reference/candidate qualification harness.

---

## 15. Producer-neutrality

For the same raw matching command, the same zero-based `command_index`, and the same logical post-command observation, a conforming C++ producer and a conforming Python producer must be capable of producing byte-identical command records.

Canonical bytes must not depend on:

- language;
- class names;
- enum storage layout;
- map/list/dict representation;
- hash iteration order;
- object identity;
- memory addresses;
- locale;
- wall-clock time;
- host name;
- file-system path;
- process scheduling; or
- logging configuration.

The Python reference may use a flat collection and the C++ candidate may use map/list/index structures. Those physical differences must not appear in canonical bytes.

---

## 16. JSON writer requirements

A conforming v1 writer must construct the schema deliberately.

It must not serialize arbitrary object dictionaries and rely on incidental runtime iteration order.

It must emit object members in the exact orders defined by this contract.

It must emit:

```text
:
```

between each key and value and:

```text
,
```

between adjacent members or array elements, with no surrounding whitespace.

Because v1 schema strings are fixed ASCII literals or canonical decimal strings, a conforming writer must emit those strings exactly as specified. Alternative Unicode escapes for ASCII characters are not canonical.

For example:

```json
"\u006e\u0065\u0077"
```

is semantically the JSON string `new`, but is not canonical v1 encoding for the command kind.

A forward slash must not be escaped unnecessarily.

---

## 17. Canonical validator requirements

A validator deciding whether existing bytes are canonical v1 bytes must perform byte-sensitive validation, not merely semantic JSON equivalence.

At minimum it must reject:

- UTF-8 BOM;
- invalid UTF-8;
- CR or CRLF;
- missing final LF;
- blank lines;
- leading or trailing line whitespace;
- inter-token JSON whitespace;
- non-object top-level records;
- duplicate object member names;
- unknown or missing members;
- wrong object-member order;
- wrong record order;
- missing or repeated header;
- unknown schema or version;
- unknown record type;
- command-index gaps or duplicates;
- non-canonical decimal strings;
- out-of-range field values;
- invalid command shapes;
- invalid result/error combinations;
- invalid trade shapes;
- invalid resting-order shapes;
- wrong side value for a book array;
- non-canonical bid/ask ordering;
- invalid allocator state/value combinations;
- producer/provenance fields inside semantic records; and
- a digest field inside canonical trace bytes.

A validator must not silently rewrite invalid bytes and then declare the original bytes canonical.

One valid implementation strategy is:

1. parse with duplicate-key rejection;
2. validate the closed logical schema and ranges;
3. reserialize through the canonical writer; and
4. require byte-for-byte equality with the original trace.

Equivalent fail-closed strategies are permitted.

---

## 18. Provenance and evidence separation

Canonical semantic bytes intentionally exclude provenance.

An evidence package may separately record values such as:

```text
trace SHA-256
repository
branch
commit
tree
file blobs
runtime version
compiler version
test identity
qualification mode
environment identity
```

Those values are evidence metadata, not canonical matching semantics.

They must not be injected into the trace header or command records.

This separation prevents two correct independent producers from generating different semantic bytes solely because they ran in different environments.

---

## 19. SHA-256 integrity value

When a SHA-256 value is recorded for a canonical trace, it is computed over the exact complete trace byte stream:

```text
first byte = first `{` of the header
last byte  = mandatory LF after the final record
```

The digest therefore includes every record terminator, including the final LF.

The digest is represented externally as 64 lowercase hexadecimal characters.

The digest must not be stored inside the bytes over which it is computed.

No per-record digest is part of v1.

A matching SHA-256 value is an integrity check for byte identity. It is not proof of:

- semantic correctness;
- candidate/reference agreement;
- completeness;
- provenance;
- authenticity; or
- absence of common-mode defects.

---

## 20. Normative examples

The examples in this section are exact canonical lines. Each displayed JSON line is followed by one LF in an actual trace.

### 20.1 Empty command stream

```json
{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1"}
```

No other line is present.

### 20.2 Accepted non-crossing New

```json
{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1"}
{"record_type":"command","command_index":"0","command":{"kind":"new","order_id":"1","side_code":"0","price_ticks":"100","quantity_units":"10"},"command_result":{"accepted":true,"error":null},"trades":[],"bids":[{"order_id":"1","side":"Buy","price_ticks":"100","remaining_quantity_units":"10","sequence":"1"}],"asks":[],"next_sequence":{"state":"available","value":"2"}}
```

### 20.3 Rejected invalid side

The invalid logical side remains observable as raw `side_code` `"17"`:

```json
{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1"}
{"record_type":"command","command_index":"0","command":{"kind":"new","order_id":"9","side_code":"17","price_ticks":"100","quantity_units":"1"},"command_result":{"accepted":false,"error":"InvalidSide"},"trades":[],"bids":[],"asks":[],"next_sequence":{"state":"available","value":"1"}}
```

### 20.4 Maker-price trade

```json
{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1"}
{"record_type":"command","command_index":"0","command":{"kind":"new","order_id":"10","side_code":"1","price_ticks":"101","quantity_units":"5"},"command_result":{"accepted":true,"error":null},"trades":[],"bids":[],"asks":[{"order_id":"10","side":"Sell","price_ticks":"101","remaining_quantity_units":"5","sequence":"1"}],"next_sequence":{"state":"available","value":"2"}}
{"record_type":"command","command_index":"1","command":{"kind":"new","order_id":"20","side_code":"0","price_ticks":"103","quantity_units":"5"},"command_result":{"accepted":true,"error":null},"trades":[{"maker_order_id":"10","taker_order_id":"20","price_ticks":"101","quantity_units":"5"}],"bids":[],"asks":[],"next_sequence":{"state":"available","value":"3"}}
```

The trade price is `"101"`, the resting maker price, not the incoming limit `"103"`.

### 20.5 Maximum sequence still available

```json
{"record_type":"command","command_index":"0","command":{"kind":"cancel","order_id":"999"},"command_result":{"accepted":false,"error":"UnknownOrderId"},"trades":[],"bids":[],"asks":[],"next_sequence":{"state":"available","value":"18446744073709551615"}}
```

This line can occur in a qualification run initialized through the allocator-seed seam. The seed itself is not a matching command record.

### 20.6 Exhausted sequence allocator

```json
{"record_type":"command","command_index":"0","command":{"kind":"cancel","order_id":"999"},"command_result":{"accepted":false,"error":"UnknownOrderId"},"trades":[],"bids":[],"asks":[],"next_sequence":{"state":"exhausted","value":null}}
```

The two allocator examples intentionally produce different bytes.

---

## 21. Non-canonical examples

All examples below are invalid as claimed canonical v1 bytes.

### 21.1 JSON number instead of decimal string

```json
{"record_type":"command","command_index":0}
```

### 21.2 Leading-zero decimal

```json
"0007"
```

### 21.3 Negative zero

```json
"-0"
```

### 21.4 Reordered command-result members

```json
{"error":null,"accepted":true}
```

The logical values are equivalent to an accepted result, but the member order is non-canonical.

### 21.5 Duplicate member

```json
{"accepted":true,"accepted":false,"error":null}
```

Duplicate names are invalid; last-value-wins parsing is forbidden.

### 21.6 Producer metadata

```json
{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1","producer":"python"}
```

The extra member makes the header invalid.

### 21.7 Digest self-reference

```json
{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1","sha256":"..."}
```

A digest is external evidence and cannot be inside canonical bytes.

---

## 22. Serializer failure boundary

Canonical serialization is permitted only for a logical observation that satisfies the canonical representation prerequisites in this contract.

Examples of serializer-contract failures include:

- a non-canonical bid or ask order;
- an invalid resting side;
- a zero resting quantity;
- sequence zero;
- an invalid allocator object;
- an impossible accepted/error combination; or
- a field outside its required representation range.

Such a failure is not a matching `DomainError`.

It is a serializer/qualification failure and must fail closed.

The serializer must not catch such a failure, fabricate a DomainError, and continue with a semantically altered trace.

Resource failures and programming defects are likewise not matching DomainErrors.

---

## 23. Minimum M4 qualification

Before the canonical serializer/validator implementation may be qualified, tests must cover at least the following.

### Byte discipline

- exact empty-stream header bytes;
- strict UTF-8 without BOM;
- LF-only records;
- mandatory final LF;
- rejection of CRLF;
- rejection of missing final LF;
- rejection of blank lines;
- rejection of any inter-token whitespace.

### Object grammar

- exact header member order;
- exact command-record member order;
- exact nested-object member orders;
- missing member rejection;
- unknown member rejection;
- duplicate member rejection;
- semantically equivalent reordered objects rejected as non-canonical;
- alternative Unicode escapes for fixed ASCII member names or fixed ASCII string values rejected as non-canonical, including an escaped spelling of `kind` or `"new"`.

### Record sequence and index

- first command record uses `command_index` `"0"` exactly;
- a first command record using `"1"` is rejected;
- repeated command indexes are rejected;
- skipped command indexes are rejected;
- decreasing command indexes are rejected;
- every command index must equal the zero-based position of its command record among command records.

### Decimal grammar

- `"0"` accepted where zero is in the field domain;
- leading zero rejected;
- leading plus rejected;
- `-0` rejected;
- exponent and fractional syntax rejected;
- int64 minimum and maximum represented exactly;
- uint64 maximum represented exactly;
- value one beyond each fixed-width boundary rejected;
- side code `255` represented exactly.

### Commands and results

- New, Cancel, and Modify exact command shapes;
- caller sequence field rejected by the qualification boundary;
- an invalid side code is preserved in raw command evidence;
- accepted result uses `true/null`;
- rejected result uses `false/exact-error`;
- every frozen DomainError name round-trips exactly;
- unknown error name rejected;
- malformed qualification input creates no semantic command record.

### Trades and books

- zero trades;
- one trade;
- multiple trades preserve exact emission order;
- maker and taker IDs remain distinct fields;
- maker execution price preserved;
- bid order is price-descending then sequence-ascending;
- ask order is price-ascending then sequence-ascending;
- equal-price FIFO order preserved;
- serializer does not sort deliberately permuted non-canonical input;
- deliberately permuted non-canonical input fails serialization;
- wrong-side entry in bids or asks fails serialization.

### Allocator

- ordinary available sequence;
- `UINT64_MAX` available;
- exhausted state;
- available-at-maximum differs bytewise from exhausted;
- available with null rejected;
- exhausted with non-null value rejected;
- available zero rejected.

### Rejection observation

- rejected command emits empty trades;
- rejected command serializes bids, asks, and allocator state;
- rejection-state evidence is not replaced by an error-only record.

### Producer neutrality and evidence separation

- no producer identifier in semantic bytes;
- no timestamp in semantic bytes;
- no Git identity in semantic bytes;
- no runtime identity in semantic bytes;
- no digest field in semantic bytes;
- SHA-256 over exact bytes changes if any canonical byte changes;
- final LF participates in the digest.

### Determinism

- repeated serialization of one immutable logical observation yields exactly equal bytes;
- validator accepts canonical writer output;
- parse/validate/reserialize of canonical bytes is byte-identical;
- validator rejects an input that it would need to repair before reserialization;
- at least one complete one-command trace and one complete two-command trace are compared byte-for-byte against independently reviewed literal expected bytes;
- the two-command known-answer fixture covers `command_index` `"0"` followed by `"1"` and uses the literal, unescaped ASCII command-kind spelling required by v1.

Passing these cases qualifies only the covered canonical serializer/validator behaviour. It is not universal proof over all possible values or byte strings.

---

## 24. Change control

Any change to:

- schema name or version;
- record sequence;
- field names;
- field order;
- decimal grammar;
- permitted string vocabulary;
- array ordering;
- allocator representation;
- byte encoding;
- whitespace rules;
- provenance exclusion; or
- digest boundary

changes the canonical evidence contract and requires explicit architecture review and qualification-impact analysis.

A schema-breaking change must not silently retain version `"1"`.

Implementation convenience and performance are not sufficient reasons to weaken exact-byte determinism or producer neutrality.

---

## 25. Non-claims

This contract does not establish:

- correctness of the C++ candidate;
- correctness of the Python reference implementation;
- candidate/reference differential agreement;
- universal correctness;
- formal verification;
- real-exchange fidelity;
- production readiness;
- replay closure;
- provenance authenticity;
- cryptographic signing;
- low latency;
- high throughput;
- HFT suitability;
- concurrency correctness;
- persistence correctness; or
- networking correctness.

Those require separate implementation and evidence gates.

---

## 26. Freeze rule

After qualification, changes to this contract require explicit architecture review and qualification-impact analysis.

No serializer implementation, test convenience, benchmark objective, or producer-specific representation may silently redefine canonical v1 bytes.
