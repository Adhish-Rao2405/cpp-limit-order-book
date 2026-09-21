"""Reference-owned logical values, independent of candidate types and helpers.

Raw command construction fixes the closed field shape. ReferenceModel.process
validates scalar representations before applying matching-domain validation.
"""

from dataclasses import dataclass
from enum import Enum

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
UINT8_MAX = 2**8 - 1
UINT64_MAX = 2**64 - 1


class Side(Enum):
    Buy = "Buy"
    Sell = "Sell"


class DomainError(Enum):
    InvalidPrice = "InvalidPrice"
    InvalidQuantity = "InvalidQuantity"
    InvalidSide = "InvalidSide"
    DuplicateOrderId = "DuplicateOrderId"
    UnknownOrderId = "UnknownOrderId"
    SequenceExhausted = "SequenceExhausted"
    InvalidModification = "InvalidModification"


class MalformedQualificationInput(ValueError):
    """Invalid qualification representation, never a matching DomainError."""


@dataclass(frozen=True, slots=True)
class RawNew:
    order_id: int
    side_code: int
    price_ticks: int
    quantity_units: int


@dataclass(frozen=True, slots=True)
class RawCancel:
    order_id: int


@dataclass(frozen=True, slots=True)
class RawModify:
    order_id: int
    price_ticks: int
    quantity_units: int


@dataclass(frozen=True, slots=True)
class ReferenceOrder:
    order_id: int
    side: Side
    price_ticks: int
    remaining_quantity: int
    sequence: int


@dataclass(frozen=True, slots=True)
class Trade:
    maker_order_id: int
    taker_order_id: int
    price_ticks: int
    quantity_units: int


@dataclass(frozen=True, slots=True)
class CommandResult:
    accepted: bool
    error: DomainError | None


@dataclass(frozen=True, slots=True)
class CommandObservation:
    command_result: CommandResult
    trades: tuple[Trade, ...]
    bids: tuple[ReferenceOrder, ...]
    asks: tuple[ReferenceOrder, ...]
    next_sequence: int | None
