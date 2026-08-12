#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_p3_orientation_freeze_v0.3.1"

INPUT="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"

OUTDIR="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_orientation_freeze/$RUN_ID"

OUTPUT="$OUTDIR/p3_orientation_corrected_classification.tsv"
SUMMARY="$OUTDIR/p3_orientation_corrected_summary.tsv"
RULES="$OUTDIR/p3_frozen_rules.tsv"
QC="$QCDIR/p3_orientation_freeze.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_orientation_freeze.manifest.tsv"
PY="$OUTDIR/classify_p3_orientation.py"

EXPECTED_ROWS=23
EXPECTED_REVERSE_ROWS=22
EXPECTED_PLUS_ROWS=1
EXPECTED_HOMOPOLYMER_ROWS=23

mkdir -p "$OUTDIR" "$QCDIR"

test -s "$INPUT" || {
    echo "ERROR: missing input: $INPUT" >&2
    exit 1
}

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import sys
from collections import Counter

(
    input_path,
    output_path,
    summary_path,
    rules_path,
    qc_path,
    model_id,
    expected_rows_text,
    expected_reverse_text,
    expected_plus_text,
    expected_homopolymer_text,
) = sys.argv[1:]

EXPECTED_ROWS = int(expected_rows_text)
EXPECTED_REVERSE = int(expected_reverse_text)
EXPECTED_PLUS = int(expected_plus_text)
EXPECTED_HOMOPOLYMER = int(
    expected_homopolymer_text
)

with open(
    input_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

output_rows = []
counts = Counter()

for row in rows:
    strand = row["best_alignment_strand"]
    motif_length = int(row["motif_length_bp"])
    projection_status = row[
        "target_entry_projection_status"
    ]
    original_sizing = row["sizing_status"]

    if strand != "+":
        frozen_status = (
            "REJECT_ORIENTATION_INCONSISTENT_BRIDGE"
        )
        standard_evidence = "false"
        interpretation = (
            "Query and candidate reference were both normalized "
            "from mapped-block boundary toward the target, so a "
            "reverse-strand isolated alignment cannot establish "
            "continuous anchor-to-target bridge geometry."
        )

    elif projection_status != "TARGET_ENTRY_PROJECTED":
        frozen_status = (
            "REJECT_TARGET_ENTRY_NOT_PROJECTED"
        )
        standard_evidence = "false"
        interpretation = (
            "Orientation is compatible, but the target-entry "
            "boundary was not projected through a validated CIGAR."
        )

    elif motif_length == 1:
        frozen_status = (
            "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE"
        )
        standard_evidence = "false"
        interpretation = (
            "Orientation and target entry are compatible, but "
            "mononucleotide A/T tracts are routed to a dedicated "
            "poly(A)/poly(T)/homopolymer artifact review rather "
            "than the standard tandem-repeat evidence stream."
        )

    elif original_sizing in {
        "lower_bound",
        "partial_internal",
    }:
        frozen_status = (
            "ELIGIBLE_STANDARD_P3_SEQUENCE_EVIDENCE"
        )
        standard_evidence = "true"
        interpretation = (
            "Orientation, target-entry projection, and a "
            "non-homopolymer target-entry repeat tract are "
            "supported. Exact allele length and expansion remain "
            "unassessed."
        )

    else:
        frozen_status = (
            "ORIENTATION_VALID_BRIDGE_ONLY_NO_REPEAT_TRACT"
        )
        standard_evidence = "false"
        interpretation = (
            "Bridge orientation is valid, but no qualifying "
            "non-homopolymer repeat tract was measured."
        )

    counts[
        "frozen_status::{}".format(frozen_status)
    ] += 1
    counts[
        "alignment_strand::{}".format(strand)
    ] += 1
    counts[
        "motif_length::{}".format(motif_length)
    ] += 1

    output_rows.append(
        {
            "model_id": model_id,
            "projection_id": row["projection_id"],
            "read_id": row["read_id"],
            "target_region_id": row[
                "target_region_id"
            ],
            "anchor_mapq": row["anchor_mapq"],
            "target_facing_genomic_side": row[
                "target_facing_genomic_side"
            ],
            "orientation_transform": row[
                "orientation_transform"
            ],
            "canonical_motif": row[
                "canonical_motif"
            ],
            "motif_length_bp": motif_length,
            "best_alignment_strand": strand,
            "target_entry_projection_status": (
                projection_status
            ),
            "original_evidence_class": row[
                "evidence_class"
            ],
            "original_sizing_status": (
                original_sizing
            ),
            "original_tract_bp": row[
                "tract_bp"
            ],
            "original_purity": row["purity"],
            "frozen_p3_status": frozen_status,
            "standard_p3_evidence_emitted": (
                standard_evidence
            ),
            "repeat_length_status": (
                "NOT_ASSESSED"
            ),
            "allele_length_status": (
                "NOT_ASSESSED"
            ),
            "expansion_status": "NOT_ASSESSED",
            "interpretation": interpretation,
        }
    )

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

summary_rows = []

for key, count in sorted(counts.items()):
    summary_rows.append(
        {
            "group": key,
            "rows": count,
        }
    )

with open(
    summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=["group", "rows"],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(summary_rows)

rules = [
    (
        "P3_ORIENTATION",
        "After normalizing both query and candidate reference "
        "from mapped-block boundary toward target, require PAF "
        "strand '+' for a bridge.",
    ),
    (
        "P3_TARGET_ENTRY",
        "Require target-entry boundary projection through a "
        "validated plus-strand CIGAR before repeat sizing.",
    ),
    (
        "P3_HOMOPOLYMER",
        "Motif length 1 is excluded from the standard P3 "
        "evidence stream and routed to dedicated poly(A)/poly(T) "
        "or homopolymer review.",
    ),
    (
        "P3_LENGTH",
        "One-flank P3 evidence may emit partial_internal or a "
        "censored lower bound only; never an exact allele length.",
    ),
    (
        "P3_EXPANSION",
        "P3 sequence evidence alone does not emit a "
        "reference-relative expansion or pathogenicity call.",
    ),
]

with open(
    rules_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.writer(
        handle,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(["rule_id", "rule"])
    writer.writerows(rules)

reverse_rows = sum(
    row["best_alignment_strand"] == "-"
    for row in rows
)
plus_rows = sum(
    row["best_alignment_strand"] == "+"
    for row in rows
)
homopolymer_rows = sum(
    int(row["motif_length_bp"]) == 1
    for row in rows
)
standard_evidence_rows = sum(
    row["standard_p3_evidence_emitted"]
    == "true"
    for row in output_rows
)

status = "PASS"

if (
    len(rows) != EXPECTED_ROWS
    or reverse_rows != EXPECTED_REVERSE
    or plus_rows != EXPECTED_PLUS
    or homopolymer_rows
       != EXPECTED_HOMOPOLYMER
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "input_rows\t{}\n".format(len(rows))
    )
    handle.write(
        "reverse_orientation_rows\t{}\n".format(
            reverse_rows
        )
    )
    handle.write(
        "plus_orientation_rows\t{}\n".format(
            plus_rows
        )
    )
    handle.write(
        "homopolymer_rows\t{}\n".format(
            homopolymer_rows
        )
    )
    handle.write(
        "standard_p3_evidence_calls_emitted\t{}\n".format(
            standard_evidence_rows
        )
    )

    for key, count in sorted(counts.items()):
        handle.write(
            "{}\t{}\n".format(key, count)
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
        "freeze_status\t{}\n".format(status)
    )

if status != "PASS":
    raise SystemExit(
        "P3 orientation freeze requires review"
    )
PY

python -m py_compile "$PY"

rm -f \
  "$OUTPUT" \
  "$SUMMARY" \
  "$RULES" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$INPUT" \
  "$OUTPUT" \
  "$SUMMARY" \
  "$RULES" \
  "$QC" \
  "$MODEL_ID" \
  "$EXPECTED_ROWS" \
  "$EXPECTED_REVERSE_ROWS" \
  "$EXPECTED_PLUS_ROWS" \
  "$EXPECTED_HOMOPOLYMER_ROWS"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== FROZEN RULES ====="
column -ts $'\t' "$RULES"

echo
echo "===== CORRECTED CLASSIFICATION ====="
column -ts $'\t' "$OUTPUT"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$OUTPUT" \
      "$SUMMARY" \
      "$RULES" \
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
