#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_reference_architecture_v0.3.2"

JOBS="$PROJECT_ROOT/results/11_extreme_nonexact_refined/$RUN_ID/reference_comparison_jobs.tsv"
EVENTS="$PROJECT_ROOT/results/11_extreme_nonexact_refined/$RUN_ID/extreme_nonexact_events.refined.tsv"
FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_reference_architecture/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_reference_architecture/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_reference_architecture/$RUN_ID"
DATADIR="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_reference_architecture"

COMPARISON="$OUTDIR/event_reference_architecture.tsv"
PROFILES="$OUTDIR/reference_and_observed_motif_profiles.tsv"
TARGETS="$OUTDIR/reference_target_intervals.tsv"
CLUSTERS="$OUTDIR/reference_locus_clusters.tsv"
REF_FASTA_OUT="$DATADIR/reference_targets_and_clusters.fasta.gz"
OBS_FASTA_OUT="$DATADIR/observed_reference_job_tracts.fasta.gz"
QC="$QCDIR/reference_architecture.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.reference_architecture.manifest.tsv"
PY="$WORKDIR/compare_reference_architecture.py"

EXPECTED_JOBS=2
EXPECTED_EVENTS=2
EXPECTED_TARGET_INTERVALS=2
EXPECTED_LOCUS_CLUSTERS=1

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR" "$DATADIR"

for path in "$JOBS" "$EVENTS" "$FASTQ"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

resolve_reference_fasta() {
    local candidates=(
        "${REF_FASTA:-}"
        "${REFERENCE_FASTA:-}"
        "${GENOME_FASTA:-}"
        "${GENCODE_FASTA:-}"
        "$PROJECT_ROOT/reference/GRCh38.primary_assembly.genome.fa"
        "$PROJECT_ROOT/references/GRCh38.primary_assembly.genome.fa"
        "$PROJECT_ROOT/reference/gencode.v50.primary_assembly.genome.fa"
        "$PROJECT_ROOT/references/gencode.v50.primary_assembly.genome.fa"
        "$PROJECT_ROOT/reference/gencode_v50/GRCh38.primary_assembly.genome.fa"
        "$PROJECT_ROOT/references/gencode_v50/GRCh38.primary_assembly.genome.fa"
    )

    local candidate
    for candidate in "${candidates[@]}"; do
        if [[ -n "$candidate" && -s "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    local found
    found="$(
        find "$PROJECT_ROOT" \
          -maxdepth 7 \
          -type f \
          \( \
            -name 'GRCh38.primary_assembly.genome.fa' \
            -o -name 'gencode.v50.primary_assembly.genome.fa' \
            -o -name '*primary_assembly*genome*.fa' \
          \) \
          -print \
          2>/dev/null \
        | head -n 1
    )"

    if [[ -n "$found" && -s "$found" ]]; then
        printf '%s\n' "$found"
        return 0
    fi

    return 1
}

REFERENCE_FASTA="$(resolve_reference_fasta)" || {
    echo "ERROR: GENCODE/GRCh38 reference FASTA could not be resolved." >&2
    echo "Set REF_FASTA in paths.env or place the FASTA under PROJECT_ROOT." >&2
    exit 1
}

test -s "${REFERENCE_FASTA}.fai" || {
    echo "ERROR: FASTA index missing: ${REFERENCE_FASTA}.fai" >&2
    exit 1
}

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
model_id	$MODEL_ID	Reference-sequence architecture prototype
reference_fasta	$REFERENCE_FASTA	GRCh38 primary assembly
comparison_scope	reference_sequence_architecture_only	No expansion or pathogenicity inference
target_coordinate_semantics	zero_based_half_open	Coordinates passed directly to pysam.FastaFile.fetch
observed_sequence_source	raw_fastq_event_interval	Raw RNA sequence, not BAM CIGAR sequence
motif_set	all_reference_job_motifs_at_locus	Every retained motif tested on every sequence from the same locus
periodicity_model	indel_aware_periodic_dynamic_programming	Global and local motif profiles
reference_interval_guardrail	target_interval_length_is_not_reference_allele_length	Catalog interval boundaries are profiled, not treated as allele truth
EOF

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass

import pysam

(
    jobs_path,
    events_path,
    fastq_path,
    reference_fasta_path,
    comparison_path,
    profiles_path,
    targets_path,
    clusters_path,
    reference_fasta_output_path,
    observed_fasta_output_path,
    qc_path,
    model_id,
    expected_jobs_text,
    expected_events_text,
    expected_targets_text,
    expected_clusters_text,
) = sys.argv[1:]

EXPECTED_JOBS = int(expected_jobs_text)
EXPECTED_EVENTS = int(expected_events_text)
EXPECTED_TARGETS = int(expected_targets_text)
EXPECTED_CLUSTERS = int(expected_clusters_text)

MATCH_SCORE = 3
MISMATCH_PENALTY = 4
INSERTION_PENALTY = 4
DELETION_PENALTY = 4
MAX_DELETIONS = 1

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


def canonical_motif(sequence: str) -> str:
    values = []
    for oriented in (sequence, reverse_complement(sequence)):
        for index in range(len(oriented)):
            values.append(oriented[index:] + oriented[:index])
    return min(values)


def primitive_root(sequence: str) -> str:
    for length in range(1, len(sequence) + 1):
        if len(sequence) % length:
            continue
        unit = sequence[:length]
        if unit * (len(sequence) // length) == sequence:
            return unit
    return sequence


def shannon_entropy(sequence: str) -> float:
    if not sequence:
        return 0.0
    counts = Counter(sequence)
    length = len(sequence)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def parse_target(target_region_id: str):
    interval = target_region_id.split(":", 2)[1]
    chrom, start, end = interval.rsplit("-", 2)
    return chrom, int(start), int(end)


def parse_cluster(cluster_id: str):
    match = re.match(
        r"^EXTLOC_[0-9]+_(.+)_([0-9]+)_([0-9]+)$",
        cluster_id,
    )
    if match is None:
        raise ValueError(
            "Unrecognized locus cluster ID: {}".format(cluster_id)
        )
    return match.group(1), int(match.group(2)), int(match.group(3))


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


def state_rank(state: State):
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


def call_rank(call: Call):
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


def align_orientation(sequence: str, motif: str, local: bool):
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
                delta = MATCH_SCORE if is_match else -MISMATCH_PENALTY
                delta -= deleted * DELETION_PENALTY

                update(
                    current,
                    (phase + 1) % motif_length,
                    State(
                        score=state.score + delta,
                        start=state.start,
                        motif_positions=state.motif_positions + deleted + 1,
                        matches=state.matches + (1 if is_match else 0),
                        mismatches=state.mismatches + (0 if is_match else 1),
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


def align_periodic(sequence: str, motif: str, local: bool):
    orientations = [motif]
    reverse = reverse_complement(motif)
    if reverse != motif:
        orientations.append(reverse)

    best = None

    for orientation in orientations:
        candidate = align_orientation(
            sequence,
            orientation,
            local,
        )
        if candidate is None:
            continue
        if best is None or call_rank(candidate) > call_rank(best):
            best = candidate

    return best


def call_metrics(call: Call, sequence_length: int, motif_length: int):
    denominator = (
        call.matches
        + call.mismatches
        + call.insertions
        + call.deletions
    )
    purity = call.matches / denominator if denominator else 0.0
    edit_fraction = (
        (
            call.mismatches
            + call.insertions
            + call.deletions
        )
        / denominator
        if denominator
        else 1.0
    )
    tract_bp = call.end - call.start

    return {
        "tract_start": call.start,
        "tract_end": call.end,
        "tract_bp": tract_bp,
        "tract_fraction": (
            tract_bp / sequence_length
            if sequence_length
            else 0.0
        ),
        "motif_path_units": (
            call.motif_positions / motif_length
        ),
        "matches": call.matches,
        "mismatches": call.mismatches,
        "insertions": call.insertions,
        "deletions": call.deletions,
        "purity": purity,
        "edit_fraction": edit_fraction,
        "score": call.score,
        "orientation": call.orientation,
    }


with open(
    jobs_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    jobs = list(csv.DictReader(handle, delimiter="\t"))

with open(
    events_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    events = {
        row["event_id"]: row
        for row in csv.DictReader(handle, delimiter="\t")
    }

selected_events = {}

for job in jobs:
    event_id = job["event_id"]
    if event_id not in events:
        raise RuntimeError(
            "Reference job event missing from refined events: {}".format(
                event_id
            )
        )
    selected_events[event_id] = events[event_id]

read_ids = {
    row["read_id"]
    for row in selected_events.values()
}

fastq_records = {}

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        if entry.name in read_ids:
            fastq_records[entry.name] = entry.sequence.upper()

missing_reads = read_ids - set(fastq_records)

reference = pysam.FastaFile(reference_fasta_path)
reference_contigs = set(reference.references)
contig_alias_resolution = {}


def resolve_reference_contig(catalog_chrom: str) -> str:
    if catalog_chrom in reference_contigs:
        contig_alias_resolution[catalog_chrom] = catalog_chrom
        return catalog_chrom

    candidates = []

    if catalog_chrom.startswith("chr"):
        candidates.append(catalog_chrom[3:])
    else:
        candidates.append("chr" + catalog_chrom)

    if catalog_chrom in {"M", "MT", "chrM", "chrMT"}:
        candidates.extend(["chrM", "MT", "M", "chrMT"])

    for candidate in candidates:
        if candidate in reference_contigs:
            contig_alias_resolution[catalog_chrom] = candidate
            return candidate

    raise KeyError(
        "Catalog contig {!r} is absent from the reference FASTA. "
        "Tried aliases: {}. Reference examples: {}".format(
            catalog_chrom,
            ",".join(candidates),
            ",".join(sorted(reference_contigs)[:12]),
        )
    )


target_intervals = {}
cluster_intervals = {}
motifs_by_cluster = defaultdict(set)

for job in jobs:
    cluster_ids = job["locus_cluster_ids"].split(";")
    target_ids = job["target_region_ids"].split(";")
    motifs = job["motifs"].split(";")

    for cluster_id in cluster_ids:
        catalog_chrom, start, end = parse_cluster(cluster_id)
        reference_chrom = resolve_reference_contig(catalog_chrom)
        cluster_intervals[cluster_id] = (
            reference_chrom,
            start,
            end,
        )
        motifs_by_cluster[cluster_id].update(motifs)

    for target_id in target_ids:
        catalog_chrom, start, end = parse_target(target_id)
        reference_chrom = resolve_reference_contig(catalog_chrom)
        target_intervals[target_id] = (
            reference_chrom,
            start,
            end,
        )

target_sequences = {}
cluster_sequences = {}

for target_id, (chrom, start, end) in target_intervals.items():
    target_sequences[target_id] = reference.fetch(
        chrom,
        start,
        end,
    ).upper()

for cluster_id, (chrom, start, end) in cluster_intervals.items():
    cluster_sequences[cluster_id] = reference.fetch(
        chrom,
        start,
        end,
    ).upper()

reference.close()

profile_fields = [
    "profile_id",
    "model_id",
    "sequence_source",
    "sequence_id",
    "event_id",
    "locus_cluster_id",
    "target_region_id",
    "chrom",
    "start",
    "end",
    "sequence_bp",
    "sequence_entropy_bits",
    "motif",
    "canonical_motif",
    "primitive_motif",
    "motif_length_bp",
    "global_tract_bp",
    "global_motif_path_units",
    "global_matches",
    "global_mismatches",
    "global_insertions",
    "global_deletions",
    "global_purity",
    "global_edit_fraction",
    "global_score",
    "global_orientation",
    "local_tract_start",
    "local_tract_end",
    "local_tract_bp",
    "local_tract_fraction",
    "local_motif_path_units",
    "local_purity",
    "local_edit_fraction",
    "local_score",
    "local_orientation",
]

profiles = []


def add_profiles(
    sequence_source,
    sequence_id,
    sequence,
    event_id,
    cluster_id,
    target_id,
    chrom,
    start,
    end,
    motifs,
):
    for motif in sorted(motifs):
        canonical = canonical_motif(motif)
        global_call = align_periodic(
            sequence,
            canonical,
            local=False,
        )
        local_call = align_periodic(
            sequence,
            canonical,
            local=True,
        )

        global_metrics = call_metrics(
            global_call,
            len(sequence),
            len(canonical),
        )
        local_metrics = call_metrics(
            local_call,
            len(sequence),
            len(canonical),
        )

        profile_id = hashlib.sha256(
            (
                "{}|{}|{}|{}".format(
                    sequence_source,
                    sequence_id,
                    event_id,
                    canonical,
                )
            ).encode()
        ).hexdigest()[:24]

        profiles.append(
            {
                "profile_id": profile_id,
                "model_id": model_id,
                "sequence_source": sequence_source,
                "sequence_id": sequence_id,
                "event_id": event_id,
                "locus_cluster_id": cluster_id,
                "target_region_id": target_id,
                "chrom": chrom,
                "start": start,
                "end": end,
                "sequence_bp": len(sequence),
                "sequence_entropy_bits": "{:.6f}".format(
                    shannon_entropy(sequence)
                ),
                "motif": motif,
                "canonical_motif": canonical,
                "primitive_motif": primitive_root(canonical),
                "motif_length_bp": len(canonical),
                "global_tract_bp": global_metrics["tract_bp"],
                "global_motif_path_units": "{:.6f}".format(
                    global_metrics["motif_path_units"]
                ),
                "global_matches": global_metrics["matches"],
                "global_mismatches": global_metrics["mismatches"],
                "global_insertions": global_metrics["insertions"],
                "global_deletions": global_metrics["deletions"],
                "global_purity": "{:.6f}".format(
                    global_metrics["purity"]
                ),
                "global_edit_fraction": "{:.6f}".format(
                    global_metrics["edit_fraction"]
                ),
                "global_score": global_metrics["score"],
                "global_orientation": global_metrics["orientation"],
                "local_tract_start": local_metrics["tract_start"],
                "local_tract_end": local_metrics["tract_end"],
                "local_tract_bp": local_metrics["tract_bp"],
                "local_tract_fraction": "{:.6f}".format(
                    local_metrics["tract_fraction"]
                ),
                "local_motif_path_units": "{:.6f}".format(
                    local_metrics["motif_path_units"]
                ),
                "local_purity": "{:.6f}".format(
                    local_metrics["purity"]
                ),
                "local_edit_fraction": "{:.6f}".format(
                    local_metrics["edit_fraction"]
                ),
                "local_score": local_metrics["score"],
                "local_orientation": local_metrics["orientation"],
            }
        )


for cluster_id, sequence in cluster_sequences.items():
    chrom, start, end = cluster_intervals[cluster_id]
    add_profiles(
        "REFERENCE_LOCUS_CLUSTER",
        cluster_id,
        sequence,
        ".",
        cluster_id,
        ".",
        chrom,
        start,
        end,
        motifs_by_cluster[cluster_id],
    )

for target_id, sequence in target_sequences.items():
    chrom, start, end = target_intervals[target_id]
    matching_clusters = [
        cluster_id
        for cluster_id, interval in cluster_intervals.items()
        if interval[0] == chrom
        and interval[1] <= start
        and interval[2] >= end
    ]
    cluster_id = (
        matching_clusters[0]
        if matching_clusters
        else "."
    )
    motifs = (
        motifs_by_cluster[cluster_id]
        if cluster_id != "."
        else {
            motif
            for job in jobs
            if target_id in job["target_region_ids"].split(";")
            for motif in job["motifs"].split(";")
        }
    )
    add_profiles(
        "REFERENCE_TARGET_INTERVAL",
        target_id,
        sequence,
        ".",
        cluster_id,
        target_id,
        chrom,
        start,
        end,
        motifs,
    )

observed_sequences = {}

for job in jobs:
    event_id = job["event_id"]
    event = selected_events[event_id]
    read_id = event["read_id"]
    sequence = fastq_records[read_id]
    start = int(event["event_start"])
    end = int(event["event_end"])

    if not (0 <= start < end <= len(sequence)):
        raise RuntimeError(
            "Invalid event interval for {}: {}-{} / {}".format(
                event_id,
                start,
                end,
                len(sequence),
            )
        )

    observed = sequence[start:end]
    observed_sequences[event_id] = observed

    cluster_id = job["locus_cluster_ids"].split(";")[0]
    chrom, cluster_start, cluster_end = cluster_intervals[
        cluster_id
    ]

    add_profiles(
        "OBSERVED_RAW_RNA_EVENT",
        event_id,
        observed,
        event_id,
        cluster_id,
        job["target_region_ids"],
        chrom,
        start,
        end,
        motifs_by_cluster[cluster_id],
    )

with open(
    profiles_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=profile_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(profiles)

profile_lookup = {}

for row in profiles:
    key = (
        row["sequence_source"],
        row["sequence_id"],
        row["canonical_motif"],
    )
    profile_lookup[key] = row

comparison_fields = [
    "event_id",
    "read_id",
    "locus_cluster_id",
    "target_region_id",
    "job_motif",
    "canonical_job_motif",
    "observed_event_bp",
    "target_interval_bp",
    "locus_cluster_bp",
    "observed_to_target_interval_ratio",
    "observed_to_cluster_interval_ratio",
    "observed_global_purity_job_motif",
    "observed_local_tract_bp_job_motif",
    "observed_local_purity_job_motif",
    "reference_target_global_purity_job_motif",
    "reference_target_local_tract_bp_job_motif",
    "reference_target_local_purity_job_motif",
    "reference_cluster_global_purity_job_motif",
    "reference_cluster_local_tract_bp_job_motif",
    "reference_cluster_local_purity_job_motif",
    "best_observed_motif",
    "best_observed_global_purity",
    "best_reference_cluster_motif",
    "best_reference_cluster_global_purity",
    "same_best_motif",
    "reference_architecture_status",
    "expansion_status",
    "interpretation_guardrail",
]

comparison_rows = []

for job in jobs:
    event_id = job["event_id"]
    event = selected_events[event_id]
    cluster_id = job["locus_cluster_ids"].split(";")[0]
    target_id = job["target_region_ids"].split(";")[0]
    job_motif = job["motifs"].split(";")[0]
    canonical = canonical_motif(job_motif)

    observed_profile = profile_lookup[
        (
            "OBSERVED_RAW_RNA_EVENT",
            event_id,
            canonical,
        )
    ]
    target_profile = profile_lookup[
        (
            "REFERENCE_TARGET_INTERVAL",
            target_id,
            canonical,
        )
    ]
    cluster_profile = profile_lookup[
        (
            "REFERENCE_LOCUS_CLUSTER",
            cluster_id,
            canonical,
        )
    ]

    observed_candidates = [
        row
        for row in profiles
        if row["sequence_source"] == "OBSERVED_RAW_RNA_EVENT"
        and row["sequence_id"] == event_id
    ]
    cluster_candidates = [
        row
        for row in profiles
        if row["sequence_source"] == "REFERENCE_LOCUS_CLUSTER"
        and row["sequence_id"] == cluster_id
    ]

    best_observed = max(
        observed_candidates,
        key=lambda row: (
            float(row["global_purity"]),
            int(row["global_score"]),
        ),
    )
    best_cluster = max(
        cluster_candidates,
        key=lambda row: (
            float(row["global_purity"]),
            int(row["global_score"]),
        ),
    )

    observed_bp = len(observed_sequences[event_id])
    target_bp = len(target_sequences[target_id])
    cluster_bp = len(cluster_sequences[cluster_id])

    comparison_rows.append(
        {
            "event_id": event_id,
            "read_id": event["read_id"],
            "locus_cluster_id": cluster_id,
            "target_region_id": target_id,
            "job_motif": job_motif,
            "canonical_job_motif": canonical,
            "observed_event_bp": observed_bp,
            "target_interval_bp": target_bp,
            "locus_cluster_bp": cluster_bp,
            "observed_to_target_interval_ratio": "{:.6f}".format(
                observed_bp / target_bp
            ),
            "observed_to_cluster_interval_ratio": "{:.6f}".format(
                observed_bp / cluster_bp
            ),
            "observed_global_purity_job_motif": observed_profile[
                "global_purity"
            ],
            "observed_local_tract_bp_job_motif": observed_profile[
                "local_tract_bp"
            ],
            "observed_local_purity_job_motif": observed_profile[
                "local_purity"
            ],
            "reference_target_global_purity_job_motif": target_profile[
                "global_purity"
            ],
            "reference_target_local_tract_bp_job_motif": target_profile[
                "local_tract_bp"
            ],
            "reference_target_local_purity_job_motif": target_profile[
                "local_purity"
            ],
            "reference_cluster_global_purity_job_motif": cluster_profile[
                "global_purity"
            ],
            "reference_cluster_local_tract_bp_job_motif": cluster_profile[
                "local_tract_bp"
            ],
            "reference_cluster_local_purity_job_motif": cluster_profile[
                "local_purity"
            ],
            "best_observed_motif": best_observed[
                "canonical_motif"
            ],
            "best_observed_global_purity": best_observed[
                "global_purity"
            ],
            "best_reference_cluster_motif": best_cluster[
                "canonical_motif"
            ],
            "best_reference_cluster_global_purity": best_cluster[
                "global_purity"
            ],
            "same_best_motif": str(
                best_observed["canonical_motif"]
                == best_cluster["canonical_motif"]
            ).lower(),
            "reference_architecture_status": (
                "REFERENCE_INTERVALS_PROFILED"
            ),
            "expansion_status": "NOT_ASSESSED",
            "interpretation_guardrail": (
                "Catalog interval length and reference local periodic "
                "tract length are architecture measurements, not an "
                "individual reference allele truth or disease threshold"
            ),
        }
    )

with open(
    comparison_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=comparison_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(comparison_rows)

target_fields = [
    "target_region_id",
    "chrom",
    "start",
    "end",
    "interval_bp",
    "sequence_entropy_bits",
    "sha256",
]

target_rows = []

for target_id, sequence in sorted(target_sequences.items()):
    chrom, start, end = target_intervals[target_id]
    target_rows.append(
        {
            "target_region_id": target_id,
            "chrom": chrom,
            "start": start,
            "end": end,
            "interval_bp": len(sequence),
            "sequence_entropy_bits": "{:.6f}".format(
                shannon_entropy(sequence)
            ),
            "sha256": hashlib.sha256(
                sequence.encode()
            ).hexdigest(),
        }
    )

with open(
    targets_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=target_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(target_rows)

cluster_fields = [
    "locus_cluster_id",
    "chrom",
    "start",
    "end",
    "interval_bp",
    "motifs_tested",
    "sequence_entropy_bits",
    "sha256",
]

cluster_rows = []

for cluster_id, sequence in sorted(cluster_sequences.items()):
    chrom, start, end = cluster_intervals[cluster_id]
    cluster_rows.append(
        {
            "locus_cluster_id": cluster_id,
            "chrom": chrom,
            "start": start,
            "end": end,
            "interval_bp": len(sequence),
            "motifs_tested": ";".join(
                sorted(motifs_by_cluster[cluster_id])
            ),
            "sequence_entropy_bits": "{:.6f}".format(
                shannon_entropy(sequence)
            ),
            "sha256": hashlib.sha256(
                sequence.encode()
            ).hexdigest(),
        }
    )

with open(
    clusters_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=cluster_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(cluster_rows)

with gzip.open(
    reference_fasta_output_path,
    "wt",
    encoding="utf-8",
) as handle:
    for cluster_id, sequence in sorted(cluster_sequences.items()):
        chrom, start, end = cluster_intervals[cluster_id]
        handle.write(
            ">{} source=REFERENCE_LOCUS_CLUSTER coordinate={}:{}-{}\n{}\n".format(
                cluster_id,
                chrom,
                start,
                end,
                sequence,
            )
        )

    for target_id, sequence in sorted(target_sequences.items()):
        chrom, start, end = target_intervals[target_id]
        handle.write(
            ">{} source=REFERENCE_TARGET_INTERVAL coordinate={}:{}-{}\n{}\n".format(
                target_id,
                chrom,
                start,
                end,
                sequence,
            )
        )

with gzip.open(
    observed_fasta_output_path,
    "wt",
    encoding="utf-8",
) as handle:
    for event_id, sequence in sorted(observed_sequences.items()):
        event = selected_events[event_id]
        handle.write(
            ">{} source=OBSERVED_RAW_RNA_EVENT read={} raw={}-{}\n{}\n".format(
                event_id,
                event["read_id"],
                event["event_start"],
                event["event_end"],
                sequence,
            )
        )

status = "PASS"

if (
    len(jobs) != EXPECTED_JOBS
    or len(selected_events) != EXPECTED_EVENTS
    or len(target_intervals) != EXPECTED_TARGETS
    or len(cluster_intervals) != EXPECTED_CLUSTERS
    or missing_reads
    or len(comparison_rows) != EXPECTED_JOBS
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write("expected_jobs\t{}\n".format(EXPECTED_JOBS))
    handle.write("observed_jobs\t{}\n".format(len(jobs)))
    handle.write("expected_events\t{}\n".format(EXPECTED_EVENTS))
    handle.write(
        "observed_events\t{}\n".format(len(selected_events))
    )
    handle.write(
        "expected_target_intervals\t{}\n".format(
            EXPECTED_TARGETS
        )
    )
    handle.write(
        "observed_target_intervals\t{}\n".format(
            len(target_intervals)
        )
    )
    handle.write(
        "expected_locus_clusters\t{}\n".format(
            EXPECTED_CLUSTERS
        )
    )
    handle.write(
        "observed_locus_clusters\t{}\n".format(
            len(cluster_intervals)
        )
    )
    handle.write(
        "fastq_reads_required\t{}\n".format(len(read_ids))
    )
    handle.write(
        "fastq_reads_found\t{}\n".format(len(fastq_records))
    )
    handle.write(
        "missing_fastq_reads\t{}\n".format(len(missing_reads))
    )
    handle.write(
        "motif_profiles_written\t{}\n".format(len(profiles))
    )
    handle.write(
        "comparison_rows_written\t{}\n".format(
            len(comparison_rows)
        )
    )
    handle.write(
        "expansion_calls_emitted\t0\n"
    )
    handle.write(
        "catalog_contig_names_resolved\t{}\n".format(
            len(contig_alias_resolution)
        )
    )
    handle.write(
        "contig_alias_map\t{}\n".format(
            ";".join(
                "{}->{}".format(source, target)
                for source, target in sorted(
                    contig_alias_resolution.items()
                )
            )
        )
    )
    handle.write("audit_status\t{}\n".format(status))

if status != "PASS":
    raise SystemExit(
        "Reference architecture comparison requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

echo
echo "===== INPUTS ====="
echo "Reference FASTA: $REFERENCE_FASTA"
gzip -t "$FASTQ"
echo "Inputs: PASS"

rm -f \
  "$COMPARISON" \
  "$PROFILES" \
  "$TARGETS" \
  "$CLUSTERS" \
  "$REF_FASTA_OUT" \
  "$OBS_FASTA_OUT" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== PROFILE REFERENCE ARCHITECTURE ====="

python "$PY" \
  "$JOBS" \
  "$EVENTS" \
  "$FASTQ" \
  "$REFERENCE_FASTA" \
  "$COMPARISON" \
  "$PROFILES" \
  "$TARGETS" \
  "$CLUSTERS" \
  "$REF_FASTA_OUT" \
  "$OBS_FASTA_OUT" \
  "$QC" \
  "$MODEL_ID" \
  "$EXPECTED_JOBS" \
  "$EXPECTED_EVENTS" \
  "$EXPECTED_TARGET_INTERVALS" \
  "$EXPECTED_LOCUS_CLUSTERS"

gzip -t "$REF_FASTA_OUT"
gzip -t "$OBS_FASTA_OUT"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== EVENT / REFERENCE COMPARISON ====="
column -ts $'\t' "$COMPARISON"

echo
echo "===== MOTIF PROFILES ====="
column -ts $'\t' "$PROFILES"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$COMPARISON" \
      "$PROFILES" \
      "$TARGETS" \
      "$CLUSTERS" \
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

    for path in "$REF_FASTA_OUT" "$OBS_FASTA_OUT"; do
        rows="$(gzip -cd "$path" | grep -c '^>')"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$COMPARISON"
echo "$PROFILES"
echo "$TARGETS"
echo "$CLUSTERS"
echo "$QC"
