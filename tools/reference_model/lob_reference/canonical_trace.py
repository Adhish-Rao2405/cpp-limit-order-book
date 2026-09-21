"""Producer-neutral canonical JSONL trace writer and byte-sensitive validator."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from .types import (
    INT64_MAX,
    INT64_MIN,
    UINT8_MAX,
    UINT64_MAX,
    CommandObservation,
    CommandResult,
    DomainError,
    RawCancel,
    RawModify,
    RawNew,
    ReferenceOrder,
    Side,
    Trade,
)

_HEADER = {
    "record_type": "trace_header",
    "schema": "lob.canonical_trace",
    "version": "1",
}
_HEADER_BYTES = b'{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1"}\n'
_UNSIGNED_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_SIGNED_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*|-[1-9][0-9]*)\Z", re.ASCII)


class CanonicalTraceError(ValueError):
    """The supplied logical observation or byte stream is not canonical v1."""


class _JSONObject(list):
    """JSON object represented as ordered key/value pairs, preserving duplicates."""


def _fail(message: str) -> None:
    raise CanonicalTraceError(message)


def _exact_int(value: object, minimum: int, maximum: int, field: str) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        _fail(f"{field} is outside its canonical integer domain")
    return value


def _unsigned_text(value: object, minimum: int, maximum: int, field: str) -> str:
    return str(_exact_int(value, minimum, maximum, field))


def _signed_text(value: object, minimum: int, maximum: int, field: str) -> str:
    return str(_exact_int(value, minimum, maximum, field))


def _parse_unsigned(value: object, minimum: int, maximum: int, field: str) -> int:
    if type(value) is not str or _UNSIGNED_DECIMAL.fullmatch(value) is None:
        _fail(f"{field} is not a canonical unsigned decimal string")
    integer = int(value)
    if integer < minimum or integer > maximum:
        _fail(f"{field} is outside its canonical integer domain")
    return integer


def _parse_signed(value: object, minimum: int, maximum: int, field: str) -> int:
    if type(value) is not str or _SIGNED_DECIMAL.fullmatch(value) is None:
        _fail(f"{field} is not a canonical signed decimal string")
    integer = int(value)
    if integer < minimum or integer > maximum:
        _fail(f"{field} is outside its canonical integer domain")
    return integer


def _json_bytes(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=False,
        )
        encoded = text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CanonicalTraceError("canonical JSON emission failed") from exc
    if any(byte > 0x7F for byte in encoded):
        _fail("canonical v1 output must remain within its fixed ASCII vocabulary")
    return encoded


def _command_object(command: RawNew | RawCancel | RawModify) -> dict[str, object]:
    command_type = type(command)
    if command_type is RawNew:
        return {
            "kind": "new",
            "order_id": _unsigned_text(command.order_id, 0, UINT64_MAX, "command.order_id"),
            "side_code": _unsigned_text(command.side_code, 0, UINT8_MAX, "command.side_code"),
            "price_ticks": _signed_text(command.price_ticks, INT64_MIN, INT64_MAX, "command.price_ticks"),
            "quantity_units": _unsigned_text(command.quantity_units, 0, UINT64_MAX, "command.quantity_units"),
        }
    if command_type is RawCancel:
        return {
            "kind": "cancel",
            "order_id": _unsigned_text(command.order_id, 0, UINT64_MAX, "command.order_id"),
        }
    if command_type is RawModify:
        return {
            "kind": "modify",
            "order_id": _unsigned_text(command.order_id, 0, UINT64_MAX, "command.order_id"),
            "price_ticks": _signed_text(command.price_ticks, INT64_MIN, INT64_MAX, "command.price_ticks"),
            "quantity_units": _unsigned_text(command.quantity_units, 0, UINT64_MAX, "command.quantity_units"),
        }
    _fail("unsupported command type")


def _result_object(result: CommandResult) -> dict[str, object]:
    if type(result) is not CommandResult or type(result.accepted) is not bool:
        _fail("command_result has the wrong shape")
    if result.accepted:
        if result.error is not None:
            _fail("accepted command_result must have null error")
        error: str | None = None
    else:
        if type(result.error) is not DomainError:
            _fail("rejected command_result requires a frozen DomainError")
        error = result.error.value
    return {"accepted": result.accepted, "error": error}


def _trade_object(trade: Trade) -> dict[str, object]:
    if type(trade) is not Trade:
        _fail("trade has the wrong type")
    return {
        "maker_order_id": _unsigned_text(trade.maker_order_id, 0, UINT64_MAX, "trade.maker_order_id"),
        "taker_order_id": _unsigned_text(trade.taker_order_id, 0, UINT64_MAX, "trade.taker_order_id"),
        "price_ticks": _signed_text(trade.price_ticks, 1, INT64_MAX, "trade.price_ticks"),
        "quantity_units": _unsigned_text(trade.quantity_units, 1, UINT64_MAX, "trade.quantity_units"),
    }


def _order_object(order: ReferenceOrder, expected_side: Side) -> dict[str, object]:
    if type(order) is not ReferenceOrder or order.side is not expected_side:
        _fail("resting order has the wrong type or side")
    return {
        "order_id": _unsigned_text(order.order_id, 0, UINT64_MAX, "resting.order_id"),
        "side": expected_side.value,
        "price_ticks": _signed_text(order.price_ticks, 1, INT64_MAX, "resting.price_ticks"),
        "remaining_quantity_units": _unsigned_text(
            order.remaining_quantity,
            1,
            UINT64_MAX,
            "resting.remaining_quantity_units",
        ),
        "sequence": _unsigned_text(order.sequence, 1, UINT64_MAX, "resting.sequence"),
    }


def _validate_book_order(orders: tuple[ReferenceOrder, ...], side: Side) -> None:
    if type(orders) is not tuple:
        _fail("resting-order arrays must come from immutable tuples")
    if side is Side.Buy:
        key = lambda order: (-order.price_ticks, order.sequence)
    else:
        key = lambda order: (order.price_ticks, order.sequence)
    previous: tuple[int, int] | None = None
    for order in orders:
        _order_object(order, side)
        current = key(order)
        if previous is not None and current < previous:
            _fail("resting-order array is not already in canonical logical order")
        previous = current


def _allocator_object(next_sequence: int | None) -> dict[str, object]:
    if next_sequence is None:
        return {"state": "exhausted", "value": None}
    return {
        "state": "available",
        "value": _unsigned_text(next_sequence, 1, UINT64_MAX, "next_sequence.value"),
    }


def _command_record(
    index: int,
    command: RawNew | RawCancel | RawModify,
    observation: CommandObservation,
) -> dict[str, object]:
    if type(observation) is not CommandObservation:
        _fail("observation has the wrong type")
    if type(observation.trades) is not tuple:
        _fail("trades must be an immutable tuple")
    result = _result_object(observation.command_result)
    if not observation.command_result.accepted and observation.trades:
        _fail("rejected command must have an empty trade sequence")
    _validate_book_order(observation.bids, Side.Buy)
    _validate_book_order(observation.asks, Side.Sell)
    return {
        "record_type": "command",
        "command_index": str(index),
        "command": _command_object(command),
        "command_result": result,
        "trades": [_trade_object(trade) for trade in observation.trades],
        "bids": [_order_object(order, Side.Buy) for order in observation.bids],
        "asks": [_order_object(order, Side.Sell) for order in observation.asks],
        "next_sequence": _allocator_object(observation.next_sequence),
    }


def serialize_canonical_trace(
    entries: Iterable[tuple[RawNew | RawCancel | RawModify, CommandObservation]],
) -> bytes:
    """Serialize logical command observations to exact canonical v1 JSONL bytes."""
    try:
        materialized = tuple(entries)
    except (TypeError, RuntimeError) as exc:
        raise CanonicalTraceError("trace entries are not iterable") from exc

    output = bytearray(_HEADER_BYTES)
    for index, entry in enumerate(materialized):
        if type(entry) is not tuple or len(entry) != 2:
            _fail("each trace entry must be exactly a (command, observation) tuple")
        command, observation = entry
        output.extend(_json_bytes(_command_record(index, command, observation)))
        output.append(0x0A)
    return bytes(output)


def _expect_object(value: object, keys: tuple[str, ...], field: str) -> dict[str, object]:
    if type(value) is not _JSONObject:
        _fail(f"{field} must be a JSON object")
    actual_keys = tuple(pair[0] for pair in value)
    if actual_keys != keys:
        _fail(f"{field} has missing, duplicate, unknown, or reordered members")
    return {key: item for key, item in value}


def _parse_command(value: object) -> RawNew | RawCancel | RawModify:
    if type(value) is not _JSONObject:
        _fail("command must be a JSON object")
    keys = tuple(pair[0] for pair in value)
    if not keys or keys[0] != "kind":
        _fail("command has invalid member order")
    raw = {key: item for key, item in value}
    kind = raw.get("kind")
    if kind == "new":
        obj = _expect_object(
            value,
            ("kind", "order_id", "side_code", "price_ticks", "quantity_units"),
            "command",
        )
        return RawNew(
            _parse_unsigned(obj["order_id"], 0, UINT64_MAX, "command.order_id"),
            _parse_unsigned(obj["side_code"], 0, UINT8_MAX, "command.side_code"),
            _parse_signed(obj["price_ticks"], INT64_MIN, INT64_MAX, "command.price_ticks"),
            _parse_unsigned(obj["quantity_units"], 0, UINT64_MAX, "command.quantity_units"),
        )
    if kind == "cancel":
        obj = _expect_object(value, ("kind", "order_id"), "command")
        return RawCancel(_parse_unsigned(obj["order_id"], 0, UINT64_MAX, "command.order_id"))
    if kind == "modify":
        obj = _expect_object(
            value,
            ("kind", "order_id", "price_ticks", "quantity_units"),
            "command",
        )
        return RawModify(
            _parse_unsigned(obj["order_id"], 0, UINT64_MAX, "command.order_id"),
            _parse_signed(obj["price_ticks"], INT64_MIN, INT64_MAX, "command.price_ticks"),
            _parse_unsigned(obj["quantity_units"], 0, UINT64_MAX, "command.quantity_units"),
        )
    _fail("command kind is outside the closed v1 vocabulary")


def _parse_result(value: object) -> CommandResult:
    obj = _expect_object(value, ("accepted", "error"), "command_result")
    accepted = obj["accepted"]
    error = obj["error"]
    if type(accepted) is not bool:
        _fail("command_result.accepted must be a JSON boolean")
    if accepted:
        if error is not None:
            _fail("accepted command_result must have null error")
        return CommandResult(True, None)
    if type(error) is not str:
        _fail("rejected command_result requires an error string")
    try:
        domain_error = DomainError(error)
    except ValueError as exc:
        raise CanonicalTraceError("unknown DomainError string") from exc
    return CommandResult(False, domain_error)


def _parse_trade(value: object) -> Trade:
    obj = _expect_object(
        value,
        ("maker_order_id", "taker_order_id", "price_ticks", "quantity_units"),
        "trade",
    )
    return Trade(
        _parse_unsigned(obj["maker_order_id"], 0, UINT64_MAX, "trade.maker_order_id"),
        _parse_unsigned(obj["taker_order_id"], 0, UINT64_MAX, "trade.taker_order_id"),
        _parse_signed(obj["price_ticks"], 1, INT64_MAX, "trade.price_ticks"),
        _parse_unsigned(obj["quantity_units"], 1, UINT64_MAX, "trade.quantity_units"),
    )


def _parse_order(value: object, expected_side: Side) -> ReferenceOrder:
    obj = _expect_object(
        value,
        ("order_id", "side", "price_ticks", "remaining_quantity_units", "sequence"),
        "resting_order",
    )
    if obj["side"] != expected_side.value:
        _fail("resting order is in the wrong side array")
    return ReferenceOrder(
        _parse_unsigned(obj["order_id"], 0, UINT64_MAX, "resting.order_id"),
        expected_side,
        _parse_signed(obj["price_ticks"], 1, INT64_MAX, "resting.price_ticks"),
        _parse_unsigned(
            obj["remaining_quantity_units"],
            1,
            UINT64_MAX,
            "resting.remaining_quantity_units",
        ),
        _parse_unsigned(obj["sequence"], 1, UINT64_MAX, "resting.sequence"),
    )


def _parse_allocator(value: object) -> int | None:
    obj = _expect_object(value, ("state", "value"), "next_sequence")
    state = obj["state"]
    if state == "available":
        return _parse_unsigned(obj["value"], 1, UINT64_MAX, "next_sequence.value")
    if state == "exhausted":
        if obj["value"] is not None:
            _fail("exhausted allocator must have null value")
        return None
    _fail("unknown allocator state")


def _reject_constant(_: str) -> None:
    _fail("non-standard JSON constant is forbidden")


def _load_line(line: bytes, field: str) -> _JSONObject:
    try:
        text = line.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_JSONObject,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalTraceError(f"{field} is not strict canonical JSON") from exc
    if type(value) is not _JSONObject:
        _fail(f"{field} must contain exactly one JSON object")
    return value


def validate_canonical_trace(data: bytes) -> None:
    """Fail closed unless *data* is byte-for-byte canonical v1 trace encoding."""
    if type(data) is not bytes:
        _fail("canonical trace input must be exact bytes")
    if data.startswith(b"\xef\xbb\xbf"):
        _fail("UTF-8 BOM is forbidden")
    if b"\r" in data:
        _fail("CR and CRLF are forbidden")
    if not data.endswith(b"\n"):
        _fail("canonical trace requires a final LF")

    lines = data.split(b"\n")
    if lines[-1] != b"":
        _fail("canonical trace terminator is malformed")
    records = lines[:-1]
    if not records or any(line == b"" for line in records):
        _fail("canonical trace requires one header and no blank lines")

    header = _expect_object(
        _load_line(records[0], "trace_header"),
        ("record_type", "schema", "version"),
        "trace_header",
    )
    if header != _HEADER:
        _fail("trace header has the wrong fixed values")

    entries: list[tuple[RawNew | RawCancel | RawModify, CommandObservation]] = []
    for position, raw_line in enumerate(records[1:]):
        record = _expect_object(
            _load_line(raw_line, f"command_record[{position}]"),
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
            _fail("non-header records must have record_type command")
        command_index = _parse_unsigned(record["command_index"], 0, position, "command_index")
        if command_index != position:
            _fail("command_index must equal zero-based command position")

        command = _parse_command(record["command"])
        result = _parse_result(record["command_result"])

        trades_raw = record["trades"]
        bids_raw = record["bids"]
        asks_raw = record["asks"]
        if type(trades_raw) is not list or type(bids_raw) is not list or type(asks_raw) is not list:
            _fail("trades, bids, and asks must be JSON arrays")

        observation = CommandObservation(
            result,
            tuple(_parse_trade(item) for item in trades_raw),
            tuple(_parse_order(item, Side.Buy) for item in bids_raw),
            tuple(_parse_order(item, Side.Sell) for item in asks_raw),
            _parse_allocator(record["next_sequence"]),
        )
        entries.append((command, observation))

    rebuilt = serialize_canonical_trace(entries)
    if rebuilt != data:
        _fail("trace is logically parseable but not byte-for-byte canonical")


def canonical_trace_sha256(data: bytes) -> str:
    """Return lowercase SHA-256 over the exact supplied trace bytes."""
    if type(data) is not bytes:
        _fail("trace digest input must be exact bytes")
    return hashlib.sha256(data).hexdigest()
