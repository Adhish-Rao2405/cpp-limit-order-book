"""Independent M5 differential comparator and process harness.

This module is deliberately standard-library only and contains no matching
implementation. Producer outputs are validated independently, then their
original raw bytes are compared without normalization or repair.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


SUCCESS_TRACE = 0
MALFORMED_TRANSPORT = 10
SERIALIZER_FAILURE = 20
QUALIFICATION_INTERNAL_FAILURE = 30
IO_RUNTIME_FAILURE = 40

CLASS_MALFORMED_INPUT = 1
CLASS_CANDIDATE_ADAPTER = 2
CLASS_CANDIDATE_DOMAIN = 3
CLASS_REFERENCE_QUALIFICATION = 4
CLASS_REFERENCE_DOMAIN = 5
CLASS_CANDIDATE_SERIALIZER = 6
CLASS_REFERENCE_SERIALIZER = 7
CLASS_HARNESS = 8
CLASS_CANONICAL_MISMATCH = 9
CLASS_LOGICAL_MISMATCH = 10
CLASS_PROCESS_RUNTIME = 11

UINT8_MAX = 2**8 - 1
UINT64_MAX = 2**64 - 1
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

HEADER_OBJECT = {
    "record_type": "trace_header",
    "schema": "lob.canonical_trace",
    "version": "1",
}

DOMAIN_ERRORS = {
    "InvalidPrice",
    "InvalidQuantity",
    "InvalidSide",
    "DuplicateOrderId",
    "UnknownOrderId",
    "SequenceExhausted",
    "InvalidModification",
}


class CanonicalValidationError(ValueError):
    """Claimed canonical-v1 bytes fail the independent comparator validator."""


class _JSONObject(list):
    """Ordered JSON object pairs, preserving duplicate keys for rejection."""


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    spawn_error: str | None


@dataclass(frozen=True)
class DifferentialResult:
    outcome: str
    classification: int | None
    detail: str

    input_sha256: str

    candidate_returncode: int | None
    reference_returncode: int | None

    candidate_trace_sha256: str | None
    reference_trace_sha256: str | None

    candidate_trace_bytes: int | None
    reference_trace_bytes: int | None

    first_differing_byte_offset: int | None
    first_differing_record: int | None
    first_differing_logical_field: str | None
    logical_difference_observed: bool | None

    candidate_stdout: str
    candidate_stderr: str
    reference_stdout: str
    reference_stderr: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_diagnostic(data: bytes) -> str:
    return data.decode(
        "utf-8",
        errors="replace",
    )


def _reject_json_constant(_: str) -> None:
    raise CanonicalValidationError(
        "non-standard JSON constant forbidden"
    )


def _load_json_object(
    line: bytes,
    field: str,
) -> _JSONObject:
    try:
        text = line.decode(
            "utf-8",
            errors="strict",
        )

        value = json.loads(
            text,
            object_pairs_hook=_JSONObject,
            parse_constant=_reject_json_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise CanonicalValidationError(
            f"{field} is not strict JSON"
        ) from exc

    if type(value) is not _JSONObject:
        raise CanonicalValidationError(
            f"{field} must be a JSON object"
        )

    return value


def _expect_object(
    value: object,
    keys: tuple[str, ...],
    field: str,
) -> dict[str, object]:
    if type(value) is not _JSONObject:
        raise CanonicalValidationError(
            f"{field} must be a JSON object"
        )

    actual_keys = tuple(
        pair[0]
        for pair in value
    )

    if actual_keys != keys:
        raise CanonicalValidationError(
            f"{field} has missing, duplicate, "
            "unknown, or reordered members"
        )

    return {
        key: item
        for key, item in value
    }


def _canonical_unsigned_text(
    value: object,
    *,
    minimum: int,
    maximum: int | None,
    field: str,
) -> int:
    if type(value) is not str:
        raise CanonicalValidationError(
            f"{field} must be a JSON string"
        )

    if value == "0":
        parsed = 0
    else:
        if (
            not value
            or not "1" <= value[0] <= "9"
            or any(
                not "0" <= character <= "9"
                for character in value[1:]
            )
        ):
            raise CanonicalValidationError(
                f"{field} is not canonical unsigned decimal"
            )

        parsed = int(value, 10)

    if parsed < minimum:
        raise CanonicalValidationError(
            f"{field} below range"
        )

    if (
        maximum is not None
        and parsed > maximum
    ):
        raise CanonicalValidationError(
            f"{field} above range"
        )

    return parsed


def _canonical_signed_text(
    value: object,
    *,
    minimum: int,
    maximum: int,
    field: str,
) -> int:
    if type(value) is not str:
        raise CanonicalValidationError(
            f"{field} must be a JSON string"
        )

    if value == "0":
        parsed = 0
    elif value.startswith("-"):
        magnitude = value[1:]

        if (
            not magnitude
            or magnitude == "0"
            or not "1" <= magnitude[0] <= "9"
            or any(
                not "0" <= character <= "9"
                for character in magnitude[1:]
            )
        ):
            raise CanonicalValidationError(
                f"{field} is not canonical signed decimal"
            )

        parsed = -int(
            magnitude,
            10,
        )
    else:
        if (
            not value
            or not "1" <= value[0] <= "9"
            or any(
                not "0" <= character <= "9"
                for character in value[1:]
            )
        ):
            raise CanonicalValidationError(
                f"{field} is not canonical signed decimal"
            )

        parsed = int(value, 10)

    if not minimum <= parsed <= maximum:
        raise CanonicalValidationError(
            f"{field} outside range"
        )

    return parsed


def _parse_command(
    value: object,
) -> dict[str, object]:
    if type(value) is not _JSONObject:
        raise CanonicalValidationError(
            "command must be a JSON object"
        )

    keys = tuple(
        pair[0]
        for pair in value
    )

    if not keys or keys[0] != "kind":
        raise CanonicalValidationError(
            "command member order invalid"
        )

    raw = {
        key: item
        for key, item in value
    }

    kind = raw.get("kind")

    if kind == "new":
        obj = _expect_object(
            value,
            (
                "kind",
                "order_id",
                "side_code",
                "price_ticks",
                "quantity_units",
            ),
            "command",
        )

        _canonical_unsigned_text(
            obj["order_id"],
            minimum=0,
            maximum=UINT64_MAX,
            field="command.order_id",
        )

        _canonical_unsigned_text(
            obj["side_code"],
            minimum=0,
            maximum=UINT8_MAX,
            field="command.side_code",
        )

        _canonical_signed_text(
            obj["price_ticks"],
            minimum=INT64_MIN,
            maximum=INT64_MAX,
            field="command.price_ticks",
        )

        _canonical_unsigned_text(
            obj["quantity_units"],
            minimum=0,
            maximum=UINT64_MAX,
            field="command.quantity_units",
        )

        return obj

    if kind == "cancel":
        obj = _expect_object(
            value,
            (
                "kind",
                "order_id",
            ),
            "command",
        )

        _canonical_unsigned_text(
            obj["order_id"],
            minimum=0,
            maximum=UINT64_MAX,
            field="command.order_id",
        )

        return obj

    if kind == "modify":
        obj = _expect_object(
            value,
            (
                "kind",
                "order_id",
                "price_ticks",
                "quantity_units",
            ),
            "command",
        )

        _canonical_unsigned_text(
            obj["order_id"],
            minimum=0,
            maximum=UINT64_MAX,
            field="command.order_id",
        )

        _canonical_signed_text(
            obj["price_ticks"],
            minimum=INT64_MIN,
            maximum=INT64_MAX,
            field="command.price_ticks",
        )

        _canonical_unsigned_text(
            obj["quantity_units"],
            minimum=0,
            maximum=UINT64_MAX,
            field="command.quantity_units",
        )

        return obj

    raise CanonicalValidationError(
        "command kind outside closed v1 vocabulary"
    )


def _parse_result(
    value: object,
) -> dict[str, object]:
    obj = _expect_object(
        value,
        (
            "accepted",
            "error",
        ),
        "command_result",
    )

    accepted = obj["accepted"]
    error = obj["error"]

    if type(accepted) is not bool:
        raise CanonicalValidationError(
            "command_result.accepted must be boolean"
        )

    if accepted:
        if error is not None:
            raise CanonicalValidationError(
                "accepted result requires null error"
            )
    else:
        if (
            type(error) is not str
            or error not in DOMAIN_ERRORS
        ):
            raise CanonicalValidationError(
                "rejected result requires frozen DomainError"
            )

    return obj


def _parse_trade(
    value: object,
) -> dict[str, object]:
    obj = _expect_object(
        value,
        (
            "maker_order_id",
            "taker_order_id",
            "price_ticks",
            "quantity_units",
        ),
        "trade",
    )

    _canonical_unsigned_text(
        obj["maker_order_id"],
        minimum=0,
        maximum=UINT64_MAX,
        field="trade.maker_order_id",
    )

    _canonical_unsigned_text(
        obj["taker_order_id"],
        minimum=0,
        maximum=UINT64_MAX,
        field="trade.taker_order_id",
    )

    _canonical_signed_text(
        obj["price_ticks"],
        minimum=1,
        maximum=INT64_MAX,
        field="trade.price_ticks",
    )

    _canonical_unsigned_text(
        obj["quantity_units"],
        minimum=1,
        maximum=UINT64_MAX,
        field="trade.quantity_units",
    )

    return obj


def _parse_resting_order(
    value: object,
    expected_side: str,
) -> tuple[
    dict[str, object],
    int,
    int,
]:
    obj = _expect_object(
        value,
        (
            "order_id",
            "side",
            "price_ticks",
            "remaining_quantity_units",
            "sequence",
        ),
        "resting_order",
    )

    _canonical_unsigned_text(
        obj["order_id"],
        minimum=0,
        maximum=UINT64_MAX,
        field="resting.order_id",
    )

    if obj["side"] != expected_side:
        raise CanonicalValidationError(
            "resting order in wrong side array"
        )

    price = _canonical_signed_text(
        obj["price_ticks"],
        minimum=1,
        maximum=INT64_MAX,
        field="resting.price_ticks",
    )

    _canonical_unsigned_text(
        obj["remaining_quantity_units"],
        minimum=1,
        maximum=UINT64_MAX,
        field="resting.remaining_quantity_units",
    )

    sequence = _canonical_unsigned_text(
        obj["sequence"],
        minimum=1,
        maximum=UINT64_MAX,
        field="resting.sequence",
    )

    return obj, price, sequence


def _parse_allocator(
    value: object,
) -> dict[str, object]:
    obj = _expect_object(
        value,
        (
            "state",
            "value",
        ),
        "next_sequence",
    )

    state = obj["state"]

    if state == "available":
        _canonical_unsigned_text(
            obj["value"],
            minimum=1,
            maximum=UINT64_MAX,
            field="next_sequence.value",
        )
        return obj

    if state == "exhausted":
        if obj["value"] is not None:
            raise CanonicalValidationError(
                "exhausted allocator requires null"
            )

        return obj

    raise CanonicalValidationError(
        "allocator state outside closed vocabulary"
    )


def validate_canonical_trace(
    data: bytes,
) -> tuple[dict[str, object], ...]:
    """Independently validate exact canonical-v1 bytes."""

    if type(data) is not bytes:
        raise CanonicalValidationError(
            "canonical trace must be exact bytes"
        )

    if data.startswith(b"\xef\xbb\xbf"):
        raise CanonicalValidationError(
            "UTF-8 BOM forbidden"
        )

    if b"\r" in data:
        raise CanonicalValidationError(
            "CR forbidden"
        )

    if any(value > 0x7F for value in data):
        raise CanonicalValidationError(
            "canonical v1 must remain ASCII"
        )

    if not data.endswith(b"\n"):
        raise CanonicalValidationError(
            "mandatory final LF missing"
        )

    lines = data.split(b"\n")

    if lines[-1] != b"":
        raise CanonicalValidationError(
            "trace terminator malformed"
        )

    records = lines[:-1]

    if (
        not records
        or any(
            line == b""
            for line in records
        )
    ):
        raise CanonicalValidationError(
            "trace requires header and no blank lines"
        )

    for line in records:
        if any(
            value in b" \t\v\f"
            for value in line
        ):
            raise CanonicalValidationError(
                "canonical v1 forbids JSON whitespace"
            )

        if b"\\" in line:
            raise CanonicalValidationError(
                "canonical v1 forbids JSON escape syntax"
            )

    header = _expect_object(
        _load_json_object(
            records[0],
            "trace_header",
        ),
        (
            "record_type",
            "schema",
            "version",
        ),
        "trace_header",
    )

    if header != HEADER_OBJECT:
        raise CanonicalValidationError(
            "trace header fixed values invalid"
        )

    logical_records: list[
        dict[str, object]
    ] = [header]

    for position, raw_line in enumerate(
        records[1:]
    ):
        record = _expect_object(
            _load_json_object(
                raw_line,
                f"command_record[{position}]",
            ),
            (
                "record_type",
                "command_index",
                "command",
                "command_result",
                "trades",
                "bids",
                "asks",
                "next_sequence",
            ),
            "command_record",
        )

        if record["record_type"] != "command":
            raise CanonicalValidationError(
                "non-header record type invalid"
            )

        command_index = (
            _canonical_unsigned_text(
                record["command_index"],
                minimum=0,
                maximum=None,
                field="command_index",
            )
        )

        if command_index != position:
            raise CanonicalValidationError(
                "command_index must equal position"
            )

        command = _parse_command(
            record["command"]
        )

        result = _parse_result(
            record["command_result"]
        )

        trades_raw = record["trades"]
        bids_raw = record["bids"]
        asks_raw = record["asks"]

        if (
            type(trades_raw) is not list
            or type(bids_raw) is not list
            or type(asks_raw) is not list
        ):
            raise CanonicalValidationError(
                "trades/bids/asks must be arrays"
            )

        trades = [
            _parse_trade(item)
            for item in trades_raw
        ]

        if (
            result["accepted"] is False
            and trades
        ):
            raise CanonicalValidationError(
                "rejected command cannot have trades"
            )

        bids: list[
            dict[str, object]
        ] = []

        previous_bid: tuple[int, int] | None = None

        for item in bids_raw:
            parsed, price, sequence = (
                _parse_resting_order(
                    item,
                    "Buy",
                )
            )

            current = (
                -price,
                sequence,
            )

            if (
                previous_bid is not None
                and current < previous_bid
            ):
                raise CanonicalValidationError(
                    "bids not in canonical order"
                )

            previous_bid = current
            bids.append(parsed)

        asks: list[
            dict[str, object]
        ] = []

        previous_ask: tuple[int, int] | None = None

        for item in asks_raw:
            parsed, price, sequence = (
                _parse_resting_order(
                    item,
                    "Sell",
                )
            )

            current = (
                price,
                sequence,
            )

            if (
                previous_ask is not None
                and current < previous_ask
            ):
                raise CanonicalValidationError(
                    "asks not in canonical order"
                )

            previous_ask = current
            asks.append(parsed)

        allocator = _parse_allocator(
            record["next_sequence"]
        )

        logical_records.append(
            {
                "record_type": "command",
                "command_index": str(position),
                "command": command,
                "command_result": result,
                "trades": trades,
                "bids": bids,
                "asks": asks,
                "next_sequence": allocator,
            }
        )

    return tuple(logical_records)


def _first_differing_byte(
    left: bytes,
    right: bytes,
) -> int | None:
    common = min(
        len(left),
        len(right),
    )

    for index in range(common):
        if left[index] != right[index]:
            return index

    if len(left) != len(right):
        return common

    return None


def _first_differing_record(
    left: bytes,
    right: bytes,
) -> int | None:
    left_records = left.splitlines(
        keepends=True
    )
    right_records = right.splitlines(
        keepends=True
    )

    common = min(
        len(left_records),
        len(right_records),
    )

    for index in range(common):
        if (
            left_records[index]
            != right_records[index]
        ):
            return index

    if (
        len(left_records)
        != len(right_records)
    ):
        return common

    return None


def _first_logical_difference(
    left: object,
    right: object,
    path: str = "$",
) -> str | None:
    if type(left) is not type(right):
        return path

    if type(left) is dict:
        left_dict = left
        right_dict = right

        if tuple(left_dict) != tuple(right_dict):
            return path

        for key in left_dict:
            difference = (
                _first_logical_difference(
                    left_dict[key],
                    right_dict[key],
                    f"{path}.{key}",
                )
            )

            if difference is not None:
                return difference

        return None

    if type(left) is list or type(left) is tuple:
        if len(left) != len(right):
            return path

        for index, (
            left_item,
            right_item,
        ) in enumerate(
            zip(
                left,
                right,
                strict=True,
            )
        ):
            difference = (
                _first_logical_difference(
                    left_item,
                    right_item,
                    f"{path}[{index}]",
                )
            )

            if difference is not None:
                return difference

        return None

    if left != right:
        return path

    return None


def _execute_once(
    argv: Sequence[str],
    timeout_seconds: float,
) -> ProcessResult:
    try:
        completed = subprocess.run(
            list(argv),
            shell=False,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
        )

        return ProcessResult(
            argv=tuple(argv),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
            spawn_error=None,
        )
    except subprocess.TimeoutExpired as exc:
        return ProcessResult(
            argv=tuple(argv),
            returncode=None,
            stdout=(
                exc.stdout
                if type(exc.stdout) is bytes
                else b""
            ),
            stderr=(
                exc.stderr
                if type(exc.stderr) is bytes
                else b""
            ),
            timed_out=True,
            spawn_error=None,
        )
    except OSError as exc:
        return ProcessResult(
            argv=tuple(argv),
            returncode=None,
            stdout=b"",
            stderr=b"",
            timed_out=False,
            spawn_error=str(exc),
        )


def _expand_command(
    template: Sequence[str],
    input_path: Path,
    trace_path: Path,
) -> tuple[str, ...]:
    joined = "\0".join(template)

    if joined.count("{input}") != 1:
        raise ValueError(
            "command template requires exactly one {input}"
        )

    if joined.count("{trace}") != 1:
        raise ValueError(
            "command template requires exactly one {trace}"
        )

    return tuple(
        part.replace(
            "{input}",
            str(input_path),
        ).replace(
            "{trace}",
            str(trace_path),
        )
        for part in template
    )


def _make_result(
    *,
    outcome: str,
    classification: int | None,
    detail: str,
    input_sha256: str,
    candidate: ProcessResult,
    reference: ProcessResult,
    candidate_trace: bytes | None = None,
    reference_trace: bytes | None = None,
    first_byte: int | None = None,
    first_record: int | None = None,
    first_field: str | None = None,
    logical_difference: bool | None = None,
) -> DifferentialResult:
    return DifferentialResult(
        outcome=outcome,
        classification=classification,
        detail=detail,
        input_sha256=input_sha256,
        candidate_returncode=(
            candidate.returncode
        ),
        reference_returncode=(
            reference.returncode
        ),
        candidate_trace_sha256=(
            _sha256(candidate_trace)
            if candidate_trace is not None
            else None
        ),
        reference_trace_sha256=(
            _sha256(reference_trace)
            if reference_trace is not None
            else None
        ),
        candidate_trace_bytes=(
            len(candidate_trace)
            if candidate_trace is not None
            else None
        ),
        reference_trace_bytes=(
            len(reference_trace)
            if reference_trace is not None
            else None
        ),
        first_differing_byte_offset=first_byte,
        first_differing_record=first_record,
        first_differing_logical_field=first_field,
        logical_difference_observed=logical_difference,
        candidate_stdout=_decode_diagnostic(
            candidate.stdout
        ),
        candidate_stderr=_decode_diagnostic(
            candidate.stderr
        ),
        reference_stdout=_decode_diagnostic(
            reference.stdout
        ),
        reference_stderr=_decode_diagnostic(
            reference.stderr
        ),
    )


def _classify_nonzero(
    role: str,
    returncode: int,
) -> int:
    if role == "candidate":
        if returncode == MALFORMED_TRANSPORT:
            return CLASS_CANDIDATE_ADAPTER

        if returncode == SERIALIZER_FAILURE:
            return CLASS_CANDIDATE_SERIALIZER

        if returncode == QUALIFICATION_INTERNAL_FAILURE:
            return CLASS_CANDIDATE_ADAPTER
    else:
        if returncode == MALFORMED_TRANSPORT:
            return CLASS_REFERENCE_QUALIFICATION

        if returncode == SERIALIZER_FAILURE:
            return CLASS_REFERENCE_SERIALIZER

        if returncode == QUALIFICATION_INTERNAL_FAILURE:
            return CLASS_REFERENCE_QUALIFICATION

    return CLASS_PROCESS_RUNTIME


def _run_in_directory(
    *,
    source_input: Path,
    source_bytes: bytes,
    input_sha: str,
    candidate_template: Sequence[str],
    reference_template: Sequence[str],
    expected_malformed: bool,
    timeout_seconds: float,
    directory: Path,
) -> DifferentialResult:
    candidate_input = (
        directory / "candidate-input.lobq1"
    )
    reference_input = (
        directory / "reference-input.lobq1"
    )

    candidate_trace_path = (
        directory / "candidate-trace.jsonl"
    )
    reference_trace_path = (
        directory / "reference-trace.jsonl"
    )

    empty = ProcessResult(
        argv=(),
        returncode=None,
        stdout=b"",
        stderr=b"",
        timed_out=False,
        spawn_error=None,
    )

    try:
        candidate_input.write_bytes(
            source_bytes
        )
        reference_input.write_bytes(
            source_bytes
        )

        candidate_initial = (
            candidate_input.read_bytes()
        )
        reference_initial = (
            reference_input.read_bytes()
        )
    except OSError as exc:
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "input byte identity setup failed: "
                + str(exc)
            ),
            input_sha256=input_sha,
            candidate=empty,
            reference=empty,
        )

    if (
        candidate_initial != source_bytes
        or reference_initial != source_bytes
        or _sha256(candidate_initial) != input_sha
        or _sha256(reference_initial) != input_sha
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail="input byte identity setup failed",
            input_sha256=input_sha,
            candidate=empty,
            reference=empty,
        )

    try:
        candidate_command = _expand_command(
            candidate_template,
            candidate_input,
            candidate_trace_path,
        )

        reference_command = _expand_command(
            reference_template,
            reference_input,
            reference_trace_path,
        )
    except ValueError as exc:
        empty = ProcessResult(
            argv=(),
            returncode=None,
            stdout=b"",
            stderr=b"",
            timed_out=False,
            spawn_error=None,
        )

        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=str(exc),
            input_sha256=input_sha,
            candidate=empty,
            reference=empty,
        )

    candidate = _execute_once(
        candidate_command,
        timeout_seconds,
    )

    reference = _execute_once(
        reference_command,
        timeout_seconds,
    )

    try:
        source_after = (
            source_input.read_bytes()
        )
        candidate_after = (
            candidate_input.read_bytes()
        )
        reference_after = (
            reference_input.read_bytes()
        )
    except OSError as exc:
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "input re-read failed: "
                + str(exc)
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if (
        source_after != source_bytes
        or candidate_after != source_bytes
        or reference_after != source_bytes
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "qualification input bytes "
                "changed during producer execution"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if (
        candidate.timed_out
        or reference.timed_out
        or candidate.spawn_error is not None
        or reference.spawn_error is not None
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_PROCESS_RUNTIME,
            detail=(
                "producer timeout or spawn failure"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    try:
        try:
            candidate_trace_stat = (
                candidate_trace_path.lstat()
            )
        except FileNotFoundError:
            candidate_trace_stat = None

        try:
            reference_trace_stat = (
                reference_trace_path.lstat()
            )
        except FileNotFoundError:
            reference_trace_stat = None
    except OSError as exc:
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "trace metadata read failed: "
                + str(exc)
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    candidate_trace_exists = (
        candidate_trace_stat is not None
    )
    reference_trace_exists = (
        reference_trace_stat is not None
    )

    if (
        candidate.returncode == SUCCESS_TRACE
        and not candidate_trace_exists
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "candidate reported success "
                "without trace"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if (
        reference.returncode == SUCCESS_TRACE
        and not reference_trace_exists
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "reference reported success "
                "without trace"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if (
        candidate.returncode != SUCCESS_TRACE
        and candidate_trace_exists
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "candidate emitted trace "
                "despite nonzero status"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if (
        reference.returncode != SUCCESS_TRACE
        and reference_trace_exists
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "reference emitted trace "
                "despite nonzero status"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if (
        candidate_trace_stat is not None
        and not stat.S_ISREG(
            candidate_trace_stat.st_mode
        )
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "candidate trace is not "
                "a regular file"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if (
        reference_trace_stat is not None
        and not stat.S_ISREG(
            reference_trace_stat.st_mode
        )
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "reference trace is not "
                "a regular file"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if (
        candidate_trace_stat is not None
        and reference_trace_stat is not None
        and os.path.samestat(
            candidate_trace_stat,
            reference_trace_stat,
        )
    ):
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "candidate/reference trace paths "
                "alias the same filesystem object"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if expected_malformed:
        if (
            candidate.returncode
            == MALFORMED_TRANSPORT
            and reference.returncode
            == MALFORMED_TRANSPORT
        ):
            return _make_result(
                outcome="PASS",
                classification=CLASS_MALFORMED_INPUT,
                detail=(
                    "both independent parsers "
                    "rejected malformed transport"
                ),
                input_sha256=input_sha,
                candidate=candidate,
                reference=reference,
            )

        if (
            candidate.returncode
            != MALFORMED_TRANSPORT
        ):
            classification = (
                CLASS_CANDIDATE_ADAPTER
                if candidate.returncode
                == SUCCESS_TRACE
                else _classify_nonzero(
                    "candidate",
                    candidate.returncode,
                )
            )

            return _make_result(
                outcome="HOLD",
                classification=classification,
                detail=(
                    "candidate did not classify "
                    "expected malformed transport"
                ),
                input_sha256=input_sha,
                candidate=candidate,
                reference=reference,
            )

        classification = (
            CLASS_REFERENCE_QUALIFICATION
            if reference.returncode
            == SUCCESS_TRACE
            else _classify_nonzero(
                "reference",
                reference.returncode,
            )
        )

        return _make_result(
            outcome="HOLD",
            classification=classification,
            detail=(
                "reference did not classify "
                "expected malformed transport"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if candidate.returncode != SUCCESS_TRACE:
        return _make_result(
            outcome="HOLD",
            classification=_classify_nonzero(
                "candidate",
                candidate.returncode,
            ),
            detail=(
                "candidate producer failed "
                "on expected valid transport"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    if reference.returncode != SUCCESS_TRACE:
        return _make_result(
            outcome="HOLD",
            classification=_classify_nonzero(
                "reference",
                reference.returncode,
            ),
            detail=(
                "reference producer failed "
                "on expected valid transport"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    try:
        candidate_trace = (
            candidate_trace_path.read_bytes()
        )
        reference_trace = (
            reference_trace_path.read_bytes()
        )
    except OSError as exc:
        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "trace file read failed: "
                + str(exc)
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
        )

    try:
        candidate_logical = (
            validate_canonical_trace(
                candidate_trace
            )
        )
    except CanonicalValidationError as exc:
        return _make_result(
            outcome="HOLD",
            classification=CLASS_CANDIDATE_SERIALIZER,
            detail=(
                "candidate trace is not "
                "canonical-v1: "
                + str(exc)
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
            candidate_trace=candidate_trace,
            reference_trace=reference_trace,
        )

    try:
        reference_logical = (
            validate_canonical_trace(
                reference_trace
            )
        )
    except CanonicalValidationError as exc:
        return _make_result(
            outcome="HOLD",
            classification=CLASS_REFERENCE_SERIALIZER,
            detail=(
                "reference trace is not "
                "canonical-v1: "
                + str(exc)
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
            candidate_trace=candidate_trace,
            reference_trace=reference_trace,
        )

    if candidate_trace == reference_trace:
        return _make_result(
            outcome="PASS",
            classification=None,
            detail=(
                "candidate/reference canonical "
                "bytes exactly equal"
            ),
            input_sha256=input_sha,
            candidate=candidate,
            reference=reference,
            candidate_trace=candidate_trace,
            reference_trace=reference_trace,
            logical_difference=False,
        )

    first_field = (
        _first_logical_difference(
            candidate_logical,
            reference_logical,
        )
    )

    return _make_result(
        outcome="HOLD",
        classification=CLASS_CANONICAL_MISMATCH,
        detail=(
            "canonical byte mismatch; "
            "logical diagnostics cannot "
            "override Class 9"
        ),
        input_sha256=input_sha,
        candidate=candidate,
        reference=reference,
        candidate_trace=candidate_trace,
        reference_trace=reference_trace,
        first_byte=_first_differing_byte(
            candidate_trace,
            reference_trace,
        ),
        first_record=_first_differing_record(
            candidate_trace,
            reference_trace,
        ),
        first_field=first_field,
        logical_difference=(
            first_field is not None
        ),
    )


def run_differential_case(
    *,
    source_input: Path,
    candidate_template: Sequence[str],
    reference_template: Sequence[str],
    expected_malformed: bool,
    timeout_seconds: float,
    work_directory: Path | None = None,
) -> DifferentialResult:
    """Execute one preregistered stream once per producer."""

    try:
        source_input = (
            source_input.resolve(
                strict=True
            )
        )
    except OSError as exc:
        empty = ProcessResult(
            argv=(),
            returncode=None,
            stdout=b"",
            stderr=b"",
            timed_out=False,
            spawn_error=None,
        )

        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "source input unavailable: "
                + str(exc)
            ),
            input_sha256="",
            candidate=empty,
            reference=empty,
        )

    try:
        source_bytes = source_input.read_bytes()
    except OSError as exc:
        empty = ProcessResult(
            argv=(),
            returncode=None,
            stdout=b"",
            stderr=b"",
            timed_out=False,
            spawn_error=None,
        )

        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "source input read failed: "
                + str(exc)
            ),
            input_sha256="",
            candidate=empty,
            reference=empty,
        )

    input_sha = _sha256(source_bytes)

    if timeout_seconds <= 0:
        empty = ProcessResult(
            argv=(),
            returncode=None,
            stdout=b"",
            stderr=b"",
            timed_out=False,
            spawn_error=None,
        )

        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail="timeout must be positive",
            input_sha256=input_sha,
            candidate=empty,
            reference=empty,
        )

    if work_directory is None:
        try:
            with tempfile.TemporaryDirectory(
                prefix="lob-m5d-"
            ) as temporary:
                return _run_in_directory(
                    source_input=source_input,
                    source_bytes=source_bytes,
                    input_sha=input_sha,
                    candidate_template=(
                        candidate_template
                    ),
                    reference_template=(
                        reference_template
                    ),
                    expected_malformed=(
                        expected_malformed
                    ),
                    timeout_seconds=timeout_seconds,
                    directory=Path(temporary),
                )
        except OSError as exc:
            empty = ProcessResult(
                argv=(),
                returncode=None,
                stdout=b"",
                stderr=b"",
                timed_out=False,
                spawn_error=None,
            )

            return _make_result(
                outcome="HOLD",
                classification=CLASS_HARNESS,
                detail=(
                    "temporary work directory "
                    "failure: "
                    + str(exc)
                ),
                input_sha256=input_sha,
                candidate=empty,
                reference=empty,
            )

    try:
        work_directory = (
            work_directory.resolve(
                strict=False
            )
        )

        work_directory.mkdir(
            parents=True,
            exist_ok=False,
        )
    except OSError as exc:
        empty = ProcessResult(
            argv=(),
            returncode=None,
            stdout=b"",
            stderr=b"",
            timed_out=False,
            spawn_error=None,
        )

        return _make_result(
            outcome="HOLD",
            classification=CLASS_HARNESS,
            detail=(
                "work directory creation failed: "
                + str(exc)
            ),
            input_sha256=input_sha,
            candidate=empty,
            reference=empty,
        )

    return _run_in_directory(
        source_input=source_input,
        source_bytes=source_bytes,
        input_sha=input_sha,
        candidate_template=candidate_template,
        reference_template=reference_template,
        expected_malformed=expected_malformed,
        timeout_seconds=timeout_seconds,
        directory=work_directory,
    )


def _parse_arguments(
    argv: Sequence[str],
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "M5 independent differential "
            "comparator/harness"
        )
    )

    parser.add_argument(
        "--candidate-runner",
        required=True,
    )

    parser.add_argument(
        "--reference-runner",
        required=True,
    )

    parser.add_argument(
        "--input",
        required=True,
    )

    parser.add_argument(
        "--mode",
        choices=(
            "valid",
            "malformed",
        ),
        required=True,
    )

    parser.add_argument(
        "--python",
        default=sys.executable,
    )

    parser.add_argument(
        "--reference-optimize",
        action="store_true",
    )

    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
    )

    parser.add_argument(
        "--work-directory",
    )

    return parser.parse_args(
        list(argv)
    )


def main(argv: Sequence[str]) -> int:
    arguments = _parse_arguments(
        argv
    )

    candidate_runner = str(
        Path(
            arguments.candidate_runner
        ).resolve()
    )

    reference_runner = str(
        Path(
            arguments.reference_runner
        ).resolve()
    )

    reference_template: list[str] = [
        arguments.python,
        "-B",
    ]

    if arguments.reference_optimize:
        reference_template.append(
            "-O"
        )

    reference_template.extend(
        (
            reference_runner,
            "{input}",
            "{trace}",
        )
    )

    result = run_differential_case(
        source_input=Path(
            arguments.input
        ),
        candidate_template=(
            candidate_runner,
            "{input}",
            "{trace}",
        ),
        reference_template=tuple(
            reference_template
        ),
        expected_malformed=(
            arguments.mode
            == "malformed"
        ),
        timeout_seconds=(
            arguments.timeout_seconds
        ),
        work_directory=(
            Path(
                arguments.work_directory
            )
            if arguments.work_directory
            else None
        ),
    )

    print(
        json.dumps(
            asdict(result),
            sort_keys=True,
            separators=(",", ":"),
        )
    )

    return (
        0
        if result.outcome == "PASS"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main(sys.argv[1:])
    )
