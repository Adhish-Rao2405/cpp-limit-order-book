"""Contract-derived qualification; no candidate code or candidate output is used."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from fractions import Fraction
import unittest
from unittest.mock import patch

from lob_reference import (
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
    ReferenceModel,
    ReferenceOrder,
    Side,
    Trade,
)


RAW_CASES = (
    (RawNew, {"order_id": 7, "side_code": 0, "price_ticks": 100, "quantity_units": 5}),
    (RawCancel, {"order_id": 7}),
    (RawModify, {"order_id": 7, "price_ticks": 100, "quantity_units": 5}),
)


class IntSubclass(int):
    pass


class MustNotCoerce:
    def __int__(self):
        raise AssertionError("numeric coercion is forbidden")


class ModelCase(unittest.TestCase):
    def assertAccepted(self, observation):
        self.assertEqual(observation.command_result, CommandResult(True, None))

    def assertRejected(self, observation, error, before):
        self.assertEqual(observation.command_result, CommandResult(False, error))
        self.assertEqual(observation.trades, ())
        self.assertEqual(
            (observation.bids, observation.asks, observation.next_sequence),
            (before.bids, before.asks, before.next_sequence),
        )

    def exhausted_book(self):
        model = ReferenceModel.for_qualification(next_sequence=UINT64_MAX - 1)
        self.assertAccepted(model.process(RawNew(1, 0, 100, 10)))
        before = model.process(RawNew(2, 1, 105, 8))
        self.assertAccepted(before)
        self.assertIsNone(before.next_sequence)
        return model, before


class RepresentationTests(ModelCase):
    def test_integer_representation_endpoints(self):
        for order_id in (0, UINT64_MAX):
            for side in (0, 1):
                with self.subTest(order_id=order_id, side=side):
                    model = ReferenceModel()
                    low = model.process(RawNew(order_id, side, INT64_MIN, 0))
                    self.assertEqual(low.command_result.error, DomainError.InvalidPrice)
                    zero = model.process(RawNew(order_id, side, INT64_MAX, 0))
                    self.assertEqual(zero.command_result.error, DomainError.InvalidQuantity)
                    high = model.process(RawNew(order_id, side, INT64_MAX, UINT64_MAX))
                    self.assertAccepted(high)
                    self.assertEqual((high.bids + high.asks)[0], ReferenceOrder(
                        order_id, Side.Buy if side == 0 else Side.Sell,
                        INT64_MAX, UINT64_MAX, 1,
                    ))
                    low_modify = model.process(RawModify(order_id, INT64_MIN, 0))
                    self.assertRejected(low_modify, DomainError.InvalidPrice, high)
                    zero_modify = model.process(RawModify(order_id, INT64_MAX, 0))
                    self.assertRejected(zero_modify, DomainError.InvalidQuantity, high)
                    maximum_modify = model.process(RawModify(order_id, INT64_MAX, UINT64_MAX))
                    self.assertRejected(maximum_modify, DomainError.InvalidModification, high)
                    self.assertAccepted(model.process(RawCancel(order_id)))

    def test_all_representable_invalid_side_codes(self):
        model = ReferenceModel()
        for side in range(2, UINT8_MAX + 1):
            with self.subTest(side=side):
                result = model.process(RawNew(0, side, 100, 1))
                self.assertEqual(result, CommandObservation(
                    CommandResult(False, DomainError.InvalidSide), (), (), (), 1
                ))

    def test_out_of_range_in_every_raw_scalar_field(self):
        bounds = {
            "order_id": (0, UINT64_MAX),
            "side_code": (0, UINT8_MAX),
            "price_ticks": (INT64_MIN, INT64_MAX),
            "quantity_units": (0, UINT64_MAX),
        }
        for command_type, fields in RAW_CASES:
            for field in fields:
                minimum, maximum = bounds[field]
                for value in (minimum - 1, maximum + 1):
                    with self.subTest(command=command_type.__name__, field=field, value=value):
                        with self.assertRaises(MalformedQualificationInput):
                            ReferenceModel().process(command_type(**(fields | {field: value})))

    def test_bool_in_every_raw_scalar_field_is_malformed(self):
        for command_type, fields in RAW_CASES:
            for field in fields:
                for value in (True, False):
                    with self.subTest(command=command_type.__name__, field=field, value=value):
                        with self.assertRaises(MalformedQualificationInput):
                            ReferenceModel().process(command_type(**(fields | {field: value})))

    def test_non_int_scalars_are_not_coerced(self):
        values = ("1", 1.0, Decimal(1), Fraction(1, 1), None, IntSubclass(1), MustNotCoerce())
        for command_type, fields in RAW_CASES:
            for field in fields:
                for value in values:
                    with self.subTest(command=command_type.__name__, field=field, value=type(value)):
                        with self.assertRaises(MalformedQualificationInput):
                            ReferenceModel().process(command_type(**(fields | {field: value})))

    def test_closed_constructor_shapes(self):
        for command_type, fields in RAW_CASES:
            for missing in fields:
                with self.subTest(command=command_type.__name__, missing=missing):
                    with self.assertRaises(TypeError):
                        command_type(**{key: value for key, value in fields.items() if key != missing})
            for extra in ("sequence", "annotation", "timestamp", "active_orders"):
                with self.subTest(command=command_type.__name__, extra=extra):
                    with self.assertRaises(TypeError):
                        command_type(**(fields | {extra: 1}))
        with self.assertRaises(TypeError):
            RawCancel(1, price_ticks=100)
        with self.assertRaises(TypeError):
            RawModify(1, 100, 1, side_code=0)

    def test_unsupported_command_objects_are_malformed(self):
        class ExtendedNew(RawNew):
            pass

        for command in (None, True, object(), {}, (1, 0, 100, 1), ExtendedNew(1, 0, 100, 1)):
            with self.subTest(command=type(command)):
                with self.assertRaises(MalformedQualificationInput):
                    ReferenceModel().process(command)

    def test_foreign_command_metaclass_equality_cannot_bypass_admission(self):
        equality_calls = []

        class EqualToCommandClass(type):
            def __eq__(cls, other):
                equality_calls.append(other)
                return True

        class ForeignCommand(metaclass=EqualToCommandClass):
            order_id = 41
            price_ticks = 87
            quantity_units = 2

        for command_type in (RawNew, RawCancel, RawModify):
            self.assertTrue(ForeignCommand == command_type)
        equality_calls.clear()
        model = ReferenceModel()
        before = model.process(RawNew(41, 0, 87, 9))
        with patch.object(ReferenceModel, "_modify", wraps=model._modify) as modify:
            with self.assertRaises(MalformedQualificationInput):
                model.process(ForeignCommand())
            modify.assert_not_called()
        self.assertEqual(equality_calls, [])
        self.assertRejected(model.process(RawCancel(999)), DomainError.UnknownOrderId, before)

    def test_representation_validation_precedes_domain_and_preserves_state(self):
        model = ReferenceModel()
        before = model.process(RawNew(7, 0, 100, 5))
        for command in (
            RawNew(7, 256, 0, 0), RawNew(7, 17, 0, -1),
            RawModify(999, 0, -1), RawCancel(-1),
        ):
            with self.subTest(command=command):
                with self.assertRaises(MalformedQualificationInput):
                    model.process(command)
                self.assertRejected(model.process(RawCancel(999)), DomainError.UnknownOrderId, before)

    def test_allocator_seed_is_closed_and_representation_checked(self):
        for seed in (1, UINT64_MAX - 1, UINT64_MAX, None):
            with self.subTest(seed=seed):
                result = ReferenceModel.for_qualification(next_sequence=seed).process(RawCancel(9))
                self.assertEqual(result.next_sequence, seed)
                self.assertEqual(result.bids + result.asks, ())
        for seed in (0, -1, UINT64_MAX + 1, True, False, "1", 1.0, IntSubclass(1)):
            with self.subTest(seed=seed):
                with self.assertRaises(MalformedQualificationInput):
                    ReferenceModel.for_qualification(next_sequence=seed)
        with self.assertRaises(TypeError):
            ReferenceModel(next_sequence=2)
        with self.assertRaises(TypeError):
            ReferenceModel(active_orders=())
        with self.assertRaises(TypeError):
            ReferenceModel.for_qualification(next_sequence=2, active_orders=())


class RejectionTests(ModelCase):
    def test_new_precedence_and_atomicity_with_duplicate_and_exhaustion(self):
        model, before = self.exhausted_book()
        cases = (
            (RawNew(1, 17, 0, 0), DomainError.InvalidPrice),
            (RawNew(1, 17, 100, 0), DomainError.InvalidQuantity),
            (RawNew(1, 17, 100, 1), DomainError.InvalidSide),
            (RawNew(1, 0, 100, 1), DomainError.DuplicateOrderId),
            (RawNew(3, 0, 100, 1), DomainError.SequenceExhausted),
        )
        for command, error in cases:
            with self.subTest(error=error):
                self.assertRejected(model.process(command), error, before)

    def test_modify_precedence_and_exhausted_replacement_atomicity(self):
        model, before = self.exhausted_book()
        cases = (
            (RawModify(999, 0, 0), DomainError.InvalidPrice),
            (RawModify(999, 100, 0), DomainError.InvalidQuantity),
            (RawModify(999, 100, 1), DomainError.UnknownOrderId),
            (RawModify(1, 100, 10), DomainError.InvalidModification),
            (RawModify(1, 100, 11), DomainError.SequenceExhausted),
            (RawModify(1, 105, 9), DomainError.SequenceExhausted),
            (RawModify(1, 105, 10), DomainError.SequenceExhausted),
            (RawModify(1, 105, 11), DomainError.SequenceExhausted),
        )
        for command, error in cases:
            with self.subTest(command=command):
                self.assertRejected(model.process(command), error, before)

    def test_cancel_unknown_and_active_under_exhaustion(self):
        model, before = self.exhausted_book()
        self.assertRejected(model.process(RawCancel(999)), DomainError.UnknownOrderId, before)
        after = model.process(RawCancel(1))
        self.assertAccepted(after)
        self.assertEqual(after.bids, ())
        self.assertEqual(after.asks, before.asks)
        self.assertEqual(after.trades, ())
        self.assertIsNone(after.next_sequence)


class MatchingTests(ModelCase):
    def test_non_crossing_new_orders_rest_with_own_price_and_sequence(self):
        model = ReferenceModel()
        model.process(RawNew(1, 0, 100, 7))
        result = model.process(RawNew(2, 1, 105, 4))
        self.assertAccepted(result)
        self.assertEqual(result.trades, ())
        self.assertEqual(result.bids, (ReferenceOrder(1, Side.Buy, 100, 7, 1),))
        self.assertEqual(result.asks, (ReferenceOrder(2, Side.Sell, 105, 4, 2),))
        self.assertEqual(result.next_sequence, 3)

    def test_buy_sweep_price_before_time_fifo_maker_price_and_partial_fill(self):
        model = ReferenceModel()
        for command in (RawNew(1, 1, 102, 4), RawNew(2, 1, 100, 3),
                        RawNew(3, 1, 101, 5), RawNew(4, 1, 100, 2)):
            model.process(command)
        result = model.process(RawNew(5, 0, 101, 8))
        self.assertAccepted(result)
        self.assertEqual(result.trades, (Trade(2, 5, 100, 3), Trade(4, 5, 100, 2), Trade(3, 5, 101, 3)))
        self.assertEqual(result.bids, ())
        self.assertEqual(result.asks, (
            ReferenceOrder(3, Side.Sell, 101, 2, 3), ReferenceOrder(1, Side.Sell, 102, 4, 1),
        ))
        self.assertEqual(result.next_sequence, 6)

    def test_sell_sweep_price_before_time_fifo_maker_price_and_partial_fill(self):
        model = ReferenceModel()
        for command in (RawNew(1, 0, 98, 4), RawNew(2, 0, 100, 3),
                        RawNew(3, 0, 99, 5), RawNew(4, 0, 100, 2)):
            model.process(command)
        result = model.process(RawNew(5, 1, 99, 8))
        self.assertAccepted(result)
        self.assertEqual(result.trades, (Trade(2, 5, 100, 3), Trade(4, 5, 100, 2), Trade(3, 5, 99, 3)))
        self.assertEqual(result.asks, ())
        self.assertEqual(result.bids, (
            ReferenceOrder(3, Side.Buy, 99, 2, 3), ReferenceOrder(1, Side.Buy, 98, 4, 1),
        ))
        self.assertEqual(result.next_sequence, 6)

    def test_limit_stops_sweep_and_residual_rests_on_both_sides(self):
        for incoming_side, first_price, outside_price in ((0, 100, 102), (1, 102, 100)):
            with self.subTest(incoming_side=incoming_side):
                model = ReferenceModel()
                model.process(RawNew(1, 1 - incoming_side, first_price, 3))
                model.process(RawNew(2, 1 - incoming_side, outside_price, 4))
                result = model.process(RawNew(3, incoming_side, 101, 8))
                self.assertAccepted(result)
                self.assertEqual(result.trades, (Trade(1, 3, first_price, 3),))
                residual = ReferenceOrder(3, Side.Buy if incoming_side == 0 else Side.Sell, 101, 5, 3)
                outside = ReferenceOrder(2, Side.Sell if incoming_side == 0 else Side.Buy, outside_price, 4, 2)
                self.assertEqual(result.bids, (residual,) if incoming_side == 0 else (outside,))
                self.assertEqual(result.asks, (outside,) if incoming_side == 0 else (residual,))
                self.assertLess(result.bids[0].price_ticks, result.asks[0].price_ticks)

    def test_partial_maker_retains_priority_on_next_command(self):
        for maker_side in (0, 1):
            with self.subTest(maker_side=maker_side):
                model = ReferenceModel()
                model.process(RawNew(1, maker_side, 100, 10))
                model.process(RawNew(2, maker_side, 100, 4))
                partial = model.process(RawNew(3, 1 - maker_side, 100, 6))
                book = partial.bids if maker_side == 0 else partial.asks
                self.assertEqual((book[0].order_id, book[0].remaining_quantity, book[0].sequence), (1, 4, 1))
                result = model.process(RawNew(4, 1 - maker_side, 100, 5))
                self.assertEqual(result.trades, (Trade(1, 4, 100, 4), Trade(2, 4, 100, 1)))


class ModificationTests(ModelCase):
    def test_reduction_retains_priority_and_does_not_match(self):
        for side in (0, 1):
            with self.subTest(side=side):
                model = ReferenceModel()
                model.process(RawNew(1, side, 100, 10))
                model.process(RawNew(2, side, 100, 10))
                reduced = model.process(RawModify(1, 100, 6))
                self.assertAccepted(reduced)
                self.assertEqual(reduced.trades, ())
                self.assertEqual(reduced.next_sequence, 3)
                book = reduced.bids if side == 0 else reduced.asks
                self.assertEqual(book[0], ReferenceOrder(1, Side.Buy if side == 0 else Side.Sell, 100, 6, 1))
                result = model.process(RawNew(3, 1 - side, 100, 7))
                self.assertEqual(result.trades, (Trade(1, 3, 100, 6), Trade(2, 3, 100, 1)))

    def test_increase_requeues_behind_existing_equal_price_order(self):
        for side in (0, 1):
            with self.subTest(side=side):
                model = ReferenceModel()
                model.process(RawNew(1, side, 100, 5))
                model.process(RawNew(2, side, 100, 5))
                increased = model.process(RawModify(1, 100, 8))
                self.assertAccepted(increased)
                book = increased.bids if side == 0 else increased.asks
                self.assertEqual(tuple((o.order_id, o.sequence) for o in book), ((2, 2), (1, 3)))
                self.assertEqual(increased.next_sequence, 4)
                result = model.process(RawNew(3, 1 - side, 100, 6))
                self.assertEqual(result.trades, (Trade(2, 3, 100, 5), Trade(1, 3, 100, 1)))

    def test_any_price_change_loses_priority_for_every_quantity_direction(self):
        for side in (0, 1):
            for price in (99, 101):
                for quantity in (4, 5, 6):
                    with self.subTest(side=side, price=price, quantity=quantity):
                        model = ReferenceModel()
                        model.process(RawNew(7, side, 100, 5))
                        result = model.process(RawModify(7, price, quantity))
                        self.assertAccepted(result)
                        self.assertEqual(result.trades, ())
                        self.assertEqual(result.bids + result.asks, (
                            ReferenceOrder(7, Side.Buy if side == 0 else Side.Sell, price, quantity, 2),
                        ))
                        self.assertEqual(result.next_sequence, 3)

    def test_marketable_replacement_preserves_side_and_id_and_fresh_residual(self):
        for side, original_price, replacement_price in ((0, 99, 102), (1, 102, 99)):
            with self.subTest(side=side):
                model = ReferenceModel()
                model.process(RawNew(1, side, original_price, 5))
                model.process(RawNew(10, 1 - side, 101, 3))
                result = model.process(RawModify(1, replacement_price, 5))
                self.assertAccepted(result)
                self.assertEqual(result.trades, (Trade(10, 1, 101, 3),))
                self.assertEqual(result.bids + result.asks, (
                    ReferenceOrder(1, Side.Buy if side == 0 else Side.Sell, replacement_price, 2, 3),
                ))
                self.assertEqual(result.next_sequence, 4)

    def test_modify_after_partial_fill_uses_target_remaining_quantity(self):
        model = ReferenceModel()
        model.process(RawNew(1, 0, 100, 10))
        partial = model.process(RawNew(2, 1, 100, 4))
        self.assertEqual(partial.bids, (ReferenceOrder(1, Side.Buy, 100, 6, 1),))
        self.assertRejected(model.process(RawModify(1, 100, 6)), DomainError.InvalidModification, partial)
        reduced = model.process(RawModify(1, 100, 3))
        self.assertEqual(reduced.bids, (ReferenceOrder(1, Side.Buy, 100, 3, 1),))
        self.assertEqual(reduced.next_sequence, 3)
        increased = model.process(RawModify(1, 100, 5))
        self.assertEqual(increased.bids, (ReferenceOrder(1, Side.Buy, 100, 5, 3),))
        self.assertEqual(increased.next_sequence, 4)

    def test_original_is_absent_before_replacement_matching_begins(self):
        model = ReferenceModel()
        model.process(RawNew(1, 0, 99, 5))
        model.process(RawNew(2, 1, 101, 3))
        original_match = ReferenceModel._match_incoming

        def inspect_entry(instance, order_id, side, price, quantity, sequence):
            self.assertIs(instance, model)
            self.assertEqual((order_id, side, price, quantity, sequence), (1, Side.Buy, 102, 5, 3))
            self.assertIsNone(instance._find_order_index(1))
            return original_match(instance, order_id, side, price, quantity, sequence)

        with patch.object(ReferenceModel, "_match_incoming", autospec=True, side_effect=inspect_entry) as entry:
            result = model.process(RawModify(1, 102, 5))
            entry.assert_called_once()
        self.assertEqual(result.trades, (Trade(2, 1, 101, 3),))
        self.assertEqual(result.bids, (ReferenceOrder(1, Side.Buy, 102, 2, 3),))


class SequenceTests(ModelCase):
    def test_normal_first_sequence_and_fully_executed_new_consumption(self):
        model = ReferenceModel()
        first = model.process(RawNew(1, 1, 100, 5))
        self.assertEqual(first.asks[0].sequence, 1)
        self.assertEqual(first.next_sequence, 2)
        filled = model.process(RawNew(2, 0, 100, 5))
        self.assertAccepted(filled)
        self.assertEqual(filled.trades, (Trade(1, 2, 100, 5),))
        self.assertEqual(filled.bids + filled.asks, ())
        self.assertEqual(filled.next_sequence, 3)

    def test_max_allocated_once_and_no_wrap_after_cancellation(self):
        model = ReferenceModel.for_qualification(next_sequence=UINT64_MAX)
        available = model.process(RawCancel(9))
        self.assertEqual(available.next_sequence, UINT64_MAX)
        last = model.process(RawNew(1, 0, 100, 5))
        self.assertEqual(last.bids[0].sequence, UINT64_MAX)
        self.assertIsNone(last.next_sequence)
        self.assertRejected(model.process(RawNew(2, 0, 100, 1)), DomainError.SequenceExhausted, last)
        cancelled = model.process(RawCancel(1))
        self.assertAccepted(cancelled)
        self.assertIsNone(cancelled.next_sequence)
        self.assertRejected(model.process(RawNew(1, 0, 100, 1)), DomainError.SequenceExhausted, cancelled)

    def test_max_consumed_even_when_new_fully_executes(self):
        model = ReferenceModel.for_qualification(next_sequence=UINT64_MAX - 1)
        model.process(RawNew(1, 1, 100, 5))
        result = model.process(RawNew(2, 0, 100, 5))
        self.assertAccepted(result)
        self.assertEqual(result.bids + result.asks, ())
        self.assertEqual(result.trades, (Trade(1, 2, 100, 5),))
        self.assertIsNone(result.next_sequence)

    def test_max_consumed_even_when_replacement_fully_executes(self):
        for side, old_price, new_price in ((0, 99, 101), (1, 101, 99)):
            with self.subTest(side=side):
                model = ReferenceModel.for_qualification(next_sequence=UINT64_MAX - 2)
                model.process(RawNew(1, side, old_price, 5))
                model.process(RawNew(2, 1 - side, 100, 5))
                result = model.process(RawModify(1, new_price, 5))
                self.assertAccepted(result)
                self.assertEqual(result.trades, (Trade(2, 1, 100, 5),))
                self.assertEqual(result.bids + result.asks, ())
                self.assertIsNone(result.next_sequence)
                self.assertRejected(model.process(RawNew(3, side, old_price, 1)), DomainError.SequenceExhausted, result)

    def test_reduction_remains_available_when_exhausted(self):
        model, before = self.exhausted_book()
        result = model.process(RawModify(1, 100, 4))
        self.assertAccepted(result)
        self.assertEqual(result.trades, ())
        self.assertEqual(result.bids, (ReferenceOrder(1, Side.Buy, 100, 4, UINT64_MAX - 1),))
        self.assertEqual(result.asks, before.asks)
        self.assertIsNone(result.next_sequence)

    def test_rejections_cancellations_and_reductions_consume_no_sequence(self):
        model = ReferenceModel()
        before = model.process(RawNew(1, 0, 100, 5))
        for command, error in (
            (RawNew(1, 0, 100, 1), DomainError.DuplicateOrderId),
            (RawNew(2, 0, 0, 1), DomainError.InvalidPrice),
            (RawNew(2, 0, 100, 0), DomainError.InvalidQuantity),
            (RawNew(2, 9, 100, 1), DomainError.InvalidSide),
            (RawCancel(2), DomainError.UnknownOrderId),
            (RawModify(1, 100, 5), DomainError.InvalidModification),
        ):
            self.assertRejected(model.process(command), error, before)
        self.assertEqual(model.process(RawModify(1, 100, 4)).next_sequence, 2)
        self.assertEqual(model.process(RawCancel(1)).next_sequence, 2)
        after = model.process(RawNew(2, 0, 100, 1))
        self.assertEqual(after.bids[0].sequence, 2)
        self.assertEqual(after.next_sequence, 3)


class LifetimeTests(ModelCase):
    def test_duplicate_active_id_rejected_across_sides(self):
        model = ReferenceModel()
        before = model.process(RawNew(0, 0, 100, 5))
        self.assertRejected(model.process(RawNew(0, 1, 100, 5)), DomainError.DuplicateOrderId, before)

    def test_id_reuse_after_cancellation(self):
        model = ReferenceModel()
        model.process(RawNew(0, 0, 100, 5))
        cancelled = model.process(RawCancel(0))
        self.assertEqual(cancelled.bids + cancelled.asks, ())
        result = model.process(RawNew(0, 1, 101, 7))
        self.assertAccepted(result)
        self.assertEqual(result.asks, (ReferenceOrder(0, Side.Sell, 101, 7, 2),))

    def test_id_reuse_after_maker_and_taker_full_fill(self):
        model = ReferenceModel()
        model.process(RawNew(1, 0, 100, 5))
        model.process(RawNew(2, 1, 100, 5))
        self.assertAccepted(model.process(RawNew(1, 0, 99, 4)))
        result = model.process(RawNew(2, 1, 101, 6))
        self.assertAccepted(result)
        self.assertEqual(result.bids, (ReferenceOrder(1, Side.Buy, 99, 4, 3),))
        self.assertEqual(result.asks, (ReferenceOrder(2, Side.Sell, 101, 6, 4),))


class IndependenceTests(ModelCase):
    def exercise_permutation(self, maker_side):
        ordinary = ReferenceModel()
        permuted = ReferenceModel()
        for model in (ordinary, permuted):
            model.process(RawNew(1, maker_side, 100, 2))
            model.process(RawNew(2, maker_side, 100, 3))
            model.process(RawNew(3, maker_side, 100, 4))
        permuted.reorder_for_qualification((3, 2, 1))
        self.assertEqual(ordinary.process(RawCancel(999)), permuted.process(RawCancel(999)))
        command = RawNew(4, 1 - maker_side, 100, 6)
        expected = (Trade(1, 4, 100, 2), Trade(2, 4, 100, 3), Trade(3, 4, 100, 1))
        left, right = ordinary.process(command), permuted.process(command)
        self.assertEqual(left.trades, expected)
        self.assertEqual(right.trades, expected)
        self.assertEqual(left, right)

    def test_bid_maker_selection_is_independent_of_physical_order(self):
        self.exercise_permutation(0)

    def test_ask_maker_selection_is_independent_of_physical_order(self):
        self.exercise_permutation(1)

    def test_reorder_hook_rejects_non_permutations_without_mutation(self):
        model = ReferenceModel()
        model.process(RawNew(1, 0, 100, 5))
        before = model.process(RawNew(2, 1, 105, 4))
        for permutation in ((1,), (1, 1), (1, 2, 3), (1, 999), (1, True),
                            (1, "2"), (1, UINT64_MAX + 1), [2, 1]):
            with self.subTest(permutation=permutation):
                with self.assertRaises(MalformedQualificationInput):
                    model.reorder_for_qualification(permutation)
                self.assertRejected(model.process(RawCancel(999)), DomainError.UnknownOrderId, before)
        model.reorder_for_qualification((2, 1))
        self.assertRejected(model.process(RawCancel(999)), DomainError.UnknownOrderId, before)

    def test_empty_reorder_does_not_inject_state(self):
        model = ReferenceModel.for_qualification(next_sequence=UINT64_MAX)
        model.reorder_for_qualification(())
        with self.assertRaises(MalformedQualificationInput):
            model.reorder_for_qualification((1,))
        result = model.process(RawCancel(1))
        self.assertEqual(result.bids + result.asks, ())
        self.assertEqual(result.next_sequence, UINT64_MAX)


class ConservationTests(ModelCase):
    def test_maximum_quantity_conservation_on_both_sides(self):
        for taker_side in (0, 1):
            with self.subTest(taker_side=taker_side):
                model = ReferenceModel()
                model.process(RawNew(1, 1 - taker_side, 100, UINT64_MAX - 2))
                model.process(RawNew(2, 1 - taker_side, 100, 5))
                result = model.process(RawNew(3, taker_side, 100, UINT64_MAX))
                self.assertEqual(result.trades, (
                    Trade(1, 3, 100, UINT64_MAX - 2), Trade(2, 3, 100, 2),
                ))
                self.assertEqual(sum(t.quantity_units for t in result.trades), UINT64_MAX)
                remaining = result.bids + result.asks
                self.assertEqual(len(remaining), 1)
                self.assertEqual(remaining[0].order_id, 2)
                self.assertEqual(remaining[0].remaining_quantity, 3)
                self.assertEqual(5, result.trades[1].quantity_units + remaining[0].remaining_quantity)
                self.assertEqual((UINT64_MAX - 2) + 5, sum(t.quantity_units for t in result.trades) + 3)
                self.assertTrue(all(t.quantity_units > 0 for t in result.trades))
                self.assertTrue(all(o.remaining_quantity > 0 for o in remaining))

    def test_residual_conservation_limits_and_quiescence(self):
        for side, eligible_price, outside_price in ((0, 99, 101), (1, 101, 99)):
            with self.subTest(side=side):
                model = ReferenceModel()
                model.process(RawNew(1, 1 - side, eligible_price, 3))
                model.process(RawNew(2, 1 - side, outside_price, 6))
                result = model.process(RawNew(3, side, 100, 8))
                residual = next(o for o in result.bids + result.asks if o.order_id == 3)
                self.assertEqual(8, sum(t.quantity_units for t in result.trades) + residual.remaining_quantity)
                self.assertEqual(result.trades, (Trade(1, 3, eligible_price, 3),))
                self.assertEqual(residual.remaining_quantity, 5)
                for trade in result.trades:
                    self.assertGreater(trade.quantity_units, 0)
                    if side == 0:
                        self.assertLessEqual(trade.price_ticks, 100)
                    else:
                        self.assertGreaterEqual(trade.price_ticks, 100)
                self.assertTrue(all(o.remaining_quantity > 0 for o in result.bids + result.asks))
                self.assertLess(result.bids[0].price_ticks, result.asks[0].price_ticks)


class ObservationTests(ModelCase):
    def test_canonical_snapshot_order_on_both_sides(self):
        model = ReferenceModel()
        for command in (RawNew(1, 0, 99, 1), RawNew(2, 0, 100, 2), RawNew(3, 0, 100, 3),
                        RawNew(4, 1, 103, 4), RawNew(5, 1, 102, 5), RawNew(6, 1, 102, 6)):
            model.process(command)
        model.reorder_for_qualification((6, 4, 3, 1, 5, 2))
        result = model.process(RawCancel(999))
        self.assertEqual(result.bids, (
            ReferenceOrder(2, Side.Buy, 100, 2, 2), ReferenceOrder(3, Side.Buy, 100, 3, 3),
            ReferenceOrder(1, Side.Buy, 99, 1, 1),
        ))
        self.assertEqual(result.asks, (
            ReferenceOrder(5, Side.Sell, 102, 5, 5), ReferenceOrder(6, Side.Sell, 102, 6, 6),
            ReferenceOrder(4, Side.Sell, 103, 4, 4),
        ))

    def test_historical_observation_is_immutable_and_stable(self):
        model = ReferenceModel()
        first = model.process(RawNew(1, 0, 100, 10))
        expected_first = CommandObservation(CommandResult(True, None), (), (
            ReferenceOrder(1, Side.Buy, 100, 10, 1),
        ), (), 2)
        traded = model.process(RawNew(2, 1, 100, 4))
        expected_traded = CommandObservation(CommandResult(True, None), (Trade(1, 2, 100, 4),), (
            ReferenceOrder(1, Side.Buy, 100, 6, 1),
        ), (), 3)
        model.process(RawModify(1, 100, 3))
        model.process(RawCancel(1))
        model.process(RawNew(1, 1, 105, 2))
        self.assertEqual(first, expected_first)
        self.assertEqual(traded, expected_traded)
        self.assertIsInstance(first.bids, tuple)
        self.assertIsInstance(traded.trades, tuple)
        for value, field, replacement in (
            (first, "next_sequence", 99), (first.command_result, "accepted", False),
            (first.bids[0], "remaining_quantity", 1), (traded.trades[0], "quantity_units", 1),
        ):
            with self.subTest(field=field):
                with self.assertRaises(FrozenInstanceError):
                    setattr(value, field, replacement)

    def test_fixed_stream_is_deterministic_with_explicit_final_expectation(self):
        commands = (
            RawNew(1, 1, 101, 3), RawNew(2, 1, 102, 5), RawNew(3, 0, 101, 4),
            RawModify(3, 102, 2), RawCancel(999), RawModify(2, 102, 2), RawCancel(2),
            RawNew(1, 0, 100, 7), RawNew(1, 1, 101, 1),
        )
        left, right = ReferenceModel(), ReferenceModel()
        left_observations = tuple(left.process(command) for command in commands)
        right_observations = tuple(right.process(command) for command in commands)
        self.assertEqual(left_observations, right_observations)
        self.assertEqual(left_observations[2].trades, (Trade(1, 3, 101, 3),))
        self.assertEqual(left_observations[3].trades, (Trade(2, 3, 102, 2),))
        self.assertEqual(left_observations[-1], CommandObservation(
            CommandResult(False, DomainError.DuplicateOrderId), (),
            (ReferenceOrder(1, Side.Buy, 100, 7, 5),), (), 6,
        ))


if __name__ == "__main__":
    unittest.main()
