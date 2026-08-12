#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_repeat_event_flank_rescue_v0.3.1"

ALIGNMENT_SUMMARY="$PROJECT_ROOT/results/11_observed_reference_alignment/$RUN_ID/observed_to_reference_locus.summary.tsv"
EVENTS="$PROJECT_ROOT/results/11_extreme_nonexact_refined/$RUN_ID/extreme_nonexact_events.refined.tsv"
FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_flank_rescue/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_flank_rescue/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_flank_rescue/$RUN_ID"
DATADIR="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_flank_rescue"

CONTEXT_FASTA="$DATADIR/reference_compatible_event_flanks.fasta.gz"
CONTEXT_META="$OUTDIR/reference_compatible_event_flanks.metadata.tsv"
PAF="$OUTDIR/reference_compatible_event_flanks.whole_genome.paf"
PLACEMENTS="$OUTDIR/reference_compatible_event_flank_placements.tsv"
SUMMARY="$OUTDIR/reference_compatible_event_flank_rescue.tsv"
QC="$QCDIR/reference_compatible_event_flank_rescue.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.flank_rescue.manifest.tsv"

PREPARE_PY="$WORKDIR/prepare_event_flanks.py"
PARSE_PY="$WORKDIR/parse_flank_alignments.py"
PLAIN_FASTA="$WORKDIR/reference_compatible_event_flanks.fa"

EXPECTED_EVENTS=2
EXPECTED_CONTEXTS=3
MIN_CONTEXT_BP=20
MAX_CONTEXT_BP=2000
END_TOLERANCE_BP=10
MIN_ANCHOR_QUERY_COVERAGE=0.80
MIN_ANCHOR_IDENTITY=0.70
MIN_ANCHOR_MAPQ=20
NEAR_BEST_SCORE_FRACTION=0.95
MAX_ANCHOR_DISTANCE_BP=100000

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR" "$DATADIR"

for path in "$ALIGNMENT_SUMMARY" "$EVENTS" "$FASTQ"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

resolve_genome_index() {
    local candidates=(
        "${MINIMAP2_INDEX:-}"
        "${REFERENCE_MMI:-}"
        "$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.mmi"
        "$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa.mmi"
        "$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa"
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
        find "$PROJECT_ROOT/refs" \
          -maxdepth 5 \
          -type f \
          \( \
            -name '*GRCh38*.mmi' \
            -o -name 'GRCh38.primary_assembly.genome.fa' \
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

GENOME_INDEX="$(resolve_genome_index)" || {
    echo "ERROR: minimap2 genome index/reference could not be resolved" >&2
    exit 1
}

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
model_id	$MODEL_ID	Raw-read flank rescue for reference-compatible repeat-only events
genome_index	$GENOME_INDEX	Whole-genome reference or minimap2 index
minimum_context_bp	$MIN_CONTEXT_BP	Shorter raw-read contexts are not mapped
maximum_context_bp	$MAX_CONTEXT_BP	Maximum bases retained from each event side
end_tolerance_bp	$END_TOLERANCE_BP	Event within this distance of raw-read end is end-truncated
minimum_anchor_query_coverage	$MIN_ANCHOR_QUERY_COVERAGE	Required context coverage
minimum_anchor_identity	$MIN_ANCHOR_IDENTITY	Required alignment identity
minimum_anchor_mapq	$MIN_ANCHOR_MAPQ	Required mapping quality
near_best_score_fraction	$NEAR_BEST_SCORE_FRACTION	Alternative placement threshold
maximum_anchor_distance_bp	$MAX_ANCHOR_DISTANCE_BP	Maximum distance from locus on expected genomic side
rescue_semantics	candidate_reclassification_only	No allele length or expansion call
EOF

cat > "$PREPARE_PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import math
import re
import sys
from collections import Counter

import pysam

(
    alignment_summary_path,
    events_path,
    fastq_path,
    fasta_gz_path,
    plain_fasta_path,
    metadata_path,
    expected_events_text,
    expected_contexts_text,
    minimum_context_text,
    maximum_context_text,
    end_tolerance_text,
) = sys.argv[1:]

EXPECTED_EVENTS = int(expected_events_text)
EXPECTED_CONTEXTS = int(expected_contexts_text)
MINIMUM_CONTEXT = int(minimum_context_text)
MAXIMUM_CONTEXT = int(maximum_context_text)
END_TOLERANCE = int(end_tolerance_text)


def entropy(sequence):
    if not sequence:
        return 0.0

    counts = Counter(sequence)
    length = len(sequence)

    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def longest_homopolymer(sequence):
    if not sequence:
        return 0, "."

    best_length = 1
    best_base = sequence[0]
    current_length = 1
    current_base = sequence[0]

    for base in sequence[1:]:
        if base == current_base:
            current_length += 1
        else:
            if current_length > best_length:
                best_length = current_length
                best_base = current_base

            current_length = 1
            current_base = base

    if current_length > best_length:
        best_length = current_length
        best_base = current_base

    return best_length, best_base


def parse_cluster(cluster_id):
    match = re.match(
        r"^EXTLOC_[0-9]+_(.+)_([0-9]+)_([0-9]+)$",
        cluster_id,
    )

    if match is None:
        raise ValueError(
            "Unrecognized cluster ID: {}".format(cluster_id)
        )

    return match.group(1), int(match.group(2)), int(match.group(3))


with open(
    alignment_summary_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    selected = {
        row["event_id"]: row
        for row in csv.DictReader(handle, delimiter="\t")
    }

with open(
    events_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    event_lookup = {
        row["event_id"]: row
        for row in csv.DictReader(handle, delimiter="\t")
    }

missing_events = set(selected) - set(event_lookup)

if missing_events:
    raise RuntimeError(
        "Events missing from refined event table: {}".format(
            ",".join(sorted(missing_events))
        )
    )

read_ids = {
    event_lookup[event_id]["read_id"]
    for event_id in selected
}

reads = {}

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        if entry.name in read_ids:
            reads[entry.name] = entry.sequence.upper()

missing_reads = read_ids - set(reads)

metadata_rows = []
fasta_records = []

for event_id in sorted(selected):
    summary = selected[event_id]
    event = event_lookup[event_id]
    read_id = event["read_id"]
    sequence = reads[read_id]
    read_length = len(sequence)
    event_start = int(event["event_start"])
    event_end = int(event["event_end"])

    if not (0 <= event_start < event_end <= read_length):
        raise RuntimeError(
            "Invalid event interval {}: {}-{} / {}".format(
                event_id,
                event_start,
                event_end,
                read_length,
            )
        )

    cluster_id = summary["reference_locus_id"]
    cluster_chrom, cluster_start, cluster_end = parse_cluster(
        cluster_id
    )
    reference_strand = summary["best_strand"]

    raw_contexts = [
        (
            "LEFT",
            max(0, event_start - MAXIMUM_CONTEXT),
            event_start,
        ),
        (
            "RIGHT",
            event_end,
            min(read_length, event_end + MAXIMUM_CONTEXT),
        ),
    ]

    for side, context_start, context_end in raw_contexts:
        context = sequence[context_start:context_end]

        if len(context) < MINIMUM_CONTEXT:
            continue

        context_id = "{}__{}".format(event_id, side)
        counts = Counter(context)
        dominant_base = max(
            "ACGTN",
            key=lambda base: counts.get(base, 0),
        )
        dominant_fraction = (
            counts.get(dominant_base, 0) / len(context)
        )
        hp_length, hp_base = longest_homopolymer(context)

        fasta_records.append(
            (context_id, context)
        )

        metadata_rows.append(
            {
                "context_id": context_id,
                "event_id": event_id,
                "read_id": read_id,
                "side": side,
                "read_length_bp": read_length,
                "event_start": event_start,
                "event_end": event_end,
                "event_bp": event_end - event_start,
                "event_touches_raw_start": str(
                    event_start <= END_TOLERANCE
                ).lower(),
                "event_touches_raw_end": str(
                    read_length - event_end <= END_TOLERANCE
                ).lower(),
                "context_start": context_start,
                "context_end": context_end,
                "context_bp": len(context),
                "context_entropy_bits": "{:.6f}".format(
                    entropy(context)
                ),
                "dominant_base": dominant_base,
                "dominant_base_fraction": "{:.6f}".format(
                    dominant_fraction
                ),
                "longest_homopolymer_bp": hp_length,
                "longest_homopolymer_base": hp_base,
                "longest_homopolymer_fraction": "{:.6f}".format(
                    hp_length / len(context)
                ),
                "reference_locus_id": cluster_id,
                "reference_locus_chrom": cluster_chrom,
                "reference_locus_start": cluster_start,
                "reference_locus_end": cluster_end,
                "event_reference_strand": reference_strand,
            }
        )

if len(selected) != EXPECTED_EVENTS:
    raise RuntimeError(
        "Expected {} events, observed {}".format(
            EXPECTED_EVENTS,
            len(selected),
        )
    )

if len(metadata_rows) != EXPECTED_CONTEXTS:
    raise RuntimeError(
        "Expected {} contexts, observed {}".format(
            EXPECTED_CONTEXTS,
            len(metadata_rows),
        )
    )

if missing_reads:
    raise RuntimeError(
        "Missing FASTQ reads: {}".format(
            ",".join(sorted(missing_reads))
        )
    )

with gzip.open(
    fasta_gz_path,
    "wt",
    encoding="utf-8",
) as handle:
    for context_id, sequence in fasta_records:
        handle.write(
            ">{}\n{}\n".format(
                context_id,
                sequence,
            )
        )

with open(
    plain_fasta_path,
    "w",
    encoding="utf-8",
) as handle:
    for context_id, sequence in fasta_records:
        handle.write(
            ">{}\n{}\n".format(
                context_id,
                sequence,
            )
        )

metadata_fields = [
    "context_id",
    "event_id",
    "read_id",
    "side",
    "read_length_bp",
    "event_start",
    "event_end",
    "event_bp",
    "event_touches_raw_start",
    "event_touches_raw_end",
    "context_start",
    "context_end",
    "context_bp",
    "context_entropy_bits",
    "dominant_base",
    "dominant_base_fraction",
    "longest_homopolymer_bp",
    "longest_homopolymer_base",
    "longest_homopolymer_fraction",
    "reference_locus_id",
    "reference_locus_chrom",
    "reference_locus_start",
    "reference_locus_end",
    "event_reference_strand",
]

with open(
    metadata_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=metadata_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(metadata_rows)
PY

cat > "$PARSE_PY" <<'PY'
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict

(
    paf_path,
    metadata_path,
    placements_path,
    summary_path,
    qc_path,
    model_id,
    expected_events_text,
    expected_contexts_text,
    minimum_query_coverage_text,
    minimum_identity_text,
    minimum_mapq_text,
    near_best_fraction_text,
    maximum_distance_text,
) = sys.argv[1:]

EXPECTED_EVENTS = int(expected_events_text)
EXPECTED_CONTEXTS = int(expected_contexts_text)
MINIMUM_QUERY_COVERAGE = float(minimum_query_coverage_text)
MINIMUM_IDENTITY = float(minimum_identity_text)
MINIMUM_MAPQ = int(minimum_mapq_text)
NEAR_BEST_FRACTION = float(near_best_fraction_text)
MAXIMUM_DISTANCE = int(maximum_distance_text)


def normalize_chromosome(chromosome):
    value = chromosome

    if value.startswith("chr"):
        value = value[3:]

    if value == "M":
        value = "MT"

    return value


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


with open(
    metadata_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    metadata = {
        row["context_id"]: row
        for row in csv.DictReader(handle, delimiter="\t")
    }

alignments = []

with open(
    paf_path,
    "r",
    encoding="utf-8",
) as handle:
    for line in handle:
        line = line.rstrip("\n")

        if not line:
            continue

        fields = line.split("\t")
        tags = parse_tags(fields[12:])

        query_length = int(fields[1])
        query_start = int(fields[2])
        query_end = int(fields[3])
        target_start = int(fields[7])
        target_end = int(fields[8])
        residue_matches = int(fields[9])
        alignment_block_length = int(fields[10])

        alignments.append(
            {
                "context_id": fields[0],
                "query_length": query_length,
                "query_start": query_start,
                "query_end": query_end,
                "strand": fields[4],
                "chrom": fields[5],
                "chrom_length": int(fields[6]),
                "target_start": target_start,
                "target_end": target_end,
                "residue_matches": residue_matches,
                "alignment_block_length": alignment_block_length,
                "mapq": int(fields[11]),
                "alignment_score": tags.get(
                    "AS",
                    residue_matches,
                ),
                "alignment_type": tags.get("tp", "."),
                "identity": (
                    residue_matches / alignment_block_length
                    if alignment_block_length
                    else 0.0
                ),
                "query_coverage": (
                    (query_end - query_start) / query_length
                    if query_length
                    else 0.0
                ),
            }
        )

by_context = defaultdict(list)

for row in alignments:
    by_context[row["context_id"]].append(row)

placement_fields = [
    "model_id",
    "context_id",
    "event_id",
    "side",
    "alignment_rank",
    "is_near_best",
    "alignment_type",
    "chrom",
    "target_start",
    "target_end",
    "strand",
    "query_length",
    "query_start",
    "query_end",
    "query_coverage",
    "identity",
    "mapq",
    "alignment_score",
    "same_chromosome_as_locus",
    "genomic_relation_to_locus",
    "distance_to_locus_bp",
    "expected_genomic_side",
    "expected_side_match",
    "anchor_quality_pass",
    "anchor_candidate",
]

placement_rows = []
context_summary = {}
counts = Counter()

for context_id in sorted(metadata):
    meta = metadata[context_id]
    rows = by_context.get(context_id, [])

    rows.sort(
        key=lambda row: (
            row["alignment_score"],
            row["query_coverage"],
            row["identity"],
            row["mapq"],
        ),
        reverse=True,
    )

    best_score = (
        rows[0]["alignment_score"]
        if rows
        else None
    )

    near_best_count = sum(
        row["alignment_score"]
        >= best_score * NEAR_BEST_FRACTION
        for row in rows
    ) if rows else 0

    best_anchor = None

    for rank, row in enumerate(rows, start=1):
        same_chromosome = (
            normalize_chromosome(row["chrom"])
            == normalize_chromosome(
                meta["reference_locus_chrom"]
            )
        )

        locus_start = int(
            meta["reference_locus_start"]
        )
        locus_end = int(
            meta["reference_locus_end"]
        )

        if not same_chromosome:
            relation = "OTHER_CHROMOSOME"
            distance = -1
        elif row["target_end"] <= locus_start:
            relation = "UPSTREAM"
            distance = locus_start - row["target_end"]
        elif row["target_start"] >= locus_end:
            relation = "DOWNSTREAM"
            distance = row["target_start"] - locus_end
        else:
            relation = "OVERLAPS_LOCUS"
            distance = 0

        event_strand = meta["event_reference_strand"]
        side = meta["side"]

        if event_strand == "+":
            expected_side = (
                "UPSTREAM"
                if side == "LEFT"
                else "DOWNSTREAM"
            )
        else:
            expected_side = (
                "DOWNSTREAM"
                if side == "LEFT"
                else "UPSTREAM"
            )

        expected_side_match = relation == expected_side

        dominant_fraction = float(
            meta["dominant_base_fraction"]
        )
        entropy = float(
            meta["context_entropy_bits"]
        )

        complexity_pass = (
            entropy >= 1.0
            and dominant_fraction < 0.80
        )

        quality_pass = (
            row["query_coverage"]
            >= MINIMUM_QUERY_COVERAGE
            and row["identity"]
            >= MINIMUM_IDENTITY
            and row["mapq"] >= MINIMUM_MAPQ
            and near_best_count == 1
            and complexity_pass
        )

        anchor_candidate = (
            quality_pass
            and same_chromosome
            and expected_side_match
            and distance <= MAXIMUM_DISTANCE
        )

        placement = {
            "model_id": model_id,
            "context_id": context_id,
            "event_id": meta["event_id"],
            "side": side,
            "alignment_rank": rank,
            "is_near_best": str(
                row["alignment_score"]
                >= best_score * NEAR_BEST_FRACTION
            ).lower(),
            "alignment_type": row["alignment_type"],
            "chrom": row["chrom"],
            "target_start": row["target_start"],
            "target_end": row["target_end"],
            "strand": row["strand"],
            "query_length": row["query_length"],
            "query_start": row["query_start"],
            "query_end": row["query_end"],
            "query_coverage": "{:.6f}".format(
                row["query_coverage"]
            ),
            "identity": "{:.6f}".format(
                row["identity"]
            ),
            "mapq": row["mapq"],
            "alignment_score": row[
                "alignment_score"
            ],
            "same_chromosome_as_locus": str(
                same_chromosome
            ).lower(),
            "genomic_relation_to_locus": relation,
            "distance_to_locus_bp": distance,
            "expected_genomic_side": expected_side,
            "expected_side_match": str(
                expected_side_match
            ).lower(),
            "anchor_quality_pass": str(
                quality_pass
            ).lower(),
            "anchor_candidate": str(
                anchor_candidate
            ).lower(),
        }

        placement_rows.append(placement)

        if anchor_candidate and best_anchor is None:
            best_anchor = placement

    context_summary[context_id] = {
        "alignment_count": len(rows),
        "near_best_count": near_best_count,
        "best_anchor": best_anchor,
    }

event_contexts = defaultdict(dict)

for context_id, meta in metadata.items():
    event_contexts[meta["event_id"]][
        meta["side"]
    ] = meta

summary_fields = [
    "model_id",
    "event_id",
    "read_id",
    "read_length_bp",
    "event_start",
    "event_end",
    "event_bp",
    "event_touches_raw_start",
    "event_touches_raw_end",
    "left_context_bp",
    "right_context_bp",
    "left_alignment_count",
    "right_alignment_count",
    "left_near_best_count",
    "right_near_best_count",
    "left_anchor_candidate",
    "right_anchor_candidate",
    "left_anchor_chrom",
    "left_anchor_start",
    "left_anchor_end",
    "left_anchor_distance_bp",
    "right_anchor_chrom",
    "right_anchor_start",
    "right_anchor_end",
    "right_anchor_distance_bp",
    "flank_rescue_status",
    "allele_length_status",
    "reference_relative_expansion_status",
    "interpretation",
]

summary_rows = []

for event_id in sorted(event_contexts):
    sides = event_contexts[event_id]
    representative = (
        sides.get("LEFT")
        or sides.get("RIGHT")
    )

    left_meta = sides.get("LEFT")
    right_meta = sides.get("RIGHT")

    left_summary = (
        context_summary[left_meta["context_id"]]
        if left_meta
        else {
            "alignment_count": 0,
            "near_best_count": 0,
            "best_anchor": None,
        }
    )
    right_summary = (
        context_summary[right_meta["context_id"]]
        if right_meta
        else {
            "alignment_count": 0,
            "near_best_count": 0,
            "best_anchor": None,
        }
    )

    left_anchor = left_summary["best_anchor"]
    right_anchor = right_summary["best_anchor"]

    touches_start = (
        representative[
            "event_touches_raw_start"
        ] == "true"
    )
    touches_end = (
        representative[
            "event_touches_raw_end"
        ] == "true"
    )

    if left_anchor and right_anchor:
        rescue_status = "RESCUED_BOTH_FLANKS_CANDIDATE"
        allele_status = "EXACT_SPAN_RESCUE_REQUIRES_INTERVAL_VALIDATION"

    elif left_anchor and touches_end:
        rescue_status = "LEFT_FLANK_RIGHT_CENSORED_CANDIDATE"
        allele_status = "LOWER_BOUND_RESCUE_REQUIRES_INTERVAL_VALIDATION"

    elif right_anchor and touches_start:
        rescue_status = "RIGHT_FLANK_LEFT_CENSORED_CANDIDATE"
        allele_status = "LOWER_BOUND_RESCUE_REQUIRES_INTERVAL_VALIDATION"

    elif left_anchor or right_anchor:
        rescue_status = "ONE_FLANK_PARTIAL_INTERNAL"
        allele_status = "NOT_MEASURABLE_ONE_FLANK_INTERNAL"

    elif touches_start or touches_end:
        rescue_status = "REPEAT_ONLY_END_TRUNCATED"
        allele_status = "NOT_MEASURABLE_REPEAT_ONLY_END_TRUNCATED"

    else:
        rescue_status = "REPEAT_ONLY_UNANCHORED_CONFIRMED"
        allele_status = "NOT_MEASURABLE_REPEAT_ONLY_UNANCHORED"

    counts[
        "rescue::{}".format(rescue_status)
    ] += 1

    summary_rows.append(
        {
            "model_id": model_id,
            "event_id": event_id,
            "read_id": representative["read_id"],
            "read_length_bp": representative[
                "read_length_bp"
            ],
            "event_start": representative[
                "event_start"
            ],
            "event_end": representative[
                "event_end"
            ],
            "event_bp": representative["event_bp"],
            "event_touches_raw_start": representative[
                "event_touches_raw_start"
            ],
            "event_touches_raw_end": representative[
                "event_touches_raw_end"
            ],
            "left_context_bp": (
                left_meta["context_bp"]
                if left_meta
                else 0
            ),
            "right_context_bp": (
                right_meta["context_bp"]
                if right_meta
                else 0
            ),
            "left_alignment_count": left_summary[
                "alignment_count"
            ],
            "right_alignment_count": right_summary[
                "alignment_count"
            ],
            "left_near_best_count": left_summary[
                "near_best_count"
            ],
            "right_near_best_count": right_summary[
                "near_best_count"
            ],
            "left_anchor_candidate": str(
                left_anchor is not None
            ).lower(),
            "right_anchor_candidate": str(
                right_anchor is not None
            ).lower(),
            "left_anchor_chrom": (
                left_anchor["chrom"]
                if left_anchor
                else "."
            ),
            "left_anchor_start": (
                left_anchor["target_start"]
                if left_anchor
                else "."
            ),
            "left_anchor_end": (
                left_anchor["target_end"]
                if left_anchor
                else "."
            ),
            "left_anchor_distance_bp": (
                left_anchor[
                    "distance_to_locus_bp"
                ]
                if left_anchor
                else "."
            ),
            "right_anchor_chrom": (
                right_anchor["chrom"]
                if right_anchor
                else "."
            ),
            "right_anchor_start": (
                right_anchor["target_start"]
                if right_anchor
                else "."
            ),
            "right_anchor_end": (
                right_anchor["target_end"]
                if right_anchor
                else "."
            ),
            "right_anchor_distance_bp": (
                right_anchor[
                    "distance_to_locus_bp"
                ]
                if right_anchor
                else "."
            ),
            "flank_rescue_status": rescue_status,
            "allele_length_status": allele_status,
            "reference_relative_expansion_status": "NOT_ASSESSED",
            "interpretation": (
                "Raw-read contexts are tested as unique genomic "
                "flank anchors. Rescue remains provisional until "
                "anchor orientation and repeat interval geometry "
                "are validated."
            ),
        }
    )

with open(
    placements_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=placement_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(placement_rows)

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
    writer.writerows(summary_rows)

status = "PASS"

if (
    len(metadata) != EXPECTED_CONTEXTS
    or len(summary_rows) != EXPECTED_EVENTS
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "expected_events\t{}\n".format(
            EXPECTED_EVENTS
        )
    )
    handle.write(
        "observed_events\t{}\n".format(
            len(summary_rows)
        )
    )
    handle.write(
        "expected_contexts\t{}\n".format(
            EXPECTED_CONTEXTS
        )
    )
    handle.write(
        "observed_contexts\t{}\n".format(
            len(metadata)
        )
    )
    handle.write(
        "paf_alignment_rows\t{}\n".format(
            len(alignments)
        )
    )
    handle.write(
        "contexts_with_any_alignment\t{}\n".format(
            sum(
                summary["alignment_count"] > 0
                for summary in context_summary.values()
            )
        )
    )
    handle.write(
        "anchor_candidates\t{}\n".format(
            sum(
                row["anchor_candidate"] == "true"
                for row in placement_rows
            )
        )
    )

    for key, value in sorted(counts.items()):
        handle.write("{}\t{}\n".format(key, value))

    handle.write(
        "exact_allele_length_calls_emitted\t0\n"
    )
    handle.write(
        "expansion_calls_emitted\t0\n"
    )
    handle.write(
        "audit_status\t{}\n".format(status)
    )

if status != "PASS":
    raise SystemExit(
        "Flank rescue audit requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PREPARE_PY"
python -m py_compile "$PARSE_PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$CONTEXT_FASTA" \
  "$CONTEXT_META" \
  "$PLAIN_FASTA" \
  "$PAF" \
  "$PLACEMENTS" \
  "$SUMMARY" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== PREPARE RAW-READ FLANK CONTEXTS ====="

python "$PREPARE_PY" \
  "$ALIGNMENT_SUMMARY" \
  "$EVENTS" \
  "$FASTQ" \
  "$CONTEXT_FASTA" \
  "$PLAIN_FASTA" \
  "$CONTEXT_META" \
  "$EXPECTED_EVENTS" \
  "$EXPECTED_CONTEXTS" \
  "$MIN_CONTEXT_BP" \
  "$MAX_CONTEXT_BP" \
  "$END_TOLERANCE_BP"

gzip -t "$CONTEXT_FASTA"

echo
echo "===== MAP FLANK CONTEXTS TO WHOLE GENOME ====="
echo "Genome index/reference: $GENOME_INDEX"

minimap2 \
  -x map-ont \
  -k7 \
  -w3 \
  -m10 \
  -s10 \
  -p0.50 \
  -N50 \
  -f0 \
  -c \
  --secondary=yes \
  -t4 \
  "$GENOME_INDEX" \
  "$PLAIN_FASTA" \
  > "$PAF"

echo
echo "===== PARSE FLANK ALIGNMENTS ====="

python "$PARSE_PY" \
  "$PAF" \
  "$CONTEXT_META" \
  "$PLACEMENTS" \
  "$SUMMARY" \
  "$QC" \
  "$MODEL_ID" \
  "$EXPECTED_EVENTS" \
  "$EXPECTED_CONTEXTS" \
  "$MIN_ANCHOR_QUERY_COVERAGE" \
  "$MIN_ANCHOR_IDENTITY" \
  "$MIN_ANCHOR_MAPQ" \
  "$NEAR_BEST_SCORE_FRACTION" \
  "$MAX_ANCHOR_DISTANCE_BP"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== FLANK RESCUE SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== TOP FLANK PLACEMENTS ====="
awk -F '\t' '
    NR == 1 || $5 <= 5
' "$PLACEMENTS" | column -ts $'\t'

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$CONTEXT_META" \
      "$PAF" \
      "$PLACEMENTS" \
      "$SUMMARY" \
      "$QC" \
      "$PARAMETERS"
    do
        if [[ "$path" == *.paf ]]; then
            rows="$(awk 'END {print NR}' "$path")"
        else
            rows="$(awk 'END {print NR-1}' "$path")"
        fi

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    rows="$(gzip -cd "$CONTEXT_FASTA" | grep -c '^>')"

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$CONTEXT_FASTA")" \
      "$rows" \
      "$(stat -c '%s' "$CONTEXT_FASTA")" \
      "$(sha256sum "$CONTEXT_FASTA" | awk '{print $1}')" \
      "$CONTEXT_FASTA"
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$CONTEXT_META"
echo "$PAF"
echo "$PLACEMENTS"
echo "$SUMMARY"
echo "$QC"
