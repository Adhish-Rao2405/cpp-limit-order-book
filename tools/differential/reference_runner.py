"""Independent LOBQ1 reference runner for M5 differential qualification."""

from __future__ import annotations

import os
import sys
from pathlib import Path


SUCCESS = 0
MALFORMED_TRANSPORT = 10
SERIALIZER_FAILURE = 20
QUALIFICATION_INTERNAL_FAILURE = 30
IO_RUNTIME_FAILURE = 40

UINT8_MAX = 2**8 - 1
UINT64_MAX = 2**64 - 1
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
MAX_RECORD_CONTENT = 128


class ReferenceTransportError(ValueError):
    """Malformed LOBQ1 transport before semantic execution."""


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_ROOT = PROJECT_ROOT / "tools" / "reference_model"

if str(REFERENCE_ROOT) not in sys.path:
    sys.path.insert(0, str(REFERENCE_ROOT))

from lob_reference import (  # noqa: E402
    CanonicalTraceError,
    MalformedQualificationInput,
    RawCancel,
    RawModify,
    RawNew,
    ReferenceModel,
    serialize_canonical_trace,
)


def _diagnostic(message: object) -> None:
    print(message, file=sys.stderr)


def _canonical_unsigned(text: bytes) -> bool:
    if text == b"0":
        return True

    if not text or not 0x31 <= text[0] <= 0x39:
        return False

    return all(
        0x30 <= value <= 0x39
        for value in text[1:]
    )


def _canonical_signed(text: bytes) -> bool:
    if _canonical_unsigned(text):
        return True

    if len(text) < 2 or text[0] != 0x2D:
        return False

    magnitude = text[1:]

    return (
        magnitude != b"0"
        and _canonical_unsigned(magnitude)
    )


def _parse_integer(
    text: bytes,
    *,
    signed: bool,
    minimum: int,
    maximum: int,
) -> int:
    grammar_ok = (
        _canonical_signed(text)
        if signed
        else _canonical_unsigned(text)
    )

    if not grammar_ok:
        raise ReferenceTransportError(
            "invalid numeric grammar"
        )

    try:
        value = int(text.decode("ascii"), 10)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReferenceTransportError(
            "numeric parse failure"
        ) from exc

    if not minimum <= value <= maximum:
        raise ReferenceTransportError(
            "numeric representation out of range"
        )

    return value


def _parse_allocator(text: bytes) -> int | None:
    if text == b"EXHAUSTED":
        return None

    return _parse_integer(
        text,
        signed=False,
        minimum=1,
        maximum=UINT64_MAX,
    )


def _parse_order_id(text: bytes) -> int:
    return _parse_integer(
        text,
        signed=False,
        minimum=0,
        maximum=UINT64_MAX,
    )


def _parse_side_code(text: bytes) -> int:
    return _parse_integer(
        text,
        signed=False,
        minimum=0,
        maximum=UINT8_MAX,
    )


def _parse_price(text: bytes) -> int:
    return _parse_integer(
        text,
        signed=True,
        minimum=INT64_MIN,
        maximum=INT64_MAX,
    )


def _parse_quantity(text: bytes) -> int:
    return _parse_integer(
        text,
        signed=False,
        minimum=0,
        maximum=UINT64_MAX,
    )


def parse_lobq1_reference(
    data: bytes,
) -> tuple[
    int | None,
    tuple[RawNew | RawCancel | RawModify, ...],
]:
    """Parse the complete LOBQ1 stream before any semantic execution."""

    if type(data) is not bytes:
        raise ReferenceTransportError(
            "transport must be exact bytes"
        )

    if not data:
        raise ReferenceTransportError(
            "empty input"
        )

    if data.startswith(b"\xef\xbb\xbf"):
        raise ReferenceTransportError(
            "UTF-8 BOM forbidden"
        )

    if not data.endswith(b"\n"):
        raise ReferenceTransportError(
            "mandatory final LF missing"
        )

    if b"\r" in data:
        raise ReferenceTransportError(
            "CR forbidden"
        )

    if b"\x00" in data:
        raise ReferenceTransportError(
            "embedded NUL forbidden"
        )

    if any(value > 0x7F for value in data):
        raise ReferenceTransportError(
            "non-ASCII transport byte"
        )

    records = data.split(b"\n")[:-1]

    if not records:
        raise ReferenceTransportError(
            "missing header"
        )

    for record in records:
        if not record:
            raise ReferenceTransportError(
                "blank record"
            )

        if len(record) > MAX_RECORD_CONTENT:
            raise ReferenceTransportError(
                "record too long"
            )

        if (
            record[0] in b" \t\v\f"
            or record[-1] in b" \t\v\f"
        ):
            raise ReferenceTransportError(
                "edge whitespace forbidden"
            )

    header = records[0].split(b"|")

    if (
        len(header) != 2
        or header[0] != b"LOBQ1"
    ):
        raise ReferenceTransportError(
            "invalid header"
        )

    next_sequence = _parse_allocator(
        header[1]
    )

    commands: list[
        RawNew | RawCancel | RawModify
    ] = []

    for record in records[1:]:
        fields = record.split(b"|")

        if fields and fields[0] == b"LOBQ1":
            raise ReferenceTransportError(
                "duplicate header"
            )

        if not fields:
            raise ReferenceTransportError(
                "unknown command kind"
            )

        kind = fields[0]

        if kind == b"N":
            if len(fields) != 5:
                raise ReferenceTransportError(
                    "wrong New field count"
                )

            commands.append(
                RawNew(
                    _parse_order_id(fields[1]),
                    _parse_side_code(fields[2]),
                    _parse_price(fields[3]),
                    _parse_quantity(fields[4]),
                )
            )
            continue

        if kind == b"C":
            if len(fields) != 2:
                raise ReferenceTransportError(
                    "wrong Cancel field count"
                )

            commands.append(
                RawCancel(
                    _parse_order_id(fields[1])
                )
            )
            continue

        if kind == b"M":
            if len(fields) != 4:
                raise ReferenceTransportError(
                    "wrong Modify field count"
                )

            commands.append(
                RawModify(
                    _parse_order_id(fields[1]),
                    _parse_price(fields[2]),
                    _parse_quantity(fields[3]),
                )
            )
            continue

        raise ReferenceTransportError(
            "unknown command kind"
        )

    return next_sequence, tuple(commands)


def _atomic_write(
    output_path: Path,
    data: bytes,
) -> None:
    if output_path.exists():
        raise OSError(
            "trace output already exists"
        )

    temporary_path = Path(
        str(output_path) + ".tmp"
    )

    if temporary_path.exists():
        raise OSError(
            "temporary trace output already exists"
        )

    try:
        with temporary_path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_path,
            output_path,
        )
    except BaseException:
        try:
            temporary_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass
        raise


def run(
    input_path: Path,
    output_path: Path,
) -> int:
    try:
        input_bytes = input_path.read_bytes()
    except (OSError, MemoryError) as exc:
        _diagnostic(
            "reference runner input read failed"
        )
        _diagnostic(exc)
        return IO_RUNTIME_FAILURE

    try:
        next_sequence, commands = (
            parse_lobq1_reference(
                input_bytes
            )
        )
    except ReferenceTransportError as exc:
        _diagnostic(
            "reference runner malformed "
            "qualification transport"
        )
        _diagnostic(exc)
        return MALFORMED_TRANSPORT

    try:
        model = ReferenceModel.for_qualification(
            next_sequence=next_sequence
        )

        entries = []

        for command in commands:
            observation = model.process(
                command
            )
            entries.append(
                (command, observation)
            )

        trace = serialize_canonical_trace(
            entries
        )
    except CanonicalTraceError as exc:
        _diagnostic(
            "reference runner canonical "
            "serialization failed"
        )
        _diagnostic(exc)
        return SERIALIZER_FAILURE
    except MalformedQualificationInput as exc:
        _diagnostic(
            "reference runner internal "
            "qualification-shape failure"
        )
        _diagnostic(exc)
        return QUALIFICATION_INTERNAL_FAILURE
    except MemoryError as exc:
        _diagnostic(
            "reference runner resource failure"
        )
        _diagnostic(exc)
        return IO_RUNTIME_FAILURE
    except Exception as exc:
        _diagnostic(
            "reference runner internal failure"
        )
        _diagnostic(exc)
        return QUALIFICATION_INTERNAL_FAILURE

    try:
        _atomic_write(
            output_path,
            trace,
        )
    except (OSError, MemoryError) as exc:
        _diagnostic(
            "reference runner trace write failed"
        )
        _diagnostic(exc)
        return IO_RUNTIME_FAILURE

    return SUCCESS


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        _diagnostic(
            "reference runner requires "
            "<input-file> <trace-file>"
        )
        return IO_RUNTIME_FAILURE

    return run(
        Path(argv[1]),
        Path(argv[2]),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
