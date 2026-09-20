"""Flat-state oracle derived from the frozen textual matching contract.

Expected rejections are values. Programming and resource failures propagate;
transactional recovery from such failures is not claimed.
"""

from dataclasses import replace

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


def _require_integer(value: object, minimum: int, maximum: int, field: str) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MalformedQualificationInput(f"{field} requires an exact int in range")


class ReferenceModel:
    """Single-writer logical model with no external active-state constructor."""

    __slots__ = ("_active_orders", "_next_sequence")

    def __init__(self) -> None:
        self._active_orders: list[ReferenceOrder] = []
        self._next_sequence: int | None = 1

    @classmethod
    def for_qualification(cls, *, next_sequence: int | None) -> "ReferenceModel":
        """Construct empty state with only the qualification allocator seeded."""
        if next_sequence is not None:
            _require_integer(next_sequence, 1, UINT64_MAX, "next_sequence")
        model = cls()
        model._next_sequence = next_sequence
        return model

    def reorder_for_qualification(self, order_ids: tuple[int, ...]) -> None:
        """Permute existing records only; neither logical fields nor allocator change.

        The tuple must contain every currently active ID exactly once. This hook
        is not a matching command or an arbitrary active-state constructor.
        """
        if type(order_ids) is not tuple:
            raise MalformedQualificationInput("reordering requires a tuple of active IDs")
        reordered: list[ReferenceOrder] = []
        seen: list[int] = []
        for order_id in order_ids:
            _require_integer(order_id, 0, UINT64_MAX, "order_id")
            index = self._find_order_index(order_id)
            if index is None or order_id in seen:
                raise MalformedQualificationInput("reordering requires a permutation")
            seen.append(order_id)
            reordered.append(self._active_orders[index])
        if len(reordered) != len(self._active_orders):
            raise MalformedQualificationInput("reordering must include every active ID")
        self._assert_invariants()
        self._active_orders = reordered
        self._assert_invariants()

    def process(self, command: RawNew | RawCancel | RawModify) -> CommandObservation:
        """Validate the complete raw representation before any domain decision."""
        command_type = type(command)
        if (
            command_type is not RawNew
            and command_type is not RawCancel
            and command_type is not RawModify
        ):
            raise MalformedQualificationInput("unsupported qualification command")
        _require_integer(command.order_id, 0, UINT64_MAX, "order_id")
        if type(command) is not RawCancel:
            _require_integer(command.price_ticks, INT64_MIN, INT64_MAX, "price_ticks")
            _require_integer(command.quantity_units, 0, UINT64_MAX, "quantity_units")
        if type(command) is RawNew:
            _require_integer(command.side_code, 0, UINT8_MAX, "side_code")
        self._assert_invariants()
        if type(command) is RawNew:
            return self._new(command)
        if type(command) is RawCancel:
            return self._cancel(command)
        return self._modify(command)

    def _find_order_index(self, order_id: int) -> int | None:
        for index, order in enumerate(self._active_orders):
            if order.order_id == order_id:
                return index
        return None

    def _allocate_sequence(self) -> int:
        sequence = self._next_sequence
        assert sequence is not None, "fresh-sequence availability must be established"
        self._next_sequence = None if sequence == UINT64_MAX else sequence + 1
        return sequence

    def _new(self, command: RawNew) -> CommandObservation:
        if command.price_ticks <= 0:
            return self._observation(DomainError.InvalidPrice)
        if command.quantity_units == 0:
            return self._observation(DomainError.InvalidQuantity)
        if command.side_code not in (0, 1):
            return self._observation(DomainError.InvalidSide)
        if self._find_order_index(command.order_id) is not None:
            return self._observation(DomainError.DuplicateOrderId)
        if self._next_sequence is None:
            return self._observation(DomainError.SequenceExhausted)
        side = Side.Buy if command.side_code == 0 else Side.Sell
        sequence = self._allocate_sequence()
        trades = self._match_incoming(
            command.order_id, side, command.price_ticks, command.quantity_units, sequence
        )
        return self._observation(trades=trades)

    def _cancel(self, command: RawCancel) -> CommandObservation:
        index = self._find_order_index(command.order_id)
        if index is None:
            return self._observation(DomainError.UnknownOrderId)
        del self._active_orders[index]
        return self._observation()

    def _modify(self, command: RawModify) -> CommandObservation:
        if command.price_ticks <= 0:
            return self._observation(DomainError.InvalidPrice)
        if command.quantity_units == 0:
            return self._observation(DomainError.InvalidQuantity)
        index = self._find_order_index(command.order_id)
        if index is None:
            return self._observation(DomainError.UnknownOrderId)
        original = self._active_orders[index]
        if command.price_ticks == original.price_ticks:
            if command.quantity_units == original.remaining_quantity:
                return self._observation(DomainError.InvalidModification)
            if command.quantity_units < original.remaining_quantity:
                self._active_orders[index] = replace(
                    original, remaining_quantity=command.quantity_units
                )
                return self._observation()
        if self._next_sequence is None:
            return self._observation(DomainError.SequenceExhausted)
        sequence = self._allocate_sequence()
        del self._active_orders[index]
        trades = self._match_incoming(
            original.order_id,
            original.side,
            command.price_ticks,
            command.quantity_units,
            sequence,
        )
        return self._observation(trades=trades)

    def _select_maker(self, side: Side, limit: int) -> ReferenceOrder | None:
        best: ReferenceOrder | None = None
        for order in self._active_orders:
            if side is Side.Buy:
                if order.side is not Side.Sell or order.price_ticks > limit:
                    continue
                better_price = best is None or order.price_ticks < best.price_ticks
            else:
                if order.side is not Side.Buy or order.price_ticks < limit:
                    continue
                better_price = best is None or order.price_ticks > best.price_ticks
            if (
                better_price
                or (
                    best is not None
                    and order.price_ticks == best.price_ticks
                    and order.sequence < best.sequence
                )
            ):
                best = order
        return best

    def _match_incoming(
        self, order_id: int, side: Side, price: int, quantity: int, sequence: int
    ) -> tuple[Trade, ...]:
        remaining = quantity
        trades: list[Trade] = []
        while remaining > 0:
            maker = self._select_maker(side, price)
            if maker is None:
                break
            traded = min(remaining, maker.remaining_quantity)
            trades.append(Trade(maker.order_id, order_id, maker.price_ticks, traded))
            remaining -= traded
            maker_remaining = maker.remaining_quantity - traded
            index = self._find_order_index(maker.order_id)
            assert index is not None, "selected maker must be active"
            if maker_remaining == 0:
                del self._active_orders[index]
            else:
                self._active_orders[index] = replace(
                    maker, remaining_quantity=maker_remaining
                )
        if remaining > 0:
            self._active_orders.append(ReferenceOrder(order_id, side, price, remaining, sequence))
        return tuple(trades)

    def _observation(
        self, error: DomainError | None = None, *, trades: tuple[Trade, ...] = ()
    ) -> CommandObservation:
        self._assert_invariants()
        bids = tuple(sorted(
            (order for order in self._active_orders if order.side is Side.Buy),
            key=lambda order: (-order.price_ticks, order.sequence),
        ))
        asks = tuple(sorted(
            (order for order in self._active_orders if order.side is Side.Sell),
            key=lambda order: (order.price_ticks, order.sequence),
        ))
        return CommandObservation(
            CommandResult(error is None, error), trades, bids, asks, self._next_sequence
        )

    def _assert_invariants(self) -> None:
        assert self._next_sequence is None or (
            type(self._next_sequence) is int and 1 <= self._next_sequence <= UINT64_MAX
        )
        ids: list[int] = []
        sequences: list[int] = []
        best_bid: int | None = None
        best_ask: int | None = None
        for order in self._active_orders:
            assert type(order) is ReferenceOrder
            assert type(order.order_id) is int and 0 <= order.order_id <= UINT64_MAX
            assert order.order_id not in ids
            ids.append(order.order_id)
            assert type(order.price_ticks) is int and 1 <= order.price_ticks <= INT64_MAX
            assert type(order.remaining_quantity) is int
            assert 1 <= order.remaining_quantity <= UINT64_MAX
            assert type(order.sequence) is int and 1 <= order.sequence <= UINT64_MAX
            assert order.sequence not in sequences
            sequences.append(order.sequence)
            assert self._next_sequence is None or order.sequence < self._next_sequence
            assert type(order.side) is Side
            if order.side is Side.Buy:
                best_bid = order.price_ticks if best_bid is None else max(best_bid, order.price_ticks)
            else:
                best_ask = order.price_ticks if best_ask is None else min(best_ask, order.price_ticks)
        assert best_bid is None or best_ask is None or best_bid < best_ask
