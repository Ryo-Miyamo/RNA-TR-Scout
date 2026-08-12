#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
SAMPLE_ID="ENCSR307SHM"
PARAMETER_SET_ID="rnatr_target_assignment_v0.3.1"

MAPDIR="$PROJECT_ROOT/results/11_mapping/$RUN_ID"
BAM="$MAPDIR/${RUN_ID}.sorted.bam"
BAI="${BAM}.bai"
RUN_MANIFEST="$MAPDIR/run_manifest.tsv"

TARGET_BED="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz"
TARGET_TBI="${TARGET_BED}.tbi"

SCHEMA_DIR="$PROJECT_ROOT/config/evidence_schema/v0.3"
SCHEMA_JSON="$SCHEMA_DIR/schema/rnatr_v03_table_schema.json"
VALIDATOR="$SCHEMA_DIR/rnatr_v03_validate_tsv.py"

OUTDIR="$PROJECT_ROOT/results/11_assignment/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_assignment/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_assignment/$RUN_ID"

ALIGNMENT_SEGMENTS="$OUTDIR/alignment_segments.tsv.gz"
ALIGNMENT_TARGETS="$OUTDIR/alignment_target_candidates.tsv.gz"
READ_TARGETS="$OUTDIR/read_target_candidates.tsv.gz"

BLOCKS_PADDED="$WORKDIR/alignment_blocks.padded.bed"
INTERSECTIONS="$WORKDIR/alignment_blocks_vs_targets.tsv"

DISTRIBUTION_QC="$QCDIR/alignment_distribution_qc.tsv"
ASSIGNMENT_QC="$QCDIR/target_assignment_qc.tsv"
PARAMETERS="$OUTDIR/${PARAMETER_SET_ID}.parameters.tsv"
OUTPUT_MANIFEST="$OUTDIR/${RUN_ID}.assignment_output_manifest.tsv"

EXTRACTOR="$WORKDIR/extract_alignment_segments_and_blocks.py"
AGGREGATOR="$WORKDIR/aggregate_target_candidates.py"

TARGET_PADDING_BP="${TARGET_PADDING_BP:-500}"
LOW_MAPQ_WARN="${LOW_MAPQ_WARN:-10}"
EXPECTED_ALIGNMENT_RECORDS="${EXPECTED_ALIGNMENT_RECORDS:-184820}"
EXPECTED_READS="${EXPECTED_READS:-100000}"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$BAM" \
  "$BAI" \
  "$RUN_MANIFEST" \
  "$TARGET_BED" \
  "$TARGET_TBI" \
  "$SCHEMA_JSON" \
  "$VALIDATOR"
do
    test -s "$path" || {
        echo "ERROR: missing required input: $path" >&2
        exit 1
    }
done

for tool in python samtools bedtools bgzip tabix sha256sum; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

python - <<'PY'
import pysam
print(f"pysam_version\t{pysam.__version__}")
PY

cat > "$EXTRACTOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import math
import sys
from collections import Counter, defaultdict

import pysam

(
    bam_path,
    run_id,
    sample_id,
    alignment_output,
    blocks_output,
    qc_output,
    padding_text,
    low_mapq_text,
    expected_records_text,
    expected_reads_text,
) = sys.argv[1:]

padding = int(padding_text)
low_mapq = int(low_mapq_text)
expected_records = int(expected_records_text)
expected_reads = int(expected_reads_text)

columns = [
    "schema_version",
    "run_id",
    "sample_id",
    "read_id",
    "alignment_id",
    "alignment_class",
    "segment_index",
    "chrom",
    "ref_start",
    "ref_end",
    "query_start",
    "query_end",
    "strand",
    "mapq",
    "sam_flag",
    "cigar",
    "aligned_query_bp",
    "reference_span_bp",
    "edit_distance_nm",
    "alignment_score_as",
    "splice_junction_count",
    "intron_bases",
    "insertion_bases",
    "deletion_bases",
    "softclip_left_bp",
    "softclip_right_bp",
    "hardclip_left_bp",
    "hardclip_right_bp",
    "ts_tag",
    "sa_tag_present",
    "cs_tag",
    "md_tag",
    "is_chimeric_candidate",
    "qc_status",
    "qc_flags",
]

counts = Counter()
read_seen = set()
read_segment_index = defaultdict(int)
signature_count = defaultdict(int)

primary_mapq = []
primary_softclip = []
primary_insertion = []
primary_deletion = []
primary_aligned_query = []
primary_reference_span = []
primary_splice_junctions = []

def missing(value):
    return "." if value is None else value

def get_tag(record, tag):
    return record.get_tag(tag) if record.has_tag(tag) else None

def quantile(values, probability):
    if not values:
        return None

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

def non_splice_reference_blocks(record):
    if record.is_unmapped:
        return []

    ref_pos = record.reference_start
    block_start = ref_pos
    blocks = []

    for operation, length in record.cigartuples or []:
        if operation == 3:  # N: splice skip
            if ref_pos > block_start:
                blocks.append((block_start, ref_pos))
            ref_pos += length
            block_start = ref_pos
        elif operation in {0, 2, 7, 8}:  # M, D, =, X
            ref_pos += length
        else:
            # I, S, H, P do not consume reference.
            continue

    if ref_pos > block_start:
        blocks.append((block_start, ref_pos))

    return blocks

with pysam.AlignmentFile(bam_path, "rb") as bam, gzip.open(
    alignment_output,
    "wt",
    encoding="utf-8",
    newline="",
) as alignment_handle, open(
    blocks_output,
    "w",
    encoding="utf-8",
    newline="",
) as blocks_handle:
    writer = csv.DictWriter(
        alignment_handle,
        fieldnames=columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    block_writer = csv.writer(
        blocks_handle,
        delimiter="\t",
        lineterminator="\n",
    )

    for record in bam.fetch(until_eof=True):
        counts["alignment_records"] += 1
        read_id = record.query_name
        read_seen.add(read_id)

        if record.is_secondary:
            alignment_class = "secondary"
        elif record.is_supplementary:
            alignment_class = "supplementary"
        elif record.is_unmapped:
            alignment_class = "unmapped"
        else:
            alignment_class = "primary"

        segment_index = read_segment_index[read_id]
        read_segment_index[read_id] += 1

        chrom = None if record.is_unmapped else record.reference_name
        ref_start = None if record.is_unmapped else record.reference_start
        ref_end = None if record.is_unmapped else record.reference_end
        query_start = (
            None if record.is_unmapped
            else record.query_alignment_start
        )
        query_end = (
            None if record.is_unmapped
            else record.query_alignment_end
        )
        strand = "." if record.is_unmapped else (
            "-" if record.is_reverse else "+"
        )
        cigar = None if record.is_unmapped else record.cigarstring
        mapq = None if record.is_unmapped else record.mapping_quality

        signature = "|".join(
            [
                run_id,
                read_id,
                alignment_class,
                str(chrom),
                str(ref_start),
                str(ref_end),
                strand,
                str(cigar),
            ]
        )
        duplicate_ordinal = signature_count[signature]
        signature_count[signature] += 1
        alignment_id = hashlib.sha256(
            f"{signature}|{duplicate_ordinal}".encode()
        ).hexdigest()[:24]

        cigartuples = record.cigartuples or []
        splice_junction_count = sum(
            1 for operation, _ in cigartuples if operation == 3
        )
        intron_bases = sum(
            length for operation, length in cigartuples
            if operation == 3
        )
        insertion_bases = sum(
            length for operation, length in cigartuples
            if operation == 1
        )
        deletion_bases = sum(
            length for operation, length in cigartuples
            if operation == 2
        )

        query_length = record.query_length
        if record.is_unmapped or query_start is None or query_end is None:
            softclip_left = None
            softclip_right = None
        else:
            softclip_left = query_start
            softclip_right = (
                query_length - query_end
                if query_length is not None
                else None
            )

        hardclip_cigar_left = (
            cigartuples[0][1]
            if cigartuples and cigartuples[0][0] == 5
            else 0
        )
        hardclip_cigar_right = (
            cigartuples[-1][1]
            if cigartuples and cigartuples[-1][0] == 5
            else 0
        )

        # Convert CIGAR-side hard clipping to BAM-query orientation.
        if record.is_reverse:
            hardclip_left = hardclip_cigar_right
            hardclip_right = hardclip_cigar_left
        else:
            hardclip_left = hardclip_cigar_left
            hardclip_right = hardclip_cigar_right

        sa_present = record.has_tag("SA")
        chimeric_candidate = bool(
            record.is_supplementary or sa_present
        )

        flags = []
        if alignment_class == "secondary":
            flags.append("SECONDARY")
        if alignment_class == "supplementary":
            flags.append("SUPPLEMENTARY")
        if mapq is not None and mapq < low_mapq:
            flags.append(f"LOW_MAPQ_LT_{low_mapq}")
        if splice_junction_count:
            flags.append("SPLICED")
        if (
            (softclip_left or 0) > 0
            or (softclip_right or 0) > 0
        ):
            flags.append("SOFTCLIPPED")
        if sa_present:
            flags.append("SA_TAG")
        if chimeric_candidate:
            flags.append("CHIMERIC_CANDIDATE")

        if record.is_unmapped:
            qc_status = "NOT_EVALUATED"
        elif (
            alignment_class in {"secondary", "supplementary"}
            or (mapq is not None and mapq < low_mapq)
            or chimeric_candidate
        ):
            qc_status = "WARN"
        else:
            qc_status = "PASS"

        row = {
            "schema_version": "0.3.0",
            "run_id": run_id,
            "sample_id": sample_id,
            "read_id": read_id,
            "alignment_id": alignment_id,
            "alignment_class": alignment_class,
            "segment_index": segment_index,
            "chrom": missing(chrom),
            "ref_start": missing(ref_start),
            "ref_end": missing(ref_end),
            "query_start": missing(query_start),
            "query_end": missing(query_end),
            "strand": strand,
            "mapq": missing(mapq),
            "sam_flag": record.flag,
            "cigar": missing(cigar),
            "aligned_query_bp": missing(
                record.query_alignment_length
                if not record.is_unmapped else None
            ),
            "reference_span_bp": missing(
                record.reference_length
                if not record.is_unmapped else None
            ),
            "edit_distance_nm": missing(get_tag(record, "NM")),
            "alignment_score_as": missing(get_tag(record, "AS")),
            "splice_junction_count": missing(
                splice_junction_count
                if not record.is_unmapped else None
            ),
            "intron_bases": missing(
                intron_bases if not record.is_unmapped else None
            ),
            "insertion_bases": missing(
                insertion_bases if not record.is_unmapped else None
            ),
            "deletion_bases": missing(
                deletion_bases if not record.is_unmapped else None
            ),
            "softclip_left_bp": missing(softclip_left),
            "softclip_right_bp": missing(softclip_right),
            "hardclip_left_bp": missing(
                hardclip_left if not record.is_unmapped else None
            ),
            "hardclip_right_bp": missing(
                hardclip_right if not record.is_unmapped else None
            ),
            "ts_tag": missing(get_tag(record, "ts")),
            "sa_tag_present": str(sa_present).lower(),
            "cs_tag": missing(get_tag(record, "cs")),
            "md_tag": missing(get_tag(record, "MD")),
            "is_chimeric_candidate": str(
                chimeric_candidate
            ).lower(),
            "qc_status": qc_status,
            "qc_flags": ";".join(flags) if flags else ".",
        }
        writer.writerow(row)

        counts[f"class::{alignment_class}"] += 1
        counts[f"qc_status::{qc_status}"] += 1

        if alignment_class == "primary" and not record.is_unmapped:
            counts["primary_mapped"] += 1
            primary_mapq.append(record.mapping_quality)
            primary_softclip.append(
                (softclip_left or 0) + (softclip_right or 0)
            )
            primary_insertion.append(insertion_bases)
            primary_deletion.append(deletion_bases)
            primary_aligned_query.append(
                record.query_alignment_length or 0
            )
            primary_reference_span.append(
                record.reference_length or 0
            )
            primary_splice_junctions.append(splice_junction_count)

        for block_index, (block_start, block_end) in enumerate(
            non_splice_reference_blocks(record)
        ):
            padded_start = max(0, block_start - padding)
            padded_end = block_end + padding

            block_writer.writerow(
                [
                    chrom,
                    padded_start,
                    padded_end,
                    alignment_id,
                    block_index,
                    block_start,
                    block_end,
                    read_id,
                    alignment_class,
                    mapq,
                    strand,
                    (softclip_left or 0) + (softclip_right or 0),
                ]
            )
            counts["alignment_blocks"] += 1

def write_quantile(output, metric, values):
    if not values:
        return

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
        value = quantile(values, probability)
        output.write(f"{metric}::{label}\t{value:.6f}\n")

status = "PASS"

if (
    counts["alignment_records"] != expected_records
    or len(read_seen) != expected_reads
):
    status = "REVIEW"

with open(qc_output, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(
        f"expected_alignment_records\t{expected_records}\n"
    )
    output.write(
        f"observed_alignment_records\t"
        f"{counts['alignment_records']}\n"
    )
    output.write(f"expected_reads\t{expected_reads}\n")
    output.write(f"observed_unique_reads\t{len(read_seen)}\n")
    output.write(f"target_padding_bp\t{padding}\n")
    output.write(f"low_mapq_warn\t{low_mapq}\n")

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")

    write_quantile(output, "primary_mapq", primary_mapq)
    write_quantile(
        output,
        "primary_total_softclip_bp",
        primary_softclip,
    )
    write_quantile(
        output,
        "primary_insertion_bp",
        primary_insertion,
    )
    write_quantile(
        output,
        "primary_deletion_bp",
        primary_deletion,
    )
    write_quantile(
        output,
        "primary_aligned_query_bp",
        primary_aligned_query,
    )
    write_quantile(
        output,
        "primary_reference_span_bp",
        primary_reference_span,
    )
    write_quantile(
        output,
        "primary_splice_junction_count",
        primary_splice_junctions,
    )

    for threshold in [10, 50, 100, 250, 500, 1000]:
        count = sum(
            value >= threshold
            for value in primary_softclip
        )
        percent = (
            100.0 * count / len(primary_softclip)
            if primary_softclip else 0.0
        )
        output.write(
            f"primary_softclip_ge_{threshold}_bp\t{count}\n"
        )
        output.write(
            f"primary_softclip_ge_{threshold}_bp_percent\t"
            f"{percent:.6f}\n"
        )

    for threshold in [0, 1, 10, 20, 30, 40, 50, 60]:
        count = sum(value >= threshold for value in primary_mapq)
        percent = (
            100.0 * count / len(primary_mapq)
            if primary_mapq else 0.0
        )
        output.write(
            f"primary_mapq_ge_{threshold}\t{count}\n"
        )
        output.write(
            f"primary_mapq_ge_{threshold}_percent\t"
            f"{percent:.6f}\n"
        )

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Alignment extraction validation failed")
PY

cat > "$AGGREGATOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter, defaultdict

(
    intersections_path,
    alignment_output,
    read_output,
    summary_output,
    padding_text,
) = sys.argv[1:]

padding = int(padding_text)

alignment_candidates = {}

with open(
    intersections_path,
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.reader(handle, delimiter="\t")

    for fields in reader:
        if len(fields) != 20:
            raise RuntimeError(
                f"Expected 20 fields from bedtools, got {len(fields)}"
            )

        (
            chrom,
            padded_start,
            padded_end,
            alignment_id,
            block_index,
            block_start,
            block_end,
            read_id,
            alignment_class,
            mapq,
            strand,
            softclip_total,
            target_chrom,
            target_start,
            target_end,
            target_region_id,
            target_source,
            region_type,
            analysis_mode,
            representative_locus_id,
        ) = fields

        block_start_i = int(block_start)
        block_end_i = int(block_end)
        target_start_i = int(target_start)
        target_end_i = int(target_end)

        overlap = max(
            0,
            min(block_end_i, target_end_i)
            - max(block_start_i, target_start_i),
        )

        if overlap > 0:
            distance = 0
        elif block_end_i <= target_start_i:
            distance = target_start_i - block_end_i
        else:
            distance = block_start_i - target_end_i

        if distance > padding:
            continue

        key = (
            alignment_id,
            target_source,
            target_region_id,
        )

        record = alignment_candidates.get(key)

        if record is None:
            record = {
                "read_id": read_id,
                "alignment_id": alignment_id,
                "alignment_class": alignment_class,
                "mapq": int(mapq),
                "strand": strand,
                "softclip_total_bp": int(softclip_total),
                "target_region_id": target_region_id,
                "target_source": target_source,
                "region_type": region_type,
                "analysis_mode": analysis_mode,
                "representative_locus_id": representative_locus_id,
                "target_chrom": target_chrom,
                "target_start": int(target_start),
                "target_end": int(target_end),
                "target_overlap_bp": 0,
                "target_distance_bp": distance,
                "supporting_blocks": set(),
            }
            alignment_candidates[key] = record

        record["target_overlap_bp"] += overlap
        record["target_distance_bp"] = min(
            record["target_distance_bp"],
            distance,
        )
        record["supporting_blocks"].add(int(block_index))

alignment_columns = [
    "read_id",
    "alignment_id",
    "alignment_class",
    "mapq",
    "strand",
    "softclip_total_bp",
    "target_region_id",
    "target_source",
    "region_type",
    "analysis_mode",
    "representative_locus_id",
    "target_chrom",
    "target_start",
    "target_end",
    "target_overlap_bp",
    "target_distance_bp",
    "candidate_basis",
    "supporting_block_count",
]

read_candidates = {}
counts = Counter()
targets_seen = set()
reads_with_exact = set()
reads_with_any = set()

with gzip.open(
    alignment_output,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=alignment_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for record in alignment_candidates.values():
        record["candidate_basis"] = (
            "exact_overlap"
            if record["target_overlap_bp"] > 0
            else "proximal_within_padding"
        )
        record["supporting_block_count"] = len(
            record["supporting_blocks"]
        )

        output_record = {
            key: value
            for key, value in record.items()
            if key != "supporting_blocks"
        }
        writer.writerow(output_record)

        counts["alignment_target_candidates"] += 1
        counts[
            f"alignment_candidate_basis::"
            f"{record['candidate_basis']}"
        ] += 1
        counts[
            f"alignment_class::{record['alignment_class']}"
        ] += 1
        counts[f"target_source::{record['target_source']}"] += 1
        counts[f"region_type::{record['region_type']}"] += 1

        read_id = record["read_id"]
        reads_with_any.add(read_id)

        if record["target_overlap_bp"] > 0:
            reads_with_exact.add(read_id)

        targets_seen.add(
            (
                record["target_source"],
                record["target_region_id"],
            )
        )

        read_key = (
            read_id,
            record["target_source"],
            record["target_region_id"],
        )
        aggregate = read_candidates.get(read_key)

        if aggregate is None:
            aggregate = {
                "read_id": read_id,
                "target_region_id": record["target_region_id"],
                "target_source": record["target_source"],
                "region_type": record["region_type"],
                "analysis_mode": record["analysis_mode"],
                "representative_locus_id": record[
                    "representative_locus_id"
                ],
                "supporting_alignment_count": 0,
                "primary_support": False,
                "supplementary_support": False,
                "secondary_support": False,
                "best_record": None,
            }
            read_candidates[read_key] = aggregate

        aggregate["supporting_alignment_count"] += 1

        if record["alignment_class"] == "primary":
            aggregate["primary_support"] = True
        elif record["alignment_class"] == "supplementary":
            aggregate["supplementary_support"] = True
        elif record["alignment_class"] == "secondary":
            aggregate["secondary_support"] = True

        class_priority = {
            "primary": 3,
            "supplementary": 2,
            "secondary": 1,
        }.get(record["alignment_class"], 0)

        score = (
            1 if record["target_overlap_bp"] > 0 else 0,
            record["target_overlap_bp"],
            -record["target_distance_bp"],
            class_priority,
            record["mapq"],
            record["softclip_total_bp"],
        )

        best_record = aggregate["best_record"]

        if (
            best_record is None
            or score > best_record["_score"]
        ):
            selected = dict(record)
            selected["_score"] = score
            aggregate["best_record"] = selected

read_groups = defaultdict(list)

for aggregate in read_candidates.values():
    read_groups[aggregate["read_id"]].append(aggregate)

read_columns = [
    "read_id",
    "target_region_id",
    "target_source",
    "region_type",
    "analysis_mode",
    "representative_locus_id",
    "assignment_rank",
    "read_candidate_target_count",
    "best_alignment_id",
    "best_alignment_class",
    "best_mapq",
    "strand",
    "best_softclip_total_bp",
    "target_overlap_bp",
    "target_distance_bp",
    "candidate_basis",
    "supporting_alignment_count",
    "primary_support",
    "supplementary_support",
    "secondary_support",
]

with gzip.open(
    read_output,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=read_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for read_id, candidates in read_groups.items():
        def rank_key(aggregate):
            record = aggregate["best_record"]
            class_priority = {
                "primary": 3,
                "supplementary": 2,
                "secondary": 1,
            }.get(record["alignment_class"], 0)

            return (
                1 if record["target_overlap_bp"] > 0 else 0,
                record["target_overlap_bp"],
                -record["target_distance_bp"],
                class_priority,
                record["mapq"],
                record["softclip_total_bp"],
            )

        candidates.sort(key=rank_key, reverse=True)
        candidate_count = len(candidates)

        for rank, aggregate in enumerate(candidates, start=1):
            record = aggregate["best_record"]

            writer.writerow(
                {
                    "read_id": read_id,
                    "target_region_id": aggregate[
                        "target_region_id"
                    ],
                    "target_source": aggregate["target_source"],
                    "region_type": aggregate["region_type"],
                    "analysis_mode": aggregate["analysis_mode"],
                    "representative_locus_id": aggregate[
                        "representative_locus_id"
                    ],
                    "assignment_rank": rank,
                    "read_candidate_target_count": candidate_count,
                    "best_alignment_id": record["alignment_id"],
                    "best_alignment_class": record[
                        "alignment_class"
                    ],
                    "best_mapq": record["mapq"],
                    "strand": record["strand"],
                    "best_softclip_total_bp": record[
                        "softclip_total_bp"
                    ],
                    "target_overlap_bp": record[
                        "target_overlap_bp"
                    ],
                    "target_distance_bp": record[
                        "target_distance_bp"
                    ],
                    "candidate_basis": record[
                        "candidate_basis"
                    ],
                    "supporting_alignment_count": aggregate[
                        "supporting_alignment_count"
                    ],
                    "primary_support": str(
                        aggregate["primary_support"]
                    ).lower(),
                    "supplementary_support": str(
                        aggregate["supplementary_support"]
                    ).lower(),
                    "secondary_support": str(
                        aggregate["secondary_support"]
                    ).lower(),
                }
            )
            counts["read_target_candidates"] += 1
            counts[
                f"read_candidate_basis::{record['candidate_basis']}"
            ] += 1

reads_only_proximal = reads_with_any - reads_with_exact

with open(summary_output, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"target_padding_bp\t{padding}\n")
    output.write(
        f"alignment_target_candidates\t"
        f"{counts['alignment_target_candidates']}\n"
    )
    output.write(
        f"read_target_candidates\t"
        f"{counts['read_target_candidates']}\n"
    )
    output.write(f"reads_with_any_candidate\t{len(reads_with_any)}\n")
    output.write(
        f"reads_with_exact_overlap_candidate\t"
        f"{len(reads_with_exact)}\n"
    )
    output.write(
        f"reads_with_only_proximal_candidate\t"
        f"{len(reads_only_proximal)}\n"
    )
    output.write(
        f"unique_target_regions_observed\t{len(targets_seen)}\n"
    )

    for key, value in sorted(counts.items()):
        if key in {
            "alignment_target_candidates",
            "read_target_candidates",
        }:
            continue
        output.write(f"{key}\t{value}\n")

    output.write("audit_status\tPASS\n")
PY

echo "===== 1. INPUT VALIDATION ====="

samtools quickcheck -v "$BAM"
echo "BAM quickcheck: OK"

TARGET_ROWS="$(gzip -cd "$TARGET_BED" | wc -l)"
echo "Mapping target rows: $TARGET_ROWS"

if [[ "$TARGET_ROWS" != "349490" ]]; then
    echo "ERROR: expected 349490 mapping targets" >&2
    exit 1
fi

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
parameter_set_id	$PARAMETER_SET_ID	Candidate-assignment parameter set
target_padding_bp	$TARGET_PADDING_BP	Recall-oriented search window around each non-splice alignment block
low_mapq_warn	$LOW_MAPQ_WARN	Warning threshold only; records are retained
splice_skip_handling	exclude_N_from_blocks	Do not assign intronic targets merely because a spliced alignment spans an intron
deletion_handling	include_D_in_reference_block	Retain candidate evidence when a deletion crosses a target
secondary_alignment	retain	Retain until final locus assignment
supplementary_alignment	retain	Retain until final locus assignment
candidate_status	not_final_call	Output is a recall-oriented candidate table, not a repeat expansion call
EOF

column -ts $'\t' "$PARAMETERS"

echo
echo "===== 2. EXTRACT ALIGNMENT SEGMENTS AND NON-SPLICE BLOCKS ====="

rm -f \
  "$ALIGNMENT_SEGMENTS" \
  "$ALIGNMENT_TARGETS" \
  "$READ_TARGETS" \
  "$BLOCKS_PADDED" \
  "$INTERSECTIONS" \
  "$DISTRIBUTION_QC" \
  "$ASSIGNMENT_QC" \
  "$OUTPUT_MANIFEST"

python "$EXTRACTOR" \
  "$BAM" \
  "$RUN_ID" \
  "$SAMPLE_ID" \
  "$ALIGNMENT_SEGMENTS" \
  "$BLOCKS_PADDED" \
  "$DISTRIBUTION_QC" \
  "$TARGET_PADDING_BP" \
  "$LOW_MAPQ_WARN" \
  "$EXPECTED_ALIGNMENT_RECORDS" \
  "$EXPECTED_READS"

python "$VALIDATOR" \
  --schema "$SCHEMA_JSON" \
  --table alignment_segments \
  --input "$ALIGNMENT_SEGMENTS" \
  --max-rows 250000

echo
echo "===== ALIGNMENT DISTRIBUTION QC ====="
column -ts $'\t' "$DISTRIBUTION_QC"

echo
echo "===== 3. INTERSECT NON-SPLICE BLOCKS WITH TARGETS ====="

bedtools intersect \
  -wa \
  -wb \
  -a "$BLOCKS_PADDED" \
  -b "$TARGET_BED" \
  > "$INTERSECTIONS"

echo "Raw block-target intersections: $(wc -l < "$INTERSECTIONS")"

echo
echo "===== 4. AGGREGATE TARGET CANDIDATES ====="

python "$AGGREGATOR" \
  "$INTERSECTIONS" \
  "$ALIGNMENT_TARGETS" \
  "$READ_TARGETS" \
  "$ASSIGNMENT_QC" \
  "$TARGET_PADDING_BP"

column -ts $'\t' "$ASSIGNMENT_QC"

echo
echo "===== 5. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$ALIGNMENT_SEGMENTS" \
      "$ALIGNMENT_TARGETS" \
      "$READ_TARGETS"
    do
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in \
      "$DISTRIBUTION_QC" \
      "$ASSIGNMENT_QC" \
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
} > "$OUTPUT_MANIFEST"

column -ts $'\t' "$OUTPUT_MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$ALIGNMENT_SEGMENTS"
echo "$ALIGNMENT_TARGETS"
echo "$READ_TARGETS"
echo "$DISTRIBUTION_QC"
echo "$ASSIGNMENT_QC"
echo "$OUTPUT_MANIFEST"
