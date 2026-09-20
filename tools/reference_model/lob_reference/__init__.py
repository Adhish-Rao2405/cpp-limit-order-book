"""Independent M4 reference oracle and canonical trace evidence surface."""

from .model import ReferenceModel
from .canonical_trace import (
    CanonicalTraceError,
    canonical_trace_sha256,
    serialize_canonical_trace,
    validate_canonical_trace,
)
from .types import (
    INT64_MAX,
    INT64_MIN,
    UINT8_MAX,
    UINT64_MAX,
    CommandObservation,
    CommandResult,
    DomainError,
    MalformedQualificationInput,
    RawCancel,
    RawModify,
    RawNew,
    ReferenceOrder,
    Side,
    Trade,
)

__all__ = (
    "ReferenceModel",
    "CanonicalTraceError",
    "serialize_canonical_trace",
    "validate_canonical_trace",
    "canonical_trace_sha256",
    "INT64_MAX",
    "INT64_MIN",
    "UINT8_MAX",
    "UINT64_MAX",
    "CommandObservation",
    "CommandResult",
    "DomainError",
    "MalformedQualificationInput",
    "RawCancel",
    "RawModify",
    "RawNew",
    "ReferenceOrder",
    "Side",
    "Trade",
)
