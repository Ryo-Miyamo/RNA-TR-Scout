#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
PARAMETER_SET_ID="rnatr_target_constrained_periodic_v0.3.2"

JOBS="$PROJECT_ROOT/results/11_motif_jobs/$RUN_ID/motif_scan_jobs.tsv.gz"
PROJECTION="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3/read_target_projection.v0.3.3.tsv.gz"
BASELINE="$PROJECT_ROOT/results/11_periodic_baseline/$RUN_ID/high_confidence_simple_periodic_calls.tsv.gz"
CANDIDATE_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_periodic_refinement/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_periodic_refinement/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_periodic_refinement/$RUN_ID"

CALLS="$OUTDIR/target_constrained_periodic_calls.tsv.gz"
TOP_CALLS="$OUTDIR/target_constrained_periodic_calls.top500.tsv"
EVIDENCE_SUMMARY="$OUTDIR/target_constrained_evidence_summary.tsv"
QC="$QCDIR/target_constrained_periodic_qc.tsv"
PARAMETERS="$OUTDIR/${PARAMETER_SET_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.target_constrained_periodic_manifest.tsv"

SCANNER="$WORKDIR/run_target_constrained_periodic.py"

MATCH_SCORE="${MATCH_SCORE:-3}"
MISMATCH_PENALTY="${MISMATCH_PENALTY:-4}"
INSERTION_PENALTY="${INSERTION_PENALTY:-4}"
DELETION_PENALTY="${DELETION_PENALTY:-4}"
MAX_DELETIONS_BEFORE_BASE="${MAX_DELETIONS_BEFORE_BASE:-1}"

MIN_PURITY="${MIN_PURITY:-0.70}"
MIN_REPEAT_BP="${MIN_REPEAT_BP:-12}"
SEARCH_MARGIN_BP="${SEARCH_MARGIN_BP:-30}"
CENSORED_END_TOLERANCE_BP="${CENSORED_END_TOLERANCE_BP:-10}"
MIN_TARGET_OVERLAP_FLOOR_BP="${MIN_TARGET_OVERLAP_FLOOR_BP:-6}"
PROGRESS_EVERY="${PROGRESS_EVERY:-5000}"

EXPECTED_SELECTED_JOBS=49793
EXPECTED_CANDIDATE_FASTQ_READS=79176
EXPECTED_PROJECTION_ROWS=388571
EXPECTED_BASELINE_CALLS=49793

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$JOBS" \
  "$PROJECTION" \
  "$BASELINE" \
  "$CANDIDATE_FASTQ"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
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
parameter_set_id	$PARAMETER_SET_ID	Target-constrained periodic refinement
selected_scan_strategy	SIMPLE_PERIODIC_SCAN	Single ACGT motifs of length <=20
selected_priorities	P0_DISEASE,P1_RANK1_EXACT_GEOMETRY	Same 49,793-job calibration cohort as baseline
match_score	$MATCH_SCORE	Periodic model match score
mismatch_penalty	$MISMATCH_PENALTY	Substitution penalty
insertion_penalty	$INSERTION_PENALTY	Read insertion penalty
deletion_penalty	$DELETION_PENALTY	Motif-position deletion penalty
max_deletions_before_base	$MAX_DELETIONS_BEFORE_BASE	Reduced from baseline 2 to 1
min_purity	$MIN_PURITY	Minimum tract purity
min_repeat_bp	$MIN_REPEAT_BP	Minimum observed raw-read tract length
search_margin_bp	$SEARCH_MARGIN_BP	Margin around a projectable target
censored_end_tolerance_bp	$CENSORED_END_TOLERANCE_BP	Maximum distance between tract and expected censored raw-read end
min_target_overlap_floor_bp	$MIN_TARGET_OVERLAP_FLOOR_BP	Minimum target overlap floor, limited by target length
repeat_units_primary	observed_raw_tract_bp_divided_by_motif_bp	Motif-path units remain diagnostic only
span_rule	both_flanks_plus_target_overlap	PASS motif tract and both projected flanks
censored_rule	one_genomic_flank_plus_target_overlap_plus_expected_raw_end	Reports a lower bound only
off_target_rule	no_final_evidence	Periodic tracts not overlapping the projected target are rejected
progress_every	$PROGRESS_EVERY	Print progress every N jobs
EOF

cat > "$SCANNER" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

import pysam

(
    jobs_path,
    projection_path,
    baseline_path,
    fastq_path,
    calls_path,
    top_calls_path,
    evidence_summary_path,
    qc_path,
    parameter_set_id,
    match_score_text,
    mismatch_penalty_text,
    insertion_penalty_text,
    deletion_penalty_text,
    max_deletions_text,
    min_purity_text,
    min_repeat_bp_text,
    search_margin_text,
    censored_tolerance_text,
    overlap_floor_text,
    progress_every_text,
    expected_jobs_text,
    expected_fastq_reads_text,
    expected_projection_rows_text,
    expected_baseline_calls_text,
) = sys.argv[1:]

MATCH_SCORE = int(match_score_text)
MISMATCH_PENALTY = int(mismatch_penalty_text)
INSERTION_PENALTY = int(insertion_penalty_text)
DELETION_PENALTY = int(deletion_penalty_text)
MAX_DELETIONS = int(max_deletions_text)

MIN_PURITY = float(min_purity_text)
MIN_REPEAT_BP = int(min_repeat_bp_text)
SEARCH_MARGIN = int(search_margin_text)
CENSORED_TOLERANCE = int(censored_tolerance_text)
OVERLAP_FLOOR = int(overlap_floor_text)
PROGRESS_EVERY = int(progress_every_text)

EXPECTED_JOBS = int(expected_jobs_text)
EXPECTED_FASTQ_READS = int(expected_fastq_reads_text)
EXPECTED_PROJECTION_ROWS = int(expected_projection_rows_text)
EXPECTED_BASELINE_CALLS = int(expected_baseline_calls_text)

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


def canonical_motif(sequence: str) -> str:
    sequence = sequence.upper()
    values = []

    for oriented in (sequence, reverse_complement(sequence)):
        for index in range(len(oriented)):
            values.append(oriented[index:] + oriented[:index])

    return min(values)


def interval_overlap(start_a, end_a, start_b, end_b):
    return max(0, min(end_a, end_b) - max(start_a, start_b))


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
        state.matches,
        state.motif_positions,
        -state.mismatches,
        -state.insertions,
        -state.deletions,
        -state.start,
    )


def call_rank(call: BestCall):
    return (
        call.score,
        call.matches,
        call.end - call.start,
        call.motif_positions,
        -call.mismatches,
        -call.insertions,
        -call.deletions,
        -call.start,
    )


def update(container, index, candidate):
    if candidate.score <= 0:
        return

    current = container[index]

    if current is None or state_rank(candidate) > state_rank(current):
        container[index] = candidate


def scan_orientation(sequence: str, motif: str):
    motif_length = len(motif)
    previous = [None] * motif_length
    best = None

    for sequence_index, base in enumerate(sequence):
        current = [None] * motif_length

        # Local starts at any cyclic phase.
        for motif_phase, expected in enumerate(motif):
            is_match = base == expected
            score = (
                MATCH_SCORE if is_match else -MISMATCH_PENALTY
            )

            if score > 0:
                next_phase = (motif_phase + 1) % motif_length
                update(
                    current,
                    next_phase,
                    State(
                        score=score,
                        start=sequence_index,
                        motif_positions=1,
                        matches=1 if is_match else 0,
                        mismatches=0 if is_match else 1,
                        insertions=0,
                        deletions=0,
                    ),
                )

        for expected_phase, state in enumerate(previous):
            if state is None:
                continue

            update(
                current,
                expected_phase,
                State(
                    score=state.score - INSERTION_PENALTY,
                    start=state.start,
                    motif_positions=state.motif_positions,
                    matches=state.matches,
                    mismatches=state.mismatches,
                    insertions=state.insertions + 1,
                    deletions=state.deletions,
                ),
            )

            for deleted in range(MAX_DELETIONS + 1):
                motif_phase = (
                    expected_phase + deleted
                ) % motif_length
                expected = motif[motif_phase]
                is_match = base == expected
                delta = (
                    MATCH_SCORE
                    if is_match
                    else -MISMATCH_PENALTY
                )
                delta -= deleted * DELETION_PENALTY

                update(
                    current,
                    (motif_phase + 1) % motif_length,
                    State(
                        score=state.score + delta,
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
                    ),
                )

        for ending_phase, state in enumerate(current):
            if state is None:
                continue

            candidate = BestCall(
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

            if best is None or call_rank(candidate) > call_rank(best):
                best = candidate

        previous = current

    return best


def scan_periodic(sequence: str, motif: str):
    orientations = [motif]
    reverse = reverse_complement(motif)

    if reverse != motif:
        orientations.append(reverse)

    best = None

    for orientation in orientations:
        candidate = scan_orientation(sequence, orientation)

        if candidate is None:
            continue

        if best is None or call_rank(candidate) > call_rank(best):
            best = candidate

    return best


def minimum_units(motif_length):
    return max(3, math.ceil(MIN_REPEAT_BP / motif_length))


def choose_search_interval(projection, read_length):
    target_start = projection["projected_start"]
    target_end = projection["projected_end"]
    geometry = projection["geometry_class"]
    strand = projection["strand"]

    if target_start is None or target_end is None:
        fallback_start = projection["window_start"]
        fallback_end = projection["window_end"]

        if fallback_start is None or fallback_end is None:
            return None, None, "NO_PROJECTED_TARGET"

        return (
            max(0, fallback_start),
            min(read_length, fallback_end),
            "FALLBACK_WINDOW_NO_PROJECTED_TARGET",
        )

    if geometry == "BOTH_FLANKS_PROJECTABLE":
        return (
            max(0, target_start - SEARCH_MARGIN),
            min(read_length, target_end + SEARCH_MARGIN),
            "TARGET_PLUS_MARGIN",
        )

    # Genomic-left flank anchored; genomic-right side is censored.
    if geometry in {
        "LEFT_FLANK_ONLY",
        "PROXIMAL_RIGHT_WITH_SOFTCLIP",
    }:
        if strand == "+":
            return (
                max(0, target_start - SEARCH_MARGIN),
                read_length,
                "TARGET_TO_RAW_END_FOR_GENOMIC_RIGHT",
            )

        return (
            0,
            min(read_length, target_end + SEARCH_MARGIN),
            "RAW_START_TO_TARGET_FOR_GENOMIC_RIGHT",
        )

    # Genomic-right flank anchored; genomic-left side is censored.
    if geometry in {
        "RIGHT_FLANK_ONLY",
        "PROXIMAL_LEFT_WITH_SOFTCLIP",
    }:
        if strand == "+":
            return (
                0,
                min(read_length, target_end + SEARCH_MARGIN),
                "RAW_START_TO_TARGET_FOR_GENOMIC_LEFT",
            )

        return (
            max(0, target_start - SEARCH_MARGIN),
            read_length,
            "TARGET_TO_RAW_END_FOR_GENOMIC_LEFT",
        )

    return (
        max(0, target_start - SEARCH_MARGIN),
        min(read_length, target_end + SEARCH_MARGIN),
        "TARGET_PLUS_MARGIN_LOW_ANCHOR",
    )


def expected_censored_raw_end(geometry, strand):
    if geometry in {
        "LEFT_FLANK_ONLY",
        "PROXIMAL_RIGHT_WITH_SOFTCLIP",
    }:
        return "RAW_END" if strand == "+" else "RAW_START"

    if geometry in {
        "RIGHT_FLANK_ONLY",
        "PROXIMAL_LEFT_WITH_SOFTCLIP",
    }:
        return "RAW_START" if strand == "+" else "RAW_END"

    return "."


# Load selected jobs.
jobs = {}

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

        if projection_id in jobs:
            raise RuntimeError(
                f"Duplicate selected job: {projection_id}"
            )

        motifs = row["canonical_motifs"].split(",")

        if len(motifs) != 1:
            raise RuntimeError(
                f"Simple job motif count != 1: {projection_id}"
            )

        row["_motif"] = motifs[0].upper()
        jobs[projection_id] = row

print(
    f"[INFO] selected jobs: {len(jobs):,}",
    file=sys.stderr,
    flush=True,
)

# Load selected projections.
projections = {}
projection_rows = 0

with gzip.open(
    projection_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        projection_rows += 1
        projection_id = row["projection_id"]

        if projection_id not in jobs:
            continue

        def optional_int(value):
            return None if value in {"", "."} else int(value)

        projections[projection_id] = {
            "read_id": row["read_id"],
            "strand": row["strand"],
            "geometry_class": row["geometry_class"],
            "projected_start": optional_int(
                row["projected_target_read_start"]
            ),
            "projected_end": optional_int(
                row["projected_target_read_end"]
            ),
            "window_start": optional_int(
                row["candidate_window_read_start"]
            ),
            "window_end": optional_int(
                row["candidate_window_read_end"]
            ),
            "left_anchor": int(row["genomic_left_anchor_bp"]),
            "right_anchor": int(row["genomic_right_anchor_bp"]),
            "mapq": int(row["best_mapq"]),
        }

# Load baseline for comparison.
baseline = {}
baseline_calls = 0

with gzip.open(
    baseline_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        baseline_calls += 1
        baseline[row["projection_id"]] = {
            "status": row["baseline_call_status"],
            "units": float(row["repeat_units_estimate"]),
            "tract_bp": int(row["tract_read_bp"]),
            "purity": float(row["purity"]),
        }

# Load full candidate reads.
reads = {}

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        reads[entry.name] = entry.sequence.upper()

print(
    f"[INFO] candidate FASTQ reads loaded: {len(reads):,}",
    file=sys.stderr,
    flush=True,
)

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
    "read_candidate_target_count",
    "scan_priority",
    "geometry_class",
    "potential_evidence_class",
    "strand",
    "best_mapq",
    "motif",
    "canonical_motif",
    "motif_length_bp",
    "read_length_bp",
    "projected_target_read_start",
    "projected_target_read_end",
    "projected_target_bp",
    "search_read_start",
    "search_read_end",
    "search_length_bp",
    "search_scope",
    "tract_read_start",
    "tract_read_end",
    "tract_read_bp",
    "target_overlap_bp",
    "minimum_required_target_overlap_bp",
    "target_coverage_fraction",
    "tract_overlap_fraction",
    "expected_censored_raw_end",
    "distance_to_expected_raw_end_bp",
    "repeat_units_observed_read",
    "repeat_units_motif_path",
    "motif_path_to_read_units_ratio",
    "matches",
    "mismatches",
    "insertions",
    "deletions",
    "purity",
    "edit_fraction",
    "score",
    "score_per_motif_position",
    "selected_orientation",
    "ending_phase",
    "minimum_required_units",
    "minimum_required_repeat_bp",
    "minimum_required_purity",
    "motif_tract_status",
    "evidence_class",
    "sizing_status",
    "repeat_bp_estimate",
    "repeat_bp_lower_bound",
    "confidence_label",
    "baseline_status",
    "baseline_repeat_units",
    "baseline_tract_bp",
    "baseline_purity",
    "refinement_flags",
]

counts = Counter()
rows = []
start_time = time.time()

for index, projection_id in enumerate(sorted(jobs), start=1):
    job = jobs[projection_id]
    projection = projections.get(projection_id)
    baseline_row = baseline.get(projection_id)

    if projection is None:
        raise RuntimeError(
            f"Missing selected projection: {projection_id}"
        )
    if baseline_row is None:
        raise RuntimeError(
            f"Missing baseline call: {projection_id}"
        )

    read_id = projection["read_id"]
    sequence = reads.get(read_id)

    if sequence is None:
        raise RuntimeError(f"Missing FASTQ read: {read_id}")

    read_length = len(sequence)
    motif = job["_motif"]
    motif_length = len(motif)

    search_start, search_end, search_scope = (
        choose_search_interval(projection, read_length)
    )

    flags = []

    if search_start is None or search_end is None:
        search_start = 0
        search_end = 0
        search_sequence = ""
        flags.append("NO_SEARCH_INTERVAL")
    else:
        search_start = max(0, min(search_start, read_length))
        search_end = max(
            search_start,
            min(search_end, read_length),
        )
        search_sequence = sequence[search_start:search_end]

    call = (
        scan_periodic(search_sequence, motif)
        if search_sequence else None
    )

    target_start = projection["projected_start"]
    target_end = projection["projected_end"]
    target_bp = (
        target_end - target_start
        if target_start is not None and target_end is not None
        else None
    )

    if call is None:
        tract_start = None
        tract_end = None
        tract_bp = 0
        motif_positions = 0
        observed_units = 0.0
        path_units = 0.0
        inflation = 0.0
        matches = 0
        mismatches = 0
        insertions = 0
        deletions = 0
        purity = 0.0
        edit_fraction = 1.0
        score = 0
        score_density = 0.0
        orientation = "."
        ending_phase = "."
    else:
        tract_start = search_start + call.start
        tract_end = search_start + call.end
        tract_bp = tract_end - tract_start
        motif_positions = call.motif_positions
        observed_units = tract_bp / motif_length
        path_units = motif_positions / motif_length
        inflation = (
            path_units / observed_units
            if observed_units > 0 else 0.0
        )
        matches = call.matches
        mismatches = call.mismatches
        insertions = call.insertions
        deletions = call.deletions
        denominator = (
            matches + mismatches + insertions + deletions
        )
        purity = matches / denominator if denominator else 0.0
        edit_fraction = (
            (mismatches + insertions + deletions) / denominator
            if denominator else 1.0
        )
        score = call.score
        score_density = (
            score / motif_positions
            if motif_positions else 0.0
        )
        orientation = call.orientation
        ending_phase = call.ending_phase

    if (
        tract_start is not None
        and target_start is not None
        and target_end is not None
    ):
        target_overlap = interval_overlap(
            tract_start,
            tract_end,
            target_start,
            target_end,
        )
        required_overlap = min(
            target_bp,
            max(OVERLAP_FLOOR, 2 * motif_length),
        )
        target_coverage = (
            target_overlap / target_bp
            if target_bp > 0 else 0.0
        )
        tract_overlap = (
            target_overlap / tract_bp
            if tract_bp > 0 else 0.0
        )
    else:
        target_overlap = 0
        required_overlap = None
        target_coverage = None
        tract_overlap = None

    required_units = minimum_units(motif_length)

    quality_pass = (
        call is not None
        and tract_bp >= MIN_REPEAT_BP
        and observed_units >= required_units
        and purity >= MIN_PURITY
        and required_overlap is not None
        and target_overlap >= required_overlap
    )

    if tract_bp < MIN_REPEAT_BP:
        flags.append("BELOW_MINIMUM_REPEAT_BP")
    if observed_units < required_units:
        flags.append("BELOW_MINIMUM_UNITS")
    if purity < MIN_PURITY:
        flags.append("BELOW_MINIMUM_PURITY")
    if required_overlap is None:
        flags.append("NO_PROJECTED_TARGET_INTERVAL")
    elif target_overlap < required_overlap:
        flags.append("INSUFFICIENT_TARGET_OVERLAP")
    if inflation > 1.25:
        flags.append("MOTIF_PATH_UNIT_INFLATION_GT_1_25")

    geometry = projection["geometry_class"]
    strand = projection["strand"]
    censored_end = expected_censored_raw_end(geometry, strand)

    if tract_start is None:
        distance_to_end = None
    elif censored_end == "RAW_START":
        distance_to_end = tract_start
    elif censored_end == "RAW_END":
        distance_to_end = read_length - tract_end
    else:
        distance_to_end = None

    evidence_class = "UNRESOLVED"
    sizing_status = "no_call"
    repeat_bp_estimate = None
    repeat_bp_lower_bound = None
    confidence = "LOW"

    if quality_pass and geometry == "BOTH_FLANKS_PROJECTABLE":
        evidence_class = "SPAN"
        sizing_status = "exact_span"
        repeat_bp_estimate = tract_bp
        confidence = (
            "HIGH"
            if (
                int(job["read_candidate_target_count"]) == 1
                and projection["mapq"] >= 20
            )
            else "MEDIUM"
        )

    elif (
        quality_pass
        and geometry
        in {
            "LEFT_FLANK_ONLY",
            "PROXIMAL_RIGHT_WITH_SOFTCLIP",
        }
        and distance_to_end is not None
        and distance_to_end <= CENSORED_TOLERANCE
    ):
        evidence_class = "LEFT_ANCHORED_CENSORED_RIGHT"
        sizing_status = "lower_bound"
        repeat_bp_lower_bound = tract_bp
        confidence = "MEDIUM"

    elif (
        quality_pass
        and geometry
        in {
            "RIGHT_FLANK_ONLY",
            "PROXIMAL_LEFT_WITH_SOFTCLIP",
        }
        and distance_to_end is not None
        and distance_to_end <= CENSORED_TOLERANCE
    ):
        evidence_class = "RIGHT_ANCHORED_CENSORED_LEFT"
        sizing_status = "lower_bound"
        repeat_bp_lower_bound = tract_bp
        confidence = "MEDIUM"

    elif quality_pass and geometry == "TARGET_INTERNAL_NO_FLANK":
        evidence_class = "REPEAT_ONLY_UNANCHORED"
        sizing_status = "no_call"
        confidence = "LOW"

    elif geometry == "BOTH_FLANKS_PROJECTABLE":
        evidence_class = "FLANKS_WITHOUT_REPEAT"
        sizing_status = "no_call"
        confidence = "LOW"

    if (
        quality_pass
        and censored_end != "."
        and (
            distance_to_end is None
            or distance_to_end > CENSORED_TOLERANCE
        )
    ):
        flags.append("TRACT_NOT_TOUCHING_EXPECTED_CENSORED_END")

    motif_tract_status = (
        "PASS" if quality_pass else "LOW_CONFIDENCE"
    )

    if int(job["read_candidate_target_count"]) > 1:
        flags.append("MULTIPLE_TARGET_CANDIDATES")

    if job["scan_priority"] == "P0_DISEASE":
        flags.append("KNOWN_DISEASE_REGION")

    row = {
        "schema_version": "0.3.0",
        "parameter_set_id": parameter_set_id,
        "projection_id": projection_id,
        "read_id": read_id,
        "target_region_id": job["target_region_id"],
        "target_source": job["target_source"],
        "region_type": job["region_type"],
        "representative_locus_id": job[
            "representative_locus_id"
        ],
        "assignment_rank": job["assignment_rank"],
        "read_candidate_target_count": job[
            "read_candidate_target_count"
        ],
        "scan_priority": job["scan_priority"],
        "geometry_class": geometry,
        "potential_evidence_class": job[
            "potential_evidence_class"
        ],
        "strand": strand,
        "best_mapq": projection["mapq"],
        "motif": motif,
        "canonical_motif": canonical_motif(motif),
        "motif_length_bp": motif_length,
        "read_length_bp": read_length,
        "projected_target_read_start": (
            "." if target_start is None else target_start
        ),
        "projected_target_read_end": (
            "." if target_end is None else target_end
        ),
        "projected_target_bp": (
            "." if target_bp is None else target_bp
        ),
        "search_read_start": search_start,
        "search_read_end": search_end,
        "search_length_bp": search_end - search_start,
        "search_scope": search_scope,
        "tract_read_start": (
            "." if tract_start is None else tract_start
        ),
        "tract_read_end": (
            "." if tract_end is None else tract_end
        ),
        "tract_read_bp": tract_bp,
        "target_overlap_bp": target_overlap,
        "minimum_required_target_overlap_bp": (
            "." if required_overlap is None else required_overlap
        ),
        "target_coverage_fraction": (
            "."
            if target_coverage is None
            else f"{target_coverage:.6f}"
        ),
        "tract_overlap_fraction": (
            "."
            if tract_overlap is None
            else f"{tract_overlap:.6f}"
        ),
        "expected_censored_raw_end": censored_end,
        "distance_to_expected_raw_end_bp": (
            "." if distance_to_end is None else distance_to_end
        ),
        "repeat_units_observed_read": f"{observed_units:.6f}",
        "repeat_units_motif_path": f"{path_units:.6f}",
        "motif_path_to_read_units_ratio": f"{inflation:.6f}",
        "matches": matches,
        "mismatches": mismatches,
        "insertions": insertions,
        "deletions": deletions,
        "purity": f"{purity:.6f}",
        "edit_fraction": f"{edit_fraction:.6f}",
        "score": score,
        "score_per_motif_position": f"{score_density:.6f}",
        "selected_orientation": orientation,
        "ending_phase": ending_phase,
        "minimum_required_units": required_units,
        "minimum_required_repeat_bp": MIN_REPEAT_BP,
        "minimum_required_purity": f"{MIN_PURITY:.6f}",
        "motif_tract_status": motif_tract_status,
        "evidence_class": evidence_class,
        "sizing_status": sizing_status,
        "repeat_bp_estimate": (
            "."
            if repeat_bp_estimate is None
            else repeat_bp_estimate
        ),
        "repeat_bp_lower_bound": (
            "."
            if repeat_bp_lower_bound is None
            else repeat_bp_lower_bound
        ),
        "confidence_label": confidence,
        "baseline_status": baseline_row["status"],
        "baseline_repeat_units": (
            f"{baseline_row['units']:.6f}"
        ),
        "baseline_tract_bp": baseline_row["tract_bp"],
        "baseline_purity": f"{baseline_row['purity']:.6f}",
        "refinement_flags": (
            ";".join(sorted(set(flags))) if flags else "."
        ),
    }
    rows.append(row)

    counts[f"motif_tract_status::{motif_tract_status}"] += 1
    counts[f"evidence_class::{evidence_class}"] += 1
    counts[f"sizing_status::{sizing_status}"] += 1
    counts[f"confidence::{confidence}"] += 1
    counts[f"geometry::{geometry}"] += 1
    counts[f"search_scope::{search_scope}"] += 1
    counts[
        f"baseline_to_refined::{baseline_row['status']}"
        f"->{motif_tract_status}"
    ] += 1

    for flag in set(flags):
        counts[f"flag::{flag}"] += 1

    if (
        baseline_row["status"] == "PASS"
        and motif_tract_status != "PASS"
    ):
        counts["baseline_pass_rejected_by_refinement"] += 1

    if (
        baseline_row["status"] == "LOW_CONFIDENCE"
        and motif_tract_status == "PASS"
    ):
        counts["baseline_low_confidence_rescued"] += 1

    if index % PROGRESS_EVERY == 0 or index == len(jobs):
        elapsed = time.time() - start_time
        rate = index / elapsed if elapsed > 0 else 0.0
        remaining = (
            (len(jobs) - index) / rate
            if rate > 0 else 0.0
        )
        print(
            f"[INFO] refined {index:,}/{len(jobs):,} "
            f"jobs; {rate:.1f} jobs/s; "
            f"ETA {remaining / 60:.1f} min",
            file=sys.stderr,
            flush=True,
        )

status = "PASS"

if (
    len(jobs) != EXPECTED_JOBS
    or len(projections) != EXPECTED_JOBS
    or len(baseline) != EXPECTED_BASELINE_CALLS
    or len(reads) != EXPECTED_FASTQ_READS
    or projection_rows != EXPECTED_PROJECTION_ROWS
    or len(rows) != EXPECTED_JOBS
):
    status = "REVIEW"

with gzip.open(
    calls_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=call_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

# Top evidence candidates: exact SPAN first, then censored lower bounds.
evidence_rank = {
    "SPAN": 3,
    "LEFT_ANCHORED_CENSORED_RIGHT": 2,
    "RIGHT_ANCHORED_CENSORED_LEFT": 2,
    "REPEAT_ONLY_UNANCHORED": 1,
    "FLANKS_WITHOUT_REPEAT": 0,
    "UNRESOLVED": 0,
}

top_rows = sorted(
    rows,
    key=lambda row: (
        evidence_rank[row["evidence_class"]],
        (
            int(row["repeat_bp_estimate"])
            if row["repeat_bp_estimate"] != "."
            else int(row["repeat_bp_lower_bound"])
            if row["repeat_bp_lower_bound"] != "."
            else int(row["tract_read_bp"])
        ),
        float(row["purity"]),
        int(row["best_mapq"]),
    ),
    reverse=True,
)[:500]

with open(
    top_calls_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=call_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(top_rows)

summary_columns = [
    "evidence_class",
    "rows",
    "unique_reads",
    "unique_targets",
    "tract_bp_median",
    "tract_bp_p95",
    "tract_bp_max",
    "purity_median",
]

summary_data = defaultdict(
    lambda: {
        "rows": 0,
        "reads": set(),
        "targets": set(),
        "tract_bp": [],
        "purity": [],
    }
)

for row in rows:
    record = summary_data[row["evidence_class"]]
    record["rows"] += 1
    record["reads"].add(row["read_id"])
    record["targets"].add(
        (row["target_source"], row["target_region_id"])
    )
    record["tract_bp"].append(int(row["tract_read_bp"]))
    record["purity"].append(float(row["purity"]))

with open(
    evidence_summary_path,
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

    for evidence_class in sorted(summary_data):
        record = summary_data[evidence_class]
        writer.writerow(
            {
                "evidence_class": evidence_class,
                "rows": record["rows"],
                "unique_reads": len(record["reads"]),
                "unique_targets": len(record["targets"]),
                "tract_bp_median": (
                    f"{quantile(record['tract_bp'], 0.5):.6f}"
                ),
                "tract_bp_p95": (
                    f"{quantile(record['tract_bp'], 0.95):.6f}"
                ),
                "tract_bp_max": max(record["tract_bp"]),
                "purity_median": (
                    f"{quantile(record['purity'], 0.5):.6f}"
                ),
            }
        )

numeric_values = {
    "observed_units": [
        float(row["repeat_units_observed_read"])
        for row in rows
    ],
    "purity": [float(row["purity"]) for row in rows],
    "tract_bp": [int(row["tract_read_bp"]) for row in rows],
    "target_overlap_bp": [
        int(row["target_overlap_bp"]) for row in rows
    ],
    "unit_inflation": [
        float(row["motif_path_to_read_units_ratio"])
        for row in rows
    ],
}

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(f"expected_selected_jobs\t{EXPECTED_JOBS}\n")
    handle.write(f"selected_jobs\t{len(jobs)}\n")
    handle.write(
        f"selected_projection_rows\t{len(projections)}\n"
    )
    handle.write(
        f"candidate_fastq_reads_loaded\t{len(reads)}\n"
    )
    handle.write(
        f"baseline_calls_loaded\t{len(baseline)}\n"
    )
    handle.write(
        f"refined_calls_written\t{len(rows)}\n"
    )

    for key, value in sorted(counts.items()):
        handle.write(f"{key}\t{value}\n")

    for metric_name, values in numeric_values.items():
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
        "Target-constrained periodic refinement requires review"
    )
PY

echo "===== 1. INPUT INTEGRITY ====="

gzip -t "$JOBS"
gzip -t "$PROJECTION"
gzip -t "$BASELINE"
gzip -t "$CANDIDATE_FASTQ"

echo "Inputs: PASS"

echo
echo "===== 2. PARAMETERS ====="
column -ts $'\t' "$PARAMETERS"

echo
echo "===== 3. TARGET-CONSTRAINED PERIODIC REFINEMENT ====="

rm -f \
  "$CALLS" \
  "$TOP_CALLS" \
  "$EVIDENCE_SUMMARY" \
  "$QC" \
  "$MANIFEST"

python "$SCANNER" \
  "$JOBS" \
  "$PROJECTION" \
  "$BASELINE" \
  "$CANDIDATE_FASTQ" \
  "$CALLS" \
  "$TOP_CALLS" \
  "$EVIDENCE_SUMMARY" \
  "$QC" \
  "$PARAMETER_SET_ID" \
  "$MATCH_SCORE" \
  "$MISMATCH_PENALTY" \
  "$INSERTION_PENALTY" \
  "$DELETION_PENALTY" \
  "$MAX_DELETIONS_BEFORE_BASE" \
  "$MIN_PURITY" \
  "$MIN_REPEAT_BP" \
  "$SEARCH_MARGIN_BP" \
  "$CENSORED_END_TOLERANCE_BP" \
  "$MIN_TARGET_OVERLAP_FLOOR_BP" \
  "$PROGRESS_EVERY" \
  "$EXPECTED_SELECTED_JOBS" \
  "$EXPECTED_CANDIDATE_FASTQ_READS" \
  "$EXPECTED_PROJECTION_ROWS" \
  "$EXPECTED_BASELINE_CALLS"

gzip -t "$CALLS"

echo
echo "===== TARGET-CONSTRAINED QC ====="
column -ts $'\t' "$QC"

echo
echo "===== EVIDENCE SUMMARY ====="
column -ts $'\t' "$EVIDENCE_SUMMARY"

echo
echo "===== TOP 20 REFINED EVIDENCE ROWS ====="
column -ts $'\t' "$TOP_CALLS" | head -n 21

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
      "$EVIDENCE_SUMMARY" \
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
echo "$CALLS"
echo "$TOP_CALLS"
echo "$EVIDENCE_SUMMARY"
echo "$QC"
echo "$MANIFEST"
