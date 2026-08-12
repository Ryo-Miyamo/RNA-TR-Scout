#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
PARAMETER_SET_ID="rnatr_p2_alternate_exact_simple_periodic_v0.3.1"

JOBS="$PROJECT_ROOT/results/11_motif_jobs/$RUN_ID/motif_scan_jobs.tsv.gz"
PROJECTION="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3/read_target_projection.v0.3.3.tsv.gz"
CANDIDATE_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_p2_periodic/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p2_periodic/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p2_periodic/$RUN_ID"

EVIDENCE="$OUTDIR/p2_alternate_exact_simple_periodic_evidence.tsv.gz"
TOP="$OUTDIR/p2_alternate_exact_simple_periodic_evidence.top500.tsv"
SUMMARY="$OUTDIR/p2_alternate_exact_simple_periodic_summary.tsv"
QC="$QCDIR/p2_alternate_exact_simple_periodic_qc.tsv"
PARAMETERS="$OUTDIR/${PARAMETER_SET_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p2_alternate_exact_simple_periodic.manifest.tsv"

SCANNER="$WORKDIR/run_p2_alternate_exact_periodic.py"

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

EXPECTED_JOB_ROWS=388571
EXPECTED_PROJECTION_ROWS=388571
EXPECTED_FASTQ_READS=79176

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$JOBS" "$PROJECTION" "$CANDIDATE_FASTQ"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
parameter_set_id	$PARAMETER_SET_ID	P2 alternate exact-target periodic analysis
selected_scan_strategy	SIMPLE_PERIODIC_SCAN	Single ACGT motif length <=20
selected_priority	P2_OTHER_EXACT	Exact-overlap alternate target hypotheses
assignment_status	alternate_exact_target	Sequence evidence does not resolve locus assignment
assignment_confidence	LOW	P2 rows cannot become uniquely assigned in this step
span_size_rule	projected_interval_between_both_flanks	Exact size for BOTH_FLANKS_PROJECTABLE
span_sequence_rule	global_periodicity_over_full_projected_interval	No local extension into flanks
one_flank_rule	target_constrained_local_scan_to_expected_raw_end	Distinguishes censored from internal one-flank evidence
match_score	$MATCH_SCORE	Periodic match score
mismatch_penalty	$MISMATCH_PENALTY	Substitution penalty
insertion_penalty	$INSERTION_PENALTY	Read insertion penalty
deletion_penalty	$DELETION_PENALTY	Motif deletion penalty
max_deletions_before_base	$MAX_DELETIONS_BEFORE_BASE	Maximum skipped motif positions
min_purity	$MIN_PURITY	Minimum local/global periodic purity
min_repeat_bp	$MIN_REPEAT_BP	Minimum tract length except exact short SPAN
search_margin_bp	$SEARCH_MARGIN_BP	Margin around projected target
censored_end_tolerance_bp	$CENSORED_END_TOLERANCE_BP	Maximum distance from expected raw-read end
min_target_overlap_floor_bp	$MIN_TARGET_OVERLAP_FLOOR_BP	Target overlap floor
call_semantics	alternate_hypothesis_not_expansion	No pathological expansion inference
progress_every	$PROGRESS_EVERY	Print progress every N jobs
EOF

cat > "$SCANNER" <<'PY'
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
    jobs_path,
    projection_path,
    fastq_path,
    evidence_path,
    top_path,
    summary_path,
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
    expected_job_rows_text,
    expected_projection_rows_text,
    expected_fastq_reads_text,
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

EXPECTED_JOB_ROWS = int(expected_job_rows_text)
EXPECTED_PROJECTION_ROWS = int(expected_projection_rows_text)
EXPECTED_FASTQ_READS = int(expected_fastq_reads_text)

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


def canonical_motif(sequence: str) -> str:
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
    starting_phase: int


@dataclass(frozen=True)
class Call:
    score: int
    start: int
    end: int
    motif_positions: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    orientation: str
    starting_phase: int
    ending_phase: int


def state_rank(state):
    return (
        state.score,
        state.matches,
        state.motif_positions,
        -state.mismatches,
        -state.insertions,
        -state.deletions,
        -state.start,
        -state.starting_phase,
    )


def call_rank(call):
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


def update(container, index, candidate, local):
    if local and candidate.score <= 0:
        return
    current = container[index]
    if current is None or state_rank(candidate) > state_rank(current):
        container[index] = candidate


def align_periodic_orientation(sequence, motif, local):
    motif_length = len(motif)

    if local:
        previous = [None] * motif_length
    else:
        previous = [
            State(
                score=0,
                start=0,
                motif_positions=0,
                matches=0,
                mismatches=0,
                insertions=0,
                deletions=0,
                starting_phase=phase,
            )
            for phase in range(motif_length)
        ]

    best = None

    for sequence_index, base in enumerate(sequence):
        current = [None] * motif_length

        if local:
            for phase, expected in enumerate(motif):
                if base == expected:
                    update(
                        current,
                        (phase + 1) % motif_length,
                        State(
                            score=MATCH_SCORE,
                            start=sequence_index,
                            motif_positions=1,
                            matches=1,
                            mismatches=0,
                            insertions=0,
                            deletions=0,
                            starting_phase=phase,
                        ),
                        True,
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
                    starting_phase=state.starting_phase,
                ),
                local,
            )

            for deleted in range(MAX_DELETIONS + 1):
                phase = (expected_phase + deleted) % motif_length
                is_match = base == motif[phase]
                delta = (
                    MATCH_SCORE
                    if is_match
                    else -MISMATCH_PENALTY
                )
                delta -= deleted * DELETION_PENALTY

                update(
                    current,
                    (phase + 1) % motif_length,
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
                        starting_phase=state.starting_phase,
                    ),
                    local,
                )

        for ending_phase, state in enumerate(current):
            if state is None:
                continue

            candidate = Call(
                score=state.score,
                start=state.start,
                end=sequence_index + 1,
                motif_positions=state.motif_positions,
                matches=state.matches,
                mismatches=state.mismatches,
                insertions=state.insertions,
                deletions=state.deletions,
                orientation=motif,
                starting_phase=state.starting_phase,
                ending_phase=ending_phase,
            )

            if best is None or call_rank(candidate) > call_rank(best):
                best = candidate

        previous = current

    return best


def align_periodic(sequence, motif, local):
    orientations = [motif]
    rc = reverse_complement(motif)
    if rc != motif:
        orientations.append(rc)

    best = None
    for orientation in orientations:
        candidate = align_periodic_orientation(
            sequence,
            orientation,
            local,
        )
        if candidate is None:
            continue
        if best is None or call_rank(candidate) > call_rank(best):
            best = candidate
    return best


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


def one_flank_search_interval(
    geometry,
    strand,
    target_start,
    target_end,
    read_length,
):
    if geometry in {
        "LEFT_FLANK_ONLY",
        "PROXIMAL_RIGHT_WITH_SOFTCLIP",
    }:
        if strand == "+":
            return (
                max(0, target_start - SEARCH_MARGIN),
                read_length,
            )
        return (
            0,
            min(read_length, target_end + SEARCH_MARGIN),
        )

    if geometry in {
        "RIGHT_FLANK_ONLY",
        "PROXIMAL_LEFT_WITH_SOFTCLIP",
    }:
        if strand == "+":
            return (
                0,
                min(read_length, target_end + SEARCH_MARGIN),
            )
        return (
            max(0, target_start - SEARCH_MARGIN),
            read_length,
        )

    return (
        max(0, target_start - SEARCH_MARGIN),
        min(read_length, target_end + SEARCH_MARGIN),
    )


# Select P2 simple-periodic jobs.
jobs = {}
job_rows = 0

with gzip.open(
    jobs_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        job_rows += 1

        if row["scan_priority"] != "P2_OTHER_EXACT":
            continue
        if row["scan_strategy"] != "SIMPLE_PERIODIC_SCAN":
            continue
        if row["motif_scan_eligible"] != "true":
            continue

        projection_id = row["projection_id"]
        motifs = row["canonical_motifs"].split(",")

        if len(motifs) != 1:
            raise RuntimeError(
                f"P2 simple job has motif count != 1: {projection_id}"
            )

        motif = motifs[0].upper()
        if not motif or not set(motif).issubset(set("ACGT")):
            raise RuntimeError(
                f"Invalid P2 simple motif: {projection_id}, {motif}"
            )

        row["_motif"] = motif
        jobs[projection_id] = row

print(
    f"[INFO] selected P2 simple jobs: {len(jobs):,}",
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
            "mapq": int(row["best_mapq"]),
        }

# Load candidate reads.
reads = {}

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        reads[entry.name] = entry.sequence.upper()

print(
    f"[INFO] candidate FASTQ reads loaded: {len(reads):,}",
    file=sys.stderr,
    flush=True,
)

columns = [
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
    "candidate_basis",
    "assignment_status",
    "assignment_confidence_label",
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
    "tract_read_start",
    "tract_read_end",
    "tract_read_bp",
    "target_overlap_bp",
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
    "selected_orientation",
    "starting_phase",
    "ending_phase",
    "motif_tract_status",
    "evidence_class",
    "sizing_status",
    "repeat_bp_estimate",
    "repeat_bp_lower_bound",
    "span_sequence_status",
    "sequence_review_required",
    "sequence_confidence_label",
    "final_confidence_label",
    "evidence_flags",
]

counts = Counter()
rows = []
missing_projections = set(jobs) - set(projections)
missing_reads = set()
start_time = time.time()

for index, projection_id in enumerate(sorted(jobs), start=1):
    job = jobs[projection_id]
    projection = projections.get(projection_id)

    if projection is None:
        continue

    read_id = projection["read_id"]
    sequence = reads.get(read_id)

    if sequence is None:
        missing_reads.add(read_id)
        continue

    motif = job["_motif"]
    motif_length = len(motif)
    read_length = len(sequence)
    geometry = projection["geometry_class"]
    strand = projection["strand"]
    target_start = projection["projected_start"]
    target_end = projection["projected_end"]
    target_bp = (
        target_end - target_start
        if target_start is not None and target_end is not None
        else None
    )

    evidence_class = "UNRESOLVED"
    sizing_status = "no_call"
    repeat_bp_estimate = None
    repeat_bp_lower_bound = None
    span_sequence_status = "NOT_APPLICABLE"
    sequence_review_required = False
    sequence_confidence = "LOW"
    flags = ["ALTERNATE_TARGET_HYPOTHESIS"]

    search_start = None
    search_end = None
    tract_start = None
    tract_end = None
    tract_bp = 0
    target_overlap = 0
    target_coverage = None
    tract_overlap = None
    censored_end = "."
    distance_to_end = None
    observed_units = 0.0
    path_units = 0.0
    path_ratio = 0.0
    matches = 0
    mismatches = 0
    insertions = 0
    deletions = 0
    purity = 0.0
    edit_fraction = 1.0
    score = 0
    selected_orientation = "."
    starting_phase = "."
    ending_phase = "."
    motif_tract_status = "LOW_CONFIDENCE"

    if (
        geometry == "BOTH_FLANKS_PROJECTABLE"
        and target_start is not None
        and target_end is not None
        and target_end > target_start
    ):
        search_start = target_start
        search_end = target_end
        target_sequence = sequence[target_start:target_end]
        call = align_periodic(target_sequence, motif, local=False)

        tract_start = target_start
        tract_end = target_end
        tract_bp = target_bp
        target_overlap = target_bp
        target_coverage = 1.0
        tract_overlap = 1.0
        observed_units = tract_bp / motif_length
        path_units = call.motif_positions / motif_length
        path_ratio = (
            path_units / observed_units
            if observed_units else 0.0
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
        selected_orientation = call.orientation
        starting_phase = call.starting_phase
        ending_phase = call.ending_phase

        evidence_class = "SPAN"
        sizing_status = "exact_span"
        repeat_bp_estimate = tract_bp

        if tract_bp < MIN_REPEAT_BP:
            span_sequence_status = "SHORT_EXACT_SPAN"
            motif_tract_status = "PASS"
            sequence_confidence = "MEDIUM"
            flags.append("SHORT_EXACT_SPAN_LT_12_BP")

        elif purity >= MIN_PURITY:
            span_sequence_status = "PERIODIC_EXACT_SPAN"
            motif_tract_status = "PASS"
            sequence_confidence = (
                "HIGH" if projection["mapq"] >= 20 else "MEDIUM"
            )

        else:
            span_sequence_status = (
                "COMPLEX_OR_LOW_PERIODICITY_EXACT_SPAN"
            )
            motif_tract_status = "LOW_CONFIDENCE"
            sequence_review_required = True
            sequence_confidence = "MEDIUM"
            flags.append("SEQUENCE_LEVEL_REVIEW_REQUIRED")

    elif (
        geometry
        in {
            "LEFT_FLANK_ONLY",
            "RIGHT_FLANK_ONLY",
            "PROXIMAL_RIGHT_WITH_SOFTCLIP",
            "PROXIMAL_LEFT_WITH_SOFTCLIP",
        }
        and target_start is not None
        and target_end is not None
        and target_end > target_start
    ):
        search_start, search_end = one_flank_search_interval(
            geometry,
            strand,
            target_start,
            target_end,
            read_length,
        )
        subsequence = sequence[search_start:search_end]
        call = align_periodic(subsequence, motif, local=True)

        if call is not None:
            tract_start = search_start + call.start
            tract_end = search_start + call.end
            tract_bp = tract_end - tract_start
            observed_units = tract_bp / motif_length
            path_units = call.motif_positions / motif_length
            path_ratio = (
                path_units / observed_units
                if observed_units else 0.0
            )
            matches = call.matches
            mismatches = call.mismatches
            insertions = call.insertions
            deletions = call.deletions
            denominator = (
                matches + mismatches + insertions + deletions
            )
            purity = (
                matches / denominator
                if denominator else 0.0
            )
            edit_fraction = (
                (mismatches + insertions + deletions) / denominator
                if denominator else 1.0
            )
            score = call.score
            selected_orientation = call.orientation
            starting_phase = call.starting_phase
            ending_phase = call.ending_phase

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
            target_coverage = target_overlap / target_bp
            tract_overlap = (
                target_overlap / tract_bp
                if tract_bp else 0.0
            )

            required_units = max(
                3,
                math.ceil(MIN_REPEAT_BP / motif_length),
            )
            quality_pass = (
                tract_bp >= MIN_REPEAT_BP
                and observed_units >= required_units
                and purity >= MIN_PURITY
                and target_overlap >= required_overlap
            )

            censored_end = expected_censored_raw_end(
                geometry,
                strand,
            )

            if censored_end == "RAW_START":
                distance_to_end = tract_start
            elif censored_end == "RAW_END":
                distance_to_end = read_length - tract_end

            if quality_pass:
                motif_tract_status = "PASS"

                if (
                    distance_to_end is not None
                    and distance_to_end <= CENSORED_TOLERANCE
                ):
                    if geometry in {
                        "LEFT_FLANK_ONLY",
                        "PROXIMAL_RIGHT_WITH_SOFTCLIP",
                    }:
                        evidence_class = (
                            "LEFT_ANCHORED_CENSORED_RIGHT"
                        )
                    else:
                        evidence_class = (
                            "RIGHT_ANCHORED_CENSORED_LEFT"
                        )

                    sizing_status = "lower_bound"
                    repeat_bp_lower_bound = tract_bp
                    sequence_confidence = "MEDIUM"

                else:
                    if geometry in {
                        "LEFT_FLANK_ONLY",
                        "PROXIMAL_RIGHT_WITH_SOFTCLIP",
                    }:
                        evidence_class = "LEFT_ONLY_INTERNAL"
                    else:
                        evidence_class = "RIGHT_ONLY_INTERNAL"

                    sizing_status = "partial_internal"
                    sequence_confidence = "LOW"
            else:
                flags.append("MOTIF_TRACT_CRITERIA_NOT_MET")

    elif (
        geometry == "TARGET_INTERNAL_NO_FLANK"
        and target_start is not None
        and target_end is not None
    ):
        search_start = max(0, target_start - SEARCH_MARGIN)
        search_end = min(read_length, target_end + SEARCH_MARGIN)
        call = align_periodic(
            sequence[search_start:search_end],
            motif,
            local=True,
        )

        if call is not None:
            tract_start = search_start + call.start
            tract_end = search_start + call.end
            tract_bp = tract_end - tract_start
            observed_units = tract_bp / motif_length
            path_units = call.motif_positions / motif_length
            path_ratio = (
                path_units / observed_units
                if observed_units else 0.0
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
            selected_orientation = call.orientation
            starting_phase = call.starting_phase
            ending_phase = call.ending_phase
            target_overlap = interval_overlap(
                tract_start,
                tract_end,
                target_start,
                target_end,
            )
            target_coverage = target_overlap / target_bp
            tract_overlap = (
                target_overlap / tract_bp
                if tract_bp else 0.0
            )
            required_overlap = min(
                target_bp,
                max(OVERLAP_FLOOR, 2 * motif_length),
            )
            required_units = max(
                3,
                math.ceil(MIN_REPEAT_BP / motif_length),
            )

            if (
                tract_bp >= MIN_REPEAT_BP
                and observed_units >= required_units
                and purity >= MIN_PURITY
                and target_overlap >= required_overlap
            ):
                motif_tract_status = "PASS"
                evidence_class = "REPEAT_ONLY_UNANCHORED"
                sequence_confidence = "LOW"
                flags.append("LOCUS_ASSIGNMENT_WEAK")

    elif geometry == "FLANKS_WITHOUT_QUERY_TARGET":
        evidence_class = "FLANKS_WITHOUT_REPEAT"
        flags.append("TARGET_PROJECTED_AS_DELETION_OR_NO_QUERY_BASES")

    else:
        flags.append("GEOMETRY_NOT_RESOLVED_FOR_P2")

    if path_ratio > 1.25:
        flags.append("MOTIF_PATH_UNIT_INFLATION_GT_1_25")

    if purity < MIN_PURITY and tract_bp > 0:
        flags.append("PURITY_BELOW_THRESHOLD")

    final_confidence = "LOW"

    rows.append(
        {
            "schema_version": "0.3.1",
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
            "candidate_basis": job["candidate_basis"],
            "assignment_status": "alternate_exact_target",
            "assignment_confidence_label": "LOW",
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
            "search_read_start": (
                "." if search_start is None else search_start
            ),
            "search_read_end": (
                "." if search_end is None else search_end
            ),
            "tract_read_start": (
                "." if tract_start is None else tract_start
            ),
            "tract_read_end": (
                "." if tract_end is None else tract_end
            ),
            "tract_read_bp": tract_bp,
            "target_overlap_bp": target_overlap,
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
                "."
                if distance_to_end is None
                else distance_to_end
            ),
            "repeat_units_observed_read": (
                f"{observed_units:.6f}"
            ),
            "repeat_units_motif_path": (
                f"{path_units:.6f}"
            ),
            "motif_path_to_read_units_ratio": (
                f"{path_ratio:.6f}"
            ),
            "matches": matches,
            "mismatches": mismatches,
            "insertions": insertions,
            "deletions": deletions,
            "purity": f"{purity:.6f}",
            "edit_fraction": f"{edit_fraction:.6f}",
            "score": score,
            "selected_orientation": selected_orientation,
            "starting_phase": starting_phase,
            "ending_phase": ending_phase,
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
            "span_sequence_status": span_sequence_status,
            "sequence_review_required": str(
                sequence_review_required
            ).lower(),
            "sequence_confidence_label": sequence_confidence,
            "final_confidence_label": final_confidence,
            "evidence_flags": ";".join(
                sorted(set(flags))
            ),
        }
    )

    counts[f"evidence_class::{evidence_class}"] += 1
    counts[f"sizing_status::{sizing_status}"] += 1
    counts[f"span_sequence::{span_sequence_status}"] += 1
    counts[f"geometry::{geometry}"] += 1
    counts[
        f"motif_tract_status::{motif_tract_status}"
    ] += 1
    counts[
        f"sequence_confidence::{sequence_confidence}"
    ] += 1

    if index % PROGRESS_EVERY == 0 or index == len(jobs):
        elapsed = time.time() - start_time
        rate = index / elapsed if elapsed else 0.0
        remaining = (
            (len(jobs) - index) / rate
            if rate else 0.0
        )
        print(
            f"[INFO] processed {index:,}/{len(jobs):,} "
            f"P2 jobs; {rate:.1f} jobs/s; "
            f"ETA {remaining / 60:.1f} min",
            file=sys.stderr,
            flush=True,
        )

status = "PASS"

if (
    job_rows != EXPECTED_JOB_ROWS
    or projection_rows != EXPECTED_PROJECTION_ROWS
    or len(reads) != EXPECTED_FASTQ_READS
    or not jobs
    or missing_projections
    or missing_reads
    or len(rows) != len(jobs)
):
    status = "REVIEW"

with gzip.open(
    evidence_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

evidence_rank = {
    "SPAN": 5,
    "LEFT_ANCHORED_CENSORED_RIGHT": 4,
    "RIGHT_ANCHORED_CENSORED_LEFT": 4,
    "LEFT_ONLY_INTERNAL": 3,
    "RIGHT_ONLY_INTERNAL": 3,
    "REPEAT_ONLY_UNANCHORED": 2,
    "FLANKS_WITHOUT_REPEAT": 1,
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
    top_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(top_rows)

groups = defaultdict(
    lambda: {
        "rows": 0,
        "reads": set(),
        "targets": set(),
        "tract_bp": [],
        "purity": [],
    }
)

for row in rows:
    for group_name in (
        "ALL",
        f"evidence_class::{row['evidence_class']}",
        f"span_sequence::{row['span_sequence_status']}",
        f"geometry::{row['geometry_class']}",
    ):
        group = groups[group_name]
        group["rows"] += 1
        group["reads"].add(row["read_id"])
        group["targets"].add(row["target_region_id"])
        group["tract_bp"].append(int(row["tract_read_bp"]))
        group["purity"].append(float(row["purity"]))

summary_columns = [
    "group",
    "rows",
    "unique_reads",
    "unique_targets",
    "tract_bp_median",
    "tract_bp_p95",
    "tract_bp_max",
    "purity_median",
]

with open(
    summary_path,
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

    for group_name in sorted(groups):
        group = groups[group_name]
        writer.writerow(
            {
                "group": group_name,
                "rows": group["rows"],
                "unique_reads": len(group["reads"]),
                "unique_targets": len(group["targets"]),
                "tract_bp_median": (
                    f"{quantile(group['tract_bp'], 0.5):.6f}"
                ),
                "tract_bp_p95": (
                    f"{quantile(group['tract_bp'], 0.95):.6f}"
                ),
                "tract_bp_max": max(group["tract_bp"]),
                "purity_median": (
                    f"{quantile(group['purity'], 0.5):.6f}"
                ),
            }
        )

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        f"expected_job_rows\t{EXPECTED_JOB_ROWS}\n"
    )
    handle.write(f"observed_job_rows\t{job_rows}\n")
    handle.write(
        f"expected_projection_rows\t"
        f"{EXPECTED_PROJECTION_ROWS}\n"
    )
    handle.write(
        f"observed_projection_rows\t{projection_rows}\n"
    )
    handle.write(
        f"candidate_fastq_reads_loaded\t{len(reads)}\n"
    )
    handle.write(f"selected_p2_jobs\t{len(jobs)}\n")
    handle.write(
        f"selected_p2_projection_rows\t{len(projections)}\n"
    )
    handle.write(
        f"missing_selected_projections\t"
        f"{len(missing_projections)}\n"
    )
    handle.write(
        f"missing_selected_fastq_reads\t"
        f"{len(missing_reads)}\n"
    )
    handle.write(f"evidence_rows_written\t{len(rows)}\n")

    span_total = counts["evidence_class::SPAN"]
    span_periodic = counts[
        "span_sequence::PERIODIC_EXACT_SPAN"
    ]
    span_short = counts[
        "span_sequence::SHORT_EXACT_SPAN"
    ]
    span_review = counts[
        "span_sequence::COMPLEX_OR_LOW_PERIODICITY_EXACT_SPAN"
    ]
    span_ge12 = span_periodic + span_review

    handle.write(f"span_rows\t{span_total}\n")
    handle.write(
        f"span_periodic_exact_rows\t{span_periodic}\n"
    )
    handle.write(f"span_short_exact_rows\t{span_short}\n")
    handle.write(
        f"span_sequence_review_rows\t{span_review}\n"
    )
    handle.write(
        "span_periodic_pass_fraction_among_ge12\t"
        f"{span_periodic / span_ge12:.6f}\n"
        if span_ge12
        else "span_periodic_pass_fraction_among_ge12\t0.000000\n"
    )

    for key, value in sorted(counts.items()):
        handle.write(f"{key}\t{value}\n")

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit(
        "P2 alternate exact periodic analysis requires review"
    )
PY

echo "===== 1. INPUT INTEGRITY ====="

gzip -t "$JOBS"
gzip -t "$PROJECTION"
gzip -t "$CANDIDATE_FASTQ"

echo "Inputs: PASS"

echo
echo "===== 2. PARAMETERS ====="
column -ts $'\t' "$PARAMETERS"

echo
echo "===== 3. RUN P2 ALTERNATE EXACT PERIODIC ANALYSIS ====="

rm -f \
  "$EVIDENCE" \
  "$TOP" \
  "$SUMMARY" \
  "$QC" \
  "$MANIFEST"

python "$SCANNER" \
  "$JOBS" \
  "$PROJECTION" \
  "$CANDIDATE_FASTQ" \
  "$EVIDENCE" \
  "$TOP" \
  "$SUMMARY" \
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
  "$EXPECTED_JOB_ROWS" \
  "$EXPECTED_PROJECTION_ROWS" \
  "$EXPECTED_FASTQ_READS"

gzip -t "$EVIDENCE"

echo
echo "===== P2 QC ====="
column -ts $'\t' "$QC"

echo
echo "===== P2 SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== TOP 20 P2 EVIDENCE ROWS ====="
column -ts $'\t' "$TOP" | head -n 21

echo
echo "===== 4. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    rows="$(gzip -cd "$EVIDENCE" | awk 'END {print NR-1}')"

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$EVIDENCE")" \
      "$rows" \
      "$(stat -c '%s' "$EVIDENCE")" \
      "$(sha256sum "$EVIDENCE" | awk '{print $1}')" \
      "$EVIDENCE"

    for path in "$TOP" "$SUMMARY" "$QC" "$PARAMETERS"; do
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
echo "$EVIDENCE"
echo "$TOP"
echo "$SUMMARY"
echo "$QC"
echo "$MANIFEST"
