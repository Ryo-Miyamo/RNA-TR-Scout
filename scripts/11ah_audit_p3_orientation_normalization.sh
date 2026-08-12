#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_p3_orientation_normalization_audit_v0.3.1"

SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"
PAIR_META="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
INVENTORY="$PROJECT_ROOT/results/11_p3_inventory/$RUN_ID/p3_proximal_inventory.tsv.gz"

QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"
REFERENCE_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_candidate_references.fasta.gz"
RAW_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
GENOME_FASTA="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa"

OUTDIR="$PROJECT_ROOT/results/11_p3_orientation_audit/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_orientation_audit/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_orientation_audit/$RUN_ID"

OUTPUT="$OUTDIR/p3_orientation_normalization_audit.tsv"
SUMMARY="$OUTDIR/p3_orientation_normalization_audit_summary.tsv"
DECISION="$OUTDIR/p3_orientation_audit_decision.tsv"
QC="$QCDIR/p3_orientation_normalization_audit.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_orientation_audit.manifest.tsv"
PY="$WORKDIR/audit_p3_orientation_normalization.py"

EXPECTED_ROWS=23
EXPECTED_REVERSE_PAF_ROWS=22
EXPECTED_PLUS_PAF_ROWS=1
EXPECTED_QUERY_FASTA_ROWS=1007
EXPECTED_REFERENCE_FASTA_ROWS=1007
EXPECTED_RAW_FASTQ_READS=79176

MIN_TARGET_ENTRY_SUPPORT_BP=12
MIN_EFFECTIVE_COVERAGE=0.70
MIN_IDENTITY=0.70

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$SIZING" \
  "$PAIR_META" \
  "$INVENTORY" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$RAW_FASTQ" \
  "$GENOME_FASTA" \
  "${GENOME_FASTA}.fai"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter
from dataclasses import dataclass

import pysam

(
    sizing_path,
    metadata_path,
    inventory_path,
    query_fasta_path,
    reference_fasta_path,
    raw_fastq_path,
    genome_fasta_path,
    output_path,
    summary_path,
    decision_path,
    qc_path,
    model_id,
    expected_rows_text,
    expected_reverse_text,
    expected_plus_text,
    expected_query_rows_text,
    expected_reference_rows_text,
    expected_fastq_text,
    minimum_target_entry_text,
    minimum_coverage_text,
    minimum_identity_text,
) = sys.argv[1:]

EXPECTED_ROWS = int(expected_rows_text)
EXPECTED_REVERSE = int(expected_reverse_text)
EXPECTED_PLUS = int(expected_plus_text)
EXPECTED_QUERY_ROWS = int(expected_query_rows_text)
EXPECTED_REFERENCE_ROWS = int(expected_reference_rows_text)
EXPECTED_FASTQ = int(expected_fastq_text)

MINIMUM_TARGET_ENTRY = int(minimum_target_entry_text)
MINIMUM_COVERAGE = float(minimum_coverage_text)
MINIMUM_IDENTITY = float(minimum_identity_text)

MATCH_SCORE = 3
MISMATCH_PENALTY = 4
GAP_PENALTY = 4

COMPLEMENT = str.maketrans("ACGTN", "TGCAN")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def resolve_contig(reference, chromosome):
    names = set(reference.references)
    candidates = [chromosome]

    if chromosome.startswith("chr"):
        candidates.append(chromosome[3:])
    else:
        candidates.append("chr" + chromosome)

    if chromosome in {"M", "MT", "chrM", "chrMT"}:
        candidates.extend(["chrM", "MT", "M"])

    for candidate in candidates:
        if candidate in names:
            return candidate

    raise KeyError(
        "No genome FASTA contig corresponding to {}".format(
            chromosome
        )
    )


def expected_transform(strand, target_side):
    if (
        (strand == "+" and target_side == "GENOMIC_RIGHT")
        or
        (strand == "-" and target_side == "GENOMIC_LEFT")
    ):
        return "AS_RAW"

    if (
        (strand == "+" and target_side == "GENOMIC_LEFT")
        or
        (strand == "-" and target_side == "GENOMIC_RIGHT")
    ):
        return "REVERSE_COMPLEMENT"

    return "UNRESOLVED"


@dataclass(frozen=True)
class AlignmentState:
    score: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int


def state_rank(state):
    return (
        state.score,
        state.matches,
        -state.mismatches,
        -state.insertions,
        -state.deletions,
    )


def choose_best(candidates):
    candidates = [
        state
        for state in candidates
        if state is not None
    ]

    if not candidates:
        return None

    return max(candidates, key=state_rank)


def anchored_prefix_alignment(
    query,
    reference,
    required_reference_end,
):
    query_length = len(query)
    reference_length = len(reference)

    previous = [None] * (reference_length + 1)
    previous[0] = AlignmentState(
        score=0,
        matches=0,
        mismatches=0,
        insertions=0,
        deletions=0,
    )

    for reference_index in range(1, reference_length + 1):
        state = previous[reference_index - 1]
        previous[reference_index] = AlignmentState(
            score=state.score - GAP_PENALTY,
            matches=state.matches,
            mismatches=state.mismatches,
            insertions=state.insertions,
            deletions=state.deletions + 1,
        )

    valid_endpoints = []

    for query_index in range(1, query_length + 1):
        current = [None] * (reference_length + 1)

        state = previous[0]
        current[0] = AlignmentState(
            score=state.score - GAP_PENALTY,
            matches=state.matches,
            mismatches=state.mismatches,
            insertions=state.insertions + 1,
            deletions=state.deletions,
        )

        for reference_index in range(1, reference_length + 1):
            query_base = query[query_index - 1]
            reference_base = reference[reference_index - 1]

            diagonal = previous[reference_index - 1]
            if query_base == reference_base:
                diagonal_state = AlignmentState(
                    score=diagonal.score + MATCH_SCORE,
                    matches=diagonal.matches + 1,
                    mismatches=diagonal.mismatches,
                    insertions=diagonal.insertions,
                    deletions=diagonal.deletions,
                )
            else:
                diagonal_state = AlignmentState(
                    score=diagonal.score - MISMATCH_PENALTY,
                    matches=diagonal.matches,
                    mismatches=diagonal.mismatches + 1,
                    insertions=diagonal.insertions,
                    deletions=diagonal.deletions,
                )

            up = previous[reference_index]
            insertion_state = AlignmentState(
                score=up.score - GAP_PENALTY,
                matches=up.matches,
                mismatches=up.mismatches,
                insertions=up.insertions + 1,
                deletions=up.deletions,
            )

            left = current[reference_index - 1]
            deletion_state = AlignmentState(
                score=left.score - GAP_PENALTY,
                matches=left.matches,
                mismatches=left.mismatches,
                insertions=left.insertions,
                deletions=left.deletions + 1,
            )

            current[reference_index] = choose_best(
                [
                    diagonal_state,
                    insertion_state,
                    deletion_state,
                ]
            )

            if reference_index < required_reference_end:
                continue

            state = current[reference_index]
            denominator = (
                state.matches
                + state.mismatches
                + state.insertions
                + state.deletions
            )
            identity = (
                state.matches / denominator
                if denominator
                else 0.0
            )
            effective_denominator = min(
                query_length,
                reference_length,
            )
            effective_coverage = (
                query_index / effective_denominator
                if effective_denominator
                else 0.0
            )

            if (
                identity >= MINIMUM_IDENTITY
                and effective_coverage >= MINIMUM_COVERAGE
                and state.score > 0
            ):
                valid_endpoints.append(
                    {
                        "score": state.score,
                        "matches": state.matches,
                        "mismatches": state.mismatches,
                        "insertions": state.insertions,
                        "deletions": state.deletions,
                        "query_end": query_index,
                        "reference_end": reference_index,
                        "identity": identity,
                        "effective_coverage": effective_coverage,
                    }
                )

        previous = current

    if not valid_endpoints:
        return None

    return max(
        valid_endpoints,
        key=lambda row: (
            row["score"],
            row["matches"],
            row["reference_end"],
            row["query_end"],
        ),
    )


with open(
    sizing_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    sizing_rows = list(
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

with gzip.open(
    inventory_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    inventory = {
        row["projection_id"]: row
        for row in csv.DictReader(
            handle,
            delimiter="\t",
        )
    }

query_sequences = {}
with pysam.FastxFile(query_fasta_path) as source:
    for entry in source:
        query_sequences[entry.name] = entry.sequence.upper()

reference_sequences = {}
with pysam.FastxFile(reference_fasta_path) as source:
    for entry in source:
        reference_sequences[entry.name] = entry.sequence.upper()

required_read_ids = {
    row["read_id"]
    for row in sizing_rows
}

raw_reads = {}
raw_fastq_count = 0
with pysam.FastxFile(raw_fastq_path) as source:
    for entry in source:
        raw_fastq_count += 1
        if entry.name in required_read_ids:
            raw_reads[entry.name] = entry.sequence.upper()

genome = pysam.FastaFile(genome_fasta_path)

missing_metadata = {
    row["projection_id"]
    for row in sizing_rows
    if row["projection_id"] not in metadata
}
missing_inventory = {
    row["projection_id"]
    for row in sizing_rows
    if row["projection_id"] not in inventory
}
missing_queries = {
    row["projection_id"]
    for row in sizing_rows
    if row["projection_id"] not in query_sequences
}
missing_raw_reads = required_read_ids - set(raw_reads)

output_rows = []
counts = Counter()
geometry_errors = 0

for sizing in sizing_rows:
    projection_id = sizing["projection_id"]
    meta = metadata[projection_id]
    inv = inventory[projection_id]

    stored_query = query_sequences[projection_id]
    stored_reference = reference_sequences[
        meta["reference_id"]
    ]
    raw_read = raw_reads[sizing["read_id"]]

    raw_clip_start = int(meta["raw_clip_start"])
    raw_clip_end = int(meta["raw_clip_end"])
    raw_clip = raw_read[raw_clip_start:raw_clip_end]

    strand = inv["strand"]
    target_side = inv["target_facing_genomic_side"]
    independently_expected_transform = expected_transform(
        strand,
        target_side,
    )

    if independently_expected_transform == "AS_RAW":
        independently_oriented_clip = raw_clip
    elif independently_expected_transform == "REVERSE_COMPLEMENT":
        independently_oriented_clip = reverse_complement(raw_clip)
    else:
        independently_oriented_clip = ""

    expected_query_prefix = independently_oriented_clip[
        :len(stored_query)
    ]

    stored_transform = meta["orientation_transform"]

    query_matches_expected = (
        stored_query == expected_query_prefix
    )
    query_matches_reverse_expected = (
        stored_query
        == reverse_complement(expected_query_prefix)
    )

    chromosome = inv["target_chrom"]
    contig = resolve_contig(genome, chromosome)
    block_start = int(inv["selected_block_start"])
    block_end = int(inv["selected_block_end"])
    target_start = int(inv["target_start"])
    target_end = int(inv["target_end"])
    target_entry_bp = int(meta["target_entry_bp"])

    if target_side == "GENOMIC_RIGHT":
        bridge_bp_independent = target_start - block_end
        entry_end = min(
            target_end,
            target_start + target_entry_bp,
        )

        if bridge_bp_independent < 0:
            geometry_errors += 1
            independently_expected_reference = ""
        else:
            independently_expected_reference = genome.fetch(
                contig,
                block_end,
                entry_end,
            ).upper()

    elif target_side == "GENOMIC_LEFT":
        bridge_bp_independent = block_start - target_end
        entry_start = max(
            target_start,
            target_end - target_entry_bp,
        )

        if bridge_bp_independent < 0:
            geometry_errors += 1
            independently_expected_reference = ""
        else:
            independently_expected_reference = reverse_complement(
                genome.fetch(
                    contig,
                    entry_start,
                    block_start,
                ).upper()
            )

    else:
        bridge_bp_independent = -1
        independently_expected_reference = ""
        geometry_errors += 1

    reference_matches_expected = (
        stored_reference
        == independently_expected_reference
    )
    reference_matches_reverse_expected = (
        stored_reference
        == reverse_complement(
            independently_expected_reference
        )
    )

    required_reference_end = (
        int(meta["bridge_bp"])
        + min(
            int(meta["target_entry_bp"]),
            MINIMUM_TARGET_ENTRY,
        )
    )

    forward_alignment = anchored_prefix_alignment(
        stored_query,
        stored_reference,
        required_reference_end,
    )
    reverse_alignment = anchored_prefix_alignment(
        reverse_complement(stored_query),
        stored_reference,
        required_reference_end,
    )

    forward_valid = forward_alignment is not None
    reverse_valid = reverse_alignment is not None

    if stored_transform != independently_expected_transform:
        diagnosis = "QUERY_TRANSFORM_METADATA_DISAGREES_WITH_GEOMETRY"

    elif not query_matches_expected:
        if query_matches_reverse_expected:
            diagnosis = "STORED_QUERY_IS_REVERSE_OF_GEOMETRIC_EXPECTATION"
        else:
            diagnosis = "STORED_QUERY_CONTENT_OR_BOUNDARY_MISMATCH"

    elif not reference_matches_expected:
        if reference_matches_reverse_expected:
            diagnosis = "STORED_REFERENCE_IS_REVERSE_OF_GEOMETRIC_EXPECTATION"
        else:
            diagnosis = "STORED_REFERENCE_CONTENT_OR_BOUNDARY_MISMATCH"

    elif forward_valid:
        if (
            reverse_valid
            and reverse_alignment["score"]
                > forward_alignment["score"]
        ):
            diagnosis = (
                "NORMALIZATION_CORRECT_FORWARD_VALID_BUT_REVERSE_SCORES_HIGHER"
            )
        else:
            diagnosis = "NORMALIZATION_CORRECT_FORWARD_BRIDGE_SUPPORTED"

    elif reverse_valid:
        diagnosis = (
            "NORMALIZATION_CORRECT_REVERSE_ONLY_SEQUENCE_COMPATIBILITY"
        )

    else:
        diagnosis = (
            "NORMALIZATION_CORRECT_NO_ANCHORED_TARGET_ENTRY_ALIGNMENT"
        )

    counts[
        "diagnosis::{}".format(diagnosis)
    ] += 1
    counts[
        "stored_paf_strand::{}".format(
            sizing["best_alignment_strand"]
        )
    ] += 1
    counts[
        "expected_transform::{}".format(
            independently_expected_transform
        )
    ] += 1
    counts[
        "stored_transform::{}".format(
            stored_transform
        )
    ] += 1

    output_rows.append(
        {
            "model_id": model_id,
            "projection_id": projection_id,
            "read_id": sizing["read_id"],
            "target_region_id": sizing["target_region_id"],
            "alignment_strand_from_inventory": strand,
            "target_facing_genomic_side": target_side,
            "stored_orientation_transform": stored_transform,
            "independently_expected_orientation_transform": (
                independently_expected_transform
            ),
            "transform_matches_geometry": str(
                stored_transform
                == independently_expected_transform
            ).lower(),
            "raw_clip_start": raw_clip_start,
            "raw_clip_end": raw_clip_end,
            "raw_clip_bp": len(raw_clip),
            "stored_query_bp": len(stored_query),
            "stored_query_matches_expected_oriented_prefix": str(
                query_matches_expected
            ).lower(),
            "stored_query_matches_reverse_expected_prefix": str(
                query_matches_reverse_expected
            ).lower(),
            "metadata_bridge_bp": meta["bridge_bp"],
            "independent_bridge_bp": bridge_bp_independent,
            "bridge_geometry_matches_metadata": str(
                bridge_bp_independent
                == int(meta["bridge_bp"])
            ).lower(),
            "stored_reference_bp": len(stored_reference),
            "independent_reference_bp": len(
                independently_expected_reference
            ),
            "stored_reference_matches_independent_reference": str(
                reference_matches_expected
            ).lower(),
            "stored_reference_matches_reverse_independent_reference": str(
                reference_matches_reverse_expected
            ).lower(),
            "previous_best_paf_strand": sizing[
                "best_alignment_strand"
            ],
            "previous_target_entry_projection_status": sizing[
                "target_entry_projection_status"
            ],
            "forward_anchored_target_entry_valid": str(
                forward_valid
            ).lower(),
            "forward_score": (
                forward_alignment["score"]
                if forward_alignment
                else "."
            ),
            "forward_identity": (
                "{:.6f}".format(
                    forward_alignment["identity"]
                )
                if forward_alignment
                else "."
            ),
            "forward_effective_coverage": (
                "{:.6f}".format(
                    forward_alignment[
                        "effective_coverage"
                    ]
                )
                if forward_alignment
                else "."
            ),
            "forward_reference_end": (
                forward_alignment["reference_end"]
                if forward_alignment
                else "."
            ),
            "reverse_anchored_target_entry_valid": str(
                reverse_valid
            ).lower(),
            "reverse_score": (
                reverse_alignment["score"]
                if reverse_alignment
                else "."
            ),
            "reverse_identity": (
                "{:.6f}".format(
                    reverse_alignment["identity"]
                )
                if reverse_alignment
                else "."
            ),
            "reverse_effective_coverage": (
                "{:.6f}".format(
                    reverse_alignment[
                        "effective_coverage"
                    ]
                )
                if reverse_alignment
                else "."
            ),
            "reverse_reference_end": (
                reverse_alignment["reference_end"]
                if reverse_alignment
                else "."
            ),
            "orientation_diagnosis": diagnosis,
            "stored_query_sequence": stored_query,
            "expected_query_prefix": expected_query_prefix,
            "stored_reference_sequence": stored_reference,
            "independent_reference_sequence": (
                independently_expected_reference
            ),
            "standard_p3_evidence_status": "NOT_RECLASSIFIED_IN_AUDIT",
            "allele_length_status": "NOT_ASSESSED",
            "expansion_status": "NOT_ASSESSED",
        }
    )

genome.close()

fields = list(output_rows[0].keys())

with open(
    output_path,
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
    writer.writerows(output_rows)

with open(
    summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.writer(
        handle,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(["group", "rows"])

    for key, value in sorted(counts.items()):
        writer.writerow([key, value])

query_transform_mismatches = sum(
    row["transform_matches_geometry"] == "false"
    for row in output_rows
)
query_sequence_mismatches = sum(
    row[
        "stored_query_matches_expected_oriented_prefix"
    ] == "false"
    for row in output_rows
)
reference_sequence_mismatches = sum(
    row[
        "stored_reference_matches_independent_reference"
    ] == "false"
    for row in output_rows
)
forward_valid_rows = sum(
    row["forward_anchored_target_entry_valid"] == "true"
    for row in output_rows
)
reverse_valid_rows = sum(
    row["reverse_anchored_target_entry_valid"] == "true"
    for row in output_rows
)

if query_transform_mismatches:
    primary_conclusion = (
        "QUERY_ORIENTATION_TRANSFORM_BUG_DETECTED"
    )
elif query_sequence_mismatches:
    primary_conclusion = (
        "QUERY_SEQUENCE_CONSTRUCTION_BUG_DETECTED"
    )
elif reference_sequence_mismatches:
    primary_conclusion = (
        "REFERENCE_SEQUENCE_CONSTRUCTION_BUG_DETECTED"
    )
elif forward_valid_rows:
    primary_conclusion = (
        "NORMALIZATION_GEOMETRY_CORRECT_RESELECT_VALID_FORWARD_ALIGNMENT"
    )
else:
    primary_conclusion = (
        "NORMALIZATION_GEOMETRY_CORRECT_BUT_NO_FORWARD_BRIDGE_SUPPORT"
    )

with open(
    decision_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "primary_conclusion\t{}\n".format(
            primary_conclusion
        )
    )
    handle.write(
        "query_transform_mismatches\t{}\n".format(
            query_transform_mismatches
        )
    )
    handle.write(
        "query_sequence_mismatches\t{}\n".format(
            query_sequence_mismatches
        )
    )
    handle.write(
        "reference_sequence_mismatches\t{}\n".format(
            reference_sequence_mismatches
        )
    )
    handle.write(
        "forward_valid_target_entry_rows\t{}\n".format(
            forward_valid_rows
        )
    )
    handle.write(
        "reverse_valid_target_entry_rows\t{}\n".format(
            reverse_valid_rows
        )
    )
    handle.write(
        "next_rule\tDo not freeze PAF strand until this audit is interpreted.\n"
    )

observed_reverse = sum(
    row["best_alignment_strand"] == "-"
    for row in sizing_rows
)
observed_plus = sum(
    row["best_alignment_strand"] == "+"
    for row in sizing_rows
)

status = "PASS"

if (
    len(sizing_rows) != EXPECTED_ROWS
    or observed_reverse != EXPECTED_REVERSE
    or observed_plus != EXPECTED_PLUS
    or len(query_sequences) != EXPECTED_QUERY_ROWS
    or len(reference_sequences) != EXPECTED_REFERENCE_ROWS
    or raw_fastq_count != EXPECTED_FASTQ
    or missing_metadata
    or missing_inventory
    or missing_queries
    or missing_raw_reads
    or geometry_errors
    or len(output_rows) != EXPECTED_ROWS
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "input_rows\t{}\n".format(len(sizing_rows))
    )
    handle.write(
        "previous_reverse_paf_rows\t{}\n".format(
            observed_reverse
        )
    )
    handle.write(
        "previous_plus_paf_rows\t{}\n".format(
            observed_plus
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
        "raw_fastq_reads\t{}\n".format(
            raw_fastq_count
        )
    )
    handle.write(
        "missing_metadata\t{}\n".format(
            len(missing_metadata)
        )
    )
    handle.write(
        "missing_inventory\t{}\n".format(
            len(missing_inventory)
        )
    )
    handle.write(
        "missing_queries\t{}\n".format(
            len(missing_queries)
        )
    )
    handle.write(
        "missing_raw_reads\t{}\n".format(
            len(missing_raw_reads)
        )
    )
    handle.write(
        "geometry_errors\t{}\n".format(
            geometry_errors
        )
    )
    handle.write(
        "query_transform_mismatches\t{}\n".format(
            query_transform_mismatches
        )
    )
    handle.write(
        "query_sequence_mismatches\t{}\n".format(
            query_sequence_mismatches
        )
    )
    handle.write(
        "reference_sequence_mismatches\t{}\n".format(
            reference_sequence_mismatches
        )
    )
    handle.write(
        "forward_valid_target_entry_rows\t{}\n".format(
            forward_valid_rows
        )
    )
    handle.write(
        "reverse_valid_target_entry_rows\t{}\n".format(
            reverse_valid_rows
        )
    )

    for key, value in sorted(counts.items()):
        handle.write(
            "{}\t{}\n".format(key, value)
        )

    handle.write(
        "evidence_calls_emitted\t0\n"
    )
    handle.write(
        "allele_length_calls_emitted\t0\n"
    )
    handle.write(
        "expansion_calls_emitted\t0\n"
    )
    handle.write(
        "audit_status\t{}\n".format(status)
    )

if status != "PASS":
    raise SystemExit(
        "P3 orientation normalization audit requires review"
    )
PY

python -m py_compile "$PY"

rm -f \
  "$OUTPUT" \
  "$SUMMARY" \
  "$DECISION" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$SIZING" \
  "$PAIR_META" \
  "$INVENTORY" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$RAW_FASTQ" \
  "$GENOME_FASTA" \
  "$OUTPUT" \
  "$SUMMARY" \
  "$DECISION" \
  "$QC" \
  "$MODEL_ID" \
  "$EXPECTED_ROWS" \
  "$EXPECTED_REVERSE_PAF_ROWS" \
  "$EXPECTED_PLUS_PAF_ROWS" \
  "$EXPECTED_QUERY_FASTA_ROWS" \
  "$EXPECTED_REFERENCE_FASTA_ROWS" \
  "$EXPECTED_RAW_FASTQ_READS" \
  "$MIN_TARGET_ENTRY_SUPPORT_BP" \
  "$MIN_EFFECTIVE_COVERAGE" \
  "$MIN_IDENTITY"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== DECISION ====="
column -ts $'\t' "$DECISION"

echo
echo "===== SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== ROW-LEVEL AUDIT ====="
column -ts $'\t' "$OUTPUT"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$OUTPUT" \
      "$SUMMARY" \
      "$DECISION" \
      "$QC"
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
