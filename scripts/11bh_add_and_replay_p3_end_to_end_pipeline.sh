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

PAIR_META="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"
REFERENCE_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_candidate_references.fasta.gz"
RAW_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

PAIR_EXPECTED="$PROJECT_ROOT/results/11_production_p3_pair_projection_fix/$RUN_ID/p3_pair_alignment_projection_replay.corrected.tsv"
REPEAT_EXPECTED="$PROJECT_ROOT/results/11_production_p3_repeat/$RUN_ID/p3_repeat_measurement_replay.tsv"
DECISION_EXPECTED="$PROJECT_ROOT/results/11_production_p3_batch/$RUN_ID/p3_production_replay.tsv"
FROZEN_EXPECTED="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID/p3_orientation_corrected_classification.tsv"

OUTDIR="$PROJECT_ROOT/results/11_production_p3_end_to_end/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_p3_end_to_end/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_production_p3_end_to_end/$RUN_ID"

REPLAY="$OUTDIR/p3_end_to_end_replay.tsv"
COMPARISON="$OUTDIR/p3_end_to_end_field_comparison.tsv"
QC="$QCDIR/p3_end_to_end_pipeline.qc.tsv"
UNIT_LOG="$OUTDIR/unit_tests.log"
MANIFEST="$OUTDIR/${RUN_ID}.production_p3_end_to_end.manifest.tsv"

STAGE="$WORKDIR/stage"
STAGE_PACKAGE="$STAGE/rnatr_scout"
STAGE_TESTS="$STAGE/tests"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PACKAGE_DIR" \
  "$UNIT_DIR" \
  "$PAIR_META" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$RAW_FASTQ" \
  "$PAIR_EXPECTED" \
  "$REPEAT_EXPECTED" \
  "$DECISION_EXPECTED" \
  "$FROZEN_EXPECTED"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

for path in \
  "$PACKAGE_DIR/p3_pipeline.py" \
  "$UNIT_DIR/test_p3_pipeline.py"
do
    if [[ -e "$path" ]]; then
        echo "ERROR: target already exists: $path" >&2
        exit 1
    fi
done

command -v minimap2 >/dev/null 2>&1 || {
    echo "ERROR: minimap2 is unavailable" >&2
    exit 1
}

installed_version="$(rnatr-scout version)"

if [[ "$installed_version" != "$PACKAGE_VERSION" ]]; then
    echo "ERROR: unexpected package version: $installed_version" >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$PACKAGE_DIR" "$STAGE_PACKAGE"
cp -a "$UNIT_DIR" "$STAGE_TESTS"

cat > "$STAGE_PACKAGE/p3_pipeline.py" <<'PY'
"""End-to-end production orchestration for one P3 candidate pair."""

from __future__ import annotations

from dataclasses import dataclass

from .p3 import (
    P3Decision,
    P3Observation,
    classify_p3,
)
from .p3_geometry import (
    OrientationTransform,
    orient_target_facing_clip,
)
from .p3_pair import (
    PairAlignmentProjection,
    run_isolated_pair_alignment,
)
from .p3_repeat import (
    RepeatMeasurement,
    measure_target_entry_repeat,
)


@dataclass(frozen=True)
class P3PipelineResult:
    """Integrated alignment, measurement, and guarded decision."""

    orientation_transform: OrientationTransform
    query_prefix_matches: bool
    pair_projection: PairAlignmentProjection
    repeat_measurement: RepeatMeasurement
    decision: P3Decision

    def to_dict(self) -> dict[str, object]:
        return {
            "orientation_transform":
                self.orientation_transform,
            "query_prefix_matches":
                self.query_prefix_matches,
            "pair_projection":
                self.pair_projection.to_dict(),
            "repeat_measurement":
                self.repeat_measurement.to_contract_dict(),
            "decision":
                self.decision.to_dict(),
        }


def run_p3_pipeline(
    *,
    query_name: str,
    query_sequence: str,
    target_name: str,
    target_sequence: str,
    raw_read_sequence: str,
    raw_clip_start: int,
    raw_clip_end: int,
    raw_alignment_strand: str,
    target_facing_genomic_side: str,
    canonical_motif: str,
    bridge_bp: int,
    target_entry_bp: int,
    query_can_reach_target_entry: bool,
    expected_orientation_transform: str | None = None,
    minimap2_executable: str = "minimap2",
) -> P3PipelineResult:
    """Run the production P3 path for one candidate.

    The result remains a sequence-evidence interpretation. Exact allele
    length, expansion status, DNA genotype, and pathogenicity are not
    inferred from a one-flank P3 observation.
    """

    if raw_clip_start < 0:
        raise ValueError(
            "raw_clip_start must be non-negative"
        )

    if raw_clip_end < raw_clip_start:
        raise ValueError(
            "raw_clip_end must be at least raw_clip_start"
        )

    if raw_clip_end > len(raw_read_sequence):
        raise ValueError(
            "raw clip interval exceeds raw read length"
        )

    raw_clip = raw_read_sequence[
        raw_clip_start:raw_clip_end
    ]
    (
        oriented_clip,
        orientation_transform,
    ) = orient_target_facing_clip(
        raw_clip,
        raw_alignment_strand,
        target_facing_genomic_side,
    )

    if (
        expected_orientation_transform is not None
        and orientation_transform
        != expected_orientation_transform
    ):
        raise ValueError(
            "computed orientation transform does not match "
            "the expected frozen transform"
        )

    query_prefix_matches = (
        oriented_clip[
            :len(query_sequence)
        ]
        == query_sequence.upper()
    )

    pair_projection = run_isolated_pair_alignment(
        query_name=query_name,
        query_sequence=query_sequence,
        target_name=target_name,
        target_sequence=target_sequence,
        bridge_bp=bridge_bp,
        target_entry_bp=target_entry_bp,
        query_can_reach_target_entry=(
            query_can_reach_target_entry
        ),
        minimap2_executable=minimap2_executable,
    )

    repeat_measurement = measure_target_entry_repeat(
        oriented_clip=oriented_clip,
        motif=canonical_motif,
        target_entry_query_offset=(
            pair_projection.target_entry_query_offset
        ),
        raw_clip_start=raw_clip_start,
        raw_clip_end=raw_clip_end,
        orientation_transform=orientation_transform,
        target_facing_genomic_side=(
            target_facing_genomic_side
        ),
        target_entry_projection_status=(
            pair_projection.target_entry_projection_status
        ),
        query_prefix_matches=query_prefix_matches,
    )

    selected_alignment = (
        pair_projection.selected_alignment
    )
    decision_alignment_strand = (
        selected_alignment.strand
        if selected_alignment is not None
        else "+"
    )

    decision = classify_p3(
        P3Observation(
            alignment_strand=(
                decision_alignment_strand
            ),
            target_entry_projected=(
                pair_projection.target_entry_projection_status
                == "TARGET_ENTRY_PROJECTED"
            ),
            canonical_motif=canonical_motif,
            target_facing_genomic_side=(
                target_facing_genomic_side
            ),
            tract_bp=repeat_measurement.tract_bp,
            tract_reaches_expected_raw_end=(
                repeat_measurement
                .tract_reaches_expected_raw_end
            ),
        )
    )

    return P3PipelineResult(
        orientation_transform=orientation_transform,
        query_prefix_matches=query_prefix_matches,
        pair_projection=pair_projection,
        repeat_measurement=repeat_measurement,
        decision=decision,
    )
PY

cat > "$STAGE_TESTS/test_p3_pipeline.py" <<'PY'
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rnatr_scout.p3_pipeline import (
    run_p3_pipeline,
)


def pair_result(
    *,
    strand,
    projection_status,
    query_offset,
):
    selected = (
        None
        if strand is None
        else SimpleNamespace(strand=strand)
    )

    return SimpleNamespace(
        selected_alignment=selected,
        target_entry_query_offset=query_offset,
        target_entry_projection_status=(
            projection_status
        ),
        to_dict=lambda: {
            "selected_strand": strand,
            "target_entry_query_offset":
                query_offset,
            "target_entry_projection_status":
                projection_status,
        },
    )


class TestP3Pipeline(unittest.TestCase):
    @patch(
        "rnatr_scout.p3_pipeline."
        "run_isolated_pair_alignment"
    )
    def test_reverse_alignment_is_rejected(
        self,
        mocked_alignment,
    ):
        mocked_alignment.return_value = pair_result(
            strand="-",
            projection_status=(
                "UNEXPECTED_REVERSE_ALIGNMENT"
            ),
            query_offset=None,
        )
        raw_read = "A" * 30

        result = run_p3_pipeline(
            query_name="q",
            query_sequence="A" * 10,
            target_name="r",
            target_sequence="T" * 30,
            raw_read_sequence=raw_read,
            raw_clip_start=0,
            raw_clip_end=30,
            raw_alignment_strand="+",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            canonical_motif="A",
            bridge_bp=5,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
            expected_orientation_transform=(
                "AS_RAW"
            ),
        )

        self.assertEqual(
            result.decision.primary_status,
            "REJECT_ORIENTATION_INCONSISTENT_BRIDGE",
        )
        self.assertFalse(
            result.decision.standard_evidence_emitted
        )

    @patch(
        "rnatr_scout.p3_pipeline."
        "run_isolated_pair_alignment"
    )
    def test_projected_homopolymer_is_review_only(
        self,
        mocked_alignment,
    ):
        mocked_alignment.return_value = pair_result(
            strand="+",
            projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_offset=2,
        )
        raw_read = (
            "C"
            + ("A" * 13)
            + ("G" * 20)
        )

        result = run_p3_pipeline(
            query_name="q",
            query_sequence=raw_read[:10],
            target_name="r",
            target_sequence="A" * 30,
            raw_read_sequence=raw_read,
            raw_clip_start=0,
            raw_clip_end=len(raw_read),
            raw_alignment_strand="+",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            canonical_motif="A",
            bridge_bp=2,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
            expected_orientation_transform=(
                "AS_RAW"
            ),
        )

        self.assertEqual(
            result.repeat_measurement.sizing_status,
            "partial_internal",
        )
        self.assertEqual(
            result.decision.primary_status,
            "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE",
        )
        self.assertFalse(
            result.decision.standard_evidence_emitted
        )
        self.assertEqual(
            result.decision.expansion_status,
            "NOT_ASSESSED",
        )

    @patch(
        "rnatr_scout.p3_pipeline."
        "run_isolated_pair_alignment"
    )
    def test_no_alignment_is_target_entry_rejection(
        self,
        mocked_alignment,
    ):
        mocked_alignment.return_value = pair_result(
            strand=None,
            projection_status=(
                "TARGET_ENTRY_NOT_PROJECTED"
            ),
            query_offset=None,
        )
        raw_read = "CAG" * 10

        result = run_p3_pipeline(
            query_name="q",
            query_sequence=raw_read[:12],
            target_name="r",
            target_sequence=raw_read,
            raw_read_sequence=raw_read,
            raw_clip_start=0,
            raw_clip_end=len(raw_read),
            raw_alignment_strand="+",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            canonical_motif="CAG",
            bridge_bp=5,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )

        self.assertEqual(
            result.decision.primary_status,
            "REJECT_TARGET_ENTRY_NOT_PROJECTED",
        )

    @patch(
        "rnatr_scout.p3_pipeline."
        "run_isolated_pair_alignment"
    )
    def test_orientation_contract_mismatch_rejected(
        self,
        mocked_alignment,
    ):
        mocked_alignment.return_value = pair_result(
            strand="+",
            projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_offset=0,
        )

        with self.assertRaises(ValueError):
            run_p3_pipeline(
                query_name="q",
                query_sequence="AAAA",
                target_name="r",
                target_sequence="AAAA",
                raw_read_sequence="AAAA",
                raw_clip_start=0,
                raw_clip_end=4,
                raw_alignment_strand="+",
                target_facing_genomic_side=(
                    "GENOMIC_RIGHT"
                ),
                canonical_motif="A",
                bridge_bp=0,
                target_entry_bp=4,
                query_can_reach_target_entry=True,
                expected_orientation_transform=(
                    "REVERSE_COMPLEMENT"
                ),
            )


if __name__ == "__main__":
    unittest.main()
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
BACKUP="$PROJECT_ROOT/metadata/code_backups/11bh_${timestamp}"
mkdir -p "$BACKUP"

cp -a "$UNIT_DIR" "$BACKUP/unit_tests"

cp "$STAGE_PACKAGE/p3_pipeline.py" \
  "$PACKAGE_DIR/p3_pipeline.py"
cp "$STAGE_TESTS/test_p3_pipeline.py" \
  "$UNIT_DIR/test_p3_pipeline.py"

echo
echo "===== INSTALLED PACKAGE UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$UNIT_DIR" \
  -v

echo
echo "===== END-TO-END REPLAY OF 23 P3 CANDIDATES ====="

python - \
  "$PAIR_META" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$RAW_FASTQ" \
  "$PAIR_EXPECTED" \
  "$REPEAT_EXPECTED" \
  "$DECISION_EXPECTED" \
  "$FROZEN_EXPECTED" \
  "$REPLAY" \
  "$COMPARISON" \
  "$QC" \
  "$PACKAGE_VERSION" <<'PYREPLAY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter
from pathlib import Path

from rnatr_scout.fasta import load_fasta
from rnatr_scout.p3_pipeline import (
    run_p3_pipeline,
)

(
    pair_meta_text,
    query_fasta_text,
    reference_fasta_text,
    raw_fastq_text,
    pair_expected_text,
    repeat_expected_text,
    decision_expected_text,
    frozen_expected_text,
    replay_text,
    comparison_text,
    qc_text,
    package_version,
) = sys.argv[1:]

PAIR_META = Path(pair_meta_text)
QUERY_FASTA = Path(query_fasta_text)
REFERENCE_FASTA = Path(reference_fasta_text)
RAW_FASTQ = Path(raw_fastq_text)
PAIR_EXPECTED = Path(pair_expected_text)
REPEAT_EXPECTED = Path(repeat_expected_text)
DECISION_EXPECTED = Path(decision_expected_text)
FROZEN_EXPECTED = Path(frozen_expected_text)
REPLAY = Path(replay_text)
COMPARISON = Path(comparison_text)
QC = Path(qc_text)

REPEAT_FIELDS = [
    "tract_oriented_start",
    "tract_oriented_end",
    "tract_raw_start",
    "tract_raw_end",
    "tract_bp",
    "repeat_units_observed_read",
    "repeat_units_motif_path",
    "motif_path_to_read_units_ratio",
    "matches",
    "mismatches",
    "insertions",
    "deletions",
    "purity",
    "score",
    "selected_orientation",
    "entry_offset_selected_bp",
    "distance_from_tract_to_oriented_clip_end_bp",
    "tract_reaches_expected_raw_end",
    "evidence_class",
    "sizing_status",
]

DECISION_FIELDS = [
    "primary_status",
    "standard_evidence_emitted",
    "evidence_class",
    "sizing_status",
    "failure_code",
    "repeat_bp_estimate",
    "repeat_bp_lower_bound",
    "allele_length_status",
    "expansion_status",
]


def read_tsv(path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


def write_tsv(path, fields, rows):
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def load_selected_fastq(path, wanted_ids):
    records = {}

    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
    ) as handle:
        while True:
            header = handle.readline()

            if not header:
                break

            sequence = handle.readline()
            plus = handle.readline()
            quality = handle.readline()

            if not (
                sequence
                and plus
                and quality
            ):
                raise ValueError(
                    "truncated FASTQ record"
                )

            if not header.startswith("@"):
                raise ValueError(
                    "invalid FASTQ header"
                )

            read_id = header[1:].split()[0]

            if read_id in wanted_ids:
                records[read_id] = (
                    sequence.strip().upper()
                )

                if len(records) == len(
                    wanted_ids
                ):
                    break

    return records


with gzip.open(
    PAIR_META,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    metadata_rows = list(
        csv.DictReader(
            handle,
            delimiter="\t",
        )
    )

metadata_lookup = {
    row["projection_id"]: row
    for row in metadata_rows
}
query_sequences = load_fasta(
    QUERY_FASTA
)
reference_sequences = load_fasta(
    REFERENCE_FASTA
)

pair_expected_rows = read_tsv(
    PAIR_EXPECTED
)
repeat_expected_rows = read_tsv(
    REPEAT_EXPECTED
)
decision_expected_rows = read_tsv(
    DECISION_EXPECTED
)
frozen_expected_rows = read_tsv(
    FROZEN_EXPECTED
)

pair_lookup = {
    row["projection_id"]: row
    for row in pair_expected_rows
}
repeat_lookup = {
    row["projection_id"]: row
    for row in repeat_expected_rows
}
decision_lookup = {
    row["projection_id"]: row
    for row in decision_expected_rows
}
frozen_lookup = {
    row["projection_id"]: row
    for row in frozen_expected_rows
}

expected_ids = set(frozen_lookup)
wanted_read_ids = {
    metadata_lookup[projection_id]["read_id"]
    for projection_id in expected_ids
}
raw_reads = load_selected_fastq(
    RAW_FASTQ,
    wanted_read_ids,
)

missing_metadata = 0
missing_query = 0
missing_reference = 0
missing_raw_read = 0
orientation_transform_mismatches = 0
query_prefix_mismatches = 0
pair_projection_status_mismatches = 0
pair_query_offset_mismatches = 0
repeat_field_mismatches = 0
decision_field_mismatches = 0
frozen_status_mismatches = 0
frozen_emission_mismatches = 0
guardrail_failures = 0

comparison_rows = []
replay_rows = []
primary_status_counts = Counter()
failure_code_counts = Counter()
standard_evidence_emitted = 0


def compare(
    *,
    projection_id,
    layer,
    field,
    expected,
    produced,
):
    matches = str(expected) == str(produced)
    comparison_rows.append(
        {
            "projection_id": projection_id,
            "layer": layer,
            "field": field,
            "expected": str(expected),
            "produced": str(produced),
            "matches": str(matches).lower(),
        }
    )
    return matches


for projection_id in sorted(expected_ids):
    metadata = metadata_lookup.get(
        projection_id
    )
    query_sequence = query_sequences.get(
        projection_id
    )

    if metadata is None:
        missing_metadata += 1
        continue

    reference_id = metadata["reference_id"]
    reference_sequence = (
        reference_sequences.get(reference_id)
    )
    raw_read = raw_reads.get(
        metadata["read_id"]
    )

    if query_sequence is None:
        missing_query += 1
        continue

    if reference_sequence is None:
        missing_reference += 1
        continue

    if raw_read is None:
        missing_raw_read += 1
        continue

    result = run_p3_pipeline(
        query_name=projection_id,
        query_sequence=query_sequence,
        target_name=reference_id,
        target_sequence=reference_sequence,
        raw_read_sequence=raw_read,
        raw_clip_start=int(
            metadata["raw_clip_start"]
        ),
        raw_clip_end=int(
            metadata["raw_clip_end"]
        ),
        raw_alignment_strand=(
            metadata["strand"]
        ),
        target_facing_genomic_side=(
            metadata[
                "target_facing_genomic_side"
            ]
        ),
        canonical_motif=(
            metadata["canonical_motif"]
        ),
        bridge_bp=int(
            metadata["bridge_bp"]
        ),
        target_entry_bp=int(
            metadata["target_entry_bp"]
        ),
        query_can_reach_target_entry=(
            metadata[
                "query_can_reach_target_entry"
            ] == "true"
        ),
        expected_orientation_transform=(
            metadata[
                "orientation_transform"
            ]
        ),
    )

    if (
        result.orientation_transform
        != metadata["orientation_transform"]
    ):
        orientation_transform_mismatches += 1

    if not result.query_prefix_matches:
        query_prefix_mismatches += 1

    expected_pair = pair_lookup[
        projection_id
    ]
    produced_pair_status = (
        result.pair_projection
        .target_entry_projection_status
    )
    produced_pair_offset = (
        "."
        if (
            result.pair_projection
            .target_entry_query_offset
            is None
        )
        else str(
            result.pair_projection
            .target_entry_query_offset
        )
    )

    if not compare(
        projection_id=projection_id,
        layer="pair",
        field="projection_status",
        expected=expected_pair[
            "production_projection_status"
        ],
        produced=produced_pair_status,
    ):
        pair_projection_status_mismatches += 1

    if not compare(
        projection_id=projection_id,
        layer="pair",
        field="target_entry_query_offset",
        expected=expected_pair[
            "production_target_entry_query_offset"
        ],
        produced=produced_pair_offset,
    ):
        pair_query_offset_mismatches += 1

    repeat_contract = (
        result.repeat_measurement
        .to_contract_dict()
    )
    expected_repeat = repeat_lookup[
        projection_id
    ]

    for field in REPEAT_FIELDS:
        if not compare(
            projection_id=projection_id,
            layer="repeat",
            field=field,
            expected=expected_repeat[field],
            produced=repeat_contract[field],
        ):
            repeat_field_mismatches += 1

    decision = result.decision
    decision_contract = {
        "primary_status":
            decision.primary_status,
        "standard_evidence_emitted":
            str(
                decision.standard_evidence_emitted
            ).lower(),
        "evidence_class":
            decision.evidence_class,
        "sizing_status":
            decision.sizing_status,
        "failure_code":
            decision.failure_code,
        "repeat_bp_estimate":
            (
                "."
                if decision.repeat_bp_estimate
                is None
                else decision.repeat_bp_estimate
            ),
        "repeat_bp_lower_bound":
            (
                "."
                if decision.repeat_bp_lower_bound
                is None
                else decision.repeat_bp_lower_bound
            ),
        "allele_length_status":
            decision.allele_length_status,
        "expansion_status":
            decision.expansion_status,
    }
    expected_decision = decision_lookup[
        projection_id
    ]

    for field in DECISION_FIELDS:
        if not compare(
            projection_id=projection_id,
            layer="decision",
            field=field,
            expected=expected_decision[field],
            produced=decision_contract[field],
        ):
            decision_field_mismatches += 1

    frozen = frozen_lookup[
        projection_id
    ]

    if (
        decision.primary_status
        != frozen["frozen_p3_status"]
    ):
        frozen_status_mismatches += 1

    if (
        str(
            decision.standard_evidence_emitted
        ).lower()
        != frozen[
            "standard_p3_evidence_emitted"
        ]
    ):
        frozen_emission_mismatches += 1

    if (
        decision.repeat_bp_estimate
        is not None
        or decision.expansion_status
        != "NOT_ASSESSED"
        or decision.allele_length_status
        != "NOT_MEASURABLE_ONE_FLANK_P3"
    ):
        guardrail_failures += 1

    primary_status_counts[
        decision.primary_status
    ] += 1
    failure_code_counts[
        decision.failure_code
    ] += 1
    standard_evidence_emitted += int(
        decision.standard_evidence_emitted
    )

    replay_rows.append(
        {
            "package_version":
                package_version,
            "projection_id":
                projection_id,
            "read_id":
                metadata["read_id"],
            "target_region_id":
                metadata["target_region_id"],
            "orientation_transform":
                result.orientation_transform,
            "query_prefix_matches":
                str(
                    result.query_prefix_matches
                ).lower(),
            "pair_projection_status":
                produced_pair_status,
            "target_entry_query_offset":
                produced_pair_offset,
            "repeat_tract_bp":
                repeat_contract["tract_bp"],
            "repeat_purity":
                repeat_contract["purity"],
            "repeat_measurement_class":
                repeat_contract[
                    "evidence_class"
                ],
            "repeat_sizing_status":
                repeat_contract[
                    "sizing_status"
                ],
            "primary_status":
                decision.primary_status,
            "standard_evidence_emitted":
                str(
                    decision.standard_evidence_emitted
                ).lower(),
            "final_evidence_class":
                decision.evidence_class,
            "final_sizing_status":
                decision.sizing_status,
            "failure_code":
                decision.failure_code,
            "repeat_bp_estimate":
                decision_contract[
                    "repeat_bp_estimate"
                ],
            "repeat_bp_lower_bound":
                decision_contract[
                    "repeat_bp_lower_bound"
                ],
            "allele_length_status":
                decision.allele_length_status,
            "expansion_status":
                decision.expansion_status,
        }
    )

write_tsv(
    REPLAY,
    [
        "package_version",
        "projection_id",
        "read_id",
        "target_region_id",
        "orientation_transform",
        "query_prefix_matches",
        "pair_projection_status",
        "target_entry_query_offset",
        "repeat_tract_bp",
        "repeat_purity",
        "repeat_measurement_class",
        "repeat_sizing_status",
        "primary_status",
        "standard_evidence_emitted",
        "final_evidence_class",
        "final_sizing_status",
        "failure_code",
        "repeat_bp_estimate",
        "repeat_bp_lower_bound",
        "allele_length_status",
        "expansion_status",
    ],
    replay_rows,
)
write_tsv(
    COMPARISON,
    [
        "projection_id",
        "layer",
        "field",
        "expected",
        "produced",
        "matches",
    ],
    comparison_rows,
)

expected_comparisons = (
    len(expected_ids)
    * (
        2
        + len(REPEAT_FIELDS)
        + len(DECISION_FIELDS)
    )
)

status = "PASS"

if (
    len(expected_ids) != 23
    or len(metadata_rows) != 23
    or len(pair_expected_rows) != 23
    or len(repeat_expected_rows) != 23
    or len(decision_expected_rows) != 23
    or len(frozen_expected_rows) != 23
    or len(replay_rows) != 23
    or missing_metadata
    or missing_query
    or missing_reference
    or missing_raw_read
    or orientation_transform_mismatches
    or query_prefix_mismatches
    or pair_projection_status_mismatches
    or pair_query_offset_mismatches
    or repeat_field_mismatches
    or decision_field_mismatches
    or frozen_status_mismatches
    or frozen_emission_mismatches
    or guardrail_failures
    or len(comparison_rows)
       != expected_comparisons
    or standard_evidence_emitted != 0
    or primary_status_counts[
        "REJECT_ORIENTATION_INCONSISTENT_BRIDGE"
    ] != 22
    or primary_status_counts[
        "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE"
    ] != 1
    or failure_code_counts[
        "ORIENTATION_INCONSISTENT_BRIDGE"
    ] != 22
    or failure_code_counts[
        "HOMOPOLYMER_REVIEW"
    ] != 1
):
    status = "REVIEW"

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        f"package_version\t{package_version}\n"
    )
    handle.write(
        "expected_candidates\t{}\n".format(
            len(expected_ids)
        )
    )
    handle.write(
        "pipeline_rows\t{}\n".format(
            len(replay_rows)
        )
    )
    handle.write(
        "raw_reads_loaded\t{}\n".format(
            len(raw_reads)
        )
    )
    handle.write(
        "missing_metadata_rows\t{}\n".format(
            missing_metadata
        )
    )
    handle.write(
        "missing_query_rows\t{}\n".format(
            missing_query
        )
    )
    handle.write(
        "missing_reference_rows\t{}\n".format(
            missing_reference
        )
    )
    handle.write(
        "missing_raw_reads\t{}\n".format(
            missing_raw_read
        )
    )
    handle.write(
        "orientation_transform_mismatches\t{}\n".format(
            orientation_transform_mismatches
        )
    )
    handle.write(
        "query_prefix_mismatches\t{}\n".format(
            query_prefix_mismatches
        )
    )
    handle.write(
        "pair_projection_status_mismatches\t{}\n".format(
            pair_projection_status_mismatches
        )
    )
    handle.write(
        "pair_query_offset_mismatches\t{}\n".format(
            pair_query_offset_mismatches
        )
    )
    handle.write(
        "repeat_field_comparisons\t{}\n".format(
            len(expected_ids)
            * len(REPEAT_FIELDS)
        )
    )
    handle.write(
        "repeat_field_mismatches\t{}\n".format(
            repeat_field_mismatches
        )
    )
    handle.write(
        "decision_field_comparisons\t{}\n".format(
            len(expected_ids)
            * len(DECISION_FIELDS)
        )
    )
    handle.write(
        "decision_field_mismatches\t{}\n".format(
            decision_field_mismatches
        )
    )
    handle.write(
        "frozen_status_mismatches\t{}\n".format(
            frozen_status_mismatches
        )
    )
    handle.write(
        "frozen_emission_mismatches\t{}\n".format(
            frozen_emission_mismatches
        )
    )
    handle.write(
        "total_field_comparisons\t{}\n".format(
            len(comparison_rows)
        )
    )
    handle.write(
        "guardrail_failures\t{}\n".format(
            guardrail_failures
        )
    )
    handle.write(
        "standard_p3_evidence_emitted\t{}\n".format(
            standard_evidence_emitted
        )
    )

    for key, value in sorted(
        primary_status_counts.items()
    ):
        handle.write(
            "primary_status::{}\t{}\n".format(
                key,
                value,
            )
        )

    for key, value in sorted(
        failure_code_counts.items()
    ):
        handle.write(
            "failure_code::{}\t{}\n".format(
                key,
                value,
            )
        )

    handle.write(
        "p3_end_to_end_pipeline_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "Production P3 end-to-end replay requires review"
    )
PYREPLAY

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PACKAGE_DIR/p3_pipeline.py" \
      "$UNIT_DIR/test_p3_pipeline.py" \
      "$REPLAY" \
      "$COMPARISON" \
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
echo "===== END-TO-END REPLAY ====="
column -ts $'\t' "$REPLAY"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== BACKUP ====="
echo "$BACKUP"
