"""Qualification tests for the independent M5 differential harness."""

from __future__ import annotations

import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from differential_harness import (
    CLASS_CANDIDATE_ADAPTER,
    CLASS_CANDIDATE_SERIALIZER,
    CLASS_CANONICAL_MISMATCH,
    CLASS_HARNESS,
    CLASS_MALFORMED_INPUT,
    CLASS_PROCESS_RUNTIME,
    CLASS_REFERENCE_SERIALIZER,
    CanonicalValidationError,
    run_differential_case,
    validate_canonical_trace,
)


HEADER = (
    b'{"record_type":"trace_header",'
    b'"schema":"lob.canonical_trace",'
    b'"version":"1"}\n'
)

ONE_COMMAND = (
    HEADER
    + b'{"record_type":"command",'
    b'"command_index":"0",'
    b'"command":{"kind":"cancel","order_id":"1"},'
    b'"command_result":{"accepted":false,'
    b'"error":"UnknownOrderId"},'
    b'"trades":[],'
    b'"bids":[],'
    b'"asks":[],'
    b'"next_sequence":{"state":"available","value":"1"}}\n'
)


class HarnessTestCase(unittest.TestCase):
    def _write_fake_runner(
        self,
        path: Path,
        *,
        returncode: int,
        trace: bytes | None = None,
        mutate_input: bool = False,
        sleep_seconds: float = 0.0,
        counter: Path | None = None,
    ) -> None:
        source = f"""
        import pathlib
        import sys
        import time

        input_path = pathlib.Path(sys.argv[1])
        trace_path = pathlib.Path(sys.argv[2])

        counter_path = {str(counter) if counter is not None else None!r}

        if counter_path:
            counter = pathlib.Path(counter_path)
            current = (
                int(counter.read_text(encoding="ascii"))
                if counter.exists()
                else 0
            )
            counter.write_text(
                str(current + 1),
                encoding="ascii",
            )

        if {sleep_seconds!r}:
            time.sleep({sleep_seconds!r})

        if {mutate_input!r}:
            input_path.write_bytes(
                input_path.read_bytes() + b"X"
            )

        trace = {trace!r}

        if trace is not None:
            trace_path.write_bytes(trace)

        raise SystemExit({returncode!r})
        """

        path.write_text(
            textwrap.dedent(source),
            encoding="utf-8",
            newline="\n",
        )

    def _template(
        self,
        runner: Path,
    ) -> tuple[str, ...]:
        return (
            sys.executable,
            "-B",
            str(runner),
            "{input}",
            "{trace}",
        )

    def _run(
        self,
        directory: Path,
        *,
        candidate_rc: int = 0,
        reference_rc: int = 0,
        candidate_trace: bytes | None = HEADER,
        reference_trace: bytes | None = HEADER,
        malformed: bool = False,
        candidate_mutates: bool = False,
        reference_mutates: bool = False,
        candidate_sleep: float = 0.0,
        reference_sleep: float = 0.0,
        timeout: float = 5.0,
        candidate_counter: Path | None = None,
        reference_counter: Path | None = None,
    ):
        input_path = directory / "input.lobq1"

        input_path.write_bytes(
            b"BAD\n"
            if malformed
            else b"LOBQ1|1\n"
        )

        candidate_runner = (
            directory / "candidate.py"
        )

        reference_runner = (
            directory / "reference.py"
        )

        self._write_fake_runner(
            candidate_runner,
            returncode=candidate_rc,
            trace=candidate_trace,
            mutate_input=candidate_mutates,
            sleep_seconds=candidate_sleep,
            counter=candidate_counter,
        )

        self._write_fake_runner(
            reference_runner,
            returncode=reference_rc,
            trace=reference_trace,
            mutate_input=reference_mutates,
            sleep_seconds=reference_sleep,
            counter=reference_counter,
        )

        return run_differential_case(
            source_input=input_path,
            candidate_template=self._template(
                candidate_runner
            ),
            reference_template=self._template(
                reference_runner
            ),
            expected_malformed=malformed,
            timeout_seconds=timeout,
        )


class CanonicalValidatorTests(unittest.TestCase):
    def test_accepts_exact_header_only_trace(self):
        logical = validate_canonical_trace(
            HEADER
        )

        self.assertEqual(
            len(logical),
            1,
        )

    def test_accepts_exact_command_trace(self):
        logical = validate_canonical_trace(
            ONE_COMMAND
        )

        self.assertEqual(
            len(logical),
            2,
        )

    def test_rejects_crlf(self):
        with self.assertRaises(
            CanonicalValidationError
        ):
            validate_canonical_trace(
                HEADER.replace(
                    b"\n",
                    b"\r\n",
                )
            )

    def test_rejects_intertoken_whitespace(self):
        invalid = (
            b'{"record_type":"trace_header", '
            b'"schema":"lob.canonical_trace",'
            b'"version":"1"}\n'
        )

        with self.assertRaises(
            CanonicalValidationError
        ):
            validate_canonical_trace(
                invalid
            )

    def test_rejects_logically_equivalent_json_escape(self):
        invalid = (
            b'{"record_type":"trace_header",'
            b'"schema":"lob.canonical_\\u0074race",'
            b'"version":"1"}\\n'
        )

        with self.assertRaises(
            CanonicalValidationError
        ):
            validate_canonical_trace(
                invalid
            )

    def test_rejects_reordered_header_members(self):
        invalid = (
            b'{"schema":"lob.canonical_trace",'
            b'"record_type":"trace_header",'
            b'"version":"1"}\n'
        )

        with self.assertRaises(
            CanonicalValidationError
        ):
            validate_canonical_trace(
                invalid
            )

    def test_rejects_duplicate_members(self):
        invalid = (
            b'{"record_type":"trace_header",'
            b'"schema":"lob.canonical_trace",'
            b'"schema":"lob.canonical_trace",'
            b'"version":"1"}\n'
        )

        with self.assertRaises(
            CanonicalValidationError
        ):
            validate_canonical_trace(
                invalid
            )

    def test_rejects_command_index_gap(self):
        invalid = ONE_COMMAND.replace(
            b'"command_index":"0"',
            b'"command_index":"1"',
        )

        with self.assertRaises(
            CanonicalValidationError
        ):
            validate_canonical_trace(
                invalid
            )

    def test_rejects_noncanonical_decimal(self):
        invalid = ONE_COMMAND.replace(
            b'"order_id":"1"',
            b'"order_id":"01"',
            1,
        )

        with self.assertRaises(
            CanonicalValidationError
        ):
            validate_canonical_trace(
                invalid
            )

    def test_rejects_rejected_command_with_trade(self):
        invalid = ONE_COMMAND.replace(
            b'"trades":[]',
            (
                b'"trades":[{"maker_order_id":"1",'
                b'"taker_order_id":"2",'
                b'"price_ticks":"100",'
                b'"quantity_units":"1"}]'
            ),
        )

        with self.assertRaises(
            CanonicalValidationError
        ):
            validate_canonical_trace(
                invalid
            )


class DifferentialHarnessTests(HarnessTestCase):
    def test_exact_valid_bytes_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary)
            )

        self.assertEqual(
            result.outcome,
            "PASS",
        )

        self.assertIsNone(
            result.classification
        )

        self.assertEqual(
            result.candidate_trace_sha256,
            result.reference_trace_sha256,
        )

    def test_valid_canonical_mismatch_is_class_9(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary),
                reference_trace=ONE_COMMAND,
            )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )

        self.assertEqual(
            result.classification,
            CLASS_CANONICAL_MISMATCH,
        )

        self.assertIsNotNone(
            result.first_differing_byte_offset
        )

        self.assertIsNotNone(
            result.first_differing_record
        )

    def test_invalid_candidate_trace_is_class_6(self):
        invalid = (
            b'{"record_type":"trace_header", '
            b'"schema":"lob.canonical_trace",'
            b'"version":"1"}\n'
        )

        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary),
                candidate_trace=invalid,
            )

        self.assertEqual(
            result.classification,
            CLASS_CANDIDATE_SERIALIZER,
        )

    def test_invalid_reference_trace_is_class_7(self):
        invalid = (
            b'{"record_type":"trace_header", '
            b'"schema":"lob.canonical_trace",'
            b'"version":"1"}\n'
        )

        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary),
                reference_trace=invalid,
            )

        self.assertEqual(
            result.classification,
            CLASS_REFERENCE_SERIALIZER,
        )

    def test_expected_malformed_dual_rejection_passes_class_1(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary),
                candidate_rc=10,
                reference_rc=10,
                candidate_trace=None,
                reference_trace=None,
                malformed=True,
            )

        self.assertEqual(
            result.outcome,
            "PASS",
        )

        self.assertEqual(
            result.classification,
            CLASS_MALFORMED_INPUT,
        )

    def test_candidate_accepting_expected_malformed_is_class_2(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary),
                candidate_rc=0,
                reference_rc=10,
                candidate_trace=HEADER,
                reference_trace=None,
                malformed=True,
            )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )

        self.assertEqual(
            result.classification,
            CLASS_CANDIDATE_ADAPTER,
        )

    def test_success_without_trace_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary),
                candidate_rc=0,
                candidate_trace=None,
            )

        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )

    def test_nonzero_with_trace_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary),
                candidate_rc=10,
                candidate_trace=HEADER,
            )

        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )

    def test_input_mutation_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary),
                candidate_mutates=True,
            )

        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )

    def test_timeout_is_class_11(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                Path(temporary),
                candidate_sleep=0.5,
                timeout=0.05,
            )

        self.assertEqual(
            result.classification,
            CLASS_PROCESS_RUNTIME,
        )


    def test_source_read_failure_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)

            result = run_differential_case(
                source_input=directory,
                candidate_template=(
                    "unused-candidate",
                    "{input}",
                    "{trace}",
                ),
                reference_template=(
                    "unused-reference",
                    "{input}",
                    "{trace}",
                ),
                expected_malformed=False,
                timeout_seconds=5.0,
            )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "source input read failed",
            result.detail,
        )

    def test_input_copy_write_failure_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source_input = (
                directory / "input.lobq1"
            )
            source_input.write_bytes(
                b"LOBQ1|1\n"
            )

            original_write_bytes = (
                Path.write_bytes
            )

            def controlled_write_bytes(
                path,
                data,
            ):
                if (
                    path.name
                    == "candidate-input.lobq1"
                ):
                    raise OSError(
                        "synthetic input-copy failure"
                    )

                return original_write_bytes(
                    path,
                    data,
                )

            with mock.patch.object(
                Path,
                "write_bytes",
                new=controlled_write_bytes,
            ):
                result = run_differential_case(
                    source_input=source_input,
                    candidate_template=(
                        "unused-candidate",
                        "{input}",
                        "{trace}",
                    ),
                    reference_template=(
                        "unused-reference",
                        "{input}",
                        "{trace}",
                    ),
                    expected_malformed=False,
                    timeout_seconds=5.0,
                    work_directory=(
                        directory / "work"
                    ),
                )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "input byte identity setup failed",
            result.detail,
        )

    def test_temporary_work_directory_failure_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source_input = (
                directory / "input.lobq1"
            )
            source_input.write_bytes(
                b"LOBQ1|1\n"
            )

            with mock.patch(
                "differential_harness."
                "tempfile.TemporaryDirectory",
                side_effect=OSError(
                    "synthetic temporary-directory failure"
                ),
            ):
                result = run_differential_case(
                    source_input=source_input,
                    candidate_template=(
                        "unused-candidate",
                        "{input}",
                        "{trace}",
                    ),
                    reference_template=(
                        "unused-reference",
                        "{input}",
                        "{trace}",
                    ),
                    expected_malformed=False,
                    timeout_seconds=5.0,
                )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "temporary work directory failure",
            result.detail,
        )

    def test_work_directory_failure_preserves_primary_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source_input = (
                directory / "input.lobq1"
            )
            source_input.write_bytes(
                b"LOBQ1|1\n"
            )

            original_read_bytes = (
                Path.read_bytes
            )
            original_mkdir = Path.mkdir

            state = {
                "mkdir_failed": False,
            }

            def controlled_read_bytes(path):
                if (
                    path == source_input
                    and state["mkdir_failed"]
                ):
                    raise OSError(
                        "secondary source-read failure"
                    )

                return original_read_bytes(path)

            def controlled_mkdir(
                path,
                *args,
                **kwargs,
            ):
                if path.name == "work":
                    state["mkdir_failed"] = True
                    raise OSError(
                        "primary mkdir failure"
                    )

                return original_mkdir(
                    path,
                    *args,
                    **kwargs,
                )

            with mock.patch.object(
                Path,
                "read_bytes",
                new=controlled_read_bytes,
            ), mock.patch.object(
                Path,
                "mkdir",
                new=controlled_mkdir,
            ):
                result = run_differential_case(
                    source_input=source_input,
                    candidate_template=(
                        "unused-candidate",
                        "{input}",
                        "{trace}",
                    ),
                    reference_template=(
                        "unused-reference",
                        "{input}",
                        "{trace}",
                    ),
                    expected_malformed=False,
                    timeout_seconds=5.0,
                    work_directory=(
                        directory / "work"
                    ),
                )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "work directory creation failed",
            result.detail,
        )
        self.assertNotIn(
            "secondary source-read failure",
            result.detail,
        )

    def test_trace_metadata_failure_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original_lstat = Path.lstat

            def controlled_lstat(path):
                if (
                    path.name
                    == "candidate-trace.jsonl"
                ):
                    raise OSError(
                        "synthetic trace-metadata failure"
                    )

                return original_lstat(path)

            with mock.patch.object(
                Path,
                "lstat",
                new=controlled_lstat,
            ):
                result = self._run(
                    directory
                )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "trace metadata read failed",
            result.detail,
        )

    def test_non_regular_trace_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original_lstat = Path.lstat

            def controlled_lstat(path):
                if (
                    path.name
                    == "candidate-trace.jsonl"
                ):
                    return mock.Mock(
                        st_mode=(
                            stat.S_IFLNK
                            | 0o777
                        ),
                    )

                return original_lstat(path)

            with mock.patch.object(
                Path,
                "lstat",
                new=controlled_lstat,
            ):
                result = self._run(
                    directory
                )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "candidate trace is not "
            "a regular file",
            result.detail,
        )

    def test_trace_alias_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original_lstat = Path.lstat

            def controlled_lstat(path):
                if path.name in {
                    "candidate-trace.jsonl",
                    "reference-trace.jsonl",
                }:
                    return mock.Mock(
                        st_mode=(
                            stat.S_IFREG
                            | 0o600
                        ),
                        st_dev=17,
                        st_ino=23,
                    )

                return original_lstat(path)

            with mock.patch.object(
                Path,
                "lstat",
                new=controlled_lstat,
            ):
                result = self._run(
                    directory
                )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "alias the same filesystem object",
            result.detail,
        )


    def test_reference_input_copy_write_failure_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source_input = (
                directory / "input.lobq1"
            )
            source_input.write_bytes(
                b"LOBQ1|1\n"
            )

            original_write_bytes = (
                Path.write_bytes
            )

            def controlled_write_bytes(
                path,
                data,
            ):
                if (
                    path.name
                    == "reference-input.lobq1"
                ):
                    raise OSError(
                        "synthetic reference "
                        "input-copy failure"
                    )

                return original_write_bytes(
                    path,
                    data,
                )

            with mock.patch.object(
                Path,
                "write_bytes",
                new=controlled_write_bytes,
            ):
                result = run_differential_case(
                    source_input=source_input,
                    candidate_template=(
                        "unused-candidate",
                        "{input}",
                        "{trace}",
                    ),
                    reference_template=(
                        "unused-reference",
                        "{input}",
                        "{trace}",
                    ),
                    expected_malformed=False,
                    timeout_seconds=5.0,
                    work_directory=(
                        directory / "work"
                    ),
                )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "input byte identity setup failed",
            result.detail,
        )

    def test_reference_trace_metadata_failure_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original_lstat = Path.lstat

            def controlled_lstat(path):
                if (
                    path.name
                    == "reference-trace.jsonl"
                ):
                    raise OSError(
                        "synthetic reference "
                        "trace-metadata failure"
                    )

                return original_lstat(path)

            with mock.patch.object(
                Path,
                "lstat",
                new=controlled_lstat,
            ):
                result = self._run(
                    directory
                )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "trace metadata read failed",
            result.detail,
        )

    def test_reference_non_regular_trace_is_class_8(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original_lstat = Path.lstat

            def controlled_lstat(path):
                if (
                    path.name
                    == "reference-trace.jsonl"
                ):
                    return mock.Mock(
                        st_mode=(
                            stat.S_IFLNK
                            | 0o777
                        ),
                    )

                return original_lstat(path)

            with mock.patch.object(
                Path,
                "lstat",
                new=controlled_lstat,
            ):
                result = self._run(
                    directory
                )

        self.assertEqual(
            result.outcome,
            "HOLD",
        )
        self.assertEqual(
            result.classification,
            CLASS_HARNESS,
        )
        self.assertIn(
            "reference trace is not "
            "a regular file",
            result.detail,
        )

    def test_each_producer_executes_exactly_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)

            candidate_counter = (
                directory /
                "candidate-count.txt"
            )

            reference_counter = (
                directory /
                "reference-count.txt"
            )

            result = self._run(
                directory,
                candidate_counter=(
                    candidate_counter
                ),
                reference_counter=(
                    reference_counter
                ),
            )

            self.assertEqual(
                result.outcome,
                "PASS",
            )

            self.assertEqual(
                candidate_counter.read_text(
                    encoding="ascii"
                ),
                "1",
            )

            self.assertEqual(
                reference_counter.read_text(
                    encoding="ascii"
                ),
                "1",
            )


if __name__ == "__main__":
    unittest.main()
