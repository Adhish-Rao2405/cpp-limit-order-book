"""Independent M4 reference oracle; no canonical byte serializer is included."""

from .model import ReferenceModel
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
