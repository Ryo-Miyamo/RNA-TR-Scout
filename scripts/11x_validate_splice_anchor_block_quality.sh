#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
RULESET_ID="rnatr_splice_anchor_block_validation_v0.3.1"

BLOCKS_IN="$PROJECT_ROOT/results/11_full_read_block_geometry/$RUN_ID/full_read_extended_locus_blocks.tsv"
GEOMETRY_IN="$PROJECT_ROOT/results/11_full_read_block_geometry/$RUN_ID/repeat_event_full_read_geometry.tsv"

OUTDIR="$PROJECT_ROOT/results/11_anchor_block_validation/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_anchor_block_validation/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_anchor_block_validation/$RUN_ID"

BLOCKS_OUT="$OUTDIR/full_read_blocks.quality_validated.tsv"
GEOMETRY_OUT="$OUTDIR/repeat_event_geometry.quality_validated.tsv"
QC="$QCDIR/anchor_block_validation.qc.tsv"
PARAMETERS="$OUTDIR/${RULESET_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.anchor_block_validation.manifest.tsv"
PY="$WORKDIR/validate_anchor_blocks.py"

EXPECTED_EVENTS=2
EXPECTED_BLOCKS=5
EXPECTED_OLD_ANCHOR_BLOCKS=2
EXPECTED_VALIDATED_ANCHOR_BLOCKS=0

MIN_QUERY_SPAN_BP=20
MIN_REFERENCE_SPAN_BP=20
MIN_MATCHLIKE_BP=20
MIN_QUERY_MATCH_FRACTION=0.70
MIN_REFERENCE_MATCH_FRACTION=0.70
MAX_INSERTION_FRACTION=0.25
MAX_DELETION_FRACTION=0.25
MIN_SPAN_BALANCE=0.50
END_TOLERANCE_BP=10

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$BLOCKS_IN" "$GEOMETRY_IN"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
ruleset_id	$RULESET_ID	Block-level validation of splice-aware flank anchors
min_query_span_bp	$MIN_QUERY_SPAN_BP	Minimum raw-read bases in anchor block
min_reference_span_bp	$MIN_REFERENCE_SPAN_BP	Minimum reference bases in anchor block
min_matchlike_bp	$MIN_MATCHLIKE_BP	Minimum M/= bases in block CIGAR
min_query_match_fraction	$MIN_QUERY_MATCH_FRACTION	(M+=)/query span
min_reference_match_fraction	$MIN_REFERENCE_MATCH_FRACTION	(M+=)/reference span
max_insertion_fraction	$MAX_INSERTION_FRACTION	I/query span
max_deletion_fraction	$MAX_DELETION_FRACTION	D/reference span
min_span_balance	$MIN_SPAN_BALANCE	min(query span, reference span)/max(...)
end_tolerance_bp	$END_TOLERANCE_BP	Raw-read end tolerance
validation_semantics	block_quality_required_after_splice_N	Whole-alignment MAPQ cannot validate weak post-N blocks
call_semantics	geometry_correction_only	No allele-length or expansion call
EOF

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict

(
    blocks_input,
    geometry_input,
    blocks_output,
    geometry_output,
    qc_output,
    ruleset_id,
    expected_events_text,
    expected_blocks_text,
    expected_old_anchor_text,
    expected_validated_anchor_text,
    min_query_span_text,
    min_reference_span_text,
    min_matchlike_text,
    min_query_match_fraction_text,
    min_reference_match_fraction_text,
    max_insertion_fraction_text,
    max_deletion_fraction_text,
    min_span_balance_text,
    end_tolerance_text,
) = sys.argv[1:]

EXPECTED_EVENTS = int(expected_events_text)
EXPECTED_BLOCKS = int(expected_blocks_text)
EXPECTED_OLD_ANCHORS = int(expected_old_anchor_text)
EXPECTED_VALIDATED_ANCHORS = int(
    expected_validated_anchor_text
)

MIN_QUERY_SPAN = int(min_query_span_text)
MIN_REFERENCE_SPAN = int(min_reference_span_text)
MIN_MATCHLIKE = int(min_matchlike_text)
MIN_QUERY_MATCH_FRACTION = float(
    min_query_match_fraction_text
)
MIN_REFERENCE_MATCH_FRACTION = float(
    min_reference_match_fraction_text
)
MAX_INSERTION_FRACTION = float(
    max_insertion_fraction_text
)
MAX_DELETION_FRACTION = float(
    max_deletion_fraction_text
)
MIN_SPAN_BALANCE = float(min_span_balance_text)
END_TOLERANCE = int(end_tolerance_text)


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


def safe_fraction(numerator, denominator):
    return (
        numerator / denominator
        if denominator > 0
        else 0.0
    )


with open(
    blocks_input,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    block_reader = csv.DictReader(
        handle,
        delimiter="\t",
    )
    block_input_fields = block_reader.fieldnames or []
    block_rows = list(block_reader)

with open(
    geometry_input,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    geometry_reader = csv.DictReader(
        handle,
        delimiter="\t",
    )
    geometry_input_fields = geometry_reader.fieldnames or []
    geometry_rows = list(geometry_reader)

block_extra_fields = [
    "anchor_validation_ruleset_id",
    "cigar_M_bp",
    "cigar_equal_bp",
    "cigar_X_bp",
    "cigar_I_bp",
    "cigar_D_bp",
    "matchlike_bp",
    "query_match_fraction",
    "reference_match_fraction",
    "insertion_fraction",
    "deletion_fraction",
    "span_balance",
    "block_quality_pass",
    "validated_anchor_candidate",
    "block_quality_fail_reasons",
]

validated_block_rows = []
validated_by_event = defaultdict(
    lambda: {
        "GENOMIC_LEFT": [],
        "GENOMIC_RIGHT": [],
    }
)
counts = Counter()

for row in block_rows:
    operations = parse_cigar(row["block_cigar"])
    operation_counts = Counter()

    for operation, length in operations:
        operation_counts[operation] += length

    query_span = int(row["query_span_bp"])
    reference_span = int(row["genomic_span_bp"])

    m_bp = operation_counts["M"]
    equal_bp = operation_counts["="]
    x_bp = operation_counts["X"]
    insertion_bp = operation_counts["I"]
    deletion_bp = operation_counts["D"]
    matchlike_bp = m_bp + equal_bp

    query_match_fraction = safe_fraction(
        matchlike_bp,
        query_span,
    )
    reference_match_fraction = safe_fraction(
        matchlike_bp,
        reference_span,
    )
    insertion_fraction = safe_fraction(
        insertion_bp,
        query_span,
    )
    deletion_fraction = safe_fraction(
        deletion_bp,
        reference_span,
    )
    span_balance = safe_fraction(
        min(query_span, reference_span),
        max(query_span, reference_span),
    )

    fail_reasons = []

    if query_span < MIN_QUERY_SPAN:
        fail_reasons.append("QUERY_SPAN_TOO_SHORT")

    if reference_span < MIN_REFERENCE_SPAN:
        fail_reasons.append("REFERENCE_SPAN_TOO_SHORT")

    if matchlike_bp < MIN_MATCHLIKE:
        fail_reasons.append("MATCHLIKE_BP_TOO_LOW")

    if query_match_fraction < MIN_QUERY_MATCH_FRACTION:
        fail_reasons.append(
            "QUERY_MATCH_FRACTION_TOO_LOW"
        )

    if (
        reference_match_fraction
        < MIN_REFERENCE_MATCH_FRACTION
    ):
        fail_reasons.append(
            "REFERENCE_MATCH_FRACTION_TOO_LOW"
        )

    if insertion_fraction > MAX_INSERTION_FRACTION:
        fail_reasons.append("INSERTION_FRACTION_TOO_HIGH")

    if deletion_fraction > MAX_DELETION_FRACTION:
        fail_reasons.append("DELETION_FRACTION_TOO_HIGH")

    if span_balance < MIN_SPAN_BALANCE:
        fail_reasons.append("QUERY_REFERENCE_SPAN_IMBALANCE")

    quality_pass = not fail_reasons
    old_anchor = row["anchor_candidate"] == "true"
    validated_anchor = old_anchor and quality_pass

    output_row = dict(row)
    output_row.update(
        {
            "anchor_validation_ruleset_id": ruleset_id,
            "cigar_M_bp": m_bp,
            "cigar_equal_bp": equal_bp,
            "cigar_X_bp": x_bp,
            "cigar_I_bp": insertion_bp,
            "cigar_D_bp": deletion_bp,
            "matchlike_bp": matchlike_bp,
            "query_match_fraction": "{:.6f}".format(
                query_match_fraction
            ),
            "reference_match_fraction": "{:.6f}".format(
                reference_match_fraction
            ),
            "insertion_fraction": "{:.6f}".format(
                insertion_fraction
            ),
            "deletion_fraction": "{:.6f}".format(
                deletion_fraction
            ),
            "span_balance": "{:.6f}".format(
                span_balance
            ),
            "block_quality_pass": str(
                quality_pass
            ).lower(),
            "validated_anchor_candidate": str(
                validated_anchor
            ).lower(),
            "block_quality_fail_reasons": (
                ";".join(fail_reasons)
                if fail_reasons
                else "."
            ),
        }
    )
    validated_block_rows.append(output_row)

    if old_anchor:
        counts["old_anchor_blocks"] += 1

    if validated_anchor:
        counts["validated_anchor_blocks"] += 1
        validated_by_event[row["event_id"]][
            row["anchor_side"]
        ].append(output_row)

    for reason in fail_reasons:
        counts[
            "block_fail::{}".format(reason)
        ] += 1

with open(
    blocks_output,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=block_input_fields + block_extra_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(validated_block_rows)

geometry_extra_fields = [
    "anchor_validation_ruleset_id",
    "previous_rescued_geometry_class",
    "previous_provisional_evidence_class",
    "validated_genomic_left_anchor_blocks",
    "validated_genomic_right_anchor_blocks",
    "rejected_old_anchor_blocks",
    "quality_validated_geometry_class",
    "quality_validated_evidence_class",
    "quality_validation_interpretation",
]

validated_geometry_rows = []

for row in geometry_rows:
    event_id = row["event_id"]
    left_valid = validated_by_event[event_id][
        "GENOMIC_LEFT"
    ]
    right_valid = validated_by_event[event_id][
        "GENOMIC_RIGHT"
    ]

    old_left = int(row["genomic_left_anchor_blocks"])
    old_right = int(row["genomic_right_anchor_blocks"])
    rejected_old = (
        old_left
        + old_right
        - len(left_valid)
        - len(right_valid)
    )

    read_length = int(row["read_length_bp"])
    repeat_start = int(
        row["reference_compatible_repeat_raw_start"]
    )
    repeat_end = int(
        row["reference_compatible_repeat_raw_end"]
    )

    if left_valid and right_valid:
        geometry_class = "BOTH_GENOMIC_FLANKS_VALIDATED"
        evidence_class = "SPAN_RESCUE_CANDIDATE"

    elif right_valid:
        geometry_class = (
            "GENOMIC_RIGHT_FLANK_VALIDATED_ONLY"
        )
        if repeat_start <= END_TOLERANCE:
            evidence_class = (
                "RIGHT_ANCHORED_CENSORED_LEFT_CANDIDATE"
            )
        else:
            evidence_class = (
                "RIGHT_ONLY_INTERNAL_RESCUED"
            )

    elif left_valid:
        geometry_class = (
            "GENOMIC_LEFT_FLANK_VALIDATED_ONLY"
        )
        if read_length - repeat_end <= END_TOLERANCE:
            evidence_class = (
                "LEFT_ANCHORED_CENSORED_RIGHT_CANDIDATE"
            )
        else:
            evidence_class = (
                "LEFT_ONLY_INTERNAL_RESCUED"
            )

    else:
        geometry_class = "NO_VALIDATED_GENOMIC_FLANK"

        if read_length - repeat_end <= END_TOLERANCE:
            evidence_class = "REPEAT_ONLY_END_TRUNCATED"
        else:
            evidence_class = (
                "REPEAT_ONLY_UNANCHORED_CONFIRMED"
            )

    if rejected_old > 0:
        interpretation = (
            "Previous post-N anchor blocks were rejected because "
            "their block CIGAR was dominated by insertions, had "
            "insufficient reference support, or was too short."
        )
    else:
        interpretation = (
            "No previous anchor block required rejection."
        )

    output_row = dict(row)
    output_row.update(
        {
            "anchor_validation_ruleset_id": ruleset_id,
            "previous_rescued_geometry_class": row[
                "rescued_geometry_class"
            ],
            "previous_provisional_evidence_class": row[
                "provisional_evidence_class"
            ],
            "validated_genomic_left_anchor_blocks": len(
                left_valid
            ),
            "validated_genomic_right_anchor_blocks": len(
                right_valid
            ),
            "rejected_old_anchor_blocks": rejected_old,
            "quality_validated_geometry_class": (
                geometry_class
            ),
            "quality_validated_evidence_class": (
                evidence_class
            ),
            "quality_validation_interpretation": (
                interpretation
            ),
        }
    )
    validated_geometry_rows.append(output_row)

    counts[
        "validated_geometry::{}".format(
            geometry_class
        )
    ] += 1
    counts[
        "validated_evidence::{}".format(
            evidence_class
        )
    ] += 1

with open(
    geometry_output,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=(
            geometry_input_fields
            + geometry_extra_fields
        ),
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(validated_geometry_rows)

status = "PASS"

if (
    len(geometry_rows) != EXPECTED_EVENTS
    or len(block_rows) != EXPECTED_BLOCKS
    or counts["old_anchor_blocks"]
       != EXPECTED_OLD_ANCHORS
    or counts["validated_anchor_blocks"]
       != EXPECTED_VALIDATED_ANCHORS
):
    status = "REVIEW"

with open(
    qc_output,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "expected_events\t{}\n".format(EXPECTED_EVENTS)
    )
    handle.write(
        "observed_events\t{}\n".format(
            len(geometry_rows)
        )
    )
    handle.write(
        "expected_blocks\t{}\n".format(EXPECTED_BLOCKS)
    )
    handle.write(
        "observed_blocks\t{}\n".format(len(block_rows))
    )
    handle.write(
        "expected_old_anchor_blocks\t{}\n".format(
            EXPECTED_OLD_ANCHORS
        )
    )
    handle.write(
        "observed_old_anchor_blocks\t{}\n".format(
            counts["old_anchor_blocks"]
        )
    )
    handle.write(
        "expected_validated_anchor_blocks\t{}\n".format(
            EXPECTED_VALIDATED_ANCHORS
        )
    )
    handle.write(
        "validated_anchor_blocks\t{}\n".format(
            counts["validated_anchor_blocks"]
        )
    )

    for key, value in sorted(counts.items()):
        if key in {
            "old_anchor_blocks",
            "validated_anchor_blocks",
        }:
            continue
        handle.write("{}\t{}\n".format(key, value))

    handle.write("allele_length_calls_emitted\t0\n")
    handle.write("expansion_calls_emitted\t0\n")
    handle.write(
        "audit_status\t{}\n".format(status)
    )

if status != "PASS":
    raise SystemExit(
        "Anchor block validation requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$BLOCKS_OUT" \
  "$GEOMETRY_OUT" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== VALIDATE POST-N ANCHOR BLOCK QUALITY ====="

python "$PY" \
  "$BLOCKS_IN" \
  "$GEOMETRY_IN" \
  "$BLOCKS_OUT" \
  "$GEOMETRY_OUT" \
  "$QC" \
  "$RULESET_ID" \
  "$EXPECTED_EVENTS" \
  "$EXPECTED_BLOCKS" \
  "$EXPECTED_OLD_ANCHOR_BLOCKS" \
  "$EXPECTED_VALIDATED_ANCHOR_BLOCKS" \
  "$MIN_QUERY_SPAN_BP" \
  "$MIN_REFERENCE_SPAN_BP" \
  "$MIN_MATCHLIKE_BP" \
  "$MIN_QUERY_MATCH_FRACTION" \
  "$MIN_REFERENCE_MATCH_FRACTION" \
  "$MAX_INSERTION_FRACTION" \
  "$MAX_DELETION_FRACTION" \
  "$MIN_SPAN_BALANCE" \
  "$END_TOLERANCE_BP"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== CORRECTED EVENT GEOMETRY ====="
column -ts $'\t' "$GEOMETRY_OUT"

echo
echo "===== QUALITY-VALIDATED BLOCKS ====="
column -ts $'\t' "$BLOCKS_OUT"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$BLOCKS_OUT" \
      "$GEOMETRY_OUT" \
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
