#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
PACKAGE_VERSION="0.3.2"

PACKAGE_DIR="$PROJECT_ROOT/src/rnatr_scout"
UNIT_DIR="$PROJECT_ROOT/tests/unit"

ORIENTATION_AUDIT="$PROJECT_ROOT/results/11_p3_orientation_audit/$RUN_ID/p3_orientation_normalization_audit.tsv"

OUTDIR="$PROJECT_ROOT/results/11_production_p3_geometry/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_p3_geometry/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_production_p3_geometry/$RUN_ID"

QC="$QCDIR/p3_geometry_core.qc.tsv"
REPLAY="$OUTDIR/p3_orientation_transform_replay.tsv"
UNIT_LOG="$OUTDIR/unit_tests.log"
MANIFEST="$OUTDIR/${RUN_ID}.production_p3_geometry.manifest.tsv"

STAGE="$WORKDIR/stage"
STAGE_PACKAGE="$STAGE/rnatr_scout"
STAGE_TESTS="$STAGE/tests"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PACKAGE_DIR" \
  "$UNIT_DIR" \
  "$ORIENTATION_AUDIT"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

installed_version="$(rnatr-scout version)"

if [[ "$installed_version" != "$PACKAGE_VERSION" ]]; then
    echo "ERROR: unexpected installed version: $installed_version" >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$PACKAGE_DIR" "$STAGE_PACKAGE"
cp -a "$UNIT_DIR" "$STAGE_TESTS"

cat > "$STAGE_PACKAGE/sequence.py" <<'PY'
"""Small sequence utilities used by RNA-TR-Scout."""

from __future__ import annotations

_COMPLEMENT = str.maketrans(
    "ACGTNacgtn",
    "TGCANtgcan",
)


def reverse_complement(sequence: str) -> str:
    """Return the reverse complement of an A/C/G/T/N sequence."""

    invalid = {
        base
        for base in sequence
        if base not in "ACGTNacgtn"
    }

    if invalid:
        raise ValueError(
            "sequence contains unsupported bases: "
            + ",".join(sorted(invalid))
        )

    return sequence.translate(_COMPLEMENT)[::-1]
PY

cat > "$STAGE_PACKAGE/cigar.py" <<'PY'
"""CIGAR parsing and reference-to-query boundary projection."""

from __future__ import annotations

from dataclasses import dataclass
import re

_CIGAR_PATTERN = re.compile(r"([0-9]+)([MIDNSHP=X])")


@dataclass(frozen=True)
class BoundaryProjection:
    """Projected query coordinate for a reference boundary."""

    query_offset: int | None
    status: str


def parse_cigar(cigar: str) -> tuple[tuple[str, int], ...]:
    """Parse a SAM CIGAR into ``(operation, length)`` tuples."""

    if not cigar or cigar == "*":
        raise ValueError("CIGAR must be present")

    operations = tuple(
        (operation, int(length))
        for length, operation in _CIGAR_PATTERN.findall(cigar)
    )

    reconstructed = "".join(
        f"{length}{operation}"
        for operation, length in operations
    )

    if reconstructed != cigar:
        raise ValueError(
            f"invalid or incompletely parsed CIGAR: {cigar!r}"
        )

    if any(length <= 0 for _, length in operations):
        raise ValueError("CIGAR operation lengths must be positive")

    return operations


def project_reference_boundary_to_query(
    *,
    query_start: int,
    reference_start: int,
    cigar: str,
    reference_boundary: int,
) -> BoundaryProjection:
    """Project a 0-based reference boundary through a CIGAR.

    Coordinates are offsets within the query and candidate reference
    sequences used for the local alignment. Insertions advance only
    the query; deletions and ``N`` operations advance only the
    reference. A boundary inside a deletion or skipped region maps to
    the current query cursor and retains an explicit status.
    """

    if min(query_start, reference_start, reference_boundary) < 0:
        raise ValueError("coordinates must be non-negative")

    if reference_boundary < reference_start:
        return BoundaryProjection(
            None,
            "BOUNDARY_BEFORE_ALIGNMENT",
        )

    query_cursor = query_start
    reference_cursor = reference_start

    for operation, length in parse_cigar(cigar):
        if reference_boundary == reference_cursor:
            return BoundaryProjection(
                query_cursor,
                "PROJECTED_AT_OPERATION_BOUNDARY",
            )

        if operation in {"M", "=", "X"}:
            next_reference = reference_cursor + length
            next_query = query_cursor + length

            if (
                reference_cursor
                < reference_boundary
                <= next_reference
            ):
                delta = reference_boundary - reference_cursor
                return BoundaryProjection(
                    query_cursor + delta,
                    "PROJECTED_WITHIN_MATCHLIKE",
                )

            reference_cursor = next_reference
            query_cursor = next_query
            continue

        if operation == "I":
            query_cursor += length
            continue

        if operation in {"D", "N"}:
            next_reference = reference_cursor + length

            if (
                reference_cursor
                < reference_boundary
                <= next_reference
            ):
                status = (
                    "PROJECTED_WITHIN_DELETION"
                    if operation == "D"
                    else "PROJECTED_WITHIN_REFERENCE_SKIP"
                )
                return BoundaryProjection(
                    query_cursor,
                    status,
                )

            reference_cursor = next_reference
            continue

        if operation == "S":
            query_cursor += length
            continue

        if operation in {"H", "P"}:
            continue

        raise ValueError(
            f"unsupported CIGAR operation: {operation}"
        )

    if reference_boundary == reference_cursor:
        return BoundaryProjection(
            query_cursor,
            "PROJECTED_AT_ALIGNMENT_END",
        )

    return BoundaryProjection(
        None,
        "BOUNDARY_AFTER_ALIGNMENT",
    )
PY

cat > "$STAGE_PACKAGE/p3_geometry.py" <<'PY'
"""Pure P3 orientation and block-to-target geometry rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .sequence import reverse_complement

AlignmentStrand = Literal["+", "-"]
TargetSide = Literal["GENOMIC_LEFT", "GENOMIC_RIGHT"]
OrientationTransform = Literal[
    "AS_RAW",
    "REVERSE_COMPLEMENT",
]


@dataclass(frozen=True)
class CandidateReferenceGeometry:
    """Reference interval spanning block edge to target entry."""

    fetch_start: int
    fetch_end: int
    reverse_complement_after_fetch: bool
    bridge_bp: int
    target_entry_bp: int
    required_target_entry_bp: int

    @property
    def reference_bp(self) -> int:
        return self.fetch_end - self.fetch_start


def expected_orientation_transform(
    alignment_strand: AlignmentStrand,
    target_side: TargetSide,
) -> OrientationTransform:
    """Return how a raw target-facing clip must be oriented.

    The resulting sequence always runs from the mapped-block boundary
    toward the candidate repeat target.
    """

    if alignment_strand not in {"+", "-"}:
        raise ValueError("alignment_strand must be '+' or '-'")

    if target_side not in {
        "GENOMIC_LEFT",
        "GENOMIC_RIGHT",
    }:
        raise ValueError(
            "target_side must be GENOMIC_LEFT or GENOMIC_RIGHT"
        )

    if (
        alignment_strand == "+"
        and target_side == "GENOMIC_RIGHT"
    ) or (
        alignment_strand == "-"
        and target_side == "GENOMIC_LEFT"
    ):
        return "AS_RAW"

    return "REVERSE_COMPLEMENT"


def orient_target_facing_clip(
    sequence: str,
    alignment_strand: AlignmentStrand,
    target_side: TargetSide,
) -> tuple[str, OrientationTransform]:
    """Orient raw clip from mapped-block boundary toward target."""

    transform = expected_orientation_transform(
        alignment_strand,
        target_side,
    )

    if transform == "AS_RAW":
        return sequence.upper(), transform

    return reverse_complement(sequence).upper(), transform


def candidate_reference_geometry(
    *,
    block_start: int,
    block_end: int,
    target_start: int,
    target_end: int,
    target_side: TargetSide,
    target_entry_bp: int = 60,
    minimum_target_entry_bp: int = 12,
) -> CandidateReferenceGeometry:
    """Build coordinates for ``bridge + target-entry`` reference.

    All genomic coordinates are 0-based, end-exclusive.
    """

    values = (
        block_start,
        block_end,
        target_start,
        target_end,
        target_entry_bp,
        minimum_target_entry_bp,
    )

    if any(value < 0 for value in values):
        raise ValueError("coordinates and lengths must be non-negative")

    if block_end < block_start:
        raise ValueError("block_end must be >= block_start")

    if target_end <= target_start:
        raise ValueError("target_end must be > target_start")

    if target_entry_bp <= 0:
        raise ValueError("target_entry_bp must be positive")

    if minimum_target_entry_bp <= 0:
        raise ValueError(
            "minimum_target_entry_bp must be positive"
        )

    target_length = target_end - target_start
    entry_bp = min(target_length, target_entry_bp)
    required_entry = min(
        target_length,
        minimum_target_entry_bp,
    )

    if target_side == "GENOMIC_RIGHT":
        bridge_bp = target_start - block_end

        if bridge_bp < 0:
            raise ValueError(
                "right-side target overlaps or lies behind block edge"
            )

        return CandidateReferenceGeometry(
            fetch_start=block_end,
            fetch_end=target_start + entry_bp,
            reverse_complement_after_fetch=False,
            bridge_bp=bridge_bp,
            target_entry_bp=entry_bp,
            required_target_entry_bp=required_entry,
        )

    if target_side == "GENOMIC_LEFT":
        bridge_bp = block_start - target_end

        if bridge_bp < 0:
            raise ValueError(
                "left-side target overlaps or lies behind block edge"
            )

        return CandidateReferenceGeometry(
            fetch_start=target_end - entry_bp,
            fetch_end=block_start,
            reverse_complement_after_fetch=True,
            bridge_bp=bridge_bp,
            target_entry_bp=entry_bp,
            required_target_entry_bp=required_entry,
        )

    raise ValueError(
        "target_side must be GENOMIC_LEFT or GENOMIC_RIGHT"
    )


def orient_candidate_reference(
    fetched_sequence: str,
    geometry: CandidateReferenceGeometry,
) -> str:
    """Orient fetched genomic sequence from block edge toward target."""

    if len(fetched_sequence) != geometry.reference_bp:
        raise ValueError(
            "fetched sequence length does not match geometry"
        )

    if geometry.reverse_complement_after_fetch:
        return reverse_complement(fetched_sequence).upper()

    return fetched_sequence.upper()
PY

cat > "$STAGE_TESTS/test_sequence.py" <<'PY'
from __future__ import annotations

import unittest

from rnatr_scout.sequence import reverse_complement


class TestSequence(unittest.TestCase):
    def test_reverse_complement(self):
        self.assertEqual(
            reverse_complement("ACGTN"),
            "NACGT",
        )

    def test_invalid_base(self):
        with self.assertRaises(ValueError):
            reverse_complement("ACGU")


if __name__ == "__main__":
    unittest.main()
PY

cat > "$STAGE_TESTS/test_cigar.py" <<'PY'
from __future__ import annotations

import unittest

from rnatr_scout.cigar import (
    parse_cigar,
    project_reference_boundary_to_query,
)


class TestCigar(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(
            parse_cigar("5S10M2I5M3D4M"),
            (
                ("S", 5),
                ("M", 10),
                ("I", 2),
                ("M", 5),
                ("D", 3),
                ("M", 4),
            ),
        )

    def test_project_match(self):
        result = project_reference_boundary_to_query(
            query_start=0,
            reference_start=0,
            cigar="10M",
            reference_boundary=7,
        )
        self.assertEqual(result.query_offset, 7)
        self.assertEqual(
            result.status,
            "PROJECTED_WITHIN_MATCHLIKE",
        )

    def test_insertion_advances_query(self):
        result = project_reference_boundary_to_query(
            query_start=0,
            reference_start=0,
            cigar="5M3I5M",
            reference_boundary=8,
        )
        self.assertEqual(result.query_offset, 11)

    def test_deletion_projection(self):
        result = project_reference_boundary_to_query(
            query_start=0,
            reference_start=0,
            cigar="5M3D5M",
            reference_boundary=7,
        )
        self.assertEqual(result.query_offset, 5)
        self.assertEqual(
            result.status,
            "PROJECTED_WITHIN_DELETION",
        )

    def test_after_alignment(self):
        result = project_reference_boundary_to_query(
            query_start=0,
            reference_start=0,
            cigar="5M",
            reference_boundary=6,
        )
        self.assertIsNone(result.query_offset)
        self.assertEqual(
            result.status,
            "BOUNDARY_AFTER_ALIGNMENT",
        )


if __name__ == "__main__":
    unittest.main()
PY

cat > "$STAGE_TESTS/test_p3_geometry.py" <<'PY'
from __future__ import annotations

import unittest

from rnatr_scout.p3_geometry import (
    candidate_reference_geometry,
    expected_orientation_transform,
    orient_candidate_reference,
    orient_target_facing_clip,
)


class TestP3Geometry(unittest.TestCase):
    def test_all_orientation_combinations(self):
        expected = {
            ("+", "GENOMIC_RIGHT"): "AS_RAW",
            ("+", "GENOMIC_LEFT"): "REVERSE_COMPLEMENT",
            ("-", "GENOMIC_RIGHT"): "REVERSE_COMPLEMENT",
            ("-", "GENOMIC_LEFT"): "AS_RAW",
        }

        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(
                    expected_orientation_transform(*key),
                    value,
                )

    def test_orient_clip(self):
        sequence, transform = orient_target_facing_clip(
            "AACG",
            "+",
            "GENOMIC_LEFT",
        )
        self.assertEqual(sequence, "CGTT")
        self.assertEqual(
            transform,
            "REVERSE_COMPLEMENT",
        )

    def test_right_geometry(self):
        geometry = candidate_reference_geometry(
            block_start=100,
            block_end=150,
            target_start=157,
            target_end=200,
            target_side="GENOMIC_RIGHT",
        )
        self.assertEqual(geometry.fetch_start, 150)
        self.assertEqual(geometry.fetch_end, 200)
        self.assertEqual(geometry.bridge_bp, 7)
        self.assertFalse(
            geometry.reverse_complement_after_fetch
        )

    def test_left_geometry(self):
        geometry = candidate_reference_geometry(
            block_start=100,
            block_end=150,
            target_start=40,
            target_end=90,
            target_side="GENOMIC_LEFT",
            target_entry_bp=20,
        )
        self.assertEqual(geometry.fetch_start, 70)
        self.assertEqual(geometry.fetch_end, 100)
        self.assertEqual(geometry.bridge_bp, 10)
        self.assertTrue(
            geometry.reverse_complement_after_fetch
        )
        self.assertEqual(
            orient_candidate_reference(
                "A" * 30,
                geometry,
            ),
            "T" * 30,
        )

    def test_overlapping_target_rejected(self):
        with self.assertRaises(ValueError):
            candidate_reference_geometry(
                block_start=100,
                block_end=150,
                target_start=145,
                target_end=170,
                target_side="GENOMIC_RIGHT",
            )


if __name__ == "__main__":
    unittest.main()
PY

cat > "$STAGE_PACKAGE/cli.py" <<'PY'
"""Command-line interface for RNA-TR-Scout."""

from __future__ import annotations

import argparse
import json

from . import __version__
from .batch import classify_p3_tsv
from .cigar import project_reference_boundary_to_query
from .contract import check_contract
from .p3 import P3Observation, classify_p3
from .p3_geometry import (
    candidate_reference_geometry,
    expected_orientation_transform,
)


def _boolean(text: str) -> bool:
    normalized = text.strip().lower()

    if normalized in {"true", "yes", "1"}:
        return True

    if normalized in {"false", "no", "0"}:
        return False

    raise argparse.ArgumentTypeError(
        "expected true/false, yes/no, or 1/0"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rnatr-scout",
        description=(
            "Long-read RNA tandem-repeat evidence caller"
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser(
        "version",
        help="Print package version",
    )

    p3_parser = subparsers.add_parser(
        "p3-classify",
        help="Apply the frozen P3 decision layer",
    )
    p3_parser.add_argument(
        "--alignment-strand",
        required=True,
        choices=["+", "-"],
    )
    p3_parser.add_argument(
        "--target-entry-projected",
        required=True,
        type=_boolean,
    )
    p3_parser.add_argument(
        "--motif",
        required=True,
    )
    p3_parser.add_argument(
        "--target-side",
        required=True,
        choices=[
            "GENOMIC_LEFT",
            "GENOMIC_RIGHT",
        ],
    )
    p3_parser.add_argument(
        "--tract-bp",
        type=int,
        default=None,
    )
    p3_parser.add_argument(
        "--tract-reaches-raw-end",
        type=_boolean,
        default=False,
    )

    batch_parser = subparsers.add_parser(
        "p3-batch-classify",
        help=(
            "Apply P3 decision rules to every row of a TSV"
        ),
    )
    batch_parser.add_argument(
        "--input-tsv",
        required=True,
    )
    batch_parser.add_argument(
        "--output-tsv",
        required=True,
    )

    geometry_parser = subparsers.add_parser(
        "p3-geometry",
        help=(
            "Calculate target-facing orientation and local "
            "candidate-reference coordinates"
        ),
    )
    geometry_parser.add_argument(
        "--alignment-strand",
        required=True,
        choices=["+", "-"],
    )
    geometry_parser.add_argument(
        "--target-side",
        required=True,
        choices=[
            "GENOMIC_LEFT",
            "GENOMIC_RIGHT",
        ],
    )
    geometry_parser.add_argument(
        "--block-start",
        required=True,
        type=int,
    )
    geometry_parser.add_argument(
        "--block-end",
        required=True,
        type=int,
    )
    geometry_parser.add_argument(
        "--target-start",
        required=True,
        type=int,
    )
    geometry_parser.add_argument(
        "--target-end",
        required=True,
        type=int,
    )
    geometry_parser.add_argument(
        "--target-entry-bp",
        type=int,
        default=60,
    )
    geometry_parser.add_argument(
        "--minimum-target-entry-bp",
        type=int,
        default=12,
    )

    projection_parser = subparsers.add_parser(
        "project-reference-boundary",
        help=(
            "Project a candidate-reference boundary through "
            "a CIGAR onto query coordinates"
        ),
    )
    projection_parser.add_argument(
        "--query-start",
        required=True,
        type=int,
    )
    projection_parser.add_argument(
        "--reference-start",
        required=True,
        type=int,
    )
    projection_parser.add_argument(
        "--cigar",
        required=True,
    )
    projection_parser.add_argument(
        "--reference-boundary",
        required=True,
        type=int,
    )

    contract_parser = subparsers.add_parser(
        "contract-check",
        help="Check schema v0.3.2 and regression fixture",
    )
    contract_parser.add_argument(
        "--schema-dir",
        required=True,
    )
    contract_parser.add_argument(
        "--fixture-dir",
        required=True,
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    if arguments.command == "version":
        print(__version__)
        return 0

    if arguments.command == "p3-classify":
        observation = P3Observation(
            alignment_strand=arguments.alignment_strand,
            target_entry_projected=(
                arguments.target_entry_projected
            ),
            canonical_motif=arguments.motif,
            target_facing_genomic_side=(
                arguments.target_side
            ),
            tract_bp=arguments.tract_bp,
            tract_reaches_expected_raw_end=(
                arguments.tract_reaches_raw_end
            ),
        )
        decision = classify_p3(observation)
        print(
            json.dumps(
                decision.to_dict(),
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "p3-batch-classify":
        rows = classify_p3_tsv(
            arguments.input_tsv,
            arguments.output_tsv,
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "rows_written": rows,
                    "output_tsv": arguments.output_tsv,
                },
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "p3-geometry":
        transform = expected_orientation_transform(
            arguments.alignment_strand,
            arguments.target_side,
        )
        geometry = candidate_reference_geometry(
            block_start=arguments.block_start,
            block_end=arguments.block_end,
            target_start=arguments.target_start,
            target_end=arguments.target_end,
            target_side=arguments.target_side,
            target_entry_bp=arguments.target_entry_bp,
            minimum_target_entry_bp=(
                arguments.minimum_target_entry_bp
            ),
        )
        print(
            json.dumps(
                {
                    "orientation_transform": transform,
                    "fetch_start": geometry.fetch_start,
                    "fetch_end": geometry.fetch_end,
                    "reverse_complement_after_fetch": (
                        geometry.reverse_complement_after_fetch
                    ),
                    "bridge_bp": geometry.bridge_bp,
                    "target_entry_bp": geometry.target_entry_bp,
                    "required_target_entry_bp": (
                        geometry.required_target_entry_bp
                    ),
                    "reference_bp": geometry.reference_bp,
                },
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "project-reference-boundary":
        projection = project_reference_boundary_to_query(
            query_start=arguments.query_start,
            reference_start=arguments.reference_start,
            cigar=arguments.cigar,
            reference_boundary=(
                arguments.reference_boundary
            ),
        )
        print(
            json.dumps(
                {
                    "query_offset": projection.query_offset,
                    "status": projection.status,
                },
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "contract-check":
        result = check_contract(
            arguments.schema_dir,
            arguments.fixture_dir,
        )
        print(
            json.dumps(
                result,
                sort_keys=True,
            )
        )
        return 0 if result["status"] == "PASS" else 1

    parser.error(
        f"unsupported command: {arguments.command}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
PY

echo "===== STAGED PYTHON SYNTAX ====="
python -m compileall -q \
  "$STAGE_PACKAGE" \
  "$STAGE_TESTS"
echo "Python compileall: PASS"

echo
echo "===== STAGED UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
PYTHONPATH="$STAGE" \
python -m unittest discover \
  -s "$STAGE_TESTS" \
  -v \
  2>&1 | tee "$UNIT_LOG"

timestamp="$(date +%Y%m%d_%H%M%S)"
BACKUP="$PROJECT_ROOT/metadata/code_backups/11ap_${timestamp}"
mkdir -p "$BACKUP"

cp "$PACKAGE_DIR/cli.py" "$BACKUP/cli.py"
cp -a "$UNIT_DIR" "$BACKUP/unit_tests"

cp "$STAGE_PACKAGE/sequence.py" \
  "$PACKAGE_DIR/sequence.py"
cp "$STAGE_PACKAGE/cigar.py" \
  "$PACKAGE_DIR/cigar.py"
cp "$STAGE_PACKAGE/p3_geometry.py" \
  "$PACKAGE_DIR/p3_geometry.py"
cp "$STAGE_PACKAGE/cli.py" \
  "$PACKAGE_DIR/cli.py"

cp "$STAGE_TESTS/test_sequence.py" \
  "$UNIT_DIR/test_sequence.py"
cp "$STAGE_TESTS/test_cigar.py" \
  "$UNIT_DIR/test_cigar.py"
cp "$STAGE_TESTS/test_p3_geometry.py" \
  "$UNIT_DIR/test_p3_geometry.py"

echo
echo "===== INSTALLED PACKAGE UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$UNIT_DIR" \
  -v

echo
echo "===== REPLAY PILOT ORIENTATION TRANSFORMS ====="

python - \
  "$ORIENTATION_AUDIT" \
  "$REPLAY" \
  "$QC" <<'PYREPLAY'
from __future__ import annotations

import csv
import sys
from pathlib import Path

from rnatr_scout.p3_geometry import (
    expected_orientation_transform,
)

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
qc_path = Path(sys.argv[3])

with input_path.open(
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

results = []
mismatches = 0

for row in rows:
    produced = expected_orientation_transform(
        row["alignment_strand_from_inventory"],
        row["target_facing_genomic_side"],
    )
    expected = row[
        "stored_orientation_transform"
    ]
    matches = produced == expected

    if not matches:
        mismatches += 1

    results.append(
        {
            "projection_id": row["projection_id"],
            "read_id": row["read_id"],
            "alignment_strand": row[
                "alignment_strand_from_inventory"
            ],
            "target_facing_genomic_side": row[
                "target_facing_genomic_side"
            ],
            "expected_transform": expected,
            "production_transform": produced,
            "transform_matches": str(
                matches
            ).lower(),
        }
    )

with output_path.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=list(results[0].keys()),
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(results)

status = "PASS"

if len(results) != 23 or mismatches:
    status = "REVIEW"

with qc_path.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write("package_version\t0.3.2\n")
    handle.write(
        "orientation_rows_replayed\t{}\n".format(
            len(results)
        )
    )
    handle.write(
        "orientation_transform_mismatches\t{}\n".format(
            mismatches
        )
    )
    handle.write(
        "new_core_modules\t3\n"
    )
    handle.write(
        "new_unit_test_modules\t3\n"
    )
    handle.write(
        "geometry_core_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "P3 geometry production replay requires review"
    )
PYREPLAY

echo
echo "===== CLI SMOKE TESTS ====="
rnatr-scout p3-geometry \
  --alignment-strand + \
  --target-side GENOMIC_RIGHT \
  --block-start 100 \
  --block-end 150 \
  --target-start 157 \
  --target-end 200

rnatr-scout project-reference-boundary \
  --query-start 0 \
  --reference-start 0 \
  --cigar 5M3I5M \
  --reference-boundary 8

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PACKAGE_DIR/sequence.py" \
      "$PACKAGE_DIR/cigar.py" \
      "$PACKAGE_DIR/p3_geometry.py" \
      "$PACKAGE_DIR/cli.py" \
      "$UNIT_DIR/test_sequence.py" \
      "$UNIT_DIR/test_cigar.py" \
      "$UNIT_DIR/test_p3_geometry.py" \
      "$REPLAY" \
      "$QC" \
      "$UNIT_LOG"
    do
        if [[ "$path" == *.tsv ]]; then
            rows="$(awk 'END {print NR-1}' "$path")"
        else
            rows="."
        fi

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== ORIENTATION REPLAY ====="
column -ts $'\t' "$REPLAY"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== BACKUP ====="
echo "$BACKUP"
