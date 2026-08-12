#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_full_read_block_geometry_v0.3.1"

LOCAL_PAF="$PROJECT_ROOT/results/11_residual_context/$RUN_ID/full_reads_to_extended_locus.paf"
LOCAL_SUMMARY="$PROJECT_ROOT/results/11_residual_context/$RUN_ID/full_reads_to_extended_locus.summary.tsv"
FLANK_SUMMARY="$PROJECT_ROOT/results/11_flank_rescue/$RUN_ID/reference_compatible_event_flank_rescue.tsv"
DIRECT_SUMMARY="$PROJECT_ROOT/results/11_observed_reference_alignment/$RUN_ID/observed_to_reference_locus.summary.tsv"
BAM_GEOMETRY="$PROJECT_ROOT/results/11_residual_context/$RUN_ID/source_read_bam_geometry.tsv"

OUTDIR="$PROJECT_ROOT/results/11_full_read_block_geometry/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_full_read_block_geometry/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_full_read_block_geometry/$RUN_ID"

BLOCKS="$OUTDIR/full_read_extended_locus_blocks.tsv"
INTEGRATION="$OUTDIR/repeat_event_full_read_geometry.tsv"
QC="$QCDIR/full_read_block_geometry.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.full_read_block_geometry.manifest.tsv"
PY="$WORKDIR/parse_full_read_block_geometry.py"

EXPECTED_EVENTS=2
EXPECTED_PAF_ROWS=2
MIN_ANCHOR_QUERY_BP=20
END_TOLERANCE_BP=10

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$LOCAL_PAF" \
  "$LOCAL_SUMMARY" \
  "$FLANK_SUMMARY" \
  "$DIRECT_SUMMARY" \
  "$BAM_GEOMETRY"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
model_id	$MODEL_ID	Integrate direct repeat alignment and full-read splice-aware alignment
minimum_anchor_query_bp	$MIN_ANCHOR_QUERY_BP	Minimum query bases in an upstream/downstream alignment block
end_tolerance_bp	$END_TOLERANCE_BP	Raw-read end tolerance for censored classification
block_source	minimap2_cg_tag	Blocks are split at N operations in cg:Z CIGAR
repeat_boundary_source	direct_event_to_reference_alignment	Reference-compatible raw-read repeat interval
classification_scope	provisional_evidence_geometry	No allele-length or expansion call
EOF

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict

(
    paf_path,
    local_summary_path,
    flank_summary_path,
    direct_summary_path,
    bam_geometry_path,
    blocks_path,
    integration_path,
    qc_path,
    model_id,
    expected_events_text,
    expected_paf_rows_text,
    minimum_anchor_text,
    end_tolerance_text,
) = sys.argv[1:]

EXPECTED_EVENTS = int(expected_events_text)
EXPECTED_PAF_ROWS = int(expected_paf_rows_text)
MINIMUM_ANCHOR = int(minimum_anchor_text)
END_TOLERANCE = int(end_tolerance_text)


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


def parse_target_id(target_id):
    match = re.search(
        r"\|([^:|]+):([0-9]+)-([0-9]+)$",
        target_id,
    )

    if match is None:
        raise ValueError(
            "Cannot parse extended-locus target ID: {}".format(
                target_id
            )
        )

    return (
        match.group(1),
        int(match.group(2)),
        int(match.group(3)),
    )


def parse_cigar(cigar):
    operations = re.findall(
        r"([0-9]+)([MIDNSHP=X])",
        cigar,
    )

    if not operations:
        raise ValueError(
            "Cannot parse CIGAR: {}".format(cigar)
        )

    parsed = [
        (operation, int(length))
        for length, operation in operations
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


def interval_overlap(
    start_a,
    end_a,
    start_b,
    end_b,
):
    return max(
        0,
        min(end_a, end_b)
        - max(start_a, start_b),
    )


def split_alignment_blocks(
    query_start,
    query_end,
    target_start,
    strand,
    cigar,
):
    operations = parse_cigar(cigar)

    query_cursor = (
        query_start
        if strand == "+"
        else query_end
    )
    target_cursor = target_start

    blocks = []
    block_index = 1
    block_query_positions = [query_cursor]
    block_target_start = target_cursor
    block_operations = []
    block_query_consumed = 0
    block_target_consumed = 0

    def finish_block():
        nonlocal block_index
        nonlocal block_query_positions
        nonlocal block_target_start
        nonlocal block_operations
        nonlocal block_query_consumed
        nonlocal block_target_consumed

        if (
            block_query_consumed == 0
            and block_target_consumed == 0
        ):
            return

        blocks.append(
            {
                "block_index": block_index,
                "query_start": min(
                    block_query_positions
                ),
                "query_end": max(
                    block_query_positions
                ),
                "target_start": block_target_start,
                "target_end": target_cursor,
                "query_consumed_bp": block_query_consumed,
                "target_consumed_bp": block_target_consumed,
                "block_cigar": "".join(
                    "{}{}".format(length, operation)
                    for operation, length
                    in block_operations
                ),
            }
        )

        block_index += 1
        block_query_positions = [query_cursor]
        block_target_start = target_cursor
        block_operations = []
        block_query_consumed = 0
        block_target_consumed = 0

    for operation, length in operations:
        if operation == "N":
            finish_block()
            target_cursor += length
            block_target_start = target_cursor
            block_query_positions = [query_cursor]
            continue

        block_operations.append(
            (operation, length)
        )

        query_consumes = operation in {
            "M",
            "I",
            "S",
            "=",
            "X",
        }
        target_consumes = operation in {
            "M",
            "D",
            "=",
            "X",
        }

        if query_consumes:
            if strand == "+":
                query_cursor += length
            else:
                query_cursor -= length

            block_query_positions.append(
                query_cursor
            )
            block_query_consumed += length

        if target_consumes:
            target_cursor += length
            block_target_consumed += length

    finish_block()

    return blocks


def load_table(path, key):
    with open(
        path,
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return {
            row[key]: row
            for row in csv.DictReader(
                handle,
                delimiter="\t",
            )
        }


local_summary = load_table(
    local_summary_path,
    "read_id",
)
flank_summary = load_table(
    flank_summary_path,
    "event_id",
)
direct_summary = load_table(
    direct_summary_path,
    "event_id",
)

bam_geometry = defaultdict(list)

with open(
    bam_geometry_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    for row in csv.DictReader(
        handle,
        delimiter="\t",
    ):
        bam_geometry[row["read_id"]].append(
            row
        )

event_by_read = {
    row["read_id"]: event_id
    for event_id, row in flank_summary.items()
}

paf_rows = []

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

        if len(fields) < 12:
            raise RuntimeError(
                "Malformed PAF row"
            )

        tags = parse_tags(fields[12:])

        if "cg" not in tags:
            raise RuntimeError(
                "PAF row lacks cg:Z CIGAR for read {}".format(
                    fields[0]
                )
            )

        paf_rows.append(
            {
                "read_id": fields[0],
                "query_length": int(fields[1]),
                "query_start": int(fields[2]),
                "query_end": int(fields[3]),
                "strand": fields[4],
                "target_id": fields[5],
                "target_length": int(fields[6]),
                "target_start": int(fields[7]),
                "target_end": int(fields[8]),
                "matches": int(fields[9]),
                "block_length": int(fields[10]),
                "mapq": int(fields[11]),
                "alignment_score": tags.get(
                    "AS",
                    int(fields[9]),
                ),
                "cigar": tags["cg"],
            }
        )

best_paf_by_read = {}

for row in paf_rows:
    current = best_paf_by_read.get(
        row["read_id"]
    )

    rank = (
        row["alignment_score"],
        row["matches"],
        row["query_end"] - row["query_start"],
    )

    if current is None:
        best_paf_by_read[row["read_id"]] = row
    else:
        current_rank = (
            current["alignment_score"],
            current["matches"],
            current["query_end"]
            - current["query_start"],
        )

        if rank > current_rank:
            best_paf_by_read[row["read_id"]] = row

block_fields = [
    "model_id",
    "event_id",
    "read_id",
    "block_index",
    "strand",
    "target_id",
    "chrom",
    "extended_region_start",
    "extended_region_end",
    "query_start",
    "query_end",
    "query_span_bp",
    "target_local_start",
    "target_local_end",
    "genomic_start",
    "genomic_end",
    "genomic_span_bp",
    "block_cigar",
    "repeat_locus_overlap_bp",
    "genomic_relation_to_repeat_locus",
    "query_overlap_repeat_segment_bp",
    "query_overlap_left_residual_bp",
    "query_overlap_right_residual_bp",
    "anchor_side",
    "anchor_candidate",
]

block_rows = []
integration_rows = []
counts = Counter()
cigar_n_operations = 0

for read_id in sorted(event_by_read):
    event_id = event_by_read[read_id]

    if read_id not in best_paf_by_read:
        raise RuntimeError(
            "No local PAF alignment for read {}".format(
                read_id
            )
        )

    paf = best_paf_by_read[read_id]
    flank = flank_summary[event_id]
    direct = direct_summary[event_id]

    chromosome, extended_start, extended_end = (
        parse_target_id(paf["target_id"])
    )

    locus_match = re.match(
        r"^EXTLOC_[0-9]+_.+_([0-9]+)_([0-9]+)$",
        direct["reference_locus_id"],
    )

    if locus_match is None:
        raise RuntimeError(
            "Cannot parse locus coordinates: {}".format(
                direct["reference_locus_id"]
            )
        )

    locus_start = int(locus_match.group(1))
    locus_end = int(locus_match.group(2))

    event_start = int(flank["event_start"])
    event_end = int(flank["event_end"])
    read_length = int(flank["read_length_bp"])

    repeat_raw_start = (
        event_start
        + int(direct["best_query_start"])
    )
    repeat_raw_end = (
        event_start
        + int(direct["best_query_end"])
    )

    blocks = split_alignment_blocks(
        paf["query_start"],
        paf["query_end"],
        paf["target_start"],
        paf["strand"],
        paf["cigar"],
    )

    cigar_n_operations += paf["cigar"].count("N")

    left_anchor_blocks = []
    right_anchor_blocks = []

    for block in blocks:
        genomic_start = (
            extended_start
            + block["target_start"]
        )
        genomic_end = (
            extended_start
            + block["target_end"]
        )

        repeat_overlap = interval_overlap(
            genomic_start,
            genomic_end,
            locus_start,
            locus_end,
        )

        if genomic_end <= locus_start:
            relation = "UPSTREAM"
        elif genomic_start >= locus_end:
            relation = "DOWNSTREAM"
        else:
            relation = "OVERLAPS_REPEAT_LOCUS"

        repeat_query_overlap = interval_overlap(
            block["query_start"],
            block["query_end"],
            repeat_raw_start,
            repeat_raw_end,
        )
        left_query_overlap = interval_overlap(
            block["query_start"],
            block["query_end"],
            0,
            repeat_raw_start,
        )
        right_query_overlap = interval_overlap(
            block["query_start"],
            block["query_end"],
            repeat_raw_end,
            read_length,
        )

        anchor_side = "."

        if (
            relation == "UPSTREAM"
            and left_query_overlap >= MINIMUM_ANCHOR
        ):
            anchor_side = "GENOMIC_LEFT"
            left_anchor_blocks.append(block)

        elif (
            relation == "DOWNSTREAM"
            and right_query_overlap >= MINIMUM_ANCHOR
        ):
            anchor_side = "GENOMIC_RIGHT"
            right_anchor_blocks.append(block)

        anchor_candidate = anchor_side != "."

        block_rows.append(
            {
                "model_id": model_id,
                "event_id": event_id,
                "read_id": read_id,
                "block_index": block[
                    "block_index"
                ],
                "strand": paf["strand"],
                "target_id": paf["target_id"],
                "chrom": chromosome,
                "extended_region_start": extended_start,
                "extended_region_end": extended_end,
                "query_start": block[
                    "query_start"
                ],
                "query_end": block["query_end"],
                "query_span_bp": (
                    block["query_end"]
                    - block["query_start"]
                ),
                "target_local_start": block[
                    "target_start"
                ],
                "target_local_end": block[
                    "target_end"
                ],
                "genomic_start": genomic_start,
                "genomic_end": genomic_end,
                "genomic_span_bp": (
                    genomic_end - genomic_start
                ),
                "block_cigar": block[
                    "block_cigar"
                ],
                "repeat_locus_overlap_bp": repeat_overlap,
                "genomic_relation_to_repeat_locus": relation,
                "query_overlap_repeat_segment_bp": (
                    repeat_query_overlap
                ),
                "query_overlap_left_residual_bp": (
                    left_query_overlap
                ),
                "query_overlap_right_residual_bp": (
                    right_query_overlap
                ),
                "anchor_side": anchor_side,
                "anchor_candidate": str(
                    anchor_candidate
                ).lower(),
            }
        )

    left_anchor = bool(left_anchor_blocks)
    right_anchor = bool(right_anchor_blocks)

    left_unaligned_tail = repeat_raw_start
    right_unaligned_tail = (
        read_length - repeat_raw_end
    )

    if left_anchor and right_anchor:
        geometry_class = (
            "BOTH_GENOMIC_FLANKS_RESCUED"
        )
        provisional_class = (
            "SPAN_RESCUE_CANDIDATE"
        )

    elif right_anchor:
        geometry_class = (
            "GENOMIC_RIGHT_FLANK_RESCUED_ONLY"
        )

        if repeat_raw_start <= END_TOLERANCE:
            provisional_class = (
                "RIGHT_ANCHORED_CENSORED_LEFT_CANDIDATE"
            )
        else:
            provisional_class = (
                "RIGHT_ONLY_INTERNAL_RESCUED"
            )

    elif left_anchor:
        geometry_class = (
            "GENOMIC_LEFT_FLANK_RESCUED_ONLY"
        )

        if (
            read_length - repeat_raw_end
            <= END_TOLERANCE
        ):
            provisional_class = (
                "LEFT_ANCHORED_CENSORED_RIGHT_CANDIDATE"
            )
        else:
            provisional_class = (
                "LEFT_ONLY_INTERNAL_RESCUED"
            )

    else:
        geometry_class = "NO_GENOMIC_FLANK_RESCUE"

        if (
            read_length - repeat_raw_end
            <= END_TOLERANCE
        ):
            provisional_class = (
                "REPEAT_ONLY_END_TRUNCATED"
            )
        else:
            provisional_class = (
                "REPEAT_ONLY_UNANCHORED"
            )

    counts[
        "geometry::{}".format(geometry_class)
    ] += 1
    counts[
        "provisional::{}".format(
            provisional_class
        )
    ] += 1

    primary_bam = next(
        (
            row
            for row in bam_geometry[read_id]
            if row["alignment_class"] == "primary"
        ),
        None,
    )

    integration_rows.append(
        {
            "model_id": model_id,
            "event_id": event_id,
            "read_id": read_id,
            "read_length_bp": read_length,
            "original_event_start": event_start,
            "original_event_end": event_end,
            "original_event_bp": event_end - event_start,
            "direct_repeat_query_start_within_event": direct[
                "best_query_start"
            ],
            "direct_repeat_query_end_within_event": direct[
                "best_query_end"
            ],
            "reference_compatible_repeat_raw_start": (
                repeat_raw_start
            ),
            "reference_compatible_repeat_raw_end": (
                repeat_raw_end
            ),
            "reference_compatible_repeat_bp": (
                repeat_raw_end - repeat_raw_start
            ),
            "left_raw_residual_bp": left_unaligned_tail,
            "right_raw_residual_bp": right_unaligned_tail,
            "full_read_alignment_query_start": paf[
                "query_start"
            ],
            "full_read_alignment_query_end": paf[
                "query_end"
            ],
            "full_read_alignment_query_bp": (
                paf["query_end"]
                - paf["query_start"]
            ),
            "full_read_alignment_target_span_bp": (
                paf["target_end"]
                - paf["target_start"]
            ),
            "full_read_alignment_cigar": paf[
                "cigar"
            ],
            "splice_junction_count": sum(
                1
                for operation, _length
                in parse_cigar(paf["cigar"])
                if operation == "N"
            ),
            "alignment_block_count": len(blocks),
            "genomic_left_anchor_blocks": len(
                left_anchor_blocks
            ),
            "genomic_right_anchor_blocks": len(
                right_anchor_blocks
            ),
            "rescued_geometry_class": geometry_class,
            "provisional_evidence_class": (
                provisional_class
            ),
            "primary_bam_query_start": (
                primary_bam[
                    "query_alignment_start"
                ]
                if primary_bam
                else "."
            ),
            "primary_bam_query_end": (
                primary_bam[
                    "query_alignment_end"
                ]
                if primary_bam
                else "."
            ),
            "primary_bam_left_softclip_bp": (
                primary_bam[
                    "left_softclip_bp"
                ]
                if primary_bam
                else "."
            ),
            "primary_bam_right_softclip_bp": (
                primary_bam[
                    "right_softclip_bp"
                ]
                if primary_bam
                else "."
            ),
            "allele_length_status": (
                "NOT_EMITTED_GEOMETRY_RESCUE_PROTOTYPE"
            ),
            "reference_relative_expansion_status": (
                "NOT_ASSESSED"
            ),
            "interpretation": (
                "Direct repeat alignment refines the raw-read "
                "repeat-compatible interval; splice-aware full-read "
                "blocks test whether residual sequence supplies "
                "upstream or downstream transcript anchors."
            ),
        }
    )

with open(
    blocks_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=block_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(block_rows)

integration_fields = list(
    integration_rows[0].keys()
)

with open(
    integration_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=integration_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(integration_rows)

status = "PASS"

if (
    len(paf_rows) != EXPECTED_PAF_ROWS
    or len(integration_rows) != EXPECTED_EVENTS
    or not block_rows
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
            len(integration_rows)
        )
    )
    handle.write(
        "expected_paf_rows\t{}\n".format(
            EXPECTED_PAF_ROWS
        )
    )
    handle.write(
        "observed_paf_rows\t{}\n".format(
            len(paf_rows)
        )
    )
    handle.write(
        "alignment_blocks_written\t{}\n".format(
            len(block_rows)
        )
    )
    handle.write(
        "cigar_N_operations\t{}\n".format(
            cigar_n_operations
        )
    )
    handle.write(
        "events_with_genomic_left_anchor\t{}\n".format(
            sum(
                int(
                    row[
                        "genomic_left_anchor_blocks"
                    ]
                ) > 0
                for row in integration_rows
            )
        )
    )
    handle.write(
        "events_with_genomic_right_anchor\t{}\n".format(
            sum(
                int(
                    row[
                        "genomic_right_anchor_blocks"
                    ]
                ) > 0
                for row in integration_rows
            )
        )
    )

    for key, value in sorted(counts.items()):
        handle.write(
            "{}\t{}\n".format(
                key,
                value,
            )
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

if status != "PASS":
    raise SystemExit(
        "Full-read block geometry requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$BLOCKS" \
  "$INTEGRATION" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== PARSE FULL-READ SPLICE BLOCKS ====="

python "$PY" \
  "$LOCAL_PAF" \
  "$LOCAL_SUMMARY" \
  "$FLANK_SUMMARY" \
  "$DIRECT_SUMMARY" \
  "$BAM_GEOMETRY" \
  "$BLOCKS" \
  "$INTEGRATION" \
  "$QC" \
  "$MODEL_ID" \
  "$EXPECTED_EVENTS" \
  "$EXPECTED_PAF_ROWS" \
  "$MIN_ANCHOR_QUERY_BP" \
  "$END_TOLERANCE_BP"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== INTEGRATED EVENT GEOMETRY ====="
column -ts $'\t' "$INTEGRATION"

echo
echo "===== ALIGNMENT BLOCKS ====="
column -ts $'\t' "$BLOCKS"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$BLOCKS" \
      "$INTEGRATION" \
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
