#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
SAMPLE_ID="ENCSR307SHM"
PARAMETER_SET_ID="rnatr_raw_projection_v0.3.3"

BAM="$PROJECT_ROOT/results/11_mapping/$RUN_ID/${RUN_ID}.sorted.bam"
READ_TARGETS="$PROJECT_ROOT/results/11_assignment/$RUN_ID/read_target_candidates.tsv.gz"
TARGETS="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.tsv.gz"

CANDIDATE_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/stage15a_500k_seed20260809_v1/rnatr_candidates_v0.3.1/ENCFF260PGB.stage15a_500k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3"
QCDIR="$PROJECT_ROOT/qc/11_projection/$RUN_ID/v0.3.3"
WORKDIR="$PROJECT_ROOT/tmp/11_projection/$RUN_ID/v0.3.3"

DATA_OUTDIR="$RAW_ROOT/benchmarks/ENCSR307SHM/stage15a_500k_seed20260809_v1/rnatr_projection_v0.3.3"

PROJECTION="$OUTDIR/read_target_projection.v0.3.3.tsv.gz"
WINDOW_FASTQ="$DATA_OUTDIR/ENCFF260PGB.stage15a_500k.rnatr_target_windows.v0.3.3.fastq.gz"
QC_SUMMARY="$QCDIR/raw_projection_qc.v0.3.3.tsv"
PARAMETERS="$OUTDIR/${PARAMETER_SET_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.raw_projection_manifest.v0.3.3.tsv"

PROJECTOR="$WORKDIR/project_targets_to_raw_reads.py"

MIN_FLANK_ANCHOR_BP="${MIN_FLANK_ANCHOR_BP:-30}"
ANCHOR_WINDOW_BP="${ANCHOR_WINDOW_BP:-100}"
SEQUENCE_WINDOW_FLANK_BP="${SEQUENCE_WINDOW_FLANK_BP:-100}"
LOW_MAPQ_WARN="${LOW_MAPQ_WARN:-10}"

EXPECTED_CANDIDATE_ROWS=388571
EXPECTED_CANDIDATE_READS=79176

mkdir -p \
  "$OUTDIR" \
  "$QCDIR" \
  "$WORKDIR" \
  "$DATA_OUTDIR"

for path in \
  "$BAM" \
  "${BAM}.bai" \
  "$READ_TARGETS" \
  "$TARGETS" \
  "$CANDIDATE_FASTQ"
do
    test -s "$path" || {
        echo "ERROR: required input missing: $path" >&2
        exit 1
    }
done

for tool in python samtools gzip sha256sum; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
parameter_set_id	$PARAMETER_SET_ID	Raw-read target projection parameter set
min_flank_anchor_bp	$MIN_FLANK_ANCHOR_BP	Minimum aligned bases required for an anchored genomic flank
anchor_window_bp	$ANCHOR_WINDOW_BP	Maximum genomic interval used to count each flank anchor
sequence_window_flank_bp	$SEQUENCE_WINDOW_FLANK_BP	Raw-read bases retained around the projected target/softclip
low_mapq_warn	$LOW_MAPQ_WARN	Warning threshold; candidate rows are retained
coordinate_system	0_based_end_exclusive	Genomic and raw-read coordinates
splice_handling	separate_blocks_at_CIGAR_N	A target cannot be bridged through a splice skip
deletion_handling	reference_covered_but_no_query_bases	Distinguish deletion-like target geometry
orientation	raw_fastq_coordinates	Reverse-strand BAM query coordinates are converted back to raw FASTQ orientation
hardclip_handling	cigar_offset_aware	Supplementary-alignment query coordinates include CIGAR hard-clip offsets before raw-read conversion
query_length_reconstruction	cigar_query_consuming_ops_plus_H	Use M/I/S/=/X plus terminal H when BAM SEQ is omitted on secondary records
sequence_audit	hardclip_aware_raw_slice	BAM forward sequence is compared with the corresponding non-hard-clipped raw-read slice when SEQ is present
secondary_seq_absence	expected_and_cigar_audited	Secondary records without BAM SEQ are coordinate-audited from CIGAR rather than treated as zero-length
supersedes	rnatr_raw_projection_v0.3.2	v0.3.2 incorrectly treated missing secondary-alignment SEQ/query_length as zero query length
classification_status	geometry_potential_only	Final SPAN/censored requires motif detection in the raw sequence
EOF

cat > "$PROJECTOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import math
import statistics
import sys
from collections import Counter, defaultdict

import pysam

(
    bam_path,
    candidates_path,
    targets_path,
    fastq_path,
    projection_path,
    window_fastq_path,
    qc_path,
    run_id,
    sample_id,
    min_anchor_text,
    anchor_window_text,
    sequence_flank_text,
    low_mapq_text,
    expected_rows_text,
    expected_reads_text,
) = sys.argv[1:]

min_anchor = int(min_anchor_text)
anchor_window = int(anchor_window_text)
sequence_flank = int(sequence_flank_text)
low_mapq = int(low_mapq_text)
expected_rows = int(expected_rows_text)
expected_reads = int(expected_reads_text)

RC_TABLE = str.maketrans(
    "ACGTRYMKBDHVNacgtrymkbdhvn",
    "TGCAYRKMVHDBNtgcayrkmvhdbn",
)


def reverse_complement(sequence: str) -> str:
    return sequence.translate(RC_TABLE)[::-1]


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


def mean_q(quality: str | None):
    if not quality:
        return None
    return sum(ord(char) - 33 for char in quality) / len(quality)


def interval_overlap(start_a, end_a, start_b, end_b):
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def interval_distance(start_a, end_a, start_b, end_b):
    if interval_overlap(start_a, end_a, start_b, end_b) > 0:
        return 0
    if end_a <= start_b:
        return start_b - end_a
    return start_a - end_b


def convert_local_query_interval_to_raw(
    start: int,
    end: int,
    read_length: int,
    is_reverse: bool,
    hardclip_left_cigar: int,
):
    """Convert BAM-local query coordinates to full raw FASTQ coordinates.

    BAM query coordinates exclude hard-clipped bases. CIGAR-left hard clips
    therefore define the offset in the full query orientation. Reverse-strand
    records are then converted back to the original raw FASTQ orientation.
    """
    full_start = hardclip_left_cigar + start
    full_end = hardclip_left_cigar + end

    if not is_reverse:
        return full_start, full_end

    return read_length - full_end, read_length - full_start


def convert_full_oriented_interval_to_raw(
    start: int,
    end: int,
    read_length: int,
    is_reverse: bool,
):
    """Convert full-query coordinates in CIGAR orientation to raw FASTQ."""
    if not is_reverse:
        return start, end

    return read_length - end, read_length - start


def build_blocks(record):
    blocks = []
    current = {
        "ref_start": record.reference_start,
        "ref_end": record.reference_start,
        "segments": [],
    }

    query_position = 0
    reference_position = record.reference_start

    for operation, length in record.cigartuples or []:
        if operation in {0, 7, 8}:  # M, =, X
            current["segments"].append(
                {
                    "type": "ALIGNED",
                    "ref_start": reference_position,
                    "ref_end": reference_position + length,
                    "query_start": query_position,
                    "query_end": query_position + length,
                }
            )
            reference_position += length
            query_position += length
            current["ref_end"] = reference_position

        elif operation == 1:  # I
            current["segments"].append(
                {
                    "type": "INSERTION",
                    "ref_start": reference_position,
                    "ref_end": reference_position,
                    "query_start": query_position,
                    "query_end": query_position + length,
                }
            )
            query_position += length

        elif operation == 2:  # D
            current["segments"].append(
                {
                    "type": "DELETION",
                    "ref_start": reference_position,
                    "ref_end": reference_position + length,
                    "query_start": query_position,
                    "query_end": query_position,
                }
            )
            reference_position += length
            current["ref_end"] = reference_position

        elif operation == 3:  # N
            if current["ref_end"] > current["ref_start"]:
                blocks.append(current)

            reference_position += length
            current = {
                "ref_start": reference_position,
                "ref_end": reference_position,
                "segments": [],
            }

        elif operation == 4:  # S
            query_position += length

        elif operation in {5, 6}:  # H, P
            continue

        else:
            raise RuntimeError(
                f"Unsupported CIGAR operation {operation}"
            )

    if current["ref_end"] > current["ref_start"]:
        blocks.append(current)

    return blocks


def aligned_bases_in_interval(block, interval_start, interval_end):
    if interval_end <= interval_start:
        return 0

    return sum(
        interval_overlap(
            segment["ref_start"],
            segment["ref_end"],
            interval_start,
            interval_end,
        )
        for segment in block["segments"]
        if segment["type"] == "ALIGNED"
    )


def projected_query_intervals(block, target_start, target_end):
    intervals = []

    for segment in block["segments"]:
        if segment["type"] == "ALIGNED":
            overlap_start = max(
                segment["ref_start"],
                target_start,
            )
            overlap_end = min(
                segment["ref_end"],
                target_end,
            )

            if overlap_end > overlap_start:
                query_start = (
                    segment["query_start"]
                    + overlap_start
                    - segment["ref_start"]
                )
                query_end = (
                    segment["query_start"]
                    + overlap_end
                    - segment["ref_start"]
                )
                intervals.append((query_start, query_end))

        elif segment["type"] == "INSERTION":
            # Include insertions whose reference attachment point lies
            # within or on a target boundary.
            reference_point = segment["ref_start"]

            if target_start <= reference_point <= target_end:
                intervals.append(
                    (
                        segment["query_start"],
                        segment["query_end"],
                    )
                )

    return intervals


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

        if key in target_lookup:
            raise RuntimeError(f"Duplicate target key: {key}")

        target_lookup[key] = {
            "chrom": row["chrom"],
            "start": int(row["start"]),
            "end": int(row["end"]),
            "region_type": row["region_type"],
            "analysis_mode": row["analysis_mode"],
            "representative_locus_id": row[
                "representative_locus_id"
            ],
        }

fastq_records = {}

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        if entry.name in fastq_records:
            raise RuntimeError(
                f"Duplicate FASTQ read ID: {entry.name}"
            )

        fastq_records[entry.name] = {
            "sequence": entry.sequence,
            "quality": entry.quality,
            "comment": entry.comment or "",
        }

candidates_by_alignment = defaultdict(list)
candidate_rows = 0
candidate_reads = set()

with gzip.open(
    candidates_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        target_key = (
            row["target_source"],
            row["target_region_id"],
        )

        if target_key not in target_lookup:
            raise RuntimeError(
                f"Target not found in catalog: {target_key}"
            )

        row["_target"] = target_lookup[target_key]
        candidates_by_alignment[
            row["best_alignment_id"]
        ].append(row)

        candidate_rows += 1
        candidate_reads.add(row["read_id"])

projection_columns = [
    "schema_version",
    "run_id",
    "sample_id",
    "projection_id",
    "read_id",
    "read_length_bp",
    "mean_read_q",
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
    "target_chrom",
    "target_start",
    "target_end",
    "candidate_basis",
    "target_overlap_bp_reported",
    "target_distance_bp_reported",
    "selected_block_start",
    "selected_block_end",
    "selected_block_overlap_bp",
    "selected_block_distance_bp",
    "genomic_left_anchor_bp",
    "genomic_right_anchor_bp",
    "genomic_left_softclip_bp",
    "genomic_right_softclip_bp",
    "projected_target_read_start",
    "projected_target_read_end",
    "candidate_window_read_start",
    "candidate_window_read_end",
    "candidate_window_length_bp",
    "geometry_class",
    "potential_evidence_class",
    "projection_status",
    "projection_flags",
]

counts = Counter()
projection_rows_written = 0
windows_written = 0
projection_ids = set()
seen_alignment_ids = set()
seen_projection_reads = set()
window_lengths = []
rank1_geometry = Counter()
signature_count = defaultdict(int)
orientation_checked = 0
orientation_match = 0
orientation_mismatch = 0

with pysam.AlignmentFile(bam_path, "rb") as bam, gzip.open(
    projection_path,
    "wt",
    encoding="utf-8",
    newline="",
) as projection_handle, gzip.open(
    window_fastq_path,
    "wt",
    encoding="utf-8",
) as window_handle:
    writer = csv.DictWriter(
        projection_handle,
        fieldnames=projection_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for record in bam.fetch(until_eof=True):
        if record.is_secondary:
            alignment_class = "secondary"
        elif record.is_supplementary:
            alignment_class = "supplementary"
        elif record.is_unmapped:
            alignment_class = "unmapped"
        else:
            alignment_class = "primary"

        chrom = (
            None if record.is_unmapped else record.reference_name
        )
        ref_start = (
            None if record.is_unmapped else record.reference_start
        )
        ref_end = (
            None if record.is_unmapped else record.reference_end
        )
        strand = (
            "."
            if record.is_unmapped
            else ("-" if record.is_reverse else "+")
        )
        cigar = (
            None if record.is_unmapped else record.cigarstring
        )

        signature = "|".join(
            [
                run_id,
                record.query_name,
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

        candidate_list = candidates_by_alignment.get(alignment_id)

        if not candidate_list:
            continue

        seen_alignment_ids.add(alignment_id)
        read_id = record.query_name
        fastq = fastq_records.get(read_id)

        if fastq is None:
            counts["missing_fastq_read"] += len(candidate_list)
            continue

        raw_sequence = fastq["sequence"]
        raw_quality = fastq["quality"]
        read_length = len(raw_sequence)
        read_mean_q = mean_q(raw_quality)

        cigartuples = record.cigartuples or []
        hardclip_left_cigar = (
            cigartuples[0][1]
            if cigartuples and cigartuples[0][0] == 5
            else 0
        )
        hardclip_right_cigar = (
            cigartuples[-1][1]
            if cigartuples and cigartuples[-1][0] == 5
            else 0
        )
        # Secondary BAM records may omit SEQ/QUAL. In that case
        # record.query_length is None even though the CIGAR still contains
        # complete query-coordinate information. Reconstruct the non-hard-
        # clipped query length directly from query-consuming CIGAR operations.
        cigar_query_length_no_hardclip = sum(
            length
            for operation, length in cigartuples
            if operation in {0, 1, 4, 7, 8}  # M, I, S, =, X
        )
        reconstructed_full_query_length = (
            hardclip_left_cigar
            + cigar_query_length_no_hardclip
            + hardclip_right_cigar
        )

        if record.query_sequence:
            counts["bam_sequence_present_records"] += 1

            if (
                record.query_length is not None
                and record.query_length
                != cigar_query_length_no_hardclip
            ):
                counts[
                    "bam_query_length_vs_cigar_mismatch"
                ] += 1
                counts[
                    f"bam_query_length_vs_cigar_mismatch_class::"
                    f"{alignment_class}"
                ] += 1
        else:
            counts["bam_sequence_absent_records"] += 1
            counts[
                f"bam_sequence_absent_class::{alignment_class}"
            ] += 1

            if alignment_class != "secondary":
                counts[
                    "unexpected_missing_bam_sequence_nonsecondary"
                ] += 1

        if hardclip_left_cigar or hardclip_right_cigar:
            counts["hardclipped_alignment_records"] += 1
            counts[
                f"hardclipped_alignment_class::{alignment_class}"
            ] += 1
            counts["hardclipped_bases_total"] += (
                hardclip_left_cigar + hardclip_right_cigar
            )

        if reconstructed_full_query_length != read_length:
            counts["reconstructed_full_query_length_mismatch"] += 1
            counts[
                f"full_length_mismatch_class::{alignment_class}"
            ] += 1

        if record.query_sequence:
            orientation_checked += 1
            forward_sequence = record.get_forward_sequence()

            # get_forward_sequence() excludes hard-clipped bases. Compare it
            # with the corresponding raw-read slice rather than the full read.
            if record.is_reverse:
                expected_raw_start = hardclip_right_cigar
                expected_raw_end = read_length - hardclip_left_cigar
            else:
                expected_raw_start = hardclip_left_cigar
                expected_raw_end = read_length - hardclip_right_cigar

            expected_forward_sequence = raw_sequence[
                expected_raw_start:expected_raw_end
            ]

            if forward_sequence == expected_forward_sequence:
                orientation_match += 1
                counts[
                    f"orientation_match_class::{alignment_class}"
                ] += 1
                if hardclip_left_cigar or hardclip_right_cigar:
                    counts[
                        "orientation_match_hardclipped_records"
                    ] += 1
            else:
                orientation_mismatch += 1
                counts[
                    f"orientation_mismatch_class::{alignment_class}"
                ] += 1

        blocks = build_blocks(record)

        left_ref_softclip = (
            cigartuples[0][1]
            if cigartuples and cigartuples[0][0] == 4
            else 0
        )
        right_ref_softclip = (
            cigartuples[-1][1]
            if cigartuples and cigartuples[-1][0] == 4
            else 0
        )

        for candidate in candidate_list:
            target = candidate["_target"]
            target_start = target["start"]
            target_end = target["end"]

            projection_id = hashlib.sha256(
                "|".join(
                    [
                        run_id,
                        read_id,
                        candidate["target_source"],
                        candidate["target_region_id"],
                        alignment_id,
                    ]
                ).encode()
            ).hexdigest()[:24]

            if projection_id in projection_ids:
                raise RuntimeError(
                    f"Duplicate projection ID: {projection_id}"
                )
            projection_ids.add(projection_id)

            flags = []

            if record.mapping_quality < low_mapq:
                flags.append(f"LOW_MAPQ_LT_{low_mapq}")

            if alignment_class != "primary":
                flags.append(
                    f"BEST_ALIGNMENT_{alignment_class.upper()}"
                )

            if hardclip_left_cigar or hardclip_right_cigar:
                flags.append("HARDCLIPPED_ALIGNMENT")

            if reconstructed_full_query_length != read_length:
                flags.append("FULL_QUERY_LENGTH_MISMATCH")

            if int(candidate["read_candidate_target_count"]) > 1:
                flags.append("MULTIPLE_TARGET_CANDIDATES")

            if target["chrom"] != record.reference_name:
                flags.append("TARGET_ALIGNMENT_CHROM_MISMATCH")
                selected_block = None
            else:
                ranked_blocks = []

                for block in blocks:
                    overlap = interval_overlap(
                        block["ref_start"],
                        block["ref_end"],
                        target_start,
                        target_end,
                    )
                    distance = interval_distance(
                        block["ref_start"],
                        block["ref_end"],
                        target_start,
                        target_end,
                    )
                    ranked_blocks.append(
                        (
                            overlap,
                            -distance,
                            block["ref_end"] - block["ref_start"],
                            block,
                        )
                    )

                selected_block = (
                    max(ranked_blocks, key=lambda item: item[:3])[3]
                    if ranked_blocks else None
                )

            if selected_block is None:
                geometry_class = "UNRESOLVED"
                potential_class = "NOT_YET_CLASSIFIABLE"
                projection_status = "FAIL"
                block_start = None
                block_end = None
                block_overlap = 0
                block_distance = int(
                    candidate["target_distance_bp"]
                )
                left_anchor = 0
                right_anchor = 0
                projected_raw = None
                window_raw = None
                flags.append("NO_NON_SPLICE_BLOCK")

            else:
                block_start = selected_block["ref_start"]
                block_end = selected_block["ref_end"]
                block_overlap = interval_overlap(
                    block_start,
                    block_end,
                    target_start,
                    target_end,
                )
                block_distance = interval_distance(
                    block_start,
                    block_end,
                    target_start,
                    target_end,
                )

                left_anchor = aligned_bases_in_interval(
                    selected_block,
                    max(
                        block_start,
                        target_start - anchor_window,
                    ),
                    target_start,
                )
                right_anchor = aligned_bases_in_interval(
                    selected_block,
                    target_end,
                    min(
                        block_end,
                        target_end + anchor_window,
                    ),
                )

                query_intervals = projected_query_intervals(
                    selected_block,
                    target_start,
                    target_end,
                )

                if query_intervals:
                    projected_bam_start = min(
                        start for start, _ in query_intervals
                    )
                    projected_bam_end = max(
                        end for _, end in query_intervals
                    )
                    projected_raw = (
                        convert_local_query_interval_to_raw(
                            projected_bam_start,
                            projected_bam_end,
                            read_length,
                            record.is_reverse,
                            hardclip_left_cigar,
                        )
                    )
                else:
                    projected_raw = None

                left_anchored = left_anchor >= min_anchor
                right_anchored = right_anchor >= min_anchor

                if block_overlap > 0:
                    if left_anchored and right_anchored:
                        if projected_raw is not None:
                            geometry_class = (
                                "BOTH_FLANKS_PROJECTABLE"
                            )
                            potential_class = "SPAN_POTENTIAL"
                        else:
                            geometry_class = (
                                "FLANKS_WITHOUT_QUERY_TARGET"
                            )
                            potential_class = (
                                "NOT_YET_CLASSIFIABLE"
                            )

                    elif left_anchored:
                        geometry_class = "LEFT_FLANK_ONLY"
                        potential_class = (
                            "LEFT_ANCHORED_CENSORED_RIGHT_POTENTIAL"
                        )

                    elif right_anchored:
                        geometry_class = "RIGHT_FLANK_ONLY"
                        potential_class = (
                            "RIGHT_ANCHORED_CENSORED_LEFT_POTENTIAL"
                        )

                    else:
                        geometry_class = (
                            "TARGET_INTERNAL_NO_FLANK"
                        )
                        potential_class = (
                            "REPEAT_ONLY_UNANCHORED_POTENTIAL"
                        )

                elif target_start >= block_end:
                    if left_anchored and right_ref_softclip > 0:
                        geometry_class = (
                            "PROXIMAL_RIGHT_WITH_SOFTCLIP"
                        )
                        potential_class = (
                            "LEFT_ANCHORED_CENSORED_RIGHT_POTENTIAL"
                        )
                    elif left_anchored:
                        geometry_class = (
                            "PROXIMAL_RIGHT_NO_SOFTCLIP"
                        )
                        potential_class = (
                            "NOT_YET_CLASSIFIABLE"
                        )
                    else:
                        geometry_class = "PROXIMAL_ONLY"
                        potential_class = (
                            "NOT_YET_CLASSIFIABLE"
                        )

                elif target_end <= block_start:
                    if right_anchored and left_ref_softclip > 0:
                        geometry_class = (
                            "PROXIMAL_LEFT_WITH_SOFTCLIP"
                        )
                        potential_class = (
                            "RIGHT_ANCHORED_CENSORED_LEFT_POTENTIAL"
                        )
                    elif right_anchored:
                        geometry_class = (
                            "PROXIMAL_LEFT_NO_SOFTCLIP"
                        )
                        potential_class = (
                            "NOT_YET_CLASSIFIABLE"
                        )
                    else:
                        geometry_class = "PROXIMAL_ONLY"
                        potential_class = (
                            "NOT_YET_CLASSIFIABLE"
                        )

                else:
                    geometry_class = "UNRESOLVED"
                    potential_class = "NOT_YET_CLASSIFIABLE"

                projection_status = (
                    "PASS"
                    if geometry_class
                    in {
                        "BOTH_FLANKS_PROJECTABLE",
                        "LEFT_FLANK_ONLY",
                        "RIGHT_FLANK_ONLY",
                        "TARGET_INTERNAL_NO_FLANK",
                        "PROXIMAL_RIGHT_WITH_SOFTCLIP",
                        "PROXIMAL_LEFT_WITH_SOFTCLIP",
                    }
                    else "WARN"
                )

                if projected_raw is not None:
                    window_raw = (
                        max(
                            0,
                            projected_raw[0] - sequence_flank,
                        ),
                        min(
                            read_length,
                            projected_raw[1] + sequence_flank,
                        ),
                    )

                elif target_start >= block_end:
                    # Genomic-right side of the alignment.
                    bam_query_end = max(
                        (
                            segment["query_end"]
                            for segment in selected_block["segments"]
                        ),
                        default=record.query_alignment_end,
                    )
                    full_oriented_boundary = (
                        hardclip_left_cigar + bam_query_end
                    )
                    full_oriented_window = (
                        max(
                            0,
                            full_oriented_boundary - sequence_flank,
                        ),
                        read_length,
                    )
                    window_raw = (
                        convert_full_oriented_interval_to_raw(
                            full_oriented_window[0],
                            full_oriented_window[1],
                            read_length,
                            record.is_reverse,
                        )
                    )

                elif target_end <= block_start:
                    # Genomic-left side of the alignment.
                    bam_query_start = min(
                        (
                            segment["query_start"]
                            for segment in selected_block["segments"]
                        ),
                        default=record.query_alignment_start,
                    )
                    full_oriented_boundary = (
                        hardclip_left_cigar + bam_query_start
                    )
                    full_oriented_window = (
                        0,
                        min(
                            read_length,
                            full_oriented_boundary + sequence_flank,
                        ),
                    )
                    window_raw = (
                        convert_full_oriented_interval_to_raw(
                            full_oriented_window[0],
                            full_oriented_window[1],
                            read_length,
                            record.is_reverse,
                        )
                    )

                else:
                    window_raw = None

                overlapping_blocks = sum(
                    interval_overlap(
                        block["ref_start"],
                        block["ref_end"],
                        target_start,
                        target_end,
                    )
                    > 0
                    for block in blocks
                )

                if overlapping_blocks > 1:
                    flags.append("TARGET_OVERLAPS_MULTIPLE_SPLICE_BLOCKS")

            if projected_raw is None:
                projected_start = None
                projected_end = None
            else:
                projected_start, projected_end = projected_raw

            if window_raw is None:
                window_start = None
                window_end = None
                window_length = 0
                flags.append("NO_RAW_SEQUENCE_WINDOW")
            else:
                window_start, window_end = window_raw
                window_start = max(0, min(window_start, read_length))
                window_end = max(
                    window_start,
                    min(window_end, read_length),
                )
                window_length = window_end - window_start

            row = {
                "schema_version": "0.3.0",
                "run_id": run_id,
                "sample_id": sample_id,
                "projection_id": projection_id,
                "read_id": read_id,
                "read_length_bp": read_length,
                "mean_read_q": (
                    "."
                    if read_mean_q is None
                    else f"{read_mean_q:.6f}"
                ),
                "target_region_id": candidate["target_region_id"],
                "target_source": candidate["target_source"],
                "region_type": candidate["region_type"],
                "analysis_mode": candidate["analysis_mode"],
                "representative_locus_id": candidate[
                    "representative_locus_id"
                ],
                "assignment_rank": candidate["assignment_rank"],
                "read_candidate_target_count": candidate[
                    "read_candidate_target_count"
                ],
                "best_alignment_id": alignment_id,
                "best_alignment_class": alignment_class,
                "best_mapq": record.mapping_quality,
                "strand": strand,
                "target_chrom": target["chrom"],
                "target_start": target_start,
                "target_end": target_end,
                "candidate_basis": candidate["candidate_basis"],
                "target_overlap_bp_reported": candidate[
                    "target_overlap_bp"
                ],
                "target_distance_bp_reported": candidate[
                    "target_distance_bp"
                ],
                "selected_block_start": (
                    "." if block_start is None else block_start
                ),
                "selected_block_end": (
                    "." if block_end is None else block_end
                ),
                "selected_block_overlap_bp": block_overlap,
                "selected_block_distance_bp": block_distance,
                "genomic_left_anchor_bp": left_anchor,
                "genomic_right_anchor_bp": right_anchor,
                "genomic_left_softclip_bp": left_ref_softclip,
                "genomic_right_softclip_bp": right_ref_softclip,
                "projected_target_read_start": (
                    "."
                    if projected_start is None
                    else projected_start
                ),
                "projected_target_read_end": (
                    "."
                    if projected_end is None
                    else projected_end
                ),
                "candidate_window_read_start": (
                    "." if window_start is None else window_start
                ),
                "candidate_window_read_end": (
                    "." if window_end is None else window_end
                ),
                "candidate_window_length_bp": window_length,
                "geometry_class": geometry_class,
                "potential_evidence_class": potential_class,
                "projection_status": projection_status,
                "projection_flags": (
                    ";".join(sorted(set(flags)))
                    if flags else "."
                ),
            }
            writer.writerow(row)

            projection_rows_written += 1
            seen_projection_reads.add(read_id)
            counts[f"geometry::{geometry_class}"] += 1
            counts[f"potential::{potential_class}"] += 1
            counts[
                f"projection_status::{projection_status}"
            ] += 1
            counts[
                f"candidate_basis::{candidate['candidate_basis']}"
            ] += 1
            counts[
                f"target_source::{candidate['target_source']}"
            ] += 1
            counts[
                f"alignment_class::{alignment_class}"
            ] += 1

            if int(candidate["assignment_rank"]) == 1:
                rank1_geometry[geometry_class] += 1

            if window_raw is not None and window_length > 0:
                window_sequence = raw_sequence[
                    window_start:window_end
                ]
                window_quality = raw_quality[
                    window_start:window_end
                ]

                header = (
                    f"@{projection_id}"
                    f" read_id={read_id}"
                    f" target={candidate['target_region_id']}"
                    f" source={candidate['target_source']}"
                    f" raw={window_start}-{window_end}"
                    f" geometry={geometry_class}"
                )

                window_handle.write(
                    f"{header}\n"
                    f"{window_sequence}\n"
                    f"+\n"
                    f"{window_quality}\n"
                )
                windows_written += 1
                window_lengths.append(window_length)

                if len(window_sequence) != len(window_quality):
                    raise RuntimeError(
                        f"Sequence/quality length mismatch: "
                        f"{projection_id}"
                    )

missing_alignment_ids = (
    set(candidates_by_alignment) - seen_alignment_ids
)

status = "PASS"

if (
    candidate_rows != expected_rows
    or len(candidate_reads) != expected_reads
    or len(fastq_records) != expected_reads
    or projection_rows_written != expected_rows
    or len(seen_projection_reads) != expected_reads
    or missing_alignment_ids
    or counts["missing_fastq_read"] > 0
    or orientation_mismatch > 0
    or counts["reconstructed_full_query_length_mismatch"] > 0
    or counts["bam_query_length_vs_cigar_mismatch"] > 0
    or counts["unexpected_missing_bam_sequence_nonsecondary"] > 0
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"expected_candidate_rows\t{expected_rows}\n")
    output.write(f"observed_candidate_rows\t{candidate_rows}\n")
    output.write(
        f"projection_rows_written\t{projection_rows_written}\n"
    )
    output.write(
        f"expected_candidate_reads\t{expected_reads}\n"
    )
    output.write(
        f"candidate_reads_in_input\t{len(candidate_reads)}\n"
    )
    output.write(
        f"candidate_fastq_reads_loaded\t{len(fastq_records)}\n"
    )
    output.write(
        f"projection_unique_reads\t"
        f"{len(seen_projection_reads)}\n"
    )
    output.write(
        f"missing_best_alignment_ids\t"
        f"{len(missing_alignment_ids)}\n"
    )
    output.write(
        f"orientation_records_checked\t{orientation_checked}\n"
    )
    output.write(
        f"orientation_raw_sequence_match\t{orientation_match}\n"
    )
    output.write(
        f"orientation_raw_sequence_mismatch\t"
        f"{orientation_mismatch}\n"
    )
    output.write(
        f"candidate_best_alignment_records\t"
        f"{len(seen_alignment_ids)}\n"
    )
    output.write(
        f"bam_sequence_present_records\t"
        f"{counts['bam_sequence_present_records']}\n"
    )
    output.write(
        f"bam_sequence_absent_records\t"
        f"{counts['bam_sequence_absent_records']}\n"
    )
    output.write(
        f"bam_sequence_absent_secondary_records\t"
        f"{counts['bam_sequence_absent_class::secondary']}\n"
    )
    output.write(
        f"unexpected_missing_bam_sequence_nonsecondary\t"
        f"{counts['unexpected_missing_bam_sequence_nonsecondary']}\n"
    )
    output.write(
        f"hardclipped_alignment_records\t"
        f"{counts['hardclipped_alignment_records']}\n"
    )
    output.write(
        f"orientation_match_hardclipped_records\t"
        f"{counts['orientation_match_hardclipped_records']}\n"
    )
    output.write(
        f"bam_query_length_vs_cigar_mismatch\t"
        f"{counts['bam_query_length_vs_cigar_mismatch']}\n"
    )
    output.write(
        f"reconstructed_full_query_length_mismatch\t"
        f"{counts['reconstructed_full_query_length_mismatch']}\n"
    )
    output.write(f"raw_windows_written\t{windows_written}\n")
    output.write(
        f"min_flank_anchor_bp\t{min_anchor}\n"
    )
    output.write(
        f"anchor_window_bp\t{anchor_window}\n"
    )
    output.write(
        f"sequence_window_flank_bp\t{sequence_flank}\n"
    )

    explicitly_reported_count_keys = {
        "bam_sequence_present_records",
        "bam_sequence_absent_records",
        "bam_sequence_absent_class::secondary",
        "unexpected_missing_bam_sequence_nonsecondary",
        "hardclipped_alignment_records",
        "orientation_match_hardclipped_records",
        "bam_query_length_vs_cigar_mismatch",
        "reconstructed_full_query_length_mismatch",
    }

    for key, value in sorted(counts.items()):
        if key in explicitly_reported_count_keys:
            continue
        output.write(f"{key}\t{value}\n")

    for key, value in sorted(rank1_geometry.items()):
        output.write(f"rank1_geometry::{key}\t{value}\n")

    if window_lengths:
        output.write(
            f"window_length::mean\t"
            f"{statistics.mean(window_lengths):.6f}\n"
        )

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
                f"window_length::{label}\t"
                f"{quantile(window_lengths, probability):.6f}\n"
            )

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Raw-read projection audit requires review")
PY

echo "===== 1. INPUT VALIDATION ====="

samtools quickcheck -v "$BAM"
gzip -t "$READ_TARGETS"
gzip -t "$TARGETS"
gzip -t "$CANDIDATE_FASTQ"

echo "Inputs: PASS"

echo
echo "===== 2. PARAMETERS ====="
column -ts $'\t' "$PARAMETERS"

echo
echo "===== 3. PROJECT TARGETS TO RAW READS ====="

rm -f \
  "$PROJECTION" \
  "$WINDOW_FASTQ" \
  "$QC_SUMMARY" \
  "$MANIFEST"

python "$PROJECTOR" \
  "$BAM" \
  "$READ_TARGETS" \
  "$TARGETS" \
  "$CANDIDATE_FASTQ" \
  "$PROJECTION" \
  "$WINDOW_FASTQ" \
  "$QC_SUMMARY" \
  "$RUN_ID" \
  "$SAMPLE_ID" \
  "$MIN_FLANK_ANCHOR_BP" \
  "$ANCHOR_WINDOW_BP" \
  "$SEQUENCE_WINDOW_FLANK_BP" \
  "$LOW_MAPQ_WARN" \
  "$EXPECTED_CANDIDATE_ROWS" \
  "$EXPECTED_CANDIDATE_READS"

gzip -t "$PROJECTION"
gzip -t "$WINDOW_FASTQ"

echo
echo "===== RAW PROJECTION QC ====="
column -ts $'\t' "$QC_SUMMARY"

echo
echo "===== 4. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    rows="$(gzip -cd "$PROJECTION" | awk 'END {print NR-1}')"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$PROJECTION")" \
      "$rows" \
      "$(stat -c '%s' "$PROJECTION")" \
      "$(sha256sum "$PROJECTION" | awk '{print $1}')" \
      "$PROJECTION"

    rows="$(gzip -cd "$WINDOW_FASTQ" | awk 'END {print NR/4}')"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$WINDOW_FASTQ")" \
      "$rows" \
      "$(stat -c '%s' "$WINDOW_FASTQ")" \
      "$(sha256sum "$WINDOW_FASTQ" | awk '{print $1}')" \
      "$WINDOW_FASTQ"

    for path in "$QC_SUMMARY" "$PARAMETERS"; do
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
echo "$PROJECTION"
echo "$WINDOW_FASTQ"
echo "$QC_SUMMARY"
echo "$MANIFEST"
