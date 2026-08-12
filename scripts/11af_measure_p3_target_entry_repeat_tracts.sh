#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_p3_target_entry_repeat_sizing_v0.3.1"

LOCAL_RESULTS="$PROJECT_ROOT/results/11_p3_catalog_local_competition/$RUN_ID/p3_catalog_complete_local_competition.tsv"
PAIR_META="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"
REFERENCE_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_candidate_references.fasta.gz"
RAW_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_target_entry_sizing/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_target_entry_sizing/$RUN_ID"

OUTPUT="$OUTDIR/p3_target_entry_repeat_evidence.tsv"
SUMMARY="$OUTDIR/p3_target_entry_repeat_evidence_summary.tsv"
QC="$QCDIR/p3_target_entry_repeat_evidence.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_target_entry_repeat_sizing.manifest.tsv"
PY="$WORKDIR/measure_p3_target_entry_repeats.py"

EXPECTED_PAIRS=23
EXPECTED_QUERY_FASTA_ROWS=1007
EXPECTED_REFERENCE_FASTA_ROWS=1007
EXPECTED_RAW_FASTQ_READS=79176

WORKERS=8
PROGRESS_EVERY=5
MIN_REPEAT_BP=12
MIN_PURITY=0.70
MIN_PATH_RATIO=0.75
MAX_PATH_RATIO=1.25
ENTRY_OFFSET_TOLERANCE_BP=5
END_TOLERANCE_BP=10
MAX_DELETIONS_BEFORE_BASE=1

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$LOCAL_RESULTS" \
  "$PAIR_META" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$RAW_FASTQ"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

command -v minimap2 >/dev/null 2>&1 || {
    echo "ERROR: minimap2 is not available" >&2
    exit 1
}

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
model_id	$MODEL_ID	Target-entry-constrained repeat sizing for validated P3 bridges
input_pairs	$EXPECTED_PAIRS	Catalog-local validated P3 bridge candidates
target_entry_projection	isolated_pair_cg_CIGAR	Project reference bridge boundary onto oriented raw soft clip
minimum_repeat_bp	$MIN_REPEAT_BP	Minimum target-entry periodic tract
minimum_purity	$MIN_PURITY	Minimum indel-aware periodic purity
minimum_path_ratio	$MIN_PATH_RATIO	Minimum motif-path/read-unit ratio
maximum_path_ratio	$MAX_PATH_RATIO	Maximum motif-path/read-unit ratio
entry_offset_tolerance_bp	$ENTRY_OFFSET_TOLERANCE_BP	Small boundary uncertainty allowed around projected target entry
end_tolerance_bp	$END_TOLERANCE_BP	Tract must reach oriented raw-clip end for censored lower bound
max_deletions_before_base	$MAX_DELETIONS_BEFORE_BASE	Maximum motif positions skipped before a read base
classification_semantics	one_validated_anchor_plus_target_entry_bridge	No exact span without opposite flank
expansion_status	NOT_ASSESSED	Reference-relative expansion is not assessed
EOF

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import math
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pysam

(
    local_results_path,
    metadata_path,
    query_fasta_path,
    reference_fasta_path,
    raw_fastq_path,
    output_path,
    summary_path,
    qc_path,
    workdir,
    model_id,
    expected_pairs_text,
    expected_query_rows_text,
    expected_reference_rows_text,
    expected_fastq_text,
    workers_text,
    progress_every_text,
    min_repeat_text,
    min_purity_text,
    min_path_ratio_text,
    max_path_ratio_text,
    entry_offset_text,
    end_tolerance_text,
    max_deletions_text,
) = sys.argv[1:]

EXPECTED_PAIRS = int(expected_pairs_text)
EXPECTED_QUERY_ROWS = int(expected_query_rows_text)
EXPECTED_REFERENCE_ROWS = int(expected_reference_rows_text)
EXPECTED_FASTQ = int(expected_fastq_text)

WORKERS = int(workers_text)
PROGRESS_EVERY = int(progress_every_text)
MIN_REPEAT_BP = int(min_repeat_text)
MIN_PURITY = float(min_purity_text)
MIN_PATH_RATIO = float(min_path_ratio_text)
MAX_PATH_RATIO = float(max_path_ratio_text)
ENTRY_OFFSET = int(entry_offset_text)
END_TOLERANCE = int(end_tolerance_text)
MAX_DELETIONS = int(max_deletions_text)

MATCH_SCORE = 3
MISMATCH_PENALTY = 4
INSERTION_PENALTY = 4
DELETION_PENALTY = 4

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def rotations(sequence):
    return [
        sequence[index:] + sequence[:index]
        for index in range(len(sequence))
    ]


def canonical_motif(sequence):
    candidates = []

    for oriented in (
        sequence,
        reverse_complement(sequence),
    ):
        candidates.extend(rotations(oriented))

    return min(candidates)


def parse_tags(fields):
    tags = {}

    for field in fields:
        parts = field.split(":", 2)

        if len(parts) != 3:
            continue

        name, value_type, value = parts

        if value_type == "i":
            tags[name] = int(value)
        elif value_type == "f":
            tags[name] = float(value)
        else:
            tags[name] = value

    return tags


def parse_cigar(cigar):
    parsed = [
        (operation, int(length))
        for length, operation in re.findall(
            r"([0-9]+)([MIDNSHP=X])",
            cigar,
        )
    ]

    reconstructed = "".join(
        "{}{}".format(length, operation)
        for operation, length in parsed
    )

    if reconstructed != cigar:
        raise ValueError(
            "Incomplete CIGAR parse: {} != {}".format(
                reconstructed,
                cigar,
            )
        )

    return parsed


def project_reference_boundary_to_query(
    query_start,
    reference_start,
    cigar,
    reference_boundary,
):
    query_cursor = query_start
    reference_cursor = reference_start

    if reference_boundary < reference_start:
        return None, "BOUNDARY_BEFORE_ALIGNMENT"

    for operation, length in parse_cigar(cigar):
        if reference_boundary == reference_cursor:
            return query_cursor, "PROJECTED_AT_OPERATION_BOUNDARY"

        if operation in {"M", "=", "X"}:
            next_reference = reference_cursor + length
            next_query = query_cursor + length

            if (
                reference_cursor
                < reference_boundary
                <= next_reference
            ):
                delta = (
                    reference_boundary
                    - reference_cursor
                )
                return (
                    query_cursor + delta,
                    "PROJECTED_WITHIN_MATCHLIKE",
                )

            reference_cursor = next_reference
            query_cursor = next_query

        elif operation == "D":
            next_reference = reference_cursor + length

            if (
                reference_cursor
                < reference_boundary
                <= next_reference
            ):
                return (
                    query_cursor,
                    "PROJECTED_WITHIN_DELETION",
                )

            reference_cursor = next_reference

        elif operation == "I":
            query_cursor += length

        elif operation == "S":
            query_cursor += length

        elif operation in {"H", "P"}:
            continue

        elif operation == "N":
            reference_cursor += length

    if reference_boundary == reference_cursor:
        return query_cursor, "PROJECTED_AT_ALIGNMENT_END"

    return None, "BOUNDARY_AFTER_ALIGNMENT"


@dataclass(frozen=True)
class State:
    score: int
    motif_positions: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    starting_phase: int
    orientation: str


def state_rank(state):
    return (
        state.score,
        state.matches,
        state.motif_positions,
        -state.mismatches,
        -state.insertions,
        -state.deletions,
        -state.starting_phase,
    )


def update(container, index, candidate):
    current = container[index]

    if (
        current is None
        or state_rank(candidate)
        > state_rank(current)
    ):
        container[index] = candidate


def prefix_periodicity(sequence, motif):
    orientations = sorted(
        set(
            rotations(motif)
            + rotations(
                reverse_complement(motif)
            )
        )
    )
    prefix_best = [None] * (len(sequence) + 1)

    for orientation in orientations:
        motif_length = len(orientation)
        previous = [
            State(
                score=0,
                motif_positions=0,
                matches=0,
                mismatches=0,
                insertions=0,
                deletions=0,
                starting_phase=phase,
                orientation=orientation,
            )
            for phase in range(motif_length)
        ]

        for sequence_index, base in enumerate(
            sequence,
            start=1,
        ):
            current = [None] * motif_length

            for expected_phase, state in enumerate(
                previous
            ):
                if state is None:
                    continue

                update(
                    current,
                    expected_phase,
                    State(
                        score=(
                            state.score
                            - INSERTION_PENALTY
                        ),
                        motif_positions=(
                            state.motif_positions
                        ),
                        matches=state.matches,
                        mismatches=state.mismatches,
                        insertions=(
                            state.insertions + 1
                        ),
                        deletions=state.deletions,
                        starting_phase=(
                            state.starting_phase
                        ),
                        orientation=orientation,
                    ),
                )

                for deleted in range(
                    MAX_DELETIONS + 1
                ):
                    phase = (
                        expected_phase + deleted
                    ) % motif_length
                    is_match = (
                        base == orientation[phase]
                    )
                    delta = (
                        MATCH_SCORE
                        if is_match
                        else -MISMATCH_PENALTY
                    )
                    delta -= (
                        deleted
                        * DELETION_PENALTY
                    )

                    update(
                        current,
                        (phase + 1)
                        % motif_length,
                        State(
                            score=(
                                state.score + delta
                            ),
                            motif_positions=(
                                state.motif_positions
                                + deleted
                                + 1
                            ),
                            matches=(
                                state.matches
                                + (
                                    1
                                    if is_match
                                    else 0
                                )
                            ),
                            mismatches=(
                                state.mismatches
                                + (
                                    0
                                    if is_match
                                    else 1
                                )
                            ),
                            insertions=(
                                state.insertions
                            ),
                            deletions=(
                                state.deletions
                                + deleted
                            ),
                            starting_phase=(
                                state.starting_phase
                            ),
                            orientation=orientation,
                        ),
                    )

            best_state = max(
                (
                    state
                    for state in current
                    if state is not None
                ),
                key=state_rank,
            )

            existing = prefix_best[
                sequence_index
            ]

            if (
                existing is None
                or state_rank(best_state)
                > state_rank(existing)
            ):
                prefix_best[
                    sequence_index
                ] = best_state

            previous = current

    return prefix_best


def longest_valid_periodic_prefix(
    sequence,
    motif,
):
    if not sequence:
        return None

    prefix_states = prefix_periodicity(
        sequence,
        motif,
    )
    best = None
    motif_length = len(motif)

    for prefix_bp in range(
        MIN_REPEAT_BP,
        len(sequence) + 1,
    ):
        state = prefix_states[prefix_bp]

        if state is None:
            continue

        denominator = (
            state.matches
            + state.mismatches
            + state.insertions
            + state.deletions
        )
        purity = (
            state.matches / denominator
            if denominator
            else 0.0
        )
        observed_units = (
            prefix_bp / motif_length
        )
        path_units = (
            state.motif_positions
            / motif_length
        )
        path_ratio = (
            path_units / observed_units
            if observed_units
            else 0.0
        )

        if (
            purity < MIN_PURITY
            or path_ratio < MIN_PATH_RATIO
            or path_ratio > MAX_PATH_RATIO
            or state.score <= 0
        ):
            continue

        candidate = {
            "prefix_bp": prefix_bp,
            "purity": purity,
            "observed_units": observed_units,
            "path_units": path_units,
            "path_ratio": path_ratio,
            "matches": state.matches,
            "mismatches": state.mismatches,
            "insertions": state.insertions,
            "deletions": state.deletions,
            "score": state.score,
            "orientation": state.orientation,
            "starting_phase": (
                state.starting_phase
            ),
        }

        if (
            best is None
            or (
                candidate["prefix_bp"],
                candidate["purity"],
                candidate["score"],
            )
            > (
                best["prefix_bp"],
                best["purity"],
                best["score"],
            )
        ):
            best = candidate

    return best


def oriented_to_raw_interval(
    oriented_start,
    oriented_end,
    raw_clip_start,
    raw_clip_end,
    transform,
):
    if transform == "AS_RAW":
        return (
            raw_clip_start + oriented_start,
            raw_clip_start + oriented_end,
        )

    if transform == "REVERSE_COMPLEMENT":
        return (
            raw_clip_end - oriented_end,
            raw_clip_end - oriented_start,
        )

    raise ValueError(
        "Unknown orientation transform: {}".format(
            transform
        )
    )


with open(
    local_results_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    local_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

with gzip.open(
    metadata_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    metadata = {
        row["projection_id"]: row
        for row in csv.DictReader(
            handle,
            delimiter="\t",
        )
    }

query_sequences = {}

with pysam.FastxFile(
    query_fasta_path
) as source:
    for entry in source:
        query_sequences[entry.name] = (
            entry.sequence.upper()
        )

reference_sequences = {}

with pysam.FastxFile(
    reference_fasta_path
) as source:
    for entry in source:
        reference_sequences[entry.name] = (
            entry.sequence.upper()
        )

required_read_ids = {
    row["read_id"]
    for row in local_rows
}

raw_reads = {}
raw_fastq_count = 0

with pysam.FastxFile(
    raw_fastq_path
) as source:
    for entry in source:
        raw_fastq_count += 1

        if entry.name in required_read_ids:
            raw_reads[entry.name] = (
                entry.sequence.upper()
            )

missing_metadata = {
    row["projection_id"]
    for row in local_rows
    if row["projection_id"]
       not in metadata
}
missing_queries = {
    row["projection_id"]
    for row in local_rows
    if row["projection_id"]
       not in query_sequences
}
missing_references = {
    row["projection_id"]
    for row in local_rows
    if metadata.get(
        row["projection_id"],
        {},
    ).get(
        "reference_id",
        ".",
    ) not in reference_sequences
}
missing_raw_reads = (
    required_read_ids - set(raw_reads)
)

progress_lock = threading.Lock()
progress = {
    "completed": 0,
    "start": time.time(),
}


def run_pair(local_row):
    projection_id = local_row[
        "projection_id"
    ]
    meta = metadata[projection_id]
    query_sequence = query_sequences[
        projection_id
    ]
    reference_id = meta["reference_id"]
    reference_sequence = (
        reference_sequences[reference_id]
    )
    read_sequence = raw_reads[
        local_row["read_id"]
    ]

    safe_id = "".join(
        character
        if character.isalnum()
        else "_"
        for character in projection_id
    )
    pair_directory = os.path.join(
        workdir,
        "entry_" + safe_id,
    )
    os.makedirs(
        pair_directory,
        exist_ok=True,
    )
    query_path = os.path.join(
        pair_directory,
        "query.fa",
    )
    reference_path = os.path.join(
        pair_directory,
        "reference.fa",
    )

    with open(
        query_path,
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            ">{}\n{}\n".format(
                projection_id,
                query_sequence,
            )
        )

    with open(
        reference_path,
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            ">{}\n{}\n".format(
                reference_id,
                reference_sequence,
            )
        )

    completed = subprocess.run(
        [
            "minimap2",
            "-x",
            "map-ont",
            "-k7",
            "-w3",
            "-m10",
            "-s10",
            "-p0.50",
            "-N10",
            "-f0",
            "-c",
            "--cs=long",
            "--secondary=yes",
            "-t1",
            reference_path,
            query_path,
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "minimap2 failed for {}".format(
                projection_id
            )
        )

    try:
        os.remove(query_path)
        os.remove(reference_path)
        os.rmdir(pair_directory)
    except OSError:
        pass

    alignments = []

    for line in completed.stdout.splitlines():
        if not line:
            continue

        fields = line.split("\t")
        tags = parse_tags(fields[12:])

        if (
            fields[0] != projection_id
            or fields[5] != reference_id
        ):
            continue

        alignments.append(
            {
                "query_start": int(fields[2]),
                "query_end": int(fields[3]),
                "strand": fields[4],
                "reference_start": int(fields[7]),
                "reference_end": int(fields[8]),
                "matches": int(fields[9]),
                "block_length": int(fields[10]),
                "mapq": int(fields[11]),
                "alignment_score": tags.get(
                    "AS",
                    int(fields[9]),
                ),
                "cigar": tags.get("cg", "."),
            }
        )

    alignments.sort(
        key=lambda row: (
            row["alignment_score"],
            row["matches"],
            row["query_end"]
            - row["query_start"],
        ),
        reverse=True,
    )

    raw_clip_start = int(
        meta["raw_clip_start"]
    )
    raw_clip_end = int(
        meta["raw_clip_end"]
    )
    raw_clip = read_sequence[
        raw_clip_start:raw_clip_end
    ]
    transform = meta[
        "orientation_transform"
    ]
    oriented_clip = (
        raw_clip
        if transform == "AS_RAW"
        else reverse_complement(raw_clip)
    )

    query_prefix_matches = (
        oriented_clip[
            :len(query_sequence)
        ] == query_sequence
    )

    motif = canonical_motif(
        meta["canonical_motif"]
    )
    target_entry_reference = int(
        meta["bridge_bp"]
    )

    if not alignments:
        projection_status = (
            "NO_ISOLATED_ALIGNMENT"
        )
        target_entry_query = None
        projection_detail = "."
        best_alignment = None

    else:
        best_alignment = alignments[0]

        if best_alignment["strand"] != "+":
            projection_status = (
                "UNEXPECTED_REVERSE_ALIGNMENT"
            )
            target_entry_query = None
            projection_detail = "."

        elif best_alignment["cigar"] == ".":
            projection_status = (
                "CIGAR_MISSING"
            )
            target_entry_query = None
            projection_detail = "."

        else:
            (
                target_entry_query,
                projection_detail,
            ) = project_reference_boundary_to_query(
                best_alignment[
                    "query_start"
                ],
                best_alignment[
                    "reference_start"
                ],
                best_alignment["cigar"],
                target_entry_reference,
            )
            projection_status = (
                "TARGET_ENTRY_PROJECTED"
                if target_entry_query
                   is not None
                else "TARGET_ENTRY_NOT_PROJECTED"
            )

    best_tract = None

    if (
        target_entry_query is not None
        and query_prefix_matches
    ):
        minimum_start = max(
            0,
            target_entry_query
            - ENTRY_OFFSET,
        )
        maximum_start = min(
            len(oriented_clip),
            target_entry_query
            + ENTRY_OFFSET,
        )

        for tract_start in range(
            minimum_start,
            maximum_start + 1,
        ):
            call = (
                longest_valid_periodic_prefix(
                    oriented_clip[tract_start:],
                    motif,
                )
            )

            if call is None:
                continue

            tract_end = (
                tract_start
                + call["prefix_bp"]
            )
            reaches_end = (
                len(oriented_clip)
                - tract_end
                <= END_TOLERANCE
            )
            candidate = dict(call)
            candidate.update(
                {
                    "tract_start": tract_start,
                    "tract_end": tract_end,
                    "entry_offset": (
                        tract_start
                        - target_entry_query
                    ),
                    "reaches_clip_end": (
                        reaches_end
                    ),
                }
            )

            rank = (
                candidate["prefix_bp"],
                candidate["purity"],
                candidate["score"],
                -abs(
                    candidate[
                        "entry_offset"
                    ]
                ),
            )

            if (
                best_tract is None
                or rank
                > best_tract["_rank"]
            ):
                candidate["_rank"] = rank
                best_tract = candidate

    target_side = meta[
        "target_facing_genomic_side"
    ]

    if best_tract is None:
        evidence_class = (
            "P3_BRIDGE_ONLY_NO_TARGET_ENTRY_REPEAT_TRACT"
        )
        sizing_status = "no_call"
        lower_bound = "."
        tract_raw_start = "."
        tract_raw_end = "."
        tract_bp = 0
        purity = "."
        path_ratio = "."
        observed_units = "."
        path_units = "."
        matches = "."
        mismatches = "."
        insertions = "."
        deletions = "."
        score = "."
        selected_orientation = "."
        entry_offset = "."
        distance_to_clip_end = "."
        reaches_clip_end = "false"

    else:
        (
            tract_raw_start,
            tract_raw_end,
        ) = oriented_to_raw_interval(
            best_tract["tract_start"],
            best_tract["tract_end"],
            raw_clip_start,
            raw_clip_end,
            transform,
        )
        tract_bp = best_tract["prefix_bp"]
        purity = "{:.6f}".format(
            best_tract["purity"]
        )
        path_ratio = "{:.6f}".format(
            best_tract["path_ratio"]
        )
        observed_units = "{:.6f}".format(
            best_tract["observed_units"]
        )
        path_units = "{:.6f}".format(
            best_tract["path_units"]
        )
        matches = best_tract["matches"]
        mismatches = best_tract[
            "mismatches"
        ]
        insertions = best_tract[
            "insertions"
        ]
        deletions = best_tract[
            "deletions"
        ]
        score = best_tract["score"]
        selected_orientation = (
            best_tract["orientation"]
        )
        entry_offset = best_tract[
            "entry_offset"
        ]
        distance_to_clip_end = (
            len(oriented_clip)
            - best_tract["tract_end"]
        )
        reaches_clip_end = str(
            best_tract[
                "reaches_clip_end"
            ]
        ).lower()

        if best_tract[
            "reaches_clip_end"
        ]:
            sizing_status = "lower_bound"
            lower_bound = tract_bp

            if target_side == "GENOMIC_RIGHT":
                evidence_class = (
                    "LEFT_ANCHORED_CENSORED_RIGHT"
                )
            else:
                evidence_class = (
                    "RIGHT_ANCHORED_CENSORED_LEFT"
                )

        else:
            sizing_status = (
                "partial_internal"
            )
            lower_bound = "."

            if target_side == "GENOMIC_RIGHT":
                evidence_class = (
                    "LEFT_ONLY_INTERNAL"
                )
            else:
                evidence_class = (
                    "RIGHT_ONLY_INTERNAL"
                )

    result = {
        "model_id": model_id,
        "projection_id": projection_id,
        "read_id": local_row["read_id"],
        "target_region_id": local_row[
            "expected_target_region_id"
        ],
        "catalog_local_status": local_row[
            "catalog_local_status"
        ],
        "anchor_mapq": local_row[
            "anchor_mapq"
        ],
        "target_facing_genomic_side": (
            target_side
        ),
        "orientation_transform": transform,
        "canonical_motif": motif,
        "motif_length_bp": len(motif),
        "raw_clip_start": raw_clip_start,
        "raw_clip_end": raw_clip_end,
        "raw_clip_bp": len(raw_clip),
        "query_sequence_bp": len(
            query_sequence
        ),
        "query_prefix_matches_oriented_clip": str(
            query_prefix_matches
        ).lower(),
        "isolated_alignment_count": len(
            alignments
        ),
        "best_alignment_strand": (
            best_alignment["strand"]
            if best_alignment
            else "."
        ),
        "best_alignment_mapq": (
            best_alignment["mapq"]
            if best_alignment
            else "."
        ),
        "best_alignment_score": (
            best_alignment[
                "alignment_score"
            ]
            if best_alignment
            else "."
        ),
        "target_entry_reference_offset": (
            target_entry_reference
        ),
        "target_entry_query_offset": (
            target_entry_query
            if target_entry_query
               is not None
            else "."
        ),
        "target_entry_projection_status": (
            projection_status
        ),
        "target_entry_projection_detail": (
            projection_detail
        ),
        "entry_offset_selected_bp": (
            entry_offset
        ),
        "tract_oriented_start": (
            best_tract["tract_start"]
            if best_tract
            else "."
        ),
        "tract_oriented_end": (
            best_tract["tract_end"]
            if best_tract
            else "."
        ),
        "tract_raw_start": tract_raw_start,
        "tract_raw_end": tract_raw_end,
        "tract_bp": tract_bp,
        "repeat_units_observed_read": (
            observed_units
        ),
        "repeat_units_motif_path": (
            path_units
        ),
        "motif_path_to_read_units_ratio": (
            path_ratio
        ),
        "matches": matches,
        "mismatches": mismatches,
        "insertions": insertions,
        "deletions": deletions,
        "purity": purity,
        "score": score,
        "selected_orientation": (
            selected_orientation
        ),
        "distance_from_tract_to_oriented_clip_end_bp": (
            distance_to_clip_end
        ),
        "tract_reaches_expected_raw_end": (
            reaches_clip_end
        ),
        "evidence_class": evidence_class,
        "sizing_status": sizing_status,
        "repeat_bp_estimate": ".",
        "repeat_bp_lower_bound": (
            lower_bound
        ),
        "allele_length_status": (
            "NOT_MEASURABLE_ONE_FLANK_P3"
        ),
        "reference_relative_expansion_status": (
            "NOT_ASSESSED"
        ),
    }

    with progress_lock:
        progress["completed"] += 1
        completed_count = progress[
            "completed"
        ]

        if (
            completed_count
            % PROGRESS_EVERY == 0
            or completed_count
            == len(local_rows)
        ):
            elapsed = (
                time.time()
                - progress["start"]
            )
            rate = (
                completed_count / elapsed
                if elapsed
                else 0.0
            )
            remaining = (
                (
                    len(local_rows)
                    - completed_count
                )
                / rate
                if rate
                else 0.0
            )
            print(
                "[INFO] P3 target-entry sizing {}/{}; "
                "{:.1f}/s; ETA {:.1f} min".format(
                    completed_count,
                    len(local_rows),
                    rate,
                    remaining / 60.0,
                ),
                file=sys.stderr,
                flush=True,
            )

    return result


results = []
failures = []

with ThreadPoolExecutor(
    max_workers=WORKERS
) as executor:
    futures = {
        executor.submit(
            run_pair,
            row,
        ): row["projection_id"]
        for row in local_rows
    }

    for future in as_completed(futures):
        projection_id = futures[future]

        try:
            results.append(
                future.result()
            )
        except Exception as error:
            failures.append(
                (
                    projection_id,
                    str(error),
                )
            )

results.sort(
    key=lambda row: row[
        "projection_id"
    ]
)

if not results:
    raise RuntimeError(
        "No P3 target-entry sizing results"
    )

output_fields = list(
    results[0].keys()
)

with open(
    output_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=output_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(results)

counts = Counter()
summary_groups = {}

for row in results:
    counts[
        "projection_status::{}".format(
            row[
                "target_entry_projection_status"
            ]
        )
    ] += 1
    counts[
        "evidence_class::{}".format(
            row["evidence_class"]
        )
    ] += 1
    counts[
        "sizing_status::{}".format(
            row["sizing_status"]
        )
    ] += 1

    for group_name in [
        "ALL",
        "evidence_class::{}".format(
            row["evidence_class"]
        ),
        "sizing_status::{}".format(
            row["sizing_status"]
        ),
    ]:
        group = summary_groups.setdefault(
            group_name,
            {
                "rows": 0,
                "reads": set(),
                "targets": set(),
                "tract_lengths": [],
                "purities": [],
                "lower_bounds": [],
            },
        )
        group["rows"] += 1
        group["reads"].add(
            row["read_id"]
        )
        group["targets"].add(
            row["target_region_id"]
        )

        if int(row["tract_bp"]) > 0:
            group["tract_lengths"].append(
                int(row["tract_bp"])
            )
            group["purities"].append(
                float(row["purity"])
            )

        if (
            row["repeat_bp_lower_bound"]
            != "."
        ):
            group["lower_bounds"].append(
                int(
                    row[
                        "repeat_bp_lower_bound"
                    ]
                )
            )


def median(values):
    if not values:
        return None

    ordered = sorted(values)
    size = len(ordered)

    if size % 2:
        return float(
            ordered[size // 2]
        )

    return (
        ordered[size // 2 - 1]
        + ordered[size // 2]
    ) / 2.0


summary_fields = [
    "group",
    "rows",
    "unique_reads",
    "unique_targets",
    "tract_bp_median",
    "purity_median",
    "lower_bound_bp_median",
]

with open(
    summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=summary_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for group_name in sorted(
        summary_groups
    ):
        group = summary_groups[
            group_name
        ]
        tract_median = median(
            group["tract_lengths"]
        )
        purity_median = median(
            group["purities"]
        )
        lower_median = median(
            group["lower_bounds"]
        )

        writer.writerow(
            {
                "group": group_name,
                "rows": group["rows"],
                "unique_reads": len(
                    group["reads"]
                ),
                "unique_targets": len(
                    group["targets"]
                ),
                "tract_bp_median": (
                    "{:.6f}".format(
                        tract_median
                    )
                    if tract_median
                       is not None
                    else "."
                ),
                "purity_median": (
                    "{:.6f}".format(
                        purity_median
                    )
                    if purity_median
                       is not None
                    else "."
                ),
                "lower_bound_bp_median": (
                    "{:.6f}".format(
                        lower_median
                    )
                    if lower_median
                       is not None
                    else "."
                ),
            }
        )

evidence_call_count = sum(
    row["sizing_status"]
    in {
        "lower_bound",
        "partial_internal",
    }
    for row in results
)

status = "PASS"

if (
    len(local_rows) != EXPECTED_PAIRS
    or len(query_sequences)
       != EXPECTED_QUERY_ROWS
    or len(reference_sequences)
       != EXPECTED_REFERENCE_ROWS
    or raw_fastq_count
       != EXPECTED_FASTQ
    or missing_metadata
    or missing_queries
    or missing_references
    or missing_raw_reads
    or failures
    or len(results) != EXPECTED_PAIRS
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write(
        "metric\tvalue\n"
    )
    handle.write(
        "expected_pairs\t{}\n".format(
            EXPECTED_PAIRS
        )
    )
    handle.write(
        "local_result_pairs\t{}\n".format(
            len(local_rows)
        )
    )
    handle.write(
        "query_fasta_sequences\t{}\n".format(
            len(query_sequences)
        )
    )
    handle.write(
        "reference_fasta_sequences\t{}\n".format(
            len(reference_sequences)
        )
    )
    handle.write(
        "candidate_fastq_reads\t{}\n".format(
            raw_fastq_count
        )
    )
    handle.write(
        "missing_metadata\t{}\n".format(
            len(missing_metadata)
        )
    )
    handle.write(
        "missing_queries\t{}\n".format(
            len(missing_queries)
        )
    )
    handle.write(
        "missing_references\t{}\n".format(
            len(missing_references)
        )
    )
    handle.write(
        "missing_raw_reads\t{}\n".format(
            len(missing_raw_reads)
        )
    )
    handle.write(
        "pair_failures\t{}\n".format(
            len(failures)
        )
    )
    handle.write(
        "results_written\t{}\n".format(
            len(results)
        )
    )
    handle.write(
        "evidence_calls_emitted\t{}\n".format(
            evidence_call_count
        )
    )

    for key, count in sorted(
        counts.items()
    ):
        handle.write(
            "{}\t{}\n".format(
                key,
                count,
            )
        )

    handle.write(
        "exact_repeat_length_calls_emitted\t0\n"
    )
    handle.write(
        "allele_length_calls_emitted\t0\n"
    )
    handle.write(
        "expansion_calls_emitted\t0\n"
    )
    handle.write(
        "audit_status\t{}\n".format(
            status
        )
    )

if failures:
    with open(
        qc_path + ".failures.tsv",
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            "projection_id\terror\n"
        )

        for projection_id, error in failures:
            handle.write(
                "{}\t{}\n".format(
                    projection_id,
                    error.replace(
                        "\t",
                        " ",
                    ),
                )
            )

if status != "PASS":
    raise SystemExit(
        "P3 target-entry repeat sizing requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$OUTPUT" \
  "$SUMMARY" \
  "$QC" \
  "${QC}.failures.tsv" \
  "$MANIFEST"

find "$WORKDIR" \
  -maxdepth 1 \
  -type d \
  -name 'entry_*' \
  -exec rm -rf {} +

echo
echo "===== MEASURE P3 TARGET-ENTRY REPEAT TRACTS ====="

python "$PY" \
  "$LOCAL_RESULTS" \
  "$PAIR_META" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$RAW_FASTQ" \
  "$OUTPUT" \
  "$SUMMARY" \
  "$QC" \
  "$WORKDIR" \
  "$MODEL_ID" \
  "$EXPECTED_PAIRS" \
  "$EXPECTED_QUERY_FASTA_ROWS" \
  "$EXPECTED_REFERENCE_FASTA_ROWS" \
  "$EXPECTED_RAW_FASTQ_READS" \
  "$WORKERS" \
  "$PROGRESS_EVERY" \
  "$MIN_REPEAT_BP" \
  "$MIN_PURITY" \
  "$MIN_PATH_RATIO" \
  "$MAX_PATH_RATIO" \
  "$ENTRY_OFFSET_TOLERANCE_BP" \
  "$END_TOLERANCE_BP" \
  "$MAX_DELETIONS_BEFORE_BASE"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== P3 TARGET-ENTRY EVIDENCE ====="
column -ts $'\t' "$OUTPUT"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$OUTPUT" \
      "$SUMMARY" \
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

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
