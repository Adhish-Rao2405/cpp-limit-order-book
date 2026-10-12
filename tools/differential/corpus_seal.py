from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

TOOL_VERSION = "m5e3-corpus-seal-v1"

A2_DESIGN_SHA256 = (
    "30c9ae9167bef4867b2d2731b5948b135"
    "e8c8ed2dee3fb4e1efda3b9b5ae8e1c"
)

B1_BINDING_SHA256 = (
    "b877fbeea0092cefedcdd6dffdb7845f"
    "f9cf426914acd1fb610743b669174669"
)

B1_BINDING_TABLE_SHA256 = (
    "ceb3483f507c87d9d2738bbb485529ca"
    "20037883def798ff7c8a6340167e5b2d"
)

M5E1_SPEC_SHA256 = (
    "c9794d57b6318c85e31e259ac0b49289"
    "63760d870ce0ff6c45727d86a0ba719f"
)

FIXED_PATHS_SHA256 = (
    "28b3ae8b69e82ba5db25061ead532a9e"
    "85af3171fda52101ae64a55a14f77afa"
)

FIXED_IDENTITIES_SHA256 = (
    "35eafaf6c092d5e7e0e05a68ecd5e313"
    "25d636e4013d313dadbaedd5d5fbe554"
)

F_AGGREGATE_SHA256 = (
    "afbd9dbe24944ea15b6f429e22b94769"
    "b7b2bcee9ea6b6961af5ab77dd1781dc"
)

B_AGGREGATE_SHA256 = (
    "dd21969634768efc70b102cc513b6d5a"
    "8dadd136d3570fd2b7ee37eaeb3e8283"
)

X_AGGREGATE_SHA256 = (
    "bd4fbc1530a15c7ede6a759e35de4636"
    "352d6db17ff46ff94ea3daa0768736c4"
)

GENERATOR_VERSION = "m5f-generator-v1"
GENERATOR_SOURCE_PATH = "tools/differential/workload_generator.py"

FINAL_MANIFEST_PATH = (
    "tools/differential/corpus/m5e/"
    "m5e0_corpus_manifest.json"
)

CORPUS_ROOT = "tools/differential/corpus/m5e"

LOBQ1_VERSION = "1"
PRNG_ALGORITHM = "SplitMix64"

SEEDS = [
    "0x243F6A8885A308D3",
    "0x13198A2E03707344",
    "0xA4093822299F31D0",
    "0x082EFA98EC4E6C89",
]

FAMILY_ORDER = [
    "F",
    "B",
    "G1",
    "G2",
    "G3",
    "G4",
    "X",
]

STREAM_COUNTS = {
    "F": 32,
    "B": 24,
    "G1": 32,
    "G2": 32,
    "G3": 16,
    "G4": 16,
    "X": 24,
}

COMMAND_COUNTS = {
    "F": 79,
    "B": 24,
    "G1": 8192,
    "G2": 8192,
    "G3": 16384,
    "G4": 1024,
    "X": 0,
}

GENERATED_FAMILY = {
    "G1": {
        "streams_per_seed": 8,
        "stream_count": 32,
        "commands_per_stream": 256,
        "root": (
            "tools/differential/corpus/m5e/"
            "generated/g1"
        ),
    },
    "G2": {
        "streams_per_seed": 8,
        "stream_count": 32,
        "commands_per_stream": 256,
        "root": (
            "tools/differential/corpus/m5e/"
            "generated/g2"
        ),
    },
    "G3": {
        "streams_per_seed": 4,
        "stream_count": 16,
        "commands_per_stream": 1024,
        "root": (
            "tools/differential/corpus/m5e/"
            "generated/g3"
        ),
    },
    "G4": {
        "streams_per_seed": 4,
        "stream_count": 16,
        "commands_per_stream": 64,
        "root": (
            "tools/differential/corpus/m5e/"
            "generated/g4"
        ),
    },
}


class QualificationError(RuntimeError):
    def __init__(
        self,
        code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.details = details or {}


class Incomplete(QualificationError):
    pass


class Invalid(QualificationError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(
    value: object,
    *,
    final_lf: bool,
) -> bytes:
    data = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    if final_lf:
        data += b"\n"

    return data


def _binding_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []

    for family in ("G1", "G2", "G3", "G4"):
        contract = GENERATED_FAMILY[family]

        streams_per_seed = int(
            contract["streams_per_seed"]
        )

        stream_count = int(
            contract["stream_count"]
        )

        commands_per_stream = int(
            contract["commands_per_stream"]
        )

        root = str(contract["root"])

        for stream_index in range(stream_count):
            seed_index = (
                stream_index
                // streams_per_seed
            )

            seed_local_stream_index = (
                stream_index
                % streams_per_seed
            )

            stream_id = (
                family
                + "-"
                + f"{stream_index + 1:04d}"
            )

            records.append(
                {
                    "family": family,
                    "stream_index": stream_index,
                    "stream_id": stream_id,
                    "seed_index": seed_index,
                    "seed": SEEDS[seed_index],
                    "seed_local_stream_index": (
                        seed_local_stream_index
                    ),
                    "command_count": (
                        commands_per_stream
                    ),
                    "path": (
                        root
                        + "/"
                        + stream_id
                        + ".lobq1"
                    ),
                }
            )

    return records


def _binding_table_sha256() -> str:
    return _sha256(
        _canonical_json_bytes(
            _binding_records(),
            final_lf=False,
        )
    )


def _fixed_entries() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []

    for index in range(32):
        stream_id = f"F{index + 1:02d}"

        records.append(
            {
                "family": "F",
                "stream_id": stream_id,
                "stream_index": index,
                "path": (
                    "tools/differential/corpus/m5e/"
                    "fixed/"
                    + stream_id
                    + ".lobq1"
                ),
            }
        )

    for index in range(24):
        stream_id = f"B{index + 1:02d}"

        records.append(
            {
                "family": "B",
                "stream_id": stream_id,
                "stream_index": index,
                "path": (
                    "tools/differential/corpus/m5e/"
                    "boundary/"
                    + stream_id
                    + ".lobq1"
                ),
            }
        )

    for index in range(24):
        stream_id = f"X{index + 1:02d}"

        records.append(
            {
                "family": "X",
                "stream_id": stream_id,
                "stream_index": index,
                "path": (
                    "tools/differential/corpus/m5e/"
                    "malformed/"
                    + stream_id
                    + ".lobq1"
                ),
            }
        )

    return records


def _expected_streams() -> list[dict[str, object]]:
    fixed = _fixed_entries()

    fixed_by_family = {
        family: [
            record
            for record in fixed
            if record["family"] == family
        ]
        for family in ("F", "B", "X")
    }

    generated = _binding_records()

    generated_by_family = {
        family: [
            record
            for record in generated
            if record["family"] == family
        ]
        for family in ("G1", "G2", "G3", "G4")
    }

    ordered: list[dict[str, object]] = []

    ordered.extend(fixed_by_family["F"])
    ordered.extend(fixed_by_family["B"])
    ordered.extend(generated_by_family["G1"])
    ordered.extend(generated_by_family["G2"])
    ordered.extend(generated_by_family["G3"])
    ordered.extend(generated_by_family["G4"])
    ordered.extend(fixed_by_family["X"])

    return ordered


def _validate_internal_constants() -> None:
    bindings = _binding_records()

    if len(bindings) != 96:
        raise Invalid(
            "INTERNAL_BINDING_COUNT",
            {
                "observed": len(bindings),
                "expected": 96,
            },
        )

    observed_binding_sha = (
        _binding_table_sha256()
    )

    if observed_binding_sha != B1_BINDING_TABLE_SHA256:
        raise Invalid(
            "INTERNAL_BINDING_IDENTITY",
            {
                "observed": observed_binding_sha,
                "expected": B1_BINDING_TABLE_SHA256,
            },
        )

    expected = _expected_streams()

    if len(expected) != 176:
        raise Invalid(
            "INTERNAL_STREAM_COUNT",
            {
                "observed": len(expected),
                "expected": 176,
            },
        )

    ids = [
        str(record["stream_id"])
        for record in expected
    ]

    paths = [
        str(record["path"])
        for record in expected
    ]

    if len(set(ids)) != 176:
        raise Invalid(
            "INTERNAL_DUPLICATE_STREAM_ID"
        )

    if len(set(paths)) != 176:
        raise Invalid(
            "INTERNAL_DUPLICATE_STREAM_PATH"
        )


def _repo_path(
    repo_root: pathlib.Path,
    relative: str,
) -> pathlib.Path:
    pure = pathlib.PurePosixPath(relative)

    if pure.is_absolute():
        raise Invalid(
            "ABSOLUTE_PATH_FORBIDDEN",
            {"path": relative},
        )

    if ".." in pure.parts:
        raise Invalid(
            "PATH_TRAVERSAL_FORBIDDEN",
            {"path": relative},
        )

    return repo_root.joinpath(*pure.parts)


def _read_regular_file(
    path: pathlib.Path,
    relative: str,
) -> bytes:
    if path.is_symlink():
        raise Invalid(
            "SYMLINK_STREAM_FORBIDDEN",
            {"path": relative},
        )

    if not path.exists():
        raise Incomplete(
            "REQUIRED_FILE_MISSING",
            {"path": relative},
        )

    if not path.is_file():
        raise Invalid(
            "STREAM_NOT_REGULAR_FILE",
            {"path": relative},
        )

    return path.read_bytes()


def _validate_transport(
    data: bytes,
    *,
    stream_id: str,
) -> int:
    if data.startswith(b"\xef\xbb\xbf"):
        raise Invalid(
            "TRANSPORT_BOM",
            {"stream_id": stream_id},
        )

    if b"\r" in data:
        raise Invalid(
            "TRANSPORT_CR",
            {"stream_id": stream_id},
        )

    if b"\x00" in data:
        raise Invalid(
            "TRANSPORT_NUL",
            {"stream_id": stream_id},
        )

    if not data.endswith(b"\n"):
        raise Invalid(
            "TRANSPORT_FINAL_LF",
            {"stream_id": stream_id},
        )

    try:
        data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise Invalid(
            "TRANSPORT_NON_ASCII",
            {"stream_id": stream_id},
        ) from exc

    records = data.split(b"\n")[:-1]

    if not records:
        raise Invalid(
            "TRANSPORT_EMPTY",
            {"stream_id": stream_id},
        )

    if any(record == b"" for record in records):
        raise Invalid(
            "TRANSPORT_BLANK_RECORD",
            {"stream_id": stream_id},
        )

    if max(map(len, records)) > 128:
        raise Invalid(
            "TRANSPORT_RECORD_TOO_LONG",
            {"stream_id": stream_id},
        )

    if not records[0].startswith(b"LOBQ1|"):
        raise Invalid(
            "TRANSPORT_HEADER",
            {"stream_id": stream_id},
        )

    return len(records) - 1


def _family_aggregate(
    entries: list[tuple[str, bytes]],
) -> str:
    digest = hashlib.sha256()

    for stream_id, data in entries:
        digest.update(
            stream_id.encode("ascii")
        )
        digest.update(b"\x00")
        digest.update(data)
        digest.update(b"\x00")

    return digest.hexdigest()


def _audit_corpus_tree(
    repo_root: pathlib.Path,
) -> set[str]:
    corpus_root = _repo_path(
        repo_root,
        CORPUS_ROOT,
    )

    if corpus_root.is_symlink():
        raise Invalid(
            "CORPUS_ROOT_SYMLINK"
        )

    if not corpus_root.exists():
        raise Incomplete(
            "CORPUS_ROOT_MISSING"
        )

    if not corpus_root.is_dir():
        raise Invalid(
            "CORPUS_ROOT_NOT_DIRECTORY"
        )

    actual_lobq1: set[str] = set()

    for node in corpus_root.rglob("*"):
        if node.is_symlink():
            raise Invalid(
                "CORPUS_SYMLINK_FORBIDDEN",
                {
                    "path": (
                        node.relative_to(
                            repo_root
                        ).as_posix()
                    ),
                },
            )

        if node.is_file():
            relative = node.relative_to(
                repo_root
            ).as_posix()

            if node.suffix == ".lobq1":
                actual_lobq1.add(
                    relative
                )

        elif not node.is_dir():
            raise Invalid(
                "CORPUS_SPECIAL_NODE",
                {
                    "path": (
                        node.relative_to(
                            repo_root
                        ).as_posix()
                    ),
                },
            )

    return actual_lobq1


def _verify_fixed_corpus(
    repo_root: pathlib.Path,
    actual_lobq1: set[str],
) -> dict[str, object]:
    expected = _fixed_entries()

    expected_paths = [
        str(record["path"])
        for record in expected
    ]

    missing = [
        path
        for path in expected_paths
        if path not in actual_lobq1
    ]

    if missing:
        raise Incomplete(
            "FIXED_CORPUS_INCOMPLETE",
            {
                "missing_fixed_stream_count": (
                    len(missing)
                ),
                "missing_fixed_streams": (
                    missing
                ),
            },
        )

    path_blob = (
        "\n".join(
            sorted(expected_paths)
        )
        + "\n"
    ).encode("utf-8")

    observed_paths_sha256 = _sha256(
        path_blob
    )

    if (
        observed_paths_sha256
        != FIXED_PATHS_SHA256
    ):
        raise Invalid(
            "FIXED_PATH_SET_IDENTITY",
            {
                "observed": (
                    observed_paths_sha256
                ),
                "expected": (
                    FIXED_PATHS_SHA256
                ),
            },
        )

    identity_lines: list[str] = []

    family_bytes: dict[
        str,
        list[tuple[str, bytes]],
    ] = {
        "F": [],
        "B": [],
        "X": [],
    }

    manifest_records: list[
        dict[str, object]
    ] = []

    family_command_count = {
        "F": 0,
        "B": 0,
        "X": 0,
    }

    for record in expected:
        family = str(
            record["family"]
        )

        stream_id = str(
            record["stream_id"]
        )

        stream_index = int(
            record["stream_index"]
        )

        relative = str(
            record["path"]
        )

        data = _read_regular_file(
            _repo_path(
                repo_root,
                relative,
            ),
            relative,
        )

        sha256 = _sha256(data)

        if family in ("F", "B"):
            command_count = (
                _validate_transport(
                    data,
                    stream_id=stream_id,
                )
            )
        else:
            command_count = 0

        family_command_count[
            family
        ] += command_count

        family_bytes[
            family
        ].append(
            (
                stream_id,
                data,
            )
        )

        identity_lines.append(
            stream_id
            + "|"
            + family
            + "|"
            + relative
            + "|"
            + str(len(data))
            + "|"
            + sha256
        )

        manifest_records.append(
            {
                "family": family,
                "stream_id": stream_id,
                "stream_index": (
                    stream_index
                ),
                "command_count": (
                    command_count
                ),
                "path": relative,
                "byte_length": len(data),
                "sha256": sha256,
            }
        )

    identity_blob = (
        "\n".join(identity_lines)
        + "\n"
    ).encode("utf-8")

    observed_identity_sha256 = (
        _sha256(identity_blob)
    )

    if (
        observed_identity_sha256
        != FIXED_IDENTITIES_SHA256
    ):
        raise Invalid(
            "FIXED_IDENTITY_LIST",
            {
                "observed": (
                    observed_identity_sha256
                ),
                "expected": (
                    FIXED_IDENTITIES_SHA256
                ),
            },
        )

    observed_family_aggregate = {
        family: _family_aggregate(
            family_bytes[family]
        )
        for family in ("F", "B", "X")
    }

    expected_family_aggregate = {
        "F": F_AGGREGATE_SHA256,
        "B": B_AGGREGATE_SHA256,
        "X": X_AGGREGATE_SHA256,
    }

    if (
        observed_family_aggregate
        != expected_family_aggregate
    ):
        raise Invalid(
            "FIXED_FAMILY_AGGREGATE",
            {
                "observed": (
                    observed_family_aggregate
                ),
                "expected": (
                    expected_family_aggregate
                ),
            },
        )

    if family_command_count != {
        "F": 79,
        "B": 24,
        "X": 0,
    }:
        raise Invalid(
            "FIXED_COMMAND_DENOMINATOR",
            {
                "observed": (
                    family_command_count
                ),
                "expected": {
                    "F": 79,
                    "B": 24,
                    "X": 0,
                },
            },
        )

    return {
        "records": manifest_records,
        "family_aggregate": (
            observed_family_aggregate
        ),
        "family_command_count": (
            family_command_count
        ),
        "paths_sha256": (
            observed_paths_sha256
        ),
        "identities_sha256": (
            observed_identity_sha256
        ),
    }


def _verify_present_generated(
    repo_root: pathlib.Path,
    actual_lobq1: set[str],
) -> dict[str, object]:
    records: list[dict[str, object]] = []

    family_bytes: dict[
        str,
        list[tuple[str, bytes]],
    ] = {
        "G1": [],
        "G2": [],
        "G3": [],
        "G4": [],
    }

    family_command_count = {
        "G1": 0,
        "G2": 0,
        "G3": 0,
        "G4": 0,
    }

    bindings = _binding_records()

    missing: list[str] = []

    for binding in bindings:
        relative = str(
            binding["path"]
        )

        if relative not in actual_lobq1:
            missing.append(relative)
            continue

        family = str(
            binding["family"]
        )

        stream_id = str(
            binding["stream_id"]
        )

        expected_command_count = int(
            binding["command_count"]
        )

        data = _read_regular_file(
            _repo_path(
                repo_root,
                relative,
            ),
            relative,
        )

        observed_command_count = (
            _validate_transport(
                data,
                stream_id=stream_id,
            )
        )

        if (
            observed_command_count
            != expected_command_count
        ):
            raise Invalid(
                "GENERATED_COMMAND_COUNT",
                {
                    "stream_id": (
                        stream_id
                    ),
                    "observed": (
                        observed_command_count
                    ),
                    "expected": (
                        expected_command_count
                    ),
                },
            )

        sha256 = _sha256(data)

        family_command_count[
            family
        ] += observed_command_count

        family_bytes[
            family
        ].append(
            (
                stream_id,
                data,
            )
        )

        records.append(
            {
                "family": family,
                "stream_id": stream_id,
                "stream_index": int(
                    binding[
                        "stream_index"
                    ]
                ),
                "seed": str(
                    binding["seed"]
                ),
                "command_count": (
                    observed_command_count
                ),
                "path": relative,
                "byte_length": len(data),
                "sha256": sha256,
            }
        )

    aggregates: dict[str, str] = {}

    if not missing:
        for family in (
            "G1",
            "G2",
            "G3",
            "G4",
        ):
            aggregates[family] = (
                _family_aggregate(
                    family_bytes[family]
                )
            )

        if family_command_count != {
            "G1": 8192,
            "G2": 8192,
            "G3": 16384,
            "G4": 1024,
        }:
            raise Invalid(
                "GENERATED_COMMAND_DENOMINATOR",
                {
                    "observed": (
                        family_command_count
                    ),
                    "expected": {
                        "G1": 8192,
                        "G2": 8192,
                        "G3": 16384,
                        "G4": 1024,
                    },
                },
            )

    return {
        "records": records,
        "missing": missing,
        "family_aggregate": aggregates,
        "family_command_count": (
            family_command_count
        ),
    }


def _git(
    repo_root: pathlib.Path,
    *args: str,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            *args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _generator_identity(
    repo_root: pathlib.Path,
) -> tuple[str, dict[str, str] | None]:
    source = _repo_path(
        repo_root,
        GENERATOR_SOURCE_PATH,
    )

    if source.is_symlink():
        raise Invalid(
            "GENERATOR_SOURCE_SYMLINK"
        )

    if not source.exists():
        return (
            "MISSING",
            None,
        )

    if not source.is_file():
        raise Invalid(
            "GENERATOR_SOURCE_NOT_REGULAR"
        )

    blob = _git(
        repo_root,
        "rev-parse",
        "HEAD:" + GENERATOR_SOURCE_PATH,
    )

    if blob.returncode != 0:
        return (
            "UNTRACKED_AT_HEAD",
            None,
        )

    git_blob_oid = (
        blob.stdout
        .decode("ascii")
        .strip()
    )

    show = _git(
        repo_root,
        "show",
        "HEAD:" + GENERATOR_SOURCE_PATH,
    )

    if show.returncode != 0:
        raise Invalid(
            "GENERATOR_HEAD_READ_FAILED"
        )

    working_bytes = source.read_bytes()

    if working_bytes != show.stdout:
        raise Invalid(
            "GENERATOR_WORKTREE_DIFFERS_FROM_HEAD"
        )

    object_format = _git(
        repo_root,
        "rev-parse",
        "--show-object-format",
    )

    if object_format.returncode != 0:
        raise Invalid(
            "GIT_OBJECT_FORMAT_READ_FAILED"
        )

    git_object_format = (
        object_format.stdout
        .decode("ascii")
        .strip()
    )

    return (
        "READY",
        {
            "path": (
                GENERATOR_SOURCE_PATH
            ),
            "git_object_format": (
                git_object_format
            ),
            "git_blob_oid": (
                git_blob_oid
            ),
            "sha256": (
                _sha256(
                    working_bytes
                )
            ),
        },
    )


def _prepare_payload(
    repo_root: pathlib.Path,
) -> dict[str, object]:
    _validate_internal_constants()

    actual_lobq1 = (
        _audit_corpus_tree(
            repo_root
        )
    )

    expected_streams = (
        _expected_streams()
    )

    expected_paths = {
        str(record["path"])
        for record in expected_streams
    }

    extra = sorted(
        actual_lobq1
        - expected_paths
    )

    if extra:
        raise Invalid(
            "EXTRA_LOBQ1_FILES",
            {
                "extra_stream_count": (
                    len(extra)
                ),
                "extra_streams": extra,
            },
        )

    fixed = _verify_fixed_corpus(
        repo_root,
        actual_lobq1,
    )

    generated = (
        _verify_present_generated(
            repo_root,
            actual_lobq1,
        )
    )

    generator_status, generator_identity = (
        _generator_identity(
            repo_root
        )
    )

    missing_generated = list(
        generated["missing"]
    )

    missing_all = sorted(
        expected_paths
        - actual_lobq1
    )

    if (
        missing_all
        or generator_status != "READY"
    ):
        raise Incomplete(
            "CORPUS_INCOMPLETE",
            {
                "required_stream_count": 176,
                "present_stream_count": (
                    len(
                        actual_lobq1
                        & expected_paths
                    )
                ),
                "missing_stream_count": (
                    len(missing_all)
                ),
                "missing_generated_stream_count": (
                    len(
                        missing_generated
                    )
                ),
                "generator_source_status": (
                    generator_status
                ),
                "manifest_exists": (
                    _repo_path(
                        repo_root,
                        FINAL_MANIFEST_PATH,
                    ).exists()
                ),
            },
        )

    if generator_identity is None:
        raise Invalid(
            "GENERATOR_IDENTITY_INTERNAL"
        )

    fixed_records = list(
        fixed["records"]
    )

    generated_records = list(
        generated["records"]
    )

    fixed_by_family = {
        family: [
            record
            for record in fixed_records
            if record["family"] == family
        ]
        for family in ("F", "B", "X")
    }

    generated_by_family = {
        family: [
            record
            for record in generated_records
            if record["family"] == family
        ]
        for family in (
            "G1",
            "G2",
            "G3",
            "G4",
        )
    }

    streams: list[
        dict[str, object]
    ] = []

    streams.extend(
        fixed_by_family["F"]
    )
    streams.extend(
        fixed_by_family["B"]
    )
    streams.extend(
        generated_by_family["G1"]
    )
    streams.extend(
        generated_by_family["G2"]
    )
    streams.extend(
        generated_by_family["G3"]
    )
    streams.extend(
        generated_by_family["G4"]
    )
    streams.extend(
        fixed_by_family["X"]
    )

    if len(streams) != 176:
        raise Invalid(
            "FINAL_STREAM_COUNT_INTERNAL",
            {
                "observed": len(streams),
                "expected": 176,
            },
        )

    observed_ids = [
        str(record["stream_id"])
        for record in streams
    ]

    expected_ids = [
        str(record["stream_id"])
        for record in expected_streams
    ]

    if observed_ids != expected_ids:
        raise Invalid(
            "FINAL_STREAM_ORDER"
        )

    family_aggregate = dict(
        fixed["family_aggregate"]
    )

    family_aggregate.update(
        generated[
            "family_aggregate"
        ]
    )

    if set(
        family_aggregate.keys()
    ) != set(FAMILY_ORDER):
        raise Invalid(
            "FINAL_FAMILY_AGGREGATE_SET"
        )

    stream_byte_lengths = {
        str(record["stream_id"]):
            int(record["byte_length"])
        for record in streams
    }

    per_stream_sha256 = {
        str(record["stream_id"]):
            str(record["sha256"])
        for record in streams
    }

    payload = {
        "schema": (
            "lob.m5e0."
            "corpus_manifest.payload"
        ),
        "version": "1",
        "lobq1_version": (
            LOBQ1_VERSION
        ),
        "generator_version": (
            GENERATOR_VERSION
        ),
        "generator_source_identity": (
            generator_identity
        ),
        "prng_algorithm": (
            PRNG_ALGORITHM
        ),
        "exact_seeds": (
            list(SEEDS)
        ),
        "family_identifiers": (
            list(FAMILY_ORDER)
        ),
        "stream_counts": (
            dict(STREAM_COUNTS)
        ),
        "command_counts": (
            dict(COMMAND_COUNTS)
        ),
        "stream_ids": (
            observed_ids
        ),
        "stream_byte_lengths": (
            stream_byte_lengths
        ),
        "per_stream_sha256": (
            per_stream_sha256
        ),
        "fixed_corpus_identities": {
            "m5e1_materialization_spec_sha256": (
                M5E1_SPEC_SHA256
            ),
            "materialized_path_set_sha256": (
                FIXED_PATHS_SHA256
            ),
            "materialized_identity_list_sha256": (
                FIXED_IDENTITIES_SHA256
            ),
            "family_aggregate_algorithm": (
                "SHA256(stream_id_ASCII || NUL || "
                "exact_bytes || NUL) in family "
                "stream-ID order"
            ),
            "F_aggregate_sha256": (
                F_AGGREGATE_SHA256
            ),
            "B_aggregate_sha256": (
                B_AGGREGATE_SHA256
            ),
        },
        "malformed_case_identities": {
            "family": "X",
            "case_count": 24,
            "semantic_command_positions": 0,
            "family_aggregate_algorithm": (
                "SHA256(stream_id_ASCII || NUL || "
                "exact_bytes || NUL) in family "
                "stream-ID order"
            ),
            "X_aggregate_sha256": (
                X_AGGREGATE_SHA256
            ),
        },
        "family_aggregate_sha256": (
            family_aggregate
        ),
        "streams": streams,
    }

    return payload


def _wrapper_for_payload(
    payload: dict[str, object],
) -> dict[str, object]:
    payload_bytes = (
        _canonical_json_bytes(
            payload,
            final_lf=False,
        )
    )

    return {
        "aggregate_manifest_sha256": (
            _sha256(payload_bytes)
        ),
        "payload": payload,
    }


def _wrapper_bytes(
    payload: dict[str, object],
) -> bytes:
    return _canonical_json_bytes(
        _wrapper_for_payload(
            payload
        ),
        final_lf=True,
    )


def _manifest_path(
    repo_root: pathlib.Path,
) -> pathlib.Path:
    return _repo_path(
        repo_root,
        FINAL_MANIFEST_PATH,
    )


def check_ready(
    repo_root: pathlib.Path,
) -> dict[str, object]:
    payload = _prepare_payload(
        repo_root
    )

    wrapper = _wrapper_for_payload(
        payload
    )

    return {
        "status": "READY",
        "required_stream_count": 176,
        "present_stream_count": 176,
        "missing_stream_count": 0,
        "missing_generated_stream_count": 0,
        "generator_source_status": (
            "READY"
        ),
        "manifest_exists": (
            _manifest_path(
                repo_root
            ).exists()
        ),
        "aggregate_manifest_sha256": (
            wrapper[
                "aggregate_manifest_sha256"
            ]
        ),
    }


def seal_repo(
    repo_root: pathlib.Path,
) -> dict[str, object]:
    manifest = _manifest_path(
        repo_root
    )

    if manifest.is_symlink():
        raise Invalid(
            "MANIFEST_SYMLINK_FORBIDDEN"
        )

    if manifest.exists():
        raise Invalid(
            "MANIFEST_ALREADY_EXISTS"
        )

    payload = _prepare_payload(
        repo_root
    )

    data = _wrapper_bytes(
        payload
    )

    fd = os.open(
        manifest,
        (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
        ),
        0o644,
    )

    try:
        offset = 0

        while offset < len(data):
            written = os.write(
                fd,
                data[offset:],
            )

            if written <= 0:
                raise OSError(
                    "short manifest write"
                )

            offset += written

        os.fsync(fd)

    finally:
        os.close(fd)

    verification = verify_repo(
        repo_root
    )

    return {
        "status": "SEALED",
        "manifest_path": (
            FINAL_MANIFEST_PATH
        ),
        "manifest_bytes": len(data),
        "aggregate_manifest_sha256": (
            verification[
                "aggregate_manifest_sha256"
            ]
        ),
    }


def verify_repo(
    repo_root: pathlib.Path,
) -> dict[str, object]:
    manifest = _manifest_path(
        repo_root
    )

    if manifest.is_symlink():
        raise Invalid(
            "MANIFEST_SYMLINK_FORBIDDEN"
        )

    if not manifest.exists():
        raise Incomplete(
            "MANIFEST_MISSING",
            {
                "manifest_path": (
                    FINAL_MANIFEST_PATH
                ),
            },
        )

    if not manifest.is_file():
        raise Invalid(
            "MANIFEST_NOT_REGULAR"
        )

    payload = _prepare_payload(
        repo_root
    )

    expected = _wrapper_bytes(
        payload
    )

    actual = manifest.read_bytes()

    if actual != expected:
        raise Invalid(
            "MANIFEST_BYTE_MISMATCH",
            {
                "observed_sha256": (
                    _sha256(actual)
                ),
                "expected_sha256": (
                    _sha256(expected)
                ),
            },
        )

    wrapper = _wrapper_for_payload(
        payload
    )

    return {
        "status": "VERIFIED",
        "manifest_path": (
            FINAL_MANIFEST_PATH
        ),
        "manifest_bytes": (
            len(actual)
        ),
        "manifest_file_sha256": (
            _sha256(actual)
        ),
        "aggregate_manifest_sha256": (
            wrapper[
                "aggregate_manifest_sha256"
            ]
        ),
    }


def _emit(
    value: dict[str, object],
) -> None:
    sys.stdout.buffer.write(
        _canonical_json_bytes(
            value,
            final_lf=True,
        )
    )


def _parse_args(
    argv: list[str] | None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "mode",
        choices=(
            "check-ready",
            "seal",
            "verify",
        ),
    )

    parser.add_argument(
        "--repo-root",
        default=None,
    )

    return parser.parse_args(
        argv
    )


def main(
    argv: list[str] | None = None,
) -> int:
    args = _parse_args(
        argv
    )

    if args.repo_root is None:
        repo_root = (
            pathlib.Path(__file__)
            .resolve()
            .parents[2]
        )
    else:
        repo_root = pathlib.Path(
            args.repo_root
        ).resolve()

    try:
        if args.mode == "check-ready":
            result = check_ready(
                repo_root
            )

        elif args.mode == "seal":
            result = seal_repo(
                repo_root
            )

        else:
            result = verify_repo(
                repo_root
            )

        _emit(
            {
                "mode": args.mode,
                **result,
            }
        )

        return 0

    except Incomplete as exc:
        _emit(
            {
                "mode": args.mode,
                "status": "INCOMPLETE",
                "code": exc.code,
                **exc.details,
            }
        )

        return 3

    except Invalid as exc:
        _emit(
            {
                "mode": args.mode,
                "status": "INVALID",
                "code": exc.code,
                **exc.details,
            }
        )

        return 4


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
