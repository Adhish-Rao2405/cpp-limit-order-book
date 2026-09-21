"""M4 canonical trace writer/validator qualification-oriented authoring tests."""

import hashlib
import unittest

from lob_reference import (
    INT64_MAX,
    INT64_MIN,
    UINT64_MAX,
    CanonicalTraceError,
    CommandObservation,
    CommandResult,
    DomainError,
    RawCancel,
    RawModify,
    RawNew,
    ReferenceOrder,
    Side,
    Trade,
    canonical_trace_sha256,
    serialize_canonical_trace,
    validate_canonical_trace,
)


HEADER = b'{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1"}\n'


def accepted(*, trades=(), bids=(), asks=(), next_sequence=1):
    return CommandObservation(CommandResult(True, None), trades, bids, asks, next_sequence)


def rejected(error, *, bids=(), asks=(), next_sequence=1):
    return CommandObservation(CommandResult(False, error), (), bids, asks, next_sequence)


class CanonicalTraceWriterTests(unittest.TestCase):
    def test_01_empty_stream_exact_header_bytes(self):
        data = serialize_canonical_trace(())
        self.assertEqual(data, HEADER)
        self.assertTrue(data.endswith(b"\n"))
        self.assertNotIn(b"\r", data)
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))

    def test_02_one_command_known_answer_literal(self):
        observation = accepted(
            bids=(ReferenceOrder(1, Side.Buy, 100, 10, 1),),
            next_sequence=2,
        )
        expected = HEADER + (
            b'{"record_type":"command","command_index":"0","command":{"kind":"new","order_id":"1","side_code":"0","price_ticks":"100","quantity_units":"10"},'
            b'"command_result":{"accepted":true,"error":null},"trades":[],"bids":[{"order_id":"1","side":"Buy","price_ticks":"100","remaining_quantity_units":"10","sequence":"1"}],'
            b'"asks":[],"next_sequence":{"state":"available","value":"2"}}\n'
        )
        self.assertEqual(serialize_canonical_trace(((RawNew(1, 0, 100, 10), observation),)), expected)

    def test_03_two_command_known_answer_literal_and_indexes(self):
        first = accepted(
            asks=(ReferenceOrder(10, Side.Sell, 101, 5, 1),),
            next_sequence=2,
        )
        second = accepted(
            trades=(Trade(10, 20, 101, 5),),
            next_sequence=3,
        )
        expected = HEADER + (
            b'{"record_type":"command","command_index":"0","command":{"kind":"new","order_id":"10","side_code":"1","price_ticks":"101","quantity_units":"5"},'
            b'"command_result":{"accepted":true,"error":null},"trades":[],"bids":[],"asks":[{"order_id":"10","side":"Sell","price_ticks":"101","remaining_quantity_units":"5","sequence":"1"}],'
            b'"next_sequence":{"state":"available","value":"2"}}\n'
            b'{"record_type":"command","command_index":"1","command":{"kind":"new","order_id":"20","side_code":"0","price_ticks":"103","quantity_units":"5"},'
            b'"command_result":{"accepted":true,"error":null},"trades":[{"maker_order_id":"10","taker_order_id":"20","price_ticks":"101","quantity_units":"5"}],'
            b'"bids":[],"asks":[],"next_sequence":{"state":"available","value":"3"}}\n'
        )
        actual = serialize_canonical_trace(((RawNew(10, 1, 101, 5), first), (RawNew(20, 0, 103, 5), second)))
        self.assertEqual(actual, expected)

    def test_04_invalid_side_is_preserved_in_raw_command_evidence(self):
        observation = rejected(DomainError.InvalidSide)
        data = serialize_canonical_trace(((RawNew(9, 17, 100, 1), observation),))
        self.assertIn(b'"side_code":"17"', data)
        self.assertIn(b'"error":"InvalidSide"', data)
        validate_canonical_trace(data)

    def test_05_available_maximum_and_exhausted_are_distinct(self):
        command = RawCancel(999)
        available = serialize_canonical_trace(((command, rejected(DomainError.UnknownOrderId, next_sequence=UINT64_MAX)),))
        exhausted = serialize_canonical_trace(((command, rejected(DomainError.UnknownOrderId, next_sequence=None)),))
        self.assertIn(b'"state":"available","value":"18446744073709551615"', available)
        self.assertIn(b'"state":"exhausted","value":null', exhausted)
        self.assertNotEqual(available, exhausted)

    def test_06_new_cancel_modify_exact_shapes_round_trip(self):
        entries = (
            (RawNew(0, 255, INT64_MIN, 0), rejected(DomainError.InvalidPrice)),
            (RawCancel(UINT64_MAX), rejected(DomainError.UnknownOrderId)),
            (RawModify(UINT64_MAX, INT64_MAX, UINT64_MAX), rejected(DomainError.UnknownOrderId)),
        )
        data = serialize_canonical_trace(entries)
        validate_canonical_trace(data)
        self.assertIn(b'"kind":"new"', data)
        self.assertIn(b'"kind":"cancel"', data)
        self.assertIn(b'"kind":"modify"', data)

    def test_07_every_domain_error_name_round_trips_exactly(self):
        for error in DomainError:
            with self.subTest(error=error.value):
                data = serialize_canonical_trace(((RawCancel(1), rejected(error)),))
                self.assertIn(('"error":"' + error.value + '"').encode("ascii"), data)
                validate_canonical_trace(data)

    def test_08_trade_emission_order_is_preserved(self):
        observation = accepted(
            trades=(Trade(9, 50, 99, 2), Trade(7, 50, 100, 3), Trade(8, 50, 100, 1)),
            next_sequence=5,
        )
        data = serialize_canonical_trace(((RawNew(50, 0, 100, 6), observation),))
        first = data.index(b'"maker_order_id":"9"')
        second = data.index(b'"maker_order_id":"7"')
        third = data.index(b'"maker_order_id":"8"')
        self.assertLess(first, second)
        self.assertLess(second, third)

    def test_09_writer_rejects_noncanonical_bid_order_without_sorting(self):
        observation = accepted(
            bids=(
                ReferenceOrder(1, Side.Buy, 99, 1, 1),
                ReferenceOrder(2, Side.Buy, 100, 1, 2),
            ),
            next_sequence=3,
        )
        with self.assertRaises(CanonicalTraceError):
            serialize_canonical_trace(((RawCancel(999), observation),))

    def test_10_writer_rejects_wrong_side_entry(self):
        observation = accepted(
            bids=(ReferenceOrder(1, Side.Sell, 100, 1, 1),),
            next_sequence=2,
        )
        with self.assertRaises(CanonicalTraceError):
            serialize_canonical_trace(((RawCancel(999), observation),))

    def test_11_writer_rejects_zero_resting_quantity(self):
        observation = accepted(
            bids=(ReferenceOrder(1, Side.Buy, 100, 0, 1),),
            next_sequence=2,
        )
        with self.assertRaises(CanonicalTraceError):
            serialize_canonical_trace(((RawCancel(999), observation),))

    def test_12_writer_rejects_sequence_zero(self):
        observation = accepted(
            asks=(ReferenceOrder(1, Side.Sell, 100, 1, 0),),
            next_sequence=2,
        )
        with self.assertRaises(CanonicalTraceError):
            serialize_canonical_trace(((RawCancel(999), observation),))

    def test_13_writer_rejects_impossible_result_error_combinations(self):
        bad_accepted = CommandObservation(CommandResult(True, DomainError.InvalidPrice), (), (), (), 1)
        bad_rejected = CommandObservation(CommandResult(False, None), (), (), (), 1)
        with self.assertRaises(CanonicalTraceError):
            serialize_canonical_trace(((RawCancel(1), bad_accepted),))
        with self.assertRaises(CanonicalTraceError):
            serialize_canonical_trace(((RawCancel(1), bad_rejected),))

    def test_14_writer_rejects_malformed_raw_representation(self):
        good = rejected(DomainError.InvalidSide)
        for command in (
            RawNew(1, True, 100, 1),
            RawNew(1, 256, 100, 1),
            RawNew(1, 0, INT64_MAX + 1, 1),
            RawModify(-1, 100, 1),
        ):
            with self.subTest(command=command):
                with self.assertRaises(CanonicalTraceError):
                    serialize_canonical_trace(((command, good),))


    def test_15_writer_rejects_nonempty_trades_for_rejected_command(self):
        observation = CommandObservation(
            CommandResult(False, DomainError.UnknownOrderId),
            (Trade(1, 2, 100, 1),),
            (),
            (),
            1,
        )
        with self.assertRaises(CanonicalTraceError):
            serialize_canonical_trace(((RawCancel(999), observation),))


class CanonicalTraceValidatorTests(unittest.TestCase):
    def assertRejected(self, data):
        with self.assertRaises(CanonicalTraceError):
            validate_canonical_trace(data)

    def test_15_validator_rejects_utf8_bom(self):
        self.assertRejected(b"\xef\xbb\xbf" + HEADER)

    def test_16_validator_rejects_crlf(self):
        self.assertRejected(HEADER.replace(b"\n", b"\r\n"))

    def test_17_validator_rejects_missing_final_lf(self):
        self.assertRejected(HEADER[:-1])

    def test_18_validator_rejects_blank_lines(self):
        self.assertRejected(HEADER + b"\n")

    def test_19_validator_rejects_intertoken_whitespace(self):
        self.assertRejected(b'{"record_type": "trace_header","schema":"lob.canonical_trace","version":"1"}\n')

    def test_20_validator_rejects_duplicate_object_member(self):
        data = b'{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1","version":"1"}\n'
        self.assertRejected(data)

    def test_21_validator_rejects_reordered_members(self):
        data = b'{"schema":"lob.canonical_trace","record_type":"trace_header","version":"1"}\n'
        self.assertRejected(data)

    def test_22_validator_rejects_unicode_escape_for_fixed_ascii(self):
        data = b'{"record_type":"trace_header","schema":"lob.canonical_trace","version":"\\u0031"}\n'
        self.assertRejected(data)

    def test_23_validator_rejects_command_index_gap(self):
        canonical = serialize_canonical_trace(((RawCancel(1), rejected(DomainError.UnknownOrderId)),))
        mutated = canonical.replace(b'"command_index":"0"', b'"command_index":"1"')
        self.assertRejected(mutated)

    def test_24_validator_rejects_noncanonical_decimal_forms(self):
        canonical = serialize_canonical_trace(((RawCancel(7), rejected(DomainError.UnknownOrderId)),))
        for bad in (b'"07"', b'"+7"', b'"-0"', b'"7.0"', b'"7e0"'):
            with self.subTest(bad=bad):
                self.assertRejected(canonical.replace(b'"order_id":"7"', b'"order_id":' + bad))

    def test_25_validator_rejects_json_number_in_semantic_integer_field(self):
        canonical = serialize_canonical_trace(((RawCancel(7), rejected(DomainError.UnknownOrderId)),))
        self.assertRejected(canonical.replace(b'"order_id":"7"', b'"order_id":7'))

    def test_26_validator_rejects_invalid_allocator_state_value_pairs(self):
        canonical = serialize_canonical_trace(((RawCancel(7), rejected(DomainError.UnknownOrderId)),))
        self.assertRejected(canonical.replace(b'"state":"available","value":"1"', b'"state":"available","value":null'))
        self.assertRejected(canonical.replace(b'"state":"available","value":"1"', b'"state":"exhausted","value":"1"'))
        self.assertRejected(canonical.replace(b'"state":"available","value":"1"', b'"state":"available","value":"0"'))

    def test_27_validator_rejects_unknown_or_provenance_members(self):
        self.assertRejected(
            b'{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1","producer":"python"}\n'
        )
        self.assertRejected(
            b'{"record_type":"trace_header","schema":"lob.canonical_trace","version":"1","sha256":"00"}\n'
        )

    def test_28_writer_output_is_deterministic_and_validator_accepts_it(self):
        entries = (
            (RawNew(1, 0, 100, 2), accepted(bids=(ReferenceOrder(1, Side.Buy, 100, 2, 1),), next_sequence=2)),
            (RawCancel(9), rejected(DomainError.UnknownOrderId, bids=(ReferenceOrder(1, Side.Buy, 100, 2, 1),), next_sequence=2)),
        )
        first = serialize_canonical_trace(entries)
        second = serialize_canonical_trace(entries)
        self.assertEqual(first, second)
        validate_canonical_trace(first)

    def test_29_sha256_is_over_exact_complete_bytes_including_final_lf(self):
        data = serialize_canonical_trace(())
        self.assertEqual(canonical_trace_sha256(data), hashlib.sha256(data).hexdigest())
        self.assertNotEqual(canonical_trace_sha256(data), hashlib.sha256(data[:-1]).hexdigest())
        self.assertRegex(canonical_trace_sha256(data), r"^[0-9a-f]{64}$")

    def test_30_validator_rejects_repairable_noncanonical_book_order(self):
        observation = accepted(
            bids=(
                ReferenceOrder(1, Side.Buy, 100, 1, 1),
                ReferenceOrder(2, Side.Buy, 99, 1, 2),
            ),
            next_sequence=3,
        )
        canonical = serialize_canonical_trace(((RawCancel(999), observation),))
        first = b'{"order_id":"1","side":"Buy","price_ticks":"100","remaining_quantity_units":"1","sequence":"1"}'
        second = b'{"order_id":"2","side":"Buy","price_ticks":"99","remaining_quantity_units":"1","sequence":"2"}'
        mutated = canonical.replace(first + b"," + second, second + b"," + first)
        self.assertNotEqual(mutated, canonical)
        self.assertRejected(mutated)


    def test_31_validator_rejects_nonempty_trades_for_rejected_command(self):
        canonical = serialize_canonical_trace(
            ((RawCancel(999), rejected(DomainError.UnknownOrderId)),)
        )
        injected_trade = (
            b'{"maker_order_id":"1","taker_order_id":"2",'
            b'"price_ticks":"100","quantity_units":"1"}'
        )
        mutated = canonical.replace(
            b'"trades":[]',
            b'"trades":[' + injected_trade + b']',
        )
        self.assertNotEqual(mutated, canonical)
        self.assertRejected(mutated)


if __name__ == "__main__":
    unittest.main()
