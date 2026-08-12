#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
NORMALIZATION_VERSION="rnatr_exact_span_field_normalization_v0.3.3"

INPUT="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID/simple_periodic_evidence.calibrated.tsv.gz"
AUDIT="$PROJECT_ROOT/results/11_span_calibration/$RUN_ID/exact_span_global_periodicity.tsv.gz"

OUTDIR="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID/v0.3.3"
QCDIR="$PROJECT_ROOT/qc/11_periodic_calibrated/$RUN_ID/v0.3.3"
WORKDIR="$PROJECT_ROOT/tmp/11_periodic_calibrated/$RUN_ID/v0.3.3"

OUTPUT="$OUTDIR/simple_periodic_evidence.calibrated.v0.3.3.tsv.gz"
QC="$QCDIR/simple_periodic_evidence.calibrated.v0.3.3.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.simple_periodic_calibrated.v0.3.3.manifest.tsv"
PYTHON_SCRIPT="$WORKDIR/normalize_span_fields_v0.3.3.py"

EXPECTED_ROWS=49793
EXPECTED_SPAN_ROWS=23867

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$INPUT" "$AUDIT"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PYTHON_SCRIPT" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys

(
    input_path,
    audit_path,
    output_path,
    qc_path,
    normalization_version,
    expected_rows_text,
    expected_span_rows_text,
) = sys.argv[1:]

expected_rows = int(expected_rows_text)
expected_span_rows = int(expected_span_rows_text)

audit_lookup = {}

with gzip.open(
    audit_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        projection_id = row["projection_id"]

        if projection_id in audit_lookup:
            raise RuntimeError(
                f"Duplicate audit projection_id: {projection_id}"
            )

        audit_lookup[projection_id] = row

with gzip.open(
    input_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    input_fields = reader.fieldnames or []
    input_rows = list(reader)

required_input_fields = {
    "projection_id",
    "evidence_class",
    "tract_read_start",
    "tract_read_end",
    "tract_read_bp",
    "repeat_units_observed_read",
    "repeat_units_motif_path",
    "motif_path_to_read_units_ratio",
    "matches",
    "mismatches",
    "insertions",
    "deletions",
    "purity",
    "edit_fraction",
    "score",
    "score_per_motif_position",
    "selected_orientation",
    "ending_phase",
    "target_overlap_bp",
    "target_coverage_fraction",
    "tract_overlap_fraction",
    "repeat_bp_estimate",
    "repeat_bp_lower_bound",
    "sizing_status",
    "calibration_flags",
}

missing_input_fields = sorted(
    required_input_fields - set(input_fields)
)

if missing_input_fields:
    raise RuntimeError(
        "Missing required input columns: "
        + ",".join(missing_input_fields)
    )

required_audit_fields = {
    "projection_id",
    "motif_length_bp",
    "projected_target_read_start",
    "projected_target_read_end",
    "projected_span_bp",
    "projected_span_units",
    "global_motif_path_units",
    "global_motif_path_to_projected_units_ratio",
    "global_matches",
    "global_mismatches",
    "global_insertions",
    "global_deletions",
    "global_purity",
    "global_edit_fraction",
    "global_score",
    "global_selected_orientation",
    "global_ending_phase",
}

if audit_lookup:
    observed_audit_fields = set(next(iter(audit_lookup.values())).keys())
else:
    observed_audit_fields = set()

missing_audit_fields = sorted(
    required_audit_fields - observed_audit_fields
)

if missing_audit_fields:
    raise RuntimeError(
        "Missing required audit columns: "
        + ",".join(missing_audit_fields)
    )

extra_fields = [
    "span_field_normalization_version",
    "pre_normalization_tract_read_start",
    "pre_normalization_tract_read_end",
    "pre_normalization_tract_read_bp",
    "pre_normalization_repeat_units_observed_read",
    "pre_normalization_repeat_units_motif_path",
    "pre_normalization_matches",
    "pre_normalization_mismatches",
    "pre_normalization_insertions",
    "pre_normalization_deletions",
    "pre_normalization_score",
    "pre_normalization_score_per_motif_position",
    "pre_normalization_selected_orientation",
    "pre_normalization_ending_phase",
    "normalized_motif_positions_traversed",
]

output_fields = input_fields + extra_fields

span_rows_normalized = 0
consistency_errors = 0
used_audit_ids = set()
output_rows = []

for row in input_rows:
    for field in extra_fields:
        row[field] = "."

    if row["evidence_class"] != "SPAN":
        output_rows.append(row)
        continue

    projection_id = row["projection_id"]
    audit = audit_lookup.get(projection_id)

    if audit is None:
        raise RuntimeError(
            f"SPAN row missing audit record: {projection_id}"
        )

    used_audit_ids.add(projection_id)
    span_rows_normalized += 1

    row["span_field_normalization_version"] = normalization_version
    row["pre_normalization_tract_read_start"] = row[
        "tract_read_start"
    ]
    row["pre_normalization_tract_read_end"] = row[
        "tract_read_end"
    ]
    row["pre_normalization_tract_read_bp"] = row[
        "tract_read_bp"
    ]
    row["pre_normalization_repeat_units_observed_read"] = row[
        "repeat_units_observed_read"
    ]
    row["pre_normalization_repeat_units_motif_path"] = row[
        "repeat_units_motif_path"
    ]
    row["pre_normalization_matches"] = row["matches"]
    row["pre_normalization_mismatches"] = row["mismatches"]
    row["pre_normalization_insertions"] = row["insertions"]
    row["pre_normalization_deletions"] = row["deletions"]
    row["pre_normalization_score"] = row["score"]
    row["pre_normalization_score_per_motif_position"] = row[
        "score_per_motif_position"
    ]
    row["pre_normalization_selected_orientation"] = row[
        "selected_orientation"
    ]
    row["pre_normalization_ending_phase"] = row[
        "ending_phase"
    ]

    motif_length = int(audit["motif_length_bp"])
    projected_start = int(
        audit["projected_target_read_start"]
    )
    projected_end = int(
        audit["projected_target_read_end"]
    )
    projected_span_bp = int(audit["projected_span_bp"])
    projected_span_units = float(
        audit["projected_span_units"]
    )
    global_path_units = float(
        audit["global_motif_path_units"]
    )
    motif_positions = round(global_path_units * motif_length)

    global_score = int(audit["global_score"])
    score_per_position = (
        global_score / motif_positions
        if motif_positions > 0
        else 0.0
    )

    row["tract_read_start"] = str(projected_start)
    row["tract_read_end"] = str(projected_end)
    row["tract_read_bp"] = str(projected_span_bp)

    row["repeat_units_observed_read"] = (
        f"{projected_span_units:.6f}"
    )
    row["repeat_units_motif_path"] = (
        f"{global_path_units:.6f}"
    )
    row["motif_path_to_read_units_ratio"] = audit[
        "global_motif_path_to_projected_units_ratio"
    ]
    row["normalized_motif_positions_traversed"] = str(
        motif_positions
    )

    row["matches"] = audit["global_matches"]
    row["mismatches"] = audit["global_mismatches"]
    row["insertions"] = audit["global_insertions"]
    row["deletions"] = audit["global_deletions"]
    row["purity"] = audit["global_purity"]
    row["edit_fraction"] = audit["global_edit_fraction"]
    row["score"] = str(global_score)
    row["score_per_motif_position"] = (
        f"{score_per_position:.6f}"
    )
    row["selected_orientation"] = audit[
        "global_selected_orientation"
    ]
    row["ending_phase"] = audit["global_ending_phase"]

    row["target_overlap_bp"] = str(projected_span_bp)
    row["target_coverage_fraction"] = "1.000000"
    row["tract_overlap_fraction"] = "1.000000"

    row["repeat_bp_estimate"] = str(projected_span_bp)
    row["repeat_bp_lower_bound"] = "."
    row["sizing_status"] = "exact_span"

    flags = (
        []
        if row["calibration_flags"] in {"", "."}
        else row["calibration_flags"].split(";")
    )
    flags.append(
        "SPAN_TRACT_FIELDS_NORMALIZED_TO_PROJECTED_INTERVAL"
    )
    row["calibration_flags"] = ";".join(
        sorted(set(flags))
    )

    if projected_end - projected_start != projected_span_bp:
        consistency_errors += 1

    if int(row["tract_read_bp"]) != projected_span_bp:
        consistency_errors += 1

    if int(row["repeat_bp_estimate"]) != projected_span_bp:
        consistency_errors += 1

    if int(row["target_overlap_bp"]) != projected_span_bp:
        consistency_errors += 1

    if row["target_coverage_fraction"] != "1.000000":
        consistency_errors += 1

    if row["tract_overlap_fraction"] != "1.000000":
        consistency_errors += 1

    output_rows.append(row)

unused_audit_ids = set(audit_lookup) - used_audit_ids

status = "PASS"

if (
    len(input_rows) != expected_rows
    or len(output_rows) != expected_rows
    or len(audit_lookup) != expected_span_rows
    or span_rows_normalized != expected_span_rows
    or unused_audit_ids
    or consistency_errors
):
    status = "REVIEW"

with gzip.open(
    output_path,
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
    writer.writerows(output_rows)

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(f"expected_rows\t{expected_rows}\n")
    handle.write(f"input_rows\t{len(input_rows)}\n")
    handle.write(f"output_rows\t{len(output_rows)}\n")
    handle.write(
        f"expected_span_rows\t{expected_span_rows}\n"
    )
    handle.write(
        f"span_audit_rows\t{len(audit_lookup)}\n"
    )
    handle.write(
        f"span_rows_normalized\t{span_rows_normalized}\n"
    )
    handle.write(
        f"unused_span_audit_rows\t{len(unused_audit_ids)}\n"
    )
    handle.write(
        f"consistency_errors\t{consistency_errors}\n"
    )
    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit(
        "SPAN field normalization requires review"
    )
PY

echo "===== INPUT INTEGRITY ====="
gzip -t "$INPUT"
gzip -t "$AUDIT"
echo "Inputs: PASS"

rm -f "$OUTPUT" "$QC" "$MANIFEST"

echo
echo "===== NORMALIZE SPAN FIELDS ====="

python "$PYTHON_SCRIPT" \
  "$INPUT" \
  "$AUDIT" \
  "$OUTPUT" \
  "$QC" \
  "$NORMALIZATION_VERSION" \
  "$EXPECTED_ROWS" \
  "$EXPECTED_SPAN_ROWS"

gzip -t "$OUTPUT"

echo
echo "===== NORMALIZATION QC ====="
column -ts $'\t' "$QC"

echo
echo "===== OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    rows="$(gzip -cd "$OUTPUT" | awk 'END {print NR-1}')"

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$OUTPUT")" \
      "$rows" \
      "$(stat -c '%s' "$OUTPUT")" \
      "$(sha256sum "$OUTPUT" | awk '{print $1}')" \
      "$OUTPUT"

    rows="$(awk 'END {print NR-1}' "$QC")"

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$QC")" \
      "$rows" \
      "$(stat -c '%s' "$QC")" \
      "$(sha256sum "$QC" | awk '{print $1}')" \
      "$QC"
} > "$MANIFEST"

column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$OUTPUT"
echo "$QC"
echo "$MANIFEST"
