#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
PARAMETER_SET_ID="rnatr_exact_span_global_periodicity_v0.3.1"

EVIDENCE="$PROJECT_ROOT/results/11_periodic_finalization/$RUN_ID/simple_periodic_evidence.schema_v0.3.1.tsv.gz"
CANDIDATE_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_span_calibration/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_span_calibration/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_span_calibration/$RUN_ID"

SPAN_AUDIT="$OUTDIR/exact_span_global_periodicity.tsv.gz"
GROUP_SUMMARY="$OUTDIR/exact_span_global_periodicity.group_summary.tsv"
LOW_PURITY="$OUTDIR/exact_span_global_periodicity.low_purity.top500.tsv"
DISEASE="$OUTDIR/exact_span_global_periodicity.disease.tsv"
QC="$QCDIR/exact_span_global_periodicity_qc.tsv"
PARAMETERS="$OUTDIR/${PARAMETER_SET_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.exact_span_global_periodicity.manifest.tsv"

AUDITOR="$WORKDIR/audit_exact_span_global_periodicity.py"

MATCH_SCORE="${MATCH_SCORE:-3}"
MISMATCH_PENALTY="${MISMATCH_PENALTY:-4}"
INSERTION_PENALTY="${INSERTION_PENALTY:-4}"
DELETION_PENALTY="${DELETION_PENALTY:-4}"
MAX_DELETIONS_BEFORE_BASE="${MAX_DELETIONS_BEFORE_BASE:-1}"

MIN_GLOBAL_PURITY="${MIN_GLOBAL_PURITY:-0.70}"
MIN_REPEAT_BP="${MIN_REPEAT_BP:-12}"
PROGRESS_EVERY="${PROGRESS_EVERY:-5000}"

EXPECTED_EVIDENCE_ROWS=49793
EXPECTED_SPAN_ROWS=23867
EXPECTED_FASTQ_READS=79176

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$EVIDENCE" "$CANDIDATE_FASTQ"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
parameter_set_id	$PARAMETER_SET_ID	Exact-SPAN boundary calibration
input_evidence_class	SPAN	Both genomic flanks already projected
span_boundary_rule	projected_target_read_start_to_end	The projected interval between flanks defines the exact read span
alignment_scope	global_full_projected_interval	Every base in the projected target interval is evaluated
match_score	$MATCH_SCORE	Periodic model match score
mismatch_penalty	$MISMATCH_PENALTY	Substitution penalty
insertion_penalty	$INSERTION_PENALTY	Read insertion penalty
deletion_penalty	$DELETION_PENALTY	Motif deletion penalty
max_deletions_before_base	$MAX_DELETIONS_BEFORE_BASE	Maximum skipped motif positions before consuming a read base
min_global_purity	$MIN_GLOBAL_PURITY	Minimum full-interval periodic purity for provisional exact-SPAN acceptance
min_repeat_bp	$MIN_REPEAT_BP	Minimum projected repeat span
repeat_units_primary	projected_target_bp_divided_by_motif_bp	Exact SPAN sizing candidate
local_baseline_use	diagnostic_only	The prior local tract is used only to measure boundary over-extension
call_semantics	calibration_not_expansion	No disease or expansion inference
progress_every	$PROGRESS_EVERY	Print progress every N SPAN rows
EOF

cat > "$AUDITOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import math
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

import pysam

(
    evidence_path,
    fastq_path,
    audit_path,
    group_summary_path,
    low_purity_path,
    disease_path,
    qc_path,
    parameter_set_id,
    match_score_text,
    mismatch_penalty_text,
    insertion_penalty_text,
    deletion_penalty_text,
    max_deletions_text,
    min_purity_text,
    min_repeat_bp_text,
    progress_every_text,
    expected_evidence_text,
    expected_span_text,
    expected_fastq_text,
) = sys.argv[1:]

MATCH_SCORE = int(match_score_text)
MISMATCH_PENALTY = int(mismatch_penalty_text)
INSERTION_PENALTY = int(insertion_penalty_text)
DELETION_PENALTY = int(deletion_penalty_text)
MAX_DELETIONS = int(max_deletions_text)

MIN_GLOBAL_PURITY = float(min_purity_text)
MIN_REPEAT_BP = int(min_repeat_bp_text)
PROGRESS_EVERY = int(progress_every_text)

EXPECTED_EVIDENCE = int(expected_evidence_text)
EXPECTED_SPAN = int(expected_span_text)
EXPECTED_FASTQ = int(expected_fastq_text)

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


def canonical_motif(sequence: str) -> str:
    sequence = sequence.upper()
    candidates = []

    for oriented in (sequence, reverse_complement(sequence)):
        for index in range(len(oriented)):
            candidates.append(
                oriented[index:] + oriented[:index]
            )

    return min(candidates)


def quantile(values, probability):
    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return float(ordered[0])

    position = probability * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)

    if low == high:
        return float(ordered[low])

    fraction = position - low
    return (
        ordered[low] * (1.0 - fraction)
        + ordered[high] * fraction
    )


def motif_length_bin(length):
    if length == 1:
        return "1_homopolymer"
    if length == 2:
        return "2"
    if length == 3:
        return "3"
    if 4 <= length <= 6:
        return "4_to_6"
    if 7 <= length <= 10:
        return "7_to_10"
    return "11_to_20"


def span_length_bin(length):
    if length < 12:
        return "lt_12"
    if length < 20:
        return "12_to_19"
    if length < 40:
        return "20_to_39"
    if length < 80:
        return "40_to_79"
    if length < 160:
        return "80_to_159"
    if length < 320:
        return "160_to_319"
    return "ge_320"


@dataclass(frozen=True)
class State:
    score: int
    motif_positions: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    starting_phase: int


@dataclass(frozen=True)
class GlobalCall:
    score: int
    motif_positions: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    starting_phase: int
    ending_phase: int
    orientation: str


def state_rank(state: State):
    return (
        state.score,
        state.matches,
        -state.mismatches,
        -state.insertions,
        -state.deletions,
        state.motif_positions,
        -state.starting_phase,
    )


def call_rank(call: GlobalCall):
    return (
        call.score,
        call.matches,
        -call.mismatches,
        -call.insertions,
        -call.deletions,
        call.motif_positions,
        -call.starting_phase,
    )


def update(container, index, candidate):
    current = container[index]

    if current is None or state_rank(candidate) > state_rank(current):
        container[index] = candidate


def align_global_orientation(sequence: str, motif: str):
    motif_length = len(motif)

    # Before the first read base, allow any cyclic starting phase at no cost.
    previous = [
        State(
            score=0,
            motif_positions=0,
            matches=0,
            mismatches=0,
            insertions=0,
            deletions=0,
            starting_phase=phase,
        )
        for phase in range(motif_length)
    ]

    for base in sequence:
        current = [None] * motif_length

        for expected_phase, state in enumerate(previous):
            # Read insertion relative to the periodic motif.
            update(
                current,
                expected_phase,
                State(
                    score=state.score - INSERTION_PENALTY,
                    motif_positions=state.motif_positions,
                    matches=state.matches,
                    mismatches=state.mismatches,
                    insertions=state.insertions + 1,
                    deletions=state.deletions,
                    starting_phase=state.starting_phase,
                ),
            )

            # Consume the read base after zero or more skipped motif positions.
            for deleted in range(MAX_DELETIONS + 1):
                motif_phase = (
                    expected_phase + deleted
                ) % motif_length
                expected_base = motif[motif_phase]
                is_match = base == expected_base

                score_delta = (
                    MATCH_SCORE
                    if is_match
                    else -MISMATCH_PENALTY
                )
                score_delta -= deleted * DELETION_PENALTY

                update(
                    current,
                    (motif_phase + 1) % motif_length,
                    State(
                        score=state.score + score_delta,
                        motif_positions=(
                            state.motif_positions + deleted + 1
                        ),
                        matches=state.matches + (1 if is_match else 0),
                        mismatches=(
                            state.mismatches + (0 if is_match else 1)
                        ),
                        insertions=state.insertions,
                        deletions=state.deletions + deleted,
                        starting_phase=state.starting_phase,
                    ),
                )

        previous = current

    best = None

    for ending_phase, state in enumerate(previous):
        if state is None:
            continue

        candidate = GlobalCall(
            score=state.score,
            motif_positions=state.motif_positions,
            matches=state.matches,
            mismatches=state.mismatches,
            insertions=state.insertions,
            deletions=state.deletions,
            starting_phase=state.starting_phase,
            ending_phase=ending_phase,
            orientation=motif,
        )

        if best is None or call_rank(candidate) > call_rank(best):
            best = candidate

    return best


def align_global_periodic(sequence: str, motif: str):
    orientations = [motif]
    reverse = reverse_complement(motif)

    if reverse != motif:
        orientations.append(reverse)

    best = None

    for orientation in orientations:
        candidate = align_global_orientation(
            sequence,
            orientation,
        )

        if best is None or call_rank(candidate) > call_rank(best):
            best = candidate

    return best


# Deterministic self-tests.
self_tests = [
    ("CAGCAGCAGCAG", "CAG", 1.0),
    ("CTGCTGCTGCTG", "CAG", 1.0),
    ("CAGCAGTCAGCAG", "CAG", 0.75),
]

for sequence, motif, minimum_purity in self_tests:
    call = align_global_periodic(sequence, motif)
    denominator = (
        call.matches
        + call.mismatches
        + call.insertions
        + call.deletions
    )
    purity = call.matches / denominator if denominator else 0.0

    if purity < minimum_purity:
        raise RuntimeError(
            f"Global periodic self-test failed: "
            f"{sequence}, {motif}, purity={purity}"
        )


all_evidence_rows = 0
span_rows = []

with gzip.open(
    evidence_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        all_evidence_rows += 1

        if row["evidence_class"] == "SPAN":
            span_rows.append(row)

reads = {}

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        reads[entry.name] = entry.sequence.upper()

output_columns = [
    "schema_version",
    "parameter_set_id",
    "projection_id",
    "read_id",
    "target_region_id",
    "target_source",
    "region_type",
    "representative_locus_id",
    "motif",
    "canonical_motif",
    "motif_length_bp",
    "motif_length_bin",
    "projected_target_read_start",
    "projected_target_read_end",
    "projected_span_bp",
    "projected_span_length_bin",
    "projected_span_units",
    "old_local_tract_read_start",
    "old_local_tract_read_end",
    "old_local_tract_bp",
    "old_local_tract_to_projected_ratio",
    "old_left_overhang_bp",
    "old_right_overhang_bp",
    "old_total_overhang_bp",
    "old_local_purity",
    "global_matches",
    "global_mismatches",
    "global_insertions",
    "global_deletions",
    "global_edit_fraction",
    "global_insertion_fraction",
    "global_deletion_fraction",
    "global_purity",
    "global_score",
    "global_score_per_read_bp",
    "global_motif_path_units",
    "global_motif_path_to_projected_units_ratio",
    "global_selected_orientation",
    "global_starting_phase",
    "global_ending_phase",
    "minimum_required_repeat_bp",
    "minimum_required_global_purity",
    "exact_span_periodicity_status",
    "exact_span_periodicity_flags",
    "confidence_label",
    "best_mapq",
    "read_candidate_target_count",
]

counts = Counter()
rows = []
missing_reads = set()
start_time = time.time()

for index, row in enumerate(span_rows, start=1):
    read_id = row["read_id"]
    sequence = reads.get(read_id)

    if sequence is None:
        missing_reads.add(read_id)
        continue

    start = int(row["projected_target_read_start"])
    end = int(row["projected_target_read_end"])
    read_length = len(sequence)

    if not (0 <= start < end <= read_length):
        raise RuntimeError(
            f"Invalid projected interval: "
            f"{row['projection_id']} {start}-{end}/{read_length}"
        )

    target_sequence = sequence[start:end]
    motif = row["canonical_motif"].upper()
    motif_length = len(motif)
    projected_bp = end - start
    projected_units = projected_bp / motif_length

    call = align_global_periodic(target_sequence, motif)

    denominator = (
        call.matches
        + call.mismatches
        + call.insertions
        + call.deletions
    )
    edit_fraction = (
        (call.mismatches + call.insertions + call.deletions)
        / denominator
        if denominator else 1.0
    )
    insertion_fraction = (
        call.insertions / denominator
        if denominator else 0.0
    )
    deletion_fraction = (
        call.deletions / denominator
        if denominator else 0.0
    )
    purity = (
        call.matches / denominator
        if denominator else 0.0
    )
    score_per_bp = (
        call.score / projected_bp
        if projected_bp else 0.0
    )
    motif_path_units = call.motif_positions / motif_length
    path_ratio = (
        motif_path_units / projected_units
        if projected_units else 0.0
    )

    old_start = int(row["tract_read_start"])
    old_end = int(row["tract_read_end"])
    old_bp = int(row["tract_read_bp"])
    old_ratio = old_bp / projected_bp
    left_overhang = max(0, start - old_start)
    right_overhang = max(0, old_end - end)
    total_overhang = left_overhang + right_overhang

    flags = []

    if projected_bp < MIN_REPEAT_BP:
        flags.append("PROJECTED_SPAN_BELOW_MINIMUM_REPEAT_BP")

    if purity < MIN_GLOBAL_PURITY:
        flags.append("GLOBAL_PURITY_BELOW_THRESHOLD")

    if path_ratio > 1.25:
        flags.append("GLOBAL_MOTIF_PATH_INFLATION_GT_1_25")

    if edit_fraction > 0.30:
        flags.append("GLOBAL_EDIT_FRACTION_GT_0_30")

    if total_overhang > 0:
        flags.append("OLD_LOCAL_TRACT_EXTENDED_OUTSIDE_TARGET")

    if projected_bp >= MIN_REPEAT_BP and purity >= MIN_GLOBAL_PURITY:
        status = "PERIODIC_EXACT_SPAN_PASS"
    elif projected_bp < MIN_REPEAT_BP:
        status = "EXACT_SPAN_TOO_SHORT"
    else:
        status = "EXACT_SPAN_LOW_PERIODICITY"

    output_row = {
        "schema_version": "0.3.1",
        "parameter_set_id": parameter_set_id,
        "projection_id": row["projection_id"],
        "read_id": read_id,
        "target_region_id": row["target_region_id"],
        "target_source": row["target_source"],
        "region_type": row["region_type"],
        "representative_locus_id": row[
            "representative_locus_id"
        ],
        "motif": row["motif"],
        "canonical_motif": motif,
        "motif_length_bp": motif_length,
        "motif_length_bin": motif_length_bin(motif_length),
        "projected_target_read_start": start,
        "projected_target_read_end": end,
        "projected_span_bp": projected_bp,
        "projected_span_length_bin": span_length_bin(projected_bp),
        "projected_span_units": f"{projected_units:.6f}",
        "old_local_tract_read_start": old_start,
        "old_local_tract_read_end": old_end,
        "old_local_tract_bp": old_bp,
        "old_local_tract_to_projected_ratio": f"{old_ratio:.6f}",
        "old_left_overhang_bp": left_overhang,
        "old_right_overhang_bp": right_overhang,
        "old_total_overhang_bp": total_overhang,
        "old_local_purity": row["purity"],
        "global_matches": call.matches,
        "global_mismatches": call.mismatches,
        "global_insertions": call.insertions,
        "global_deletions": call.deletions,
        "global_edit_fraction": f"{edit_fraction:.6f}",
        "global_insertion_fraction": f"{insertion_fraction:.6f}",
        "global_deletion_fraction": f"{deletion_fraction:.6f}",
        "global_purity": f"{purity:.6f}",
        "global_score": call.score,
        "global_score_per_read_bp": f"{score_per_bp:.6f}",
        "global_motif_path_units": f"{motif_path_units:.6f}",
        "global_motif_path_to_projected_units_ratio": (
            f"{path_ratio:.6f}"
        ),
        "global_selected_orientation": call.orientation,
        "global_starting_phase": call.starting_phase,
        "global_ending_phase": call.ending_phase,
        "minimum_required_repeat_bp": MIN_REPEAT_BP,
        "minimum_required_global_purity": (
            f"{MIN_GLOBAL_PURITY:.6f}"
        ),
        "exact_span_periodicity_status": status,
        "exact_span_periodicity_flags": (
            ";".join(sorted(set(flags))) if flags else "."
        ),
        "confidence_label": row["confidence_label"],
        "best_mapq": row["best_mapq"],
        "read_candidate_target_count": row[
            "read_candidate_target_count"
        ],
    }
    rows.append(output_row)

    counts[f"status::{status}"] += 1
    counts[
        f"motif_length_bin::{motif_length_bin(motif_length)}"
    ] += 1
    counts[
        f"span_length_bin::{span_length_bin(projected_bp)}"
    ] += 1
    counts[f"confidence::{row['confidence_label']}"] += 1

    scope = (
        "unique_candidate"
        if int(row["read_candidate_target_count"]) == 1
        else "multiple_candidates"
    )
    counts[f"candidate_scope::{scope}"] += 1

    for flag in set(flags):
        counts[f"flag::{flag}"] += 1

    if index % PROGRESS_EVERY == 0 or index == len(span_rows):
        elapsed = time.time() - start_time
        rate = index / elapsed if elapsed else 0.0
        remaining = (
            (len(span_rows) - index) / rate
            if rate else 0.0
        )
        print(
            f"[INFO] globally audited {index:,}/{len(span_rows):,} "
            f"SPAN rows; {rate:.1f} rows/s; "
            f"ETA {remaining / 60:.1f} min",
            file=sys.stderr,
            flush=True,
        )

status = "PASS"

if (
    all_evidence_rows != EXPECTED_EVIDENCE
    or len(span_rows) != EXPECTED_SPAN
    or len(reads) != EXPECTED_FASTQ
    or missing_reads
    or len(rows) != EXPECTED_SPAN
):
    status = "REVIEW"

with gzip.open(
    audit_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=output_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

groups = defaultdict(list)

for row in rows:
    groups["ALL"].append(row)
    groups[
        f"motif_bin::{row['motif_length_bin']}"
    ].append(row)
    groups[
        f"span_length_bin::{row['projected_span_length_bin']}"
    ].append(row)
    groups[
        f"confidence::{row['confidence_label']}"
    ].append(row)
    scope = (
        "unique_candidate"
        if int(row["read_candidate_target_count"]) == 1
        else "multiple_candidates"
    )
    groups[f"candidate_scope::{scope}"].append(row)

summary_columns = [
    "group",
    "rows",
    "periodic_pass",
    "periodic_pass_fraction",
    "projected_span_bp_median",
    "global_purity_median",
    "global_purity_p05",
    "global_purity_p95",
    "global_edit_fraction_median",
    "global_path_inflation_median",
    "old_local_ratio_median",
    "old_total_overhang_bp_median",
    "old_total_overhang_bp_p95",
]

with open(
    group_summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=summary_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for group in sorted(groups):
        group_rows = groups[group]
        periodic_pass = sum(
            row["exact_span_periodicity_status"]
            == "PERIODIC_EXACT_SPAN_PASS"
            for row in group_rows
        )
        span_bp = [
            int(row["projected_span_bp"])
            for row in group_rows
        ]
        purities = [
            float(row["global_purity"])
            for row in group_rows
        ]
        edits = [
            float(row["global_edit_fraction"])
            for row in group_rows
        ]
        path_ratios = [
            float(row["global_motif_path_to_projected_units_ratio"])
            for row in group_rows
        ]
        old_ratios = [
            float(row["old_local_tract_to_projected_ratio"])
            for row in group_rows
        ]
        overhangs = [
            int(row["old_total_overhang_bp"])
            for row in group_rows
        ]

        writer.writerow(
            {
                "group": group,
                "rows": len(group_rows),
                "periodic_pass": periodic_pass,
                "periodic_pass_fraction": (
                    f"{periodic_pass / len(group_rows):.6f}"
                ),
                "projected_span_bp_median": (
                    f"{quantile(span_bp, 0.5):.6f}"
                ),
                "global_purity_median": (
                    f"{quantile(purities, 0.5):.6f}"
                ),
                "global_purity_p05": (
                    f"{quantile(purities, 0.05):.6f}"
                ),
                "global_purity_p95": (
                    f"{quantile(purities, 0.95):.6f}"
                ),
                "global_edit_fraction_median": (
                    f"{quantile(edits, 0.5):.6f}"
                ),
                "global_path_inflation_median": (
                    f"{quantile(path_ratios, 0.5):.6f}"
                ),
                "old_local_ratio_median": (
                    f"{quantile(old_ratios, 0.5):.6f}"
                ),
                "old_total_overhang_bp_median": (
                    f"{quantile(overhangs, 0.5):.6f}"
                ),
                "old_total_overhang_bp_p95": (
                    f"{quantile(overhangs, 0.95):.6f}"
                ),
            }
        )

low_purity_rows = sorted(
    rows,
    key=lambda row: (
        float(row["global_purity"]),
        -int(row["projected_span_bp"]),
    ),
)[:500]

with open(
    low_purity_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=output_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(low_purity_rows)

disease_rows = [
    row for row in rows
    if row["target_source"] == "STRchive"
]

with open(
    disease_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=output_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(disease_rows)

numeric = {
    "projected_span_bp": [
        int(row["projected_span_bp"]) for row in rows
    ],
    "global_purity": [
        float(row["global_purity"]) for row in rows
    ],
    "global_edit_fraction": [
        float(row["global_edit_fraction"]) for row in rows
    ],
    "global_path_inflation": [
        float(row["global_motif_path_to_projected_units_ratio"])
        for row in rows
    ],
    "old_local_ratio": [
        float(row["old_local_tract_to_projected_ratio"])
        for row in rows
    ],
    "old_left_overhang_bp": [
        int(row["old_left_overhang_bp"]) for row in rows
    ],
    "old_right_overhang_bp": [
        int(row["old_right_overhang_bp"]) for row in rows
    ],
    "old_total_overhang_bp": [
        int(row["old_total_overhang_bp"]) for row in rows
    ],
}

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        f"expected_evidence_rows\t{EXPECTED_EVIDENCE}\n"
    )
    handle.write(
        f"observed_evidence_rows\t{all_evidence_rows}\n"
    )
    handle.write(f"expected_span_rows\t{EXPECTED_SPAN}\n")
    handle.write(f"observed_span_rows\t{len(span_rows)}\n")
    handle.write(
        f"candidate_fastq_reads_loaded\t{len(reads)}\n"
    )
    handle.write(f"missing_fastq_reads\t{len(missing_reads)}\n")
    handle.write(f"audit_rows_written\t{len(rows)}\n")
    handle.write(f"disease_span_rows\t{len(disease_rows)}\n")

    for key, value in sorted(counts.items()):
        handle.write(f"{key}\t{value}\n")

    for metric_name, values in numeric.items():
        for label, probability in [
            ("min", 0.0),
            ("p05", 0.05),
            ("p25", 0.25),
            ("median", 0.5),
            ("p75", 0.75),
            ("p95", 0.95),
            ("p99", 0.99),
            ("max", 1.0),
        ]:
            handle.write(
                f"{metric_name}::{label}\t"
                f"{quantile(values, probability):.6f}\n"
            )

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit(
        "Exact-SPAN global periodicity audit requires review"
    )
PY

echo "===== 1. INPUT INTEGRITY ====="
gzip -t "$EVIDENCE"
gzip -t "$CANDIDATE_FASTQ"
echo "Inputs: PASS"

echo
echo "===== 2. PARAMETERS ====="
column -ts $'\t' "$PARAMETERS"

echo
echo "===== 3. GLOBAL PERIODICITY OF EXACT PROJECTED SPANS ====="

rm -f \
  "$SPAN_AUDIT" \
  "$GROUP_SUMMARY" \
  "$LOW_PURITY" \
  "$DISEASE" \
  "$QC" \
  "$MANIFEST"

python "$AUDITOR" \
  "$EVIDENCE" \
  "$CANDIDATE_FASTQ" \
  "$SPAN_AUDIT" \
  "$GROUP_SUMMARY" \
  "$LOW_PURITY" \
  "$DISEASE" \
  "$QC" \
  "$PARAMETER_SET_ID" \
  "$MATCH_SCORE" \
  "$MISMATCH_PENALTY" \
  "$INSERTION_PENALTY" \
  "$DELETION_PENALTY" \
  "$MAX_DELETIONS_BEFORE_BASE" \
  "$MIN_GLOBAL_PURITY" \
  "$MIN_REPEAT_BP" \
  "$PROGRESS_EVERY" \
  "$EXPECTED_EVIDENCE_ROWS" \
  "$EXPECTED_SPAN_ROWS" \
  "$EXPECTED_FASTQ_READS"

gzip -t "$SPAN_AUDIT"

echo
echo "===== EXACT-SPAN GLOBAL PERIODICITY QC ====="
column -ts $'\t' "$QC"

echo
echo "===== GROUP SUMMARY ====="
column -ts $'\t' "$GROUP_SUMMARY"

echo
echo "===== DISEASE SPAN ROWS ====="
column -ts $'\t' "$DISEASE"

echo
echo "===== 4. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    rows="$(gzip -cd "$SPAN_AUDIT" | awk 'END {print NR-1}')"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$SPAN_AUDIT")" \
      "$rows" \
      "$(stat -c '%s' "$SPAN_AUDIT")" \
      "$(sha256sum "$SPAN_AUDIT" | awk '{print $1}')" \
      "$SPAN_AUDIT"

    for path in \
      "$GROUP_SUMMARY" \
      "$LOW_PURITY" \
      "$DISEASE" \
      "$QC" \
      "$PARAMETERS"
    do
        rows="$(awk 'END {print NR-1}' "$path")"
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$SPAN_AUDIT"
echo "$GROUP_SUMMARY"
echo "$LOW_PURITY"
echo "$DISEASE"
echo "$QC"
echo "$MANIFEST"
