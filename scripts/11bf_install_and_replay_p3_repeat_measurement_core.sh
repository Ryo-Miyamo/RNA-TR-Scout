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

VALIDATED_SOURCE="$PROJECT_ROOT/results/11_p3_repeat_core_explicit_validation/$RUN_ID/p3_repeat_explicit_candidate.py"
VALIDATED_QC="$PROJECT_ROOT/qc/11_p3_repeat_core_explicit_validation/$RUN_ID/p3_repeat_explicit_validation.qc.tsv"

SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"
PAIR_REPLAY="$PROJECT_ROOT/results/11_production_p3_pair_projection_fix/$RUN_ID/p3_pair_alignment_projection_replay.corrected.tsv"
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"
RAW_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_production_p3_repeat/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_p3_repeat/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_production_p3_repeat/$RUN_ID"

REPLAY="$OUTDIR/p3_repeat_measurement_replay.tsv"
COMPARISON="$OUTDIR/p3_repeat_measurement_field_comparison.tsv"
QC="$QCDIR/p3_repeat_measurement_core.qc.tsv"
UNIT_LOG="$OUTDIR/unit_tests.log"
MANIFEST="$OUTDIR/${RUN_ID}.production_p3_repeat.manifest.tsv"

STAGE="$WORKDIR/stage"
STAGE_PACKAGE="$STAGE/rnatr_scout"
STAGE_TESTS="$STAGE/tests"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PACKAGE_DIR" \
  "$UNIT_DIR" \
  "$VALIDATED_SOURCE" \
  "$VALIDATED_QC" \
  "$SIZING" \
  "$PAIR_REPLAY" \
  "$QUERY_FASTA" \
  "$RAW_FASTQ"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

validated_status="$(
    awk -F '\t' '
      $1 == "explicit_repeat_core_validation_status" {
        print $2
      }
    ' "$VALIDATED_QC"
)"

validated_mismatches="$(
    awk -F '\t' '
      $1 == "field_mismatches" {
        print $2
      }
    ' "$VALIDATED_QC"
)"

if [[ "$validated_status" != "PASS" ]]; then
    echo "ERROR: validated source QC is not PASS" >&2
    exit 1
fi

if [[ "$validated_mismatches" != "0" ]]; then
    echo "ERROR: validated source has field mismatches" >&2
    exit 1
fi

if [[ -e "$PACKAGE_DIR/p3_repeat.py" ]]; then
    echo "ERROR: production module already exists: $PACKAGE_DIR/p3_repeat.py" >&2
    exit 1
fi

if [[ -e "$UNIT_DIR/test_p3_repeat.py" ]]; then
    echo "ERROR: unit test already exists: $UNIT_DIR/test_p3_repeat.py" >&2
    exit 1
fi

installed_version="$(rnatr-scout version)"

if [[ "$installed_version" != "$PACKAGE_VERSION" ]]; then
    echo "ERROR: unexpected installed version: $installed_version" >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$PACKAGE_DIR" "$STAGE_PACKAGE"
cp -a "$UNIT_DIR" "$STAGE_TESTS"

cp "$VALIDATED_SOURCE" \
  "$STAGE_PACKAGE/p3_repeat.py"

cat >> "$STAGE_PACKAGE/p3_repeat.py" <<'PY'


@dataclass(frozen=True)
class RepeatMeasurement:
    """Sequence measurement from one target-facing P3 clip.

    This object measures repeat evidence only. It does not infer an
    expanded allele, DNA genotype, or pathogenicity.
    """

    tract_oriented_start: int | None
    tract_oriented_end: int | None
    tract_raw_start: int | None
    tract_raw_end: int | None
    tract_bp: int
    repeat_units_observed_read: float | None
    repeat_units_motif_path: float | None
    motif_path_to_read_units_ratio: float | None
    matches: int | None
    mismatches: int | None
    insertions: int | None
    deletions: int | None
    purity: float | None
    score: int | None
    selected_orientation: str | None
    entry_offset_selected_bp: int | None
    distance_from_tract_to_oriented_clip_end_bp: int | None
    tract_reaches_expected_raw_end: bool
    evidence_class: str
    sizing_status: str
    repeat_bp_lower_bound: int | None
    allele_length_status: str = (
        "NOT_MEASURABLE_ONE_FLANK_P3"
    )

    def to_contract_dict(self) -> dict[str, object]:
        """Return values formatted as in the frozen 11af TSV."""

        def integer_or_dot(
            value: int | None,
        ) -> int | str:
            return "." if value is None else value

        def float_or_dot(
            value: float | None,
        ) -> str:
            if value is None:
                return "."

            return f"{value:.6f}"

        return {
            "tract_oriented_start":
                integer_or_dot(
                    self.tract_oriented_start
                ),
            "tract_oriented_end":
                integer_or_dot(
                    self.tract_oriented_end
                ),
            "tract_raw_start":
                integer_or_dot(
                    self.tract_raw_start
                ),
            "tract_raw_end":
                integer_or_dot(
                    self.tract_raw_end
                ),
            "tract_bp":
                self.tract_bp,
            "repeat_units_observed_read":
                float_or_dot(
                    self.repeat_units_observed_read
                ),
            "repeat_units_motif_path":
                float_or_dot(
                    self.repeat_units_motif_path
                ),
            "motif_path_to_read_units_ratio":
                float_or_dot(
                    self.motif_path_to_read_units_ratio
                ),
            "matches":
                integer_or_dot(self.matches),
            "mismatches":
                integer_or_dot(self.mismatches),
            "insertions":
                integer_or_dot(self.insertions),
            "deletions":
                integer_or_dot(self.deletions),
            "purity":
                float_or_dot(self.purity),
            "score":
                integer_or_dot(self.score),
            "selected_orientation":
                (
                    self.selected_orientation
                    if self.selected_orientation
                    is not None
                    else "."
                ),
            "entry_offset_selected_bp":
                integer_or_dot(
                    self.entry_offset_selected_bp
                ),
            "distance_from_tract_to_oriented_clip_end_bp":
                integer_or_dot(
                    self.distance_from_tract_to_oriented_clip_end_bp
                ),
            "tract_reaches_expected_raw_end":
                str(
                    self.tract_reaches_expected_raw_end
                ).lower(),
            "evidence_class":
                self.evidence_class,
            "sizing_status":
                self.sizing_status,
            "repeat_bp_lower_bound":
                integer_or_dot(
                    self.repeat_bp_lower_bound
                ),
            "allele_length_status":
                self.allele_length_status,
        }


def _no_repeat_measurement() -> RepeatMeasurement:
    return RepeatMeasurement(
        tract_oriented_start=None,
        tract_oriented_end=None,
        tract_raw_start=None,
        tract_raw_end=None,
        tract_bp=0,
        repeat_units_observed_read=None,
        repeat_units_motif_path=None,
        motif_path_to_read_units_ratio=None,
        matches=None,
        mismatches=None,
        insertions=None,
        deletions=None,
        purity=None,
        score=None,
        selected_orientation=None,
        entry_offset_selected_bp=None,
        distance_from_tract_to_oriented_clip_end_bp=None,
        tract_reaches_expected_raw_end=False,
        evidence_class=(
            "P3_BRIDGE_ONLY_NO_TARGET_ENTRY_REPEAT_TRACT"
        ),
        sizing_status="no_call",
        repeat_bp_lower_bound=None,
    )


def measure_target_entry_repeat(
    *,
    oriented_clip: str,
    motif: str,
    target_entry_query_offset: int | None,
    raw_clip_start: int,
    raw_clip_end: int,
    orientation_transform: str,
    target_facing_genomic_side: str,
    target_entry_projection_status: str,
    query_prefix_matches: bool,
) -> RepeatMeasurement:
    """Measure a periodic tract near a projected target entrance.

    Mononucleotide tracts may be measured here, but downstream decision
    code must continue to route them to homopolymer review rather than
    the standard P3 evidence stream.
    """

    if raw_clip_start < 0:
        raise ValueError(
            "raw_clip_start must be non-negative"
        )

    if raw_clip_end < raw_clip_start:
        raise ValueError(
            "raw_clip_end must be at least raw_clip_start"
        )

    if len(oriented_clip) != (
        raw_clip_end - raw_clip_start
    ):
        raise ValueError(
            "oriented_clip length does not match raw clip interval"
        )

    if orientation_transform not in {
        "AS_RAW",
        "REVERSE_COMPLEMENT",
    }:
        raise ValueError(
            "unsupported orientation_transform"
        )

    if target_facing_genomic_side not in {
        "GENOMIC_RIGHT",
        "GENOMIC_LEFT",
    }:
        raise ValueError(
            "unsupported target_facing_genomic_side"
        )

    if (
        target_entry_projection_status
        != "TARGET_ENTRY_PROJECTED"
        or target_entry_query_offset is None
        or not query_prefix_matches
    ):
        return _no_repeat_measurement()

    if not (
        0
        <= target_entry_query_offset
        <= len(oriented_clip)
    ):
        raise ValueError(
            "target_entry_query_offset is outside oriented clip"
        )

    normalized_motif = canonical_motif(motif)
    minimum_start = max(
        0,
        target_entry_query_offset - ENTRY_OFFSET,
    )
    maximum_start = min(
        len(oriented_clip),
        target_entry_query_offset + ENTRY_OFFSET,
    )

    best_tract = None

    for tract_start in range(
        minimum_start,
        maximum_start + 1,
    ):
        call = longest_valid_periodic_prefix(
            oriented_clip[tract_start:],
            normalized_motif,
        )

        if call is None:
            continue

        tract_end = (
            tract_start + call["prefix_bp"]
        )
        reaches_end = (
            len(oriented_clip) - tract_end
            <= END_TOLERANCE
        )
        candidate = dict(call)
        candidate.update(
            {
                "tract_start": tract_start,
                "tract_end": tract_end,
                "entry_offset": (
                    tract_start
                    - target_entry_query_offset
                ),
                "reaches_clip_end": reaches_end,
            }
        )
        rank = (
            candidate["prefix_bp"],
            candidate["purity"],
            candidate["score"],
            -abs(candidate["entry_offset"]),
        )

        if (
            best_tract is None
            or rank > best_tract["_rank"]
        ):
            candidate["_rank"] = rank
            best_tract = candidate

    if best_tract is None:
        return _no_repeat_measurement()

    tract_raw_start, tract_raw_end = (
        oriented_to_raw_interval(
            best_tract["tract_start"],
            best_tract["tract_end"],
            raw_clip_start,
            raw_clip_end,
            orientation_transform,
        )
    )

    if best_tract["reaches_clip_end"]:
        sizing_status = "lower_bound"
        repeat_bp_lower_bound = (
            best_tract["prefix_bp"]
        )

        if (
            target_facing_genomic_side
            == "GENOMIC_RIGHT"
        ):
            evidence_class = (
                "LEFT_ANCHORED_CENSORED_RIGHT"
            )
        else:
            evidence_class = (
                "RIGHT_ANCHORED_CENSORED_LEFT"
            )

    else:
        sizing_status = "partial_internal"
        repeat_bp_lower_bound = None

        if (
            target_facing_genomic_side
            == "GENOMIC_RIGHT"
        ):
            evidence_class = "LEFT_ONLY_INTERNAL"
        else:
            evidence_class = "RIGHT_ONLY_INTERNAL"

    return RepeatMeasurement(
        tract_oriented_start=(
            best_tract["tract_start"]
        ),
        tract_oriented_end=(
            best_tract["tract_end"]
        ),
        tract_raw_start=tract_raw_start,
        tract_raw_end=tract_raw_end,
        tract_bp=best_tract["prefix_bp"],
        repeat_units_observed_read=(
            best_tract["observed_units"]
        ),
        repeat_units_motif_path=(
            best_tract["path_units"]
        ),
        motif_path_to_read_units_ratio=(
            best_tract["path_ratio"]
        ),
        matches=best_tract["matches"],
        mismatches=best_tract["mismatches"],
        insertions=best_tract["insertions"],
        deletions=best_tract["deletions"],
        purity=best_tract["purity"],
        score=best_tract["score"],
        selected_orientation=(
            best_tract["orientation"]
        ),
        entry_offset_selected_bp=(
            best_tract["entry_offset"]
        ),
        distance_from_tract_to_oriented_clip_end_bp=(
            len(oriented_clip)
            - best_tract["tract_end"]
        ),
        tract_reaches_expected_raw_end=(
            best_tract["reaches_clip_end"]
        ),
        evidence_class=evidence_class,
        sizing_status=sizing_status,
        repeat_bp_lower_bound=(
            repeat_bp_lower_bound
        ),
    )
PY

cat > "$STAGE_TESTS/test_p3_repeat.py" <<'PY'
from __future__ import annotations

import unittest

from rnatr_scout.p3_repeat import (
    measure_target_entry_repeat,
)


class TestP3Repeat(unittest.TestCase):
    def test_internal_homopolymer_measurement(self):
        clip = "CAAAAAAAAAAAAAGGGGG"

        result = measure_target_entry_repeat(
            oriented_clip=clip,
            motif="A",
            target_entry_query_offset=2,
            raw_clip_start=100,
            raw_clip_end=100 + len(clip),
            orientation_transform="AS_RAW",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            target_entry_projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_prefix_matches=True,
        )

        self.assertEqual(
            result.sizing_status,
            "partial_internal",
        )
        self.assertEqual(
            result.evidence_class,
            "LEFT_ONLY_INTERNAL",
        )
        self.assertGreaterEqual(
            result.tract_bp,
            12,
        )
        self.assertIsNone(
            result.repeat_bp_lower_bound
        )

    def test_terminal_tract_is_lower_bound(self):
        clip = "CCCAAAAAAAAAAAAA"

        result = measure_target_entry_repeat(
            oriented_clip=clip,
            motif="A",
            target_entry_query_offset=3,
            raw_clip_start=10,
            raw_clip_end=10 + len(clip),
            orientation_transform="AS_RAW",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            target_entry_projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_prefix_matches=True,
        )

        self.assertEqual(
            result.sizing_status,
            "lower_bound",
        )
        self.assertEqual(
            result.evidence_class,
            "LEFT_ANCHORED_CENSORED_RIGHT",
        )
        self.assertEqual(
            result.repeat_bp_lower_bound,
            result.tract_bp,
        )

    def test_reverse_projection_is_no_call(self):
        clip = "A" * 30

        result = measure_target_entry_repeat(
            oriented_clip=clip,
            motif="A",
            target_entry_query_offset=None,
            raw_clip_start=20,
            raw_clip_end=50,
            orientation_transform="AS_RAW",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            target_entry_projection_status=(
                "UNEXPECTED_REVERSE_ALIGNMENT"
            ),
            query_prefix_matches=True,
        )

        contract = result.to_contract_dict()

        self.assertEqual(
            result.sizing_status,
            "no_call",
        )
        self.assertEqual(
            contract["tract_bp"],
            0,
        )
        self.assertEqual(
            contract["purity"],
            ".",
        )

    def test_query_prefix_mismatch_is_no_call(self):
        clip = "A" * 30

        result = measure_target_entry_repeat(
            oriented_clip=clip,
            motif="A",
            target_entry_query_offset=0,
            raw_clip_start=0,
            raw_clip_end=30,
            orientation_transform="AS_RAW",
            target_facing_genomic_side=(
                "GENOMIC_LEFT"
            ),
            target_entry_projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_prefix_matches=False,
        )

        self.assertEqual(
            result.sizing_status,
            "no_call",
        )

    def test_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            measure_target_entry_repeat(
                oriented_clip="AAAA",
                motif="A",
                target_entry_query_offset=0,
                raw_clip_start=0,
                raw_clip_end=5,
                orientation_transform="AS_RAW",
                target_facing_genomic_side=(
                    "GENOMIC_RIGHT"
                ),
                target_entry_projection_status=(
                    "TARGET_ENTRY_PROJECTED"
                ),
                query_prefix_matches=True,
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
BACKUP="$PROJECT_ROOT/metadata/code_backups/11bf_${timestamp}"
mkdir -p "$BACKUP"

cp -a "$UNIT_DIR" "$BACKUP/unit_tests"

cp "$STAGE_PACKAGE/p3_repeat.py" \
  "$PACKAGE_DIR/p3_repeat.py"
cp "$STAGE_TESTS/test_p3_repeat.py" \
  "$UNIT_DIR/test_p3_repeat.py"

echo
echo "===== INSTALLED PACKAGE UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$UNIT_DIR" \
  -v

echo
echo "===== REPLAY 23 P3 MEASUREMENTS ====="

python - \
  "$SIZING" \
  "$PAIR_REPLAY" \
  "$QUERY_FASTA" \
  "$RAW_FASTQ" \
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

from rnatr_scout.p3_repeat import (
    measure_target_entry_repeat,
    reverse_complement,
)

(
    sizing_text,
    pair_text,
    query_fasta_text,
    raw_fastq_text,
    replay_text,
    comparison_text,
    qc_text,
    package_version,
) = sys.argv[1:]

SIZING = Path(sizing_text)
PAIR = Path(pair_text)
QUERY_FASTA = Path(query_fasta_text)
RAW_FASTQ = Path(raw_fastq_text)
REPLAY = Path(replay_text)
COMPARISON = Path(comparison_text)
QC = Path(qc_text)

FIELDS = [
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


def load_fasta(path):
    records = {}

    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
    ) as handle:
        record_id = None
        parts = []

        for line in handle:
            line = line.strip()

            if not line:
                continue

            if line.startswith(">"):
                if record_id is not None:
                    records[record_id] = "".join(
                        parts
                    ).upper()

                record_id = line[1:].split()[0]
                parts = []
                continue

            parts.append(line)

        if record_id is not None:
            records[record_id] = "".join(
                parts
            ).upper()

    return records


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

            read_id = header[1:].split()[0]

            if read_id in wanted_ids:
                records[read_id] = (
                    sequence.strip().upper()
                )

                if len(records) == len(wanted_ids):
                    break

    return records


sizing_rows = read_tsv(SIZING)
pair_rows = read_tsv(PAIR)
pair_lookup = {
    row["projection_id"]: row
    for row in pair_rows
}
query_sequences = load_fasta(
    QUERY_FASTA
)
wanted_read_ids = {
    row["read_id"]
    for row in sizing_rows
}
raw_reads = load_selected_fastq(
    RAW_FASTQ,
    wanted_read_ids,
)

missing_pair_rows = 0
missing_query_rows = 0
missing_raw_reads = 0
query_prefix_mismatches = 0
comparison_rows = []
replay_rows = []
field_mismatches = 0
sizing_counts = Counter()
evidence_counts = Counter()

for expected in sizing_rows:
    projection_id = expected[
        "projection_id"
    ]
    read_id = expected["read_id"]
    pair = pair_lookup.get(projection_id)
    query_sequence = query_sequences.get(
        projection_id
    )
    raw_read = raw_reads.get(read_id)

    if pair is None:
        missing_pair_rows += 1
        continue

    if query_sequence is None:
        missing_query_rows += 1
        continue

    if raw_read is None:
        missing_raw_reads += 1
        continue

    raw_clip_start = int(
        expected["raw_clip_start"]
    )
    raw_clip_end = int(
        expected["raw_clip_end"]
    )
    raw_clip = raw_read[
        raw_clip_start:raw_clip_end
    ]
    transform = expected[
        "orientation_transform"
    ]

    if transform == "AS_RAW":
        oriented_clip = raw_clip

    elif transform == "REVERSE_COMPLEMENT":
        oriented_clip = reverse_complement(
            raw_clip
        )

    else:
        raise ValueError(
            f"unexpected transform: {transform}"
        )

    query_prefix_matches = (
        oriented_clip[
            :len(query_sequence)
        ]
        == query_sequence
    )

    if not query_prefix_matches:
        query_prefix_mismatches += 1

    offset_text = pair[
        "production_target_entry_query_offset"
    ]
    target_entry_offset = (
        None
        if offset_text == "."
        else int(offset_text)
    )

    measurement = (
        measure_target_entry_repeat(
            oriented_clip=oriented_clip,
            motif=expected[
                "canonical_motif"
            ],
            target_entry_query_offset=(
                target_entry_offset
            ),
            raw_clip_start=raw_clip_start,
            raw_clip_end=raw_clip_end,
            orientation_transform=transform,
            target_facing_genomic_side=(
                expected[
                    "target_facing_genomic_side"
                ]
            ),
            target_entry_projection_status=(
                pair[
                    "production_projection_status"
                ]
            ),
            query_prefix_matches=(
                query_prefix_matches
            ),
        )
    )
    produced = (
        measurement.to_contract_dict()
    )

    sizing_counts[
        measurement.sizing_status
    ] += 1
    evidence_counts[
        measurement.evidence_class
    ] += 1

    row = {
        "projection_id": projection_id,
        "read_id": read_id,
        "target_region_id": expected[
            "target_region_id"
        ],
        "projection_status": pair[
            "production_projection_status"
        ],
        "query_prefix_matches": str(
            query_prefix_matches
        ).lower(),
    }

    for field in FIELDS:
        row[field] = produced[field]

        expected_value = str(
            expected[field]
        )
        produced_value = str(
            produced[field]
        )
        matches = (
            expected_value == produced_value
        )

        if not matches:
            field_mismatches += 1

        comparison_rows.append(
            {
                "projection_id":
                    projection_id,
                "field":
                    field,
                "expected":
                    expected_value,
                "produced":
                    produced_value,
                "matches":
                    str(matches).lower(),
            }
        )

    replay_rows.append(row)

replay_fields = [
    "projection_id",
    "read_id",
    "target_region_id",
    "projection_status",
    "query_prefix_matches",
] + FIELDS

write_tsv(
    REPLAY,
    replay_fields,
    replay_rows,
)
write_tsv(
    COMPARISON,
    [
        "projection_id",
        "field",
        "expected",
        "produced",
        "matches",
    ],
    comparison_rows,
)

expected_comparisons = (
    len(sizing_rows) * len(FIELDS)
)

status = "PASS"

if (
    len(sizing_rows) != 23
    or len(pair_rows) != 23
    or len(replay_rows) != 23
    or missing_pair_rows
    or missing_query_rows
    or missing_raw_reads
    or query_prefix_mismatches
    or len(comparison_rows)
       != expected_comparisons
    or field_mismatches
    or sizing_counts["no_call"] != 22
    or sizing_counts["partial_internal"] != 1
    or evidence_counts[
        "P3_BRIDGE_ONLY_NO_TARGET_ENTRY_REPEAT_TRACT"
    ] != 22
    or evidence_counts[
        "LEFT_ONLY_INTERNAL"
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
        "validated_source_status\tPASS\n"
    )
    handle.write(
        "input_sizing_rows\t{}\n".format(
            len(sizing_rows)
        )
    )
    handle.write(
        "input_pair_rows\t{}\n".format(
            len(pair_rows)
        )
    )
    handle.write(
        "unique_read_ids_requested\t{}\n".format(
            len(wanted_read_ids)
        )
    )
    handle.write(
        "unique_raw_reads_loaded\t{}\n".format(
            len(raw_reads)
        )
    )
    handle.write(
        "measurement_rows\t{}\n".format(
            len(replay_rows)
        )
    )
    handle.write(
        "missing_pair_rows\t{}\n".format(
            missing_pair_rows
        )
    )
    handle.write(
        "missing_query_rows\t{}\n".format(
            missing_query_rows
        )
    )
    handle.write(
        "missing_raw_reads\t{}\n".format(
            missing_raw_reads
        )
    )
    handle.write(
        "query_prefix_mismatches\t{}\n".format(
            query_prefix_mismatches
        )
    )
    handle.write(
        "comparison_fields_per_row\t{}\n".format(
            len(FIELDS)
        )
    )
    handle.write(
        "field_comparisons\t{}\n".format(
            len(comparison_rows)
        )
    )
    handle.write(
        "field_mismatches\t{}\n".format(
            field_mismatches
        )
    )

    for key, value in sorted(
        sizing_counts.items()
    ):
        handle.write(
            "sizing_status::{}\t{}\n".format(
                key,
                value,
            )
        )

    for key, value in sorted(
        evidence_counts.items()
    ):
        handle.write(
            "evidence_class::{}\t{}\n".format(
                key,
                value,
            )
        )

    handle.write(
        "p3_repeat_measurement_core_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "Production P3 repeat replay requires review"
    )
PYREPLAY

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PACKAGE_DIR/p3_repeat.py" \
      "$UNIT_DIR/test_p3_repeat.py" \
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
echo "===== REPLAY ====="
column -ts $'\t' "$REPLAY"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== BACKUP ====="
echo "$BACKUP"
