#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

INPUT="$PROJECT_ROOT/results/11_periodic_refinement/$RUN_ID/target_constrained_periodic_calls.tsv.gz"
SCHEMA="$PROJECT_ROOT/config/evidence_schema/v0.3.1/schema/rnatr_v03_table_schema.json"

OUTDIR="$PROJECT_ROOT/results/11_periodic_finalization/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_periodic_finalization/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_periodic_finalization/$RUN_ID"

FINAL="$OUTDIR/simple_periodic_evidence.schema_v0.3.1.tsv.gz"
SPAN_CALIBRATION="$OUTDIR/span_target_concordance.tsv.gz"
SPAN_SUMMARY="$OUTDIR/span_target_concordance_summary.tsv"
DISEASE="$OUTDIR/simple_periodic_disease_evidence.tsv"
OUTLIERS="$OUTDIR/span_target_concordance_outliers.top500.tsv"
QC="$QCDIR/simple_periodic_evidence_finalization_qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.simple_periodic_finalization_manifest.tsv"

FINALIZER="$WORKDIR/finalize_simple_periodic_evidence.py"
EXPECTED_ROWS=49793

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$INPUT" "$SCHEMA"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$FINALIZER" <<'PY'
from __future__ import annotations

import csv
import gzip
import json
import math
import sys
from collections import Counter, defaultdict

(
    input_path,
    schema_path,
    final_path,
    span_path,
    span_summary_path,
    disease_path,
    outliers_path,
    qc_path,
    expected_rows_text,
) = sys.argv[1:]

expected_rows = int(expected_rows_text)
schema = json.load(open(schema_path, encoding="utf-8"))
allowed_evidence = set(schema["enums"]["evidence_class"])
allowed_sizing = set(schema["enums"]["sizing_status"])


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


def motif_bin(length):
    if length == 1:
        return "1_homopolymer"
    if length == 2:
        return "2"
    if length == 3:
        return "3"
    if 4 <= length <= 6:
        return "4_to_6"
    if 7 <= length <= 10:
        return "7_to_10"
    return "11_to_20"


with gzip.open(
    input_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    input_fields = reader.fieldnames or []
    rows = list(reader)

final_fields = input_fields + [
    "evidence_schema_version",
    "reclassification_reason",
]

counts = Counter()
final_rows = []
span_rows = []
disease_rows = []
residual_internal_unresolved = 0

for row in rows:
    original_class = row["evidence_class"]
    original_sizing = row["sizing_status"]
    new_class = original_class
    new_sizing = original_sizing
    reason = "."
    motif_pass = row["motif_tract_status"] == "PASS"
    geometry = row["geometry_class"]

    if (
        original_class == "UNRESOLVED"
        and motif_pass
        and geometry
        in {"LEFT_FLANK_ONLY", "PROXIMAL_RIGHT_WITH_SOFTCLIP"}
    ):
        new_class = "LEFT_ONLY_INTERNAL"
        new_sizing = "partial_internal"
        reason = "one_genomic_left_flank_target_repeat_not_at_raw_end"

    elif (
        original_class == "UNRESOLVED"
        and motif_pass
        and geometry
        in {"RIGHT_FLANK_ONLY", "PROXIMAL_LEFT_WITH_SOFTCLIP"}
    ):
        new_class = "RIGHT_ONLY_INTERNAL"
        new_sizing = "partial_internal"
        reason = "one_genomic_right_flank_target_repeat_not_at_raw_end"

    if new_class not in allowed_evidence:
        raise RuntimeError(f"Evidence class not in schema: {new_class}")
    if new_sizing not in allowed_sizing:
        raise RuntimeError(f"Sizing status not in schema: {new_sizing}")

    if (
        new_class in {"LEFT_ONLY_INTERNAL", "RIGHT_ONLY_INTERNAL"}
        and row["confidence_label"] == "LOW"
        and int(row["best_mapq"]) >= 20
        and int(row["read_candidate_target_count"]) == 1
    ):
        row["confidence_label"] = "MEDIUM"

    row["evidence_class"] = new_class
    row["sizing_status"] = new_sizing
    row["schema_version"] = "0.3.1"
    row["evidence_schema_version"] = "0.3.1"
    row["reclassification_reason"] = reason
    final_rows.append(row)

    counts[f"evidence_class::{new_class}"] += 1
    counts[f"sizing_status::{new_sizing}"] += 1
    counts[f"confidence::{row['confidence_label']}"] += 1
    counts[f"motif_tract_status::{row['motif_tract_status']}"] += 1

    if new_class != original_class:
        counts[f"reclassified::{original_class}->{new_class}"] += 1

    if (
        new_class == "UNRESOLVED"
        and motif_pass
        and geometry
        in {
            "LEFT_FLANK_ONLY",
            "PROXIMAL_RIGHT_WITH_SOFTCLIP",
            "RIGHT_FLANK_ONLY",
            "PROXIMAL_LEFT_WITH_SOFTCLIP",
        }
    ):
        residual_internal_unresolved += 1

    if row["target_source"] == "STRchive":
        disease_rows.append(row)

    if (
        new_class == "SPAN"
        and row["target_source"] == "TRExplorer"
        and row["region_type"] in {"TR", "TR_FALLBACK"}
        and row["projected_target_bp"] != "."
    ):
        target_bp = int(row["projected_target_bp"])
        tract_bp = int(row["tract_read_bp"])
        ratio = tract_bp / target_bp if target_bp else 0.0
        delta = tract_bp - target_bp
        relative_error = abs(delta) / target_bp if target_bp else 0.0

        span_rows.append(
            {
                "projection_id": row["projection_id"],
                "read_id": row["read_id"],
                "target_region_id": row["target_region_id"],
                "representative_locus_id": row[
                    "representative_locus_id"
                ],
                "motif": row["motif"],
                "motif_length_bp": row["motif_length_bp"],
                "motif_length_bin": motif_bin(
                    int(row["motif_length_bp"])
                ),
                "projected_target_bp": target_bp,
                "tract_read_bp": tract_bp,
                "tract_minus_target_bp": delta,
                "tract_to_target_ratio": f"{ratio:.6f}",
                "absolute_relative_error": f"{relative_error:.6f}",
                "target_overlap_bp": row["target_overlap_bp"],
                "target_coverage_fraction": row[
                    "target_coverage_fraction"
                ],
                "tract_overlap_fraction": row[
                    "tract_overlap_fraction"
                ],
                "purity": row["purity"],
                "best_mapq": row["best_mapq"],
                "read_candidate_target_count": row[
                    "read_candidate_target_count"
                ],
                "confidence_label": row["confidence_label"],
                "repeat_units_observed_read": row[
                    "repeat_units_observed_read"
                ],
            }
        )

span_fields = [
    "projection_id",
    "read_id",
    "target_region_id",
    "representative_locus_id",
    "motif",
    "motif_length_bp",
    "motif_length_bin",
    "projected_target_bp",
    "tract_read_bp",
    "tract_minus_target_bp",
    "tract_to_target_ratio",
    "absolute_relative_error",
    "target_overlap_bp",
    "target_coverage_fraction",
    "tract_overlap_fraction",
    "purity",
    "best_mapq",
    "read_candidate_target_count",
    "confidence_label",
    "repeat_units_observed_read",
]

with gzip.open(
    final_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=final_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(final_rows)

with gzip.open(
    span_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=span_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(span_rows)

with open(
    disease_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=final_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(disease_rows)

summary_groups = defaultdict(list)
for row in span_rows:
    summary_groups["ALL"].append(row)
    summary_groups[f"motif_bin::{row['motif_length_bin']}"].append(row)
    summary_groups[f"confidence::{row['confidence_label']}"].append(row)
    scope = (
        "unique_candidate"
        if int(row["read_candidate_target_count"]) == 1
        else "multiple_candidates"
    )
    summary_groups[f"candidate_scope::{scope}"].append(row)

summary_fields = [
    "group",
    "span_rows",
    "unique_reads",
    "unique_targets",
    "ratio_median",
    "ratio_p05",
    "ratio_p95",
    "absolute_relative_error_median",
    "within_10_percent",
    "within_25_percent",
    "within_50_percent",
    "purity_median",
]

with open(
    span_summary_path,
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

    for group in sorted(summary_groups):
        group_rows = summary_groups[group]
        ratios = [
            float(row["tract_to_target_ratio"])
            for row in group_rows
        ]
        errors = [
            float(row["absolute_relative_error"])
            for row in group_rows
        ]
        purities = [float(row["purity"]) for row in group_rows]

        writer.writerow(
            {
                "group": group,
                "span_rows": len(group_rows),
                "unique_reads": len(
                    {row["read_id"] for row in group_rows}
                ),
                "unique_targets": len(
                    {row["target_region_id"] for row in group_rows}
                ),
                "ratio_median": f"{quantile(ratios, 0.5):.6f}",
                "ratio_p05": f"{quantile(ratios, 0.05):.6f}",
                "ratio_p95": f"{quantile(ratios, 0.95):.6f}",
                "absolute_relative_error_median": (
                    f"{quantile(errors, 0.5):.6f}"
                ),
                "within_10_percent": sum(
                    error <= 0.10 for error in errors
                ),
                "within_25_percent": sum(
                    error <= 0.25 for error in errors
                ),
                "within_50_percent": sum(
                    error <= 0.50 for error in errors
                ),
                "purity_median": f"{quantile(purities, 0.5):.6f}",
            }
        )

outliers = sorted(
    span_rows,
    key=lambda row: (
        float(row["absolute_relative_error"]),
        int(row["tract_read_bp"]),
    ),
    reverse=True,
)[:500]

with open(
    outliers_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=span_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(outliers)

status = "PASS"
if (
    len(rows) != expected_rows
    or len(final_rows) != expected_rows
    or residual_internal_unresolved != 0
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(f"expected_rows\t{expected_rows}\n")
    handle.write(f"input_rows\t{len(rows)}\n")
    handle.write(f"final_rows\t{len(final_rows)}\n")
    handle.write(
        "residual_motif_positive_one_flank_unresolved\t"
        f"{residual_internal_unresolved}\n"
    )
    handle.write(f"span_calibration_rows\t{len(span_rows)}\n")
    handle.write(f"disease_evidence_rows\t{len(disease_rows)}\n")

    for key, value in sorted(counts.items()):
        handle.write(f"{key}\t{value}\n")

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Simple periodic finalization requires review")
PY

echo "===== 1. INPUT INTEGRITY ====="
gzip -t "$INPUT"
python -m json.tool "$SCHEMA" >/dev/null
echo "Inputs: PASS"

echo
echo "===== 2. RECLASSIFY AND AUDIT ====="

rm -f \
  "$FINAL" \
  "$SPAN_CALIBRATION" \
  "$SPAN_SUMMARY" \
  "$DISEASE" \
  "$OUTLIERS" \
  "$QC" \
  "$MANIFEST"

python "$FINALIZER" \
  "$INPUT" \
  "$SCHEMA" \
  "$FINAL" \
  "$SPAN_CALIBRATION" \
  "$SPAN_SUMMARY" \
  "$DISEASE" \
  "$OUTLIERS" \
  "$QC" \
  "$EXPECTED_ROWS"

gzip -t "$FINAL"
gzip -t "$SPAN_CALIBRATION"

echo
echo "===== FINALIZATION QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SPAN TARGET CONCORDANCE SUMMARY ====="
column -ts $'\t' "$SPAN_SUMMARY"

echo
echo "===== DISEASE EVIDENCE (FIRST 30) ====="
column -ts $'\t' "$DISEASE" | head -n 31

echo
echo "===== 3. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in "$FINAL" "$SPAN_CALIBRATION"; do
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in \
      "$SPAN_SUMMARY" \
      "$DISEASE" \
      "$OUTLIERS" \
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

column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$FINAL"
echo "$SPAN_CALIBRATION"
echo "$SPAN_SUMMARY"
echo "$DISEASE"
echo "$OUTLIERS"
echo "$QC"
echo "$MANIFEST"
