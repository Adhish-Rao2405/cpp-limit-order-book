from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(
    __file__
).resolve().parent

MODULE_PATH = (
    HERE
    / "corpus_seal.py"
)

SPEC = (
    importlib.util
    .spec_from_file_location(
        "m5e3_corpus_seal",
        MODULE_PATH,
    )
)

assert SPEC is not None
assert SPEC.loader is not None

seal = importlib.util.module_from_spec(
    SPEC
)

SPEC.loader.exec_module(
    seal
)


class CorpusSealTests(
    unittest.TestCase
):
    def test_import_surface_is_stdlib_only(
        self,
    ) -> None:
        tree = ast.parse(
            MODULE_PATH.read_text(
                encoding="utf-8"
            )
        )

        imported: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(
                node,
                ast.Import,
            ):
                for alias in node.names:
                    imported.add(
                        alias.name.split(".")[0]
                    )

            elif isinstance(
                node,
                ast.ImportFrom,
            ):
                if node.module is not None:
                    imported.add(
                        node.module.split(".")[0]
                    )

        self.assertEqual(
            imported,
            {
                "__future__",
                "argparse",
                "hashlib",
                "json",
                "os",
                "pathlib",
                "subprocess",
                "sys",
            },
        )

    def test_binding_table_identity(
        self,
    ) -> None:
        records = (
            seal._binding_records()
        )

        self.assertEqual(
            len(records),
            96,
        )

        self.assertEqual(
            seal._binding_table_sha256(),
            (
                "ceb3483f507c87d9d2738bbb"
                "485529ca20037883def798ff"
                "7c8a6340167e5b2d"
            ),
        )

        self.assertEqual(
            records[0]["stream_id"],
            "G1-0001",
        )

        self.assertEqual(
            records[31]["stream_id"],
            "G1-0032",
        )

        self.assertEqual(
            records[32]["stream_id"],
            "G2-0001",
        )

        self.assertEqual(
            records[-1]["stream_id"],
            "G4-0016",
        )

    def test_expected_stream_denominator(
        self,
    ) -> None:
        records = (
            seal._expected_streams()
        )

        self.assertEqual(
            len(records),
            176,
        )

        self.assertEqual(
            len({
                record["stream_id"]
                for record in records
            }),
            176,
        )

        self.assertEqual(
            len({
                record["path"]
                for record in records
            }),
            176,
        )

        self.assertEqual(
            records[0]["stream_id"],
            "F01",
        )

        self.assertEqual(
            records[-1]["stream_id"],
            "X24",
        )

    def test_fixed_path_set_identity(
        self,
    ) -> None:
        paths = [
            str(record["path"])
            for record
            in seal._fixed_entries()
        ]

        payload = (
            "\n".join(
                sorted(paths)
            )
            + "\n"
        ).encode("utf-8")

        self.assertEqual(
            hashlib.sha256(
                payload
            ).hexdigest(),
            (
                "28b3ae8b69e82ba5db25061e"
                "ad532a9e85af3171fda52101"
                "ae64a55a14f77afa"
            ),
        )

    def test_transport_validator(
        self,
    ) -> None:
        valid = (
            b"LOBQ1|1\n"
            b"N|1|0|10|2\n"
        )

        self.assertEqual(
            seal._validate_transport(
                valid,
                stream_id="probe",
            ),
            1,
        )

        invalid_cases = [
            (
                b"LOBQ1|1\r\n",
                "CR",
            ),
            (
                b"LOBQ1|1",
                "NO_FINAL_LF",
            ),
            (
                b"LOBQ1|1\n\n",
                "BLANK",
            ),
            (
                b"LOBQ1|1\n"
                b"N|1|0|10|2\x00\n",
                "NUL",
            ),
            (
                b"\xef\xbb\xbf"
                b"LOBQ1|1\n",
                "BOM",
            ),
        ]

        for data, label in invalid_cases:
            with self.subTest(
                label=label
            ):
                with self.assertRaises(
                    seal.Invalid
                ):
                    seal._validate_transport(
                        data,
                        stream_id="probe",
                    )

    def test_wrapper_hash_domain(
        self,
    ) -> None:
        payload = {
            "schema": (
                "lob.m5e0."
                "corpus_manifest.payload"
            ),
            "version": "1",
            "probe": "test",
        }

        wrapper = (
            seal._wrapper_for_payload(
                payload
            )
        )

        payload_bytes = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")

        self.assertEqual(
            wrapper[
                "aggregate_manifest_sha256"
            ],
            hashlib.sha256(
                payload_bytes
            ).hexdigest(),
        )

        self.assertNotIn(
            "aggregate_manifest_sha256",
            wrapper["payload"],
        )

        self.assertTrue(
            seal._wrapper_bytes(
                payload
            ).endswith(b"\n")
        )

    def test_incomplete_seal_writes_nothing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)

            with self.assertRaises(
                seal.Incomplete
            ):
                seal.seal_repo(
                    root
                )

            manifest = (
                root
                / "tools"
                / "differential"
                / "corpus"
                / "m5e"
                / "m5e0_corpus_manifest.json"
            )

            self.assertFalse(
                manifest.exists()
            )

    def test_existing_manifest_is_never_overwritten(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)

            manifest = (
                root
                / "tools"
                / "differential"
                / "corpus"
                / "m5e"
                / "m5e0_corpus_manifest.json"
            )

            manifest.parent.mkdir(
                parents=True
            )

            original = b"do-not-overwrite\n"

            manifest.write_bytes(
                original
            )

            with self.assertRaises(
                seal.Invalid
            ) as ctx:
                seal.seal_repo(
                    root
                )

            self.assertEqual(
                ctx.exception.code,
                "MANIFEST_ALREADY_EXISTS",
            )

            self.assertEqual(
                manifest.read_bytes(),
                original,
            )

    def test_missing_manifest_verify_is_incomplete(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)

            with self.assertRaises(
                seal.Incomplete
            ) as ctx:
                seal.verify_repo(
                    root
                )

            self.assertEqual(
                ctx.exception.code,
                "MANIFEST_MISSING",
            )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
