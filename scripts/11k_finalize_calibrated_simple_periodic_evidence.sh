#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
CALIBRATION_VERSION="rnatr_exact_span_calibration_v0.3.1"

EVIDENCE="$PROJECT_ROOT/results/11_periodic_finalization/$RUN_ID/simple_periodic_evidence.schema_v0.3.1.tsv.gz"
SPAN_AUDIT="$PROJECT_ROOT/results/11_span_calibration/$RUN_ID/exact_span_global_periodicity.tsv.gz"

OUTDIR="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_periodic_calibrated/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_periodic_calibrated/$RUN_ID"

CALIBRATED="$OUTDIR/simple_periodic_evidence.calibrated.tsv.gz"
SPAN_REVIEW="$OUTDIR/exact_span_sequence_review.tsv"
SHORT_SPAN="$OUTDIR/short_exact_span_summary.tsv"
DISEASE_SUMMARY="$OUTDIR/calibrated_disease_evidence_summary.tsv"
QC="$QCDIR/simple_periodic_calibration_qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.simple_periodic_calibration_manifest.tsv"

FINALIZER="$WORKDIR/finalize_calibrated_evidence.py"

EXPECTED_EVIDENCE_ROWS=49793
EXPECTED_SPAN_ROWS=23867
EXPECTED_PERIODIC_SPAN=14690
EXPECTED_SHORT_SPAN=9047
EXPECTED_SEQUENCE_REVIEW=130

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$EVIDENCE" "$SPAN_AUDIT"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$FINALIZER" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter, defaultdict

(
    evidence_path,
    span_audit_path,
    calibrated_path,
    span_review_path,
    short_summary_path,
    disease_summary_path,
    qc_path,
    calibration_version,
    expected_evidence_text,
    expected_span_text,
    expected_periodic_text,
    expected_short_text,
    expected_review_text,
) = sys.argv[1:]

expected_evidence = int(expected_evidence_text)
expected_span = int(expected_span_text)
expected_periodic = int(expected_periodic_text)
expected_short = int(expected_short_text)
expected_review = int(expected_review_text)

span_lookup = {}

with gzip.open(
    span_audit_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    span_fields = reader.fieldnames or []

    for row in reader:
        projection_id = row["projection_id"]

        if projection_id in span_lookup:
            raise RuntimeError(
                f"Duplicate SPAN audit projection: {projection_id}"
            )

        span_lookup[projection_id] = row

with gzip.open(
    evidence_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    input_fields = reader.fieldnames or []
    evidence_rows = list(reader)

added_fields = [
    "calibration_version",
    "precalibration_repeat_bp_estimate",
    "precalibration_repeat_units",
    "precalibration_purity",
    "exact_span_size_source",
    "exact_span_sequence_status",
    "exact_span_sequence_review_required",
    "exact_span_global_purity",
    "exact_span_global_edit_fraction",
    "exact_span_global_motif_path_inflation",
    "calibration_flags",
]
output_fields = input_fields + added_fields

counts = Counter()
calibrated_rows = []
review_rows = []
short_groups = defaultdict(
    lambda: {
        "rows": 0,
        "reads": set(),
        "targets": set(),
        "span_bp": [],
        "motif_lengths": Counter(),
    }
)
disease_groups = defaultdict(
    lambda: {
        "rows": 0,
        "reads": set(),
        "targets": set(),
        "span_rows": 0,
        "censored_rows": 0,
        "internal_rows": 0,
        "unresolved_rows": 0,
    }
)

used_span_ids = set()

for row in evidence_rows:
    projection_id = row["projection_id"]
    evidence_class = row["evidence_class"]

    row["calibration_version"] = calibration_version
    row["precalibration_repeat_bp_estimate"] = (
        row["repeat_bp_estimate"]
    )
    row["precalibration_repeat_units"] = (
        row["repeat_units_observed_read"]
    )
    row["precalibration_purity"] = row["purity"]

    row["exact_span_size_source"] = "."
    row["exact_span_sequence_status"] = "NOT_APPLICABLE"
    row["exact_span_sequence_review_required"] = "false"
    row["exact_span_global_purity"] = "."
    row["exact_span_global_edit_fraction"] = "."
    row["exact_span_global_motif_path_inflation"] = "."
    row["calibration_flags"] = "."

    if evidence_class == "SPAN":
        audit = span_lookup.get(projection_id)

        if audit is None:
            raise RuntimeError(
                f"SPAN evidence lacks audit row: {projection_id}"
            )

        used_span_ids.add(projection_id)
        audit_status = audit["exact_span_periodicity_status"]
        projected_bp = int(audit["projected_span_bp"])
        projected_units = float(audit["projected_span_units"])
        global_purity = float(audit["global_purity"])
        global_edit = float(audit["global_edit_fraction"])
        path_inflation = float(
            audit["global_motif_path_to_projected_units_ratio"]
        )

        flags = ["EXACT_SPAN_CALIBRATED_FROM_FLANKS"]

        if audit_status == "PERIODIC_EXACT_SPAN_PASS":
            sequence_status = "PERIODIC_EXACT_SPAN"
            review_required = False
            counts["span_sequence::PERIODIC_EXACT_SPAN"] += 1

        elif audit_status == "EXACT_SPAN_TOO_SHORT":
            sequence_status = "SHORT_EXACT_SPAN"
            review_required = False
            flags.append("SHORT_EXACT_SPAN_LT_12_BP")
            counts["span_sequence::SHORT_EXACT_SPAN"] += 1

            key = (
                audit["motif_length_bin"],
                audit["projected_span_length_bin"],
            )
            record = short_groups[key]
            record["rows"] += 1
            record["reads"].add(row["read_id"])
            record["targets"].add(row["target_region_id"])
            record["span_bp"].append(projected_bp)
            record["motif_lengths"][
                int(audit["motif_length_bp"])
            ] += 1

        elif audit_status == "EXACT_SPAN_LOW_PERIODICITY":
            sequence_status = (
                "COMPLEX_OR_LOW_PERIODICITY_EXACT_SPAN"
            )
            review_required = True
            flags.append("SEQUENCE_LEVEL_REVIEW_REQUIRED")
            counts[
                "span_sequence::COMPLEX_OR_LOW_PERIODICITY_EXACT_SPAN"
            ] += 1

        else:
            raise RuntimeError(
                f"Unexpected SPAN audit status: {audit_status}"
            )

        # The exact interval bounded by both mapped flanks is the calibrated
        # size. This remains exact even when sequence composition is complex.
        row["repeat_bp_estimate"] = str(projected_bp)
        row["repeat_units_observed_read"] = (
            f"{projected_units:.6f}"
        )
        row["purity"] = f"{global_purity:.6f}"
        row["edit_fraction"] = f"{global_edit:.6f}"
        row["sizing_status"] = "exact_span"

        row["exact_span_size_source"] = (
            "PROJECTED_INTERVAL_BETWEEN_BOTH_FLANKS"
        )
        row["exact_span_sequence_status"] = sequence_status
        row["exact_span_sequence_review_required"] = str(
            review_required
        ).lower()
        row["exact_span_global_purity"] = (
            f"{global_purity:.6f}"
        )
        row["exact_span_global_edit_fraction"] = (
            f"{global_edit:.6f}"
        )
        row["exact_span_global_motif_path_inflation"] = (
            f"{path_inflation:.6f}"
        )
        row["calibration_flags"] = ";".join(flags)

        if review_required:
            review_row = dict(audit)
            review_row["evidence_confidence_label"] = row[
                "confidence_label"
            ]
            review_row["evidence_target_source"] = row[
                "target_source"
            ]
            review_row["evidence_region_type"] = row[
                "region_type"
            ]
            review_row["calibration_decision"] = (
                "KEEP_EXACT_TOTAL_SPAN_AND_REVIEW_SEQUENCE_COMPOSITION"
            )
            review_rows.append(review_row)

        counts["span_rows_calibrated"] += 1

    else:
        counts[
            f"nonspan_evidence::{evidence_class}"
        ] += 1

    if row["target_source"] == "STRchive":
        group = disease_groups[row["target_region_id"]]
        group["rows"] += 1
        group["reads"].add(row["read_id"])
        group["targets"].add(row["target_region_id"])

        if row["evidence_class"] == "SPAN":
            group["span_rows"] += 1
        elif row["evidence_class"] in {
            "LEFT_ANCHORED_CENSORED_RIGHT",
            "RIGHT_ANCHORED_CENSORED_LEFT",
        }:
            group["censored_rows"] += 1
        elif row["evidence_class"] in {
            "LEFT_ONLY_INTERNAL",
            "RIGHT_ONLY_INTERNAL",
        }:
            group["internal_rows"] += 1
        elif row["evidence_class"] == "UNRESOLVED":
            group["unresolved_rows"] += 1

    counts[f"final_evidence::{row['evidence_class']}"] += 1
    counts[f"final_sizing::{row['sizing_status']}"] += 1
    counts[
        f"final_span_sequence::{row['exact_span_sequence_status']}"
    ] += 1

    calibrated_rows.append(row)

unused_span_ids = set(span_lookup) - used_span_ids

review_fields = span_fields + [
    "evidence_confidence_label",
    "evidence_target_source",
    "evidence_region_type",
    "calibration_decision",
]

with gzip.open(
    calibrated_path,
    "wt",
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
    writer.writerows(calibrated_rows)

with open(
    span_review_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=review_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(review_rows)

short_fields = [
    "motif_length_bin",
    "projected_span_length_bin",
    "rows",
    "unique_reads",
    "unique_targets",
    "span_bp_min",
    "span_bp_median",
    "span_bp_max",
    "motif_lengths",
]

with open(
    short_summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=short_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for key in sorted(short_groups):
        record = short_groups[key]
        values = sorted(record["span_bp"])
        median = values[len(values) // 2]

        writer.writerow(
            {
                "motif_length_bin": key[0],
                "projected_span_length_bin": key[1],
                "rows": record["rows"],
                "unique_reads": len(record["reads"]),
                "unique_targets": len(record["targets"]),
                "span_bp_min": min(values),
                "span_bp_median": median,
                "span_bp_max": max(values),
                "motif_lengths": ";".join(
                    f"{length}:{count}"
                    for length, count
                    in sorted(record["motif_lengths"].items())
                ),
            }
        )

disease_fields = [
    "strchive_region_id",
    "rows",
    "unique_reads",
    "span_rows",
    "censored_rows",
    "one_flank_internal_rows",
    "unresolved_rows",
]

with open(
    disease_summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=disease_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for region_id in sorted(disease_groups):
        record = disease_groups[region_id]
        writer.writerow(
            {
                "strchive_region_id": region_id,
                "rows": record["rows"],
                "unique_reads": len(record["reads"]),
                "span_rows": record["span_rows"],
                "censored_rows": record["censored_rows"],
                "one_flank_internal_rows": record[
                    "internal_rows"
                ],
                "unresolved_rows": record["unresolved_rows"],
            }
        )

status = "PASS"

if (
    len(evidence_rows) != expected_evidence
    or len(calibrated_rows) != expected_evidence
    or len(span_lookup) != expected_span
    or counts["span_rows_calibrated"] != expected_span
    or unused_span_ids
    or counts["span_sequence::PERIODIC_EXACT_SPAN"]
       != expected_periodic
    or counts["span_sequence::SHORT_EXACT_SPAN"]
       != expected_short
    or counts[
        "span_sequence::COMPLEX_OR_LOW_PERIODICITY_EXACT_SPAN"
    ] != expected_review
    or len(review_rows) != expected_review
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        f"expected_evidence_rows\t{expected_evidence}\n"
    )
    handle.write(
        f"observed_evidence_rows\t{len(evidence_rows)}\n"
    )
    handle.write(
        f"calibrated_evidence_rows\t{len(calibrated_rows)}\n"
    )
    handle.write(f"expected_span_rows\t{expected_span}\n")
    handle.write(f"span_audit_rows\t{len(span_lookup)}\n")
    handle.write(
        f"span_rows_calibrated\t"
        f"{counts['span_rows_calibrated']}\n"
    )
    handle.write(
        f"unused_span_audit_rows\t{len(unused_span_ids)}\n"
    )
    handle.write(
        f"periodic_exact_span_rows\t"
        f"{counts['span_sequence::PERIODIC_EXACT_SPAN']}\n"
    )
    handle.write(
        f"short_exact_span_rows\t"
        f"{counts['span_sequence::SHORT_EXACT_SPAN']}\n"
    )
    handle.write(
        "complex_or_low_periodicity_exact_span_rows\t"
        f"{counts['span_sequence::COMPLEX_OR_LOW_PERIODICITY_EXACT_SPAN']}\n"
    )
    handle.write(
        f"sequence_review_rows\t{len(review_rows)}\n"
    )
    handle.write(
        f"disease_regions_with_evidence\t{len(disease_groups)}\n"
    )

    for key, value in sorted(counts.items()):
        if key in {
            "span_rows_calibrated",
            "span_sequence::PERIODIC_EXACT_SPAN",
            "span_sequence::SHORT_EXACT_SPAN",
            "span_sequence::COMPLEX_OR_LOW_PERIODICITY_EXACT_SPAN",
        }:
            continue
        handle.write(f"{key}\t{value}\n")

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Calibrated evidence finalization requires review")
PY

echo "===== 1. INPUT INTEGRITY ====="
gzip -t "$EVIDENCE"
gzip -t "$SPAN_AUDIT"
echo "Inputs: PASS"

echo
echo "===== 2. APPLY EXACT-SPAN CALIBRATION ====="

rm -f \
  "$CALIBRATED" \
  "$SPAN_REVIEW" \
  "$SHORT_SPAN" \
  "$DISEASE_SUMMARY" \
  "$QC" \
  "$MANIFEST"

python "$FINALIZER" \
  "$EVIDENCE" \
  "$SPAN_AUDIT" \
  "$CALIBRATED" \
  "$SPAN_REVIEW" \
  "$SHORT_SPAN" \
  "$DISEASE_SUMMARY" \
  "$QC" \
  "$CALIBRATION_VERSION" \
  "$EXPECTED_EVIDENCE_ROWS" \
  "$EXPECTED_SPAN_ROWS" \
  "$EXPECTED_PERIODIC_SPAN" \
  "$EXPECTED_SHORT_SPAN" \
  "$EXPECTED_SEQUENCE_REVIEW"

gzip -t "$CALIBRATED"

echo
echo "===== CALIBRATION QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SHORT EXACT-SPAN SUMMARY ====="
column -ts $'\t' "$SHORT_SPAN"

echo
echo "===== DISEASE EVIDENCE SUMMARY ====="
column -ts $'\t' "$DISEASE_SUMMARY"

echo
echo "===== SEQUENCE REVIEW ROWS (FIRST 20) ====="
column -ts $'\t' "$SPAN_REVIEW" | head -n 21

echo
echo "===== 3. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    rows="$(gzip -cd "$CALIBRATED" | awk 'END {print NR-1}')"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$CALIBRATED")" \
      "$rows" \
      "$(stat -c '%s' "$CALIBRATED")" \
      "$(sha256sum "$CALIBRATED" | awk '{print $1}')" \
      "$CALIBRATED"

    for path in \
      "$SPAN_REVIEW" \
      "$SHORT_SPAN" \
      "$DISEASE_SUMMARY" \
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
echo "$CALIBRATED"
echo "$SPAN_REVIEW"
echo "$SHORT_SPAN"
echo "$DISEASE_SUMMARY"
echo "$QC"
echo "$MANIFEST"
