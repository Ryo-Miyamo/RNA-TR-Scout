#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
PARAMETER_SET_ID="rnatr_periodic_baseline_v0.3.1"

JOBS="$PROJECT_ROOT/results/11_motif_jobs/$RUN_ID/motif_scan_jobs.tsv.gz"
WINDOW_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_projection_v0.3.3/ENCFF260PGB.pilot_100k.rnatr_target_windows.v0.3.3.fastq.gz"
TARGETS="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.tsv.gz"

# Production defaults; Stage 13E validation may override these paths.
OUTDIR="${RNATR_11F_OUTDIR:-$PROJECT_ROOT/results/11_periodic_baseline/$RUN_ID}"
QCDIR="${RNATR_11F_QCDIR:-$PROJECT_ROOT/qc/11_periodic_baseline/$RUN_ID}"
WORKDIR="${RNATR_11F_WORKDIR:-$PROJECT_ROOT/tmp/11_periodic_baseline/$RUN_ID}"

CALLS="$OUTDIR/high_confidence_simple_periodic_calls.tsv.gz"
TOP_CALLS="$OUTDIR/high_confidence_simple_periodic_calls.top500.tsv"
MOTIF_SUMMARY="$OUTDIR/high_confidence_simple_periodic_motif_summary.tsv"
QC_SUMMARY="$QCDIR/high_confidence_simple_periodic_qc.tsv"
PARAMETERS="$OUTDIR/${PARAMETER_SET_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.periodic_baseline_manifest.tsv"

SCANNER="$WORKDIR/run_periodic_baseline.py"

MATCH_SCORE="${MATCH_SCORE:-2}"
MISMATCH_PENALTY="${MISMATCH_PENALTY:-2}"
INSERTION_PENALTY="${INSERTION_PENALTY:-2}"
DELETION_PENALTY="${DELETION_PENALTY:-2}"
MAX_DELETIONS_BEFORE_BASE="${MAX_DELETIONS_BEFORE_BASE:-2}"
MIN_PURITY="${MIN_PURITY:-0.70}"
MIN_REPEAT_BP="${MIN_REPEAT_BP:-12}"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$JOBS" "$WINDOW_FASTQ" "$TARGETS"; do
    test -s "$path" || {
        echo "ERROR: required input missing: $path" >&2
        exit 1
    }
done

for tool in python gzip sha256sum; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
parameter_set_id	$PARAMETER_SET_ID	First raw-read periodic-tract baseline
selected_scan_strategy	SIMPLE_PERIODIC_SCAN	Only single ACGT motifs of length <=20
selected_priorities	P0_DISEASE,P1_RANK1_EXACT_GEOMETRY	Calibration cohort before whole-catalog scan
match_score	$MATCH_SCORE	Score for motif-compatible base
mismatch_penalty	$MISMATCH_PENALTY	Penalty for substitution
insertion_penalty	$INSERTION_PENALTY	Penalty for read insertion relative to periodic model
deletion_penalty	$DELETION_PENALTY	Penalty per skipped motif base
max_deletions_before_base	$MAX_DELETIONS_BEFORE_BASE	Maximum skipped motif positions before consuming one read base
min_purity	$MIN_PURITY	Minimum baseline motif purity
min_repeat_bp	$MIN_REPEAT_BP	Minimum raw-read tract length
min_units_rule	max_3_or_ceil_12_over_motif_length	Minimum motif-unit traversal
orientation_handling	motif_and_reverse_complement	Phase is optimized internally; cyclic rotations need not be enumerated
reference_ratio_scope	TRExplorer_TR_or_TR_FALLBACK_only	Disease-region width is not used as a repeat-length denominator
call_semantics	repeat_tract_detection_not_expansion	No pathological expansion inference at this stage
EOF

cat > "$SCANNER" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import math
import statistics
import sys
import os
import multiprocessing as mp
from collections import Counter, defaultdict
from dataclasses import dataclass

import pysam

(
    jobs_path,
    windows_path,
    targets_path,
    calls_path,
    top_calls_path,
    motif_summary_path,
    qc_path,
    match_score_text,
    mismatch_penalty_text,
    insertion_penalty_text,
    deletion_penalty_text,
    max_deletions_text,
    min_purity_text,
    min_repeat_bp_text,
) = sys.argv[1:]

MATCH_SCORE = int(match_score_text)
MISMATCH_PENALTY = int(mismatch_penalty_text)
INSERTION_PENALTY = int(insertion_penalty_text)
DELETION_PENALTY = int(deletion_penalty_text)
MAX_DELETIONS = int(max_deletions_text)
MIN_PURITY = float(min_purity_text)
MIN_REPEAT_BP = int(min_repeat_bp_text)

COMPLEMENT = str.maketrans(
    "ACGT",
    "TGCA",
)


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


@dataclass(frozen=True)
class State:
    score: int
    start: int
    motif_positions: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int


@dataclass(frozen=True)
class BestCall:
    score: int
    start: int
    end: int
    motif_positions: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    orientation: str
    ending_phase: int


def state_rank(state: State):
    return (
        state.score,
        state.motif_positions,
        state.matches,
        -state.mismatches,
        -state.insertions,
        -state.deletions,
        -state.start,
    )


def best_call_rank(call: BestCall):
    return (
        call.score,
        call.motif_positions,
        call.matches,
        call.end - call.start,
        -call.mismatches,
        -call.insertions,
        -call.deletions,
        -call.start,
    )


def update_state(container, index, candidate):
    if candidate.score <= 0:
        return

    current = container[index]

    if current is None or state_rank(candidate) > state_rank(current):
        container[index] = candidate


def scan_orientation(sequence: str, motif: str) -> BestCall | None:
    motif_length = len(motif)
    previous = [None] * motif_length
    global_best = None

    for sequence_index, base in enumerate(sequence):
        current = [None] * motif_length

        # Local starts. Starting phase is free because the tract can begin
        # at any cyclic position of the motif.
        for motif_phase, expected_base in enumerate(motif):
            is_match = base == expected_base
            score = (
                MATCH_SCORE
                if is_match
                else -MISMATCH_PENALTY
            )

            if score > 0:
                next_phase = (motif_phase + 1) % motif_length
                candidate = State(
                    score=score,
                    start=sequence_index,
                    motif_positions=1,
                    matches=1 if is_match else 0,
                    mismatches=0 if is_match else 1,
                    insertions=0,
                    deletions=0,
                )
                update_state(current, next_phase, candidate)

        for expected_phase, state in enumerate(previous):
            if state is None:
                continue

            # Read insertion: consume one read base without advancing motif.
            insertion_candidate = State(
                score=state.score - INSERTION_PENALTY,
                start=state.start,
                motif_positions=state.motif_positions,
                matches=state.matches,
                mismatches=state.mismatches,
                insertions=state.insertions + 1,
                deletions=state.deletions,
            )
            update_state(
                current,
                expected_phase,
                insertion_candidate,
            )

            # Align after 0..MAX_DELETIONS skipped motif positions.
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

                candidate = State(
                    score=state.score + score_delta,
                    start=state.start,
                    motif_positions=(
                        state.motif_positions + deleted + 1
                    ),
                    matches=state.matches + (1 if is_match else 0),
                    mismatches=(
                        state.mismatches + (0 if is_match else 1)
                    ),
                    insertions=state.insertions,
                    deletions=state.deletions + deleted,
                )
                next_phase = (
                    motif_phase + 1
                ) % motif_length
                update_state(current, next_phase, candidate)

        for ending_phase, state in enumerate(current):
            if state is None:
                continue

            candidate_call = BestCall(
                score=state.score,
                start=state.start,
                end=sequence_index + 1,
                motif_positions=state.motif_positions,
                matches=state.matches,
                mismatches=state.mismatches,
                insertions=state.insertions,
                deletions=state.deletions,
                orientation=motif,
                ending_phase=ending_phase,
            )

            if (
                global_best is None
                or best_call_rank(candidate_call)
                > best_call_rank(global_best)
            ):
                global_best = candidate_call

        previous = current

    return global_best


def scan_periodic(sequence: str, motif: str) -> BestCall | None:
    orientations = [motif]
    reverse = reverse_complement(motif)

    if reverse != motif:
        orientations.append(reverse)

    best = None

    for orientation in orientations:
        candidate = scan_orientation(sequence, orientation)

        if candidate is None:
            continue

        if (
            best is None
            or best_call_rank(candidate) > best_call_rank(best)
        ):
            best = candidate

    return best


def min_required_units(motif_length: int) -> int:
    return max(3, math.ceil(12 / motif_length))


def quantile(values, probability):
    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return float(ordered[0])

    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return float(ordered[lower])

    fraction = position - lower
    return (
        ordered[lower] * (1.0 - fraction)
        + ordered[upper] * fraction
    )


# Minimal deterministic self-test before real data.
tests = [
    ("TTTCAGCAGCAGCAGAAA", "CAG", 4.0),
    ("TTTCTGCTGCTGCTGAAA", "CAG", 4.0),
    ("AAACAGCAGTCAGCAGTTT", "CAG", 4.0),
]

for sequence, motif, minimum_units in tests:
    call = scan_periodic(sequence, motif)

    if call is None:
        raise RuntimeError(
            f"Periodic scanner self-test produced no call: "
            f"{sequence}, {motif}"
        )

    units = call.motif_positions / len(motif)

    if units < minimum_units:
        raise RuntimeError(
            f"Periodic scanner self-test failed: "
            f"{sequence}, {motif}, units={units}"
        )


target_lookup = {}

with gzip.open(
    targets_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        key = (
            row["target_source"],
            row["target_region_id"],
        )
        target_lookup[key] = {
            "start": int(row["start"]),
            "end": int(row["end"]),
            "region_type": row["region_type"],
        }


selected_jobs = {}
selection_counts = Counter()

with gzip.open(
    jobs_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        if row["scan_strategy"] != "SIMPLE_PERIODIC_SCAN":
            continue

        if row["motif_scan_eligible"] != "true":
            continue

        if row["scan_priority"] not in {
            "P0_DISEASE",
            "P1_RANK1_EXACT_GEOMETRY",
        }:
            continue

        projection_id = row["projection_id"]

        if projection_id in selected_jobs:
            raise RuntimeError(
                f"Duplicate selected projection: {projection_id}"
            )

        motifs = row["canonical_motifs"].split(",")

        if len(motifs) != 1:
            raise RuntimeError(
                f"SIMPLE job does not have one motif: "
                f"{projection_id}, {motifs}"
            )

        motif = motifs[0].upper()

        if not motif or not set(motif).issubset(set("ACGT")):
            raise RuntimeError(
                f"Invalid simple motif: {projection_id}, {motif}"
            )

        if len(motif) > 20:
            raise RuntimeError(
                f"Simple motif exceeds 20 bp: {projection_id}"
            )

        row["_motif"] = motif
        selected_jobs[projection_id] = row
        selection_counts[
            f"selected_priority::{row['scan_priority']}"
        ] += 1
        selection_counts[
            f"selected_geometry::{row['geometry_class']}"
        ] += 1
        selection_counts[
            f"selected_motif_length::{len(motif)}"
        ] += 1


call_columns = [
    "schema_version",
    "parameter_set_id",
    "projection_id",
    "read_id",
    "target_region_id",
    "target_source",
    "region_type",
    "representative_locus_id",
    "assignment_rank",
    "scan_priority",
    "geometry_class",
    "potential_evidence_class",
    "motif",
    "canonical_motif",
    "motif_length_bp",
    "window_length_bp",
    "tract_read_start",
    "tract_read_end",
    "tract_read_bp",
    "motif_positions_traversed",
    "repeat_units_estimate",
    "matches",
    "mismatches",
    "insertions",
    "deletions",
    "purity",
    "alignment_score",
    "score_per_motif_position",
    "selected_orientation",
    "ending_phase",
    "minimum_required_units",
    "minimum_required_repeat_bp",
    "minimum_required_purity",
    "target_reference_span_bp",
    "reference_units_proxy",
    "observed_to_reference_units_ratio",
    "baseline_call_status",
    "baseline_call_flags",
]

counts = Counter()
seen_windows = set()
rows = []
motif_stats = defaultdict(
    lambda: {
        "jobs": 0,
        "pass": 0,
        "low_confidence": 0,
        "units": [],
        "purities": [],
    }
)

# Stage 13D performance candidate: exact kernel, multiprocessing only.
RNATR_WORKERS = int(os.environ.get("RNATR_WORKERS", "16"))

def _scan_pair(pair):
    return scan_periodic(pair[0], pair[1])

_parallel_ids = []
_parallel_inputs = []
with pysam.FastxFile(windows_path) as _source:
    for _entry in _source:
        _projection_id = _entry.name
        _job = selected_jobs.get(_projection_id)
        if _job is None:
            continue
        _parallel_ids.append(_projection_id)
        _parallel_inputs.append((_entry.sequence.upper(), _job["_motif"]))

_ctx = mp.get_context("fork")
_chunksize = max(1, len(_parallel_inputs) // max(1, RNATR_WORKERS * 16))
with _ctx.Pool(processes=RNATR_WORKERS) as _pool:
    _parallel_results = _pool.map(_scan_pair, _parallel_inputs, chunksize=_chunksize)
parallel_calls = dict(zip(_parallel_ids, _parallel_results))

with pysam.FastxFile(windows_path) as source:
    for entry in source:
        projection_id = entry.name
        job = selected_jobs.get(projection_id)

        if job is None:
            continue

        if projection_id in seen_windows:
            raise RuntimeError(
                f"Duplicate selected window: {projection_id}"
            )
        seen_windows.add(projection_id)

        sequence = entry.sequence.upper()
        motif = job["_motif"]
        call = parallel_calls[projection_id]

        if call is None:
            tract_start = "."
            tract_end = "."
            tract_bp = 0
            motif_positions = 0
            units = 0.0
            matches = 0
            mismatches = 0
            insertions = 0
            deletions = 0
            purity = 0.0
            alignment_score = 0
            score_per_position = 0.0
            orientation = "."
            ending_phase = "."
        else:
            tract_start = call.start
            tract_end = call.end
            tract_bp = call.end - call.start
            motif_positions = call.motif_positions
            units = motif_positions / len(motif)
            matches = call.matches
            mismatches = call.mismatches
            insertions = call.insertions
            deletions = call.deletions
            denominator = (
                matches
                + mismatches
                + insertions
                + deletions
            )
            purity = matches / denominator if denominator else 0.0
            alignment_score = call.score
            score_per_position = (
                call.score / motif_positions
                if motif_positions else 0.0
            )
            orientation = call.orientation
            ending_phase = call.ending_phase

        required_units = min_required_units(len(motif))
        flags = []

        if units < required_units:
            flags.append("BELOW_MINIMUM_UNITS")

        if tract_bp < MIN_REPEAT_BP:
            flags.append("BELOW_MINIMUM_REPEAT_BP")

        if purity < MIN_PURITY:
            flags.append("BELOW_MINIMUM_PURITY")

        if job["scan_priority"] == "P0_DISEASE":
            flags.append("KNOWN_DISEASE_REGION")

        if int(job["read_candidate_target_count"]) > 1:
            flags.append("MULTIPLE_TARGET_CANDIDATES")

        if not flags or flags == ["MULTIPLE_TARGET_CANDIDATES"]:
            status = "PASS"
        elif (
            units >= required_units
            and tract_bp >= MIN_REPEAT_BP
            and purity >= MIN_PURITY
        ):
            status = "PASS"
        else:
            status = "LOW_CONFIDENCE"

        target_key = (
            job["target_source"],
            job["target_region_id"],
        )
        target = target_lookup[target_key]
        reference_span = target["end"] - target["start"]

        if (
            job["target_source"] == "TRExplorer"
            and job["region_type"] in {"TR", "TR_FALLBACK"}
        ):
            reference_units = reference_span / len(motif)
            ratio = (
                units / reference_units
                if reference_units > 0 else None
            )
        else:
            reference_units = None
            ratio = None

        row = {
            "schema_version": "0.3.0",
            "parameter_set_id": "rnatr_periodic_baseline_v0.3.1",
            "projection_id": projection_id,
            "read_id": job["read_id"],
            "target_region_id": job["target_region_id"],
            "target_source": job["target_source"],
            "region_type": job["region_type"],
            "representative_locus_id": job[
                "representative_locus_id"
            ],
            "assignment_rank": job["assignment_rank"],
            "scan_priority": job["scan_priority"],
            "geometry_class": job["geometry_class"],
            "potential_evidence_class": job[
                "potential_evidence_class"
            ],
            "motif": motif,
            "canonical_motif": canonical_motif(motif),
            "motif_length_bp": len(motif),
            "window_length_bp": len(sequence),
            "tract_read_start": tract_start,
            "tract_read_end": tract_end,
            "tract_read_bp": tract_bp,
            "motif_positions_traversed": motif_positions,
            "repeat_units_estimate": f"{units:.6f}",
            "matches": matches,
            "mismatches": mismatches,
            "insertions": insertions,
            "deletions": deletions,
            "purity": f"{purity:.6f}",
            "alignment_score": alignment_score,
            "score_per_motif_position": (
                f"{score_per_position:.6f}"
            ),
            "selected_orientation": orientation,
            "ending_phase": ending_phase,
            "minimum_required_units": required_units,
            "minimum_required_repeat_bp": MIN_REPEAT_BP,
            "minimum_required_purity": f"{MIN_PURITY:.6f}",
            "target_reference_span_bp": reference_span,
            "reference_units_proxy": (
                "."
                if reference_units is None
                else f"{reference_units:.6f}"
            ),
            "observed_to_reference_units_ratio": (
                "." if ratio is None else f"{ratio:.6f}"
            ),
            "baseline_call_status": status,
            "baseline_call_flags": (
                ";".join(flags) if flags else "."
            ),
        }
        rows.append(row)

        counts["calls_written"] += 1
        counts[f"status::{status}"] += 1
        counts[
            f"priority::{job['scan_priority']}"
        ] += 1
        counts[
            f"geometry::{job['geometry_class']}"
        ] += 1
        counts[f"motif_length::{len(motif)}"] += 1

        if ratio is not None:
            if ratio >= 2.0:
                counts["reference_ratio_ge_2"] += 1
            if ratio >= 1.5:
                counts["reference_ratio_ge_1_5"] += 1
            if ratio >= 1.25:
                counts["reference_ratio_ge_1_25"] += 1

        motif_record = motif_stats[canonical_motif(motif)]
        motif_record["jobs"] += 1
        motif_record[
            "pass" if status == "PASS" else "low_confidence"
        ] += 1
        motif_record["units"].append(units)
        motif_record["purities"].append(purity)


missing_windows = set(selected_jobs) - seen_windows
status = "PASS"

if (
    len(selected_jobs) == 0
    or len(seen_windows) != len(selected_jobs)
    or missing_windows
    or len(rows) != len(selected_jobs)
):
    status = "REVIEW"

with gzip.open(
    calls_path,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=call_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

sortable_rows = []

for row in rows:
    ratio_text = row["observed_to_reference_units_ratio"]
    ratio = (
        float(ratio_text)
        if ratio_text != "."
        else -1.0
    )
    sortable_rows.append(
        (
            float(row["repeat_units_estimate"]),
            ratio,
            float(row["purity"]),
            int(row["tract_read_bp"]),
            row,
        )
    )

sortable_rows.sort(
    key=lambda item: item[:4],
    reverse=True,
)

with open(
    top_calls_path,
    "w",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=call_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for *_sort_values, row in sortable_rows[:500]:
        writer.writerow(row)

motif_summary_columns = [
    "canonical_motif",
    "motif_length_bp",
    "jobs",
    "pass_calls",
    "low_confidence_calls",
    "pass_fraction",
    "repeat_units_median",
    "repeat_units_p95",
    "repeat_units_max",
    "purity_median",
]

with open(
    motif_summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=motif_summary_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for motif in sorted(
        motif_stats,
        key=lambda value: (
            -motif_stats[value]["jobs"],
            len(value),
            value,
        ),
    ):
        record = motif_stats[motif]
        writer.writerow(
            {
                "canonical_motif": motif,
                "motif_length_bp": len(motif),
                "jobs": record["jobs"],
                "pass_calls": record["pass"],
                "low_confidence_calls": record[
                    "low_confidence"
                ],
                "pass_fraction": (
                    f"{record['pass'] / record['jobs']:.6f}"
                ),
                "repeat_units_median": (
                    f"{quantile(record['units'], 0.5):.6f}"
                ),
                "repeat_units_p95": (
                    f"{quantile(record['units'], 0.95):.6f}"
                ),
                "repeat_units_max": (
                    f"{max(record['units']):.6f}"
                ),
                "purity_median": (
                    f"{quantile(record['purities'], 0.5):.6f}"
                ),
            }
        )

unit_values = [
    float(row["repeat_units_estimate"])
    for row in rows
]
purity_values = [
    float(row["purity"])
    for row in rows
]
tract_values = [
    int(row["tract_read_bp"])
    for row in rows
]

with open(qc_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(
        f"selected_jobs\t{len(selected_jobs)}\n"
    )
    output.write(
        f"selected_windows_found\t{len(seen_windows)}\n"
    )
    output.write(
        f"selected_windows_missing\t{len(missing_windows)}\n"
    )
    output.write(f"calls_written\t{len(rows)}\n")

    for key, value in sorted(selection_counts.items()):
        output.write(f"{key}\t{value}\n")

    for key, value in sorted(counts.items()):
        if key == "calls_written":
            continue
        output.write(f"{key}\t{value}\n")

    for metric_name, values in [
        ("repeat_units", unit_values),
        ("purity", purity_values),
        ("tract_read_bp", tract_values),
    ]:
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
            output.write(
                f"{metric_name}::{label}\t"
                f"{quantile(values, probability):.6f}\n"
            )

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Periodic baseline audit requires review")
PY

echo "===== 1. INPUT INTEGRITY ====="

gzip -t "$JOBS"
gzip -t "$WINDOW_FASTQ"
gzip -t "$TARGETS"

echo "Inputs: PASS"

echo
echo "===== 2. PARAMETERS ====="
column -ts $'\t' "$PARAMETERS"

echo
echo "===== 3. RUN HIGH-CONFIDENCE SIMPLE PERIODIC BASELINE ====="

rm -f \
  "$CALLS" \
  "$TOP_CALLS" \
  "$MOTIF_SUMMARY" \
  "$QC_SUMMARY" \
  "$MANIFEST"

python "$SCANNER" \
  "$JOBS" \
  "$WINDOW_FASTQ" \
  "$TARGETS" \
  "$CALLS" \
  "$TOP_CALLS" \
  "$MOTIF_SUMMARY" \
  "$QC_SUMMARY" \
  "$MATCH_SCORE" \
  "$MISMATCH_PENALTY" \
  "$INSERTION_PENALTY" \
  "$DELETION_PENALTY" \
  "$MAX_DELETIONS_BEFORE_BASE" \
  "$MIN_PURITY" \
  "$MIN_REPEAT_BP"

gzip -t "$CALLS"

echo
echo "===== PERIODIC BASELINE QC ====="
column -ts $'\t' "$QC_SUMMARY"

echo
echo "===== MOST COMMON MOTIFS ====="
{
    head -n 1 "$MOTIF_SUMMARY"
    sed -n '2,31p' "$MOTIF_SUMMARY"
} |
column -ts $'\t'

echo
echo "===== 4. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    rows="$(gzip -cd "$CALLS" | awk 'END {print NR-1}')"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$CALLS")" \
      "$rows" \
      "$(stat -c '%s' "$CALLS")" \
      "$(sha256sum "$CALLS" | awk '{print $1}')" \
      "$CALLS"

    for path in \
      "$TOP_CALLS" \
      "$MOTIF_SUMMARY" \
      "$QC_SUMMARY" \
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
echo "$CALLS"
echo "$TOP_CALLS"
echo "$MOTIF_SUMMARY"
echo "$QC_SUMMARY"
echo "$MANIFEST"
