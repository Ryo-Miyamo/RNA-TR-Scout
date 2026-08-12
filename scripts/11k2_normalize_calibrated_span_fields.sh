#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
INPUT="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID/simple_periodic_evidence.calibrated.tsv.gz"
AUDIT="$PROJECT_ROOT/results/11_span_calibration/$RUN_ID/exact_span_global_periodicity.tsv.gz"

OUTDIR="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID/v0.3.2"
QCDIR="$PROJECT_ROOT/qc/11_periodic_calibrated/$RUN_ID/v0.3.2"
WORKDIR="$PROJECT_ROOT/tmp/11_periodic_calibrated/$RUN_ID/v0.3.2"

OUTPUT="$OUTDIR/simple_periodic_evidence.calibrated.v0.3.2.tsv.gz"
QC="$QCDIR/simple_periodic_evidence.calibrated.v0.3.2.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.simple_periodic_calibrated.v0.3.2.manifest.tsv"
PY="$WORKDIR/normalize_span_fields.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for f in "$INPUT" "$AUDIT"; do
  test -s "$f" || { echo "ERROR: missing $f" >&2; exit 1; }
done

cat > "$PY" <<'PY'
import csv
import gzip
import sys

input_path, audit_path, output_path, qc_path = sys.argv[1:]

audit = {}
with gzip.open(audit_path, "rt", encoding="utf-8", newline="") as h:
    for row in csv.DictReader(h, delimiter="\t"):
        pid = row["projection_id"]
        if pid in audit:
            raise RuntimeError(f"duplicate audit row: {pid}")
        audit[pid] = row

with gzip.open(input_path, "rt", encoding="utf-8", newline="") as h:
    reader = csv.DictReader(h, delimiter="\t")
    fields = reader.fieldnames or []
    rows = list(reader)

extra = [
    "span_field_normalization_version",
    "pre_normalization_tract_read_start",
    "pre_normalization_tract_read_end",
    "pre_normalization_tract_read_bp",
    "pre_normalization_motif_positions_traversed",
    "pre_normalization_repeat_units_motif_path",
    "pre_normalization_matches",
    "pre_normalization_mismatches",
    "pre_normalization_insertions",
    "pre_normalization_deletions",
    "pre_normalization_score",
    "pre_normalization_score_per_motif_position",
    "pre_normalization_selected_orientation",
    "pre_normalization_ending_phase",
]
out_fields = fields + extra

span_count = 0
used = set()
errors = 0

for row in rows:
    for name in extra:
        row[name] = "."

    if row["evidence_class"] != "SPAN":
        continue

    pid = row["projection_id"]
    a = audit.get(pid)
    if a is None:
        raise RuntimeError(f"missing audit row for SPAN: {pid}")

    used.add(pid)
    span_count += 1

    row["span_field_normalization_version"] = (
        "rnatr_exact_span_field_normalization_v0.3.2"
    )
    row["pre_normalization_tract_read_start"] = row["tract_read_start"]
    row["pre_normalization_tract_read_end"] = row["tract_read_end"]
    row["pre_normalization_tract_read_bp"] = row["tract_read_bp"]
    row["pre_normalization_motif_positions_traversed"] = row[
        "motif_positions_traversed"
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
    row["pre_normalization_ending_phase"] = row["ending_phase"]

    motif_len = int(a["motif_length_bp"])
    start = int(a["projected_target_read_start"])
    end = int(a["projected_target_read_end"])
    span_bp = int(a["projected_span_bp"])
    span_units = float(a["projected_span_units"])
    path_units = float(a["global_motif_path_units"])
    motif_positions = round(path_units * motif_len)
    score = int(a["global_score"])
    score_per_pos = score / motif_positions if motif_positions else 0.0

    row["tract_read_start"] = str(start)
    row["tract_read_end"] = str(end)
    row["tract_read_bp"] = str(span_bp)
    row["motif_positions_traversed"] = str(motif_positions)
    row["repeat_units_observed_read"] = f"{span_units:.6f}"
    row["repeat_units_motif_path"] = f"{path_units:.6f}"
    row["motif_path_to_read_units_ratio"] = a[
        "global_motif_path_to_projected_units_ratio"
    ]
    row["matches"] = a["global_matches"]
    row["mismatches"] = a["global_mismatches"]
    row["insertions"] = a["global_insertions"]
    row["deletions"] = a["global_deletions"]
    row["purity"] = a["global_purity"]
    row["edit_fraction"] = a["global_edit_fraction"]
    row["score"] = str(score)
    row["score_per_motif_position"] = f"{score_per_pos:.6f}"
    row["selected_orientation"] = a["global_selected_orientation"]
    row["ending_phase"] = a["global_ending_phase"]

    row["target_overlap_bp"] = str(span_bp)
    row["target_coverage_fraction"] = "1.000000"
    row["tract_overlap_fraction"] = "1.000000"
    row["repeat_bp_estimate"] = str(span_bp)
    row["repeat_bp_lower_bound"] = "."
    row["sizing_status"] = "exact_span"

    flags = [] if row["calibration_flags"] in {"", "."} \
        else row["calibration_flags"].split(";")
    flags.append("SPAN_TRACT_FIELDS_NORMALIZED_TO_PROJECTED_INTERVAL")
    row["calibration_flags"] = ";".join(sorted(set(flags)))

    if end - start != span_bp:
        errors += 1
    if int(row["repeat_bp_estimate"]) != int(row["tract_read_bp"]):
        errors += 1
    if row["target_overlap_bp"] != row["tract_read_bp"]:
        errors += 1

unused = set(audit) - used
status = "PASS"
if len(rows) != 49793 or span_count != 23867 or unused or errors:
    status = "REVIEW"

with gzip.open(output_path, "wt", encoding="utf-8", newline="") as h:
    w = csv.DictWriter(h, fieldnames=out_fields, delimiter="\t",
                       lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

with open(qc_path, "w", encoding="utf-8") as h:
    h.write("metric\tvalue\n")
    h.write("expected_rows\t49793\n")
    h.write(f"input_rows\t{len(rows)}\n")
    h.write(f"output_rows\t{len(rows)}\n")
    h.write("expected_span_rows\t23867\n")
    h.write(f"span_audit_rows\t{len(audit)}\n")
    h.write(f"span_rows_normalized\t{span_count}\n")
    h.write(f"unused_span_audit_rows\t{len(unused)}\n")
    h.write(f"consistency_errors\t{errors}\n")
    h.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("SPAN field normalization requires review")
PY

echo "===== INPUT INTEGRITY ====="
gzip -t "$INPUT"
gzip -t "$AUDIT"

rm -f "$OUTPUT" "$QC" "$MANIFEST"

python "$PY" "$INPUT" "$AUDIT" "$OUTPUT" "$QC"
gzip -t "$OUTPUT"

echo
echo "===== NORMALIZATION QC ====="
column -ts $'\t' "$QC"

{
  printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'
  rows="$(gzip -cd "$OUTPUT" | awk 'END {print NR-1}')"
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$(basename "$OUTPUT")" "$rows" "$(stat -c '%s' "$OUTPUT")" \
    "$(sha256sum "$OUTPUT" | awk '{print $1}')" "$OUTPUT"
  rows="$(awk 'END {print NR-1}' "$QC")"
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$(basename "$QC")" "$rows" "$(stat -c '%s' "$QC")" \
    "$(sha256sum "$QC" | awk '{print $1}')" "$QC"
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$OUTPUT"
echo "$QC"
echo "$MANIFEST"
