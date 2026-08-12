#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

STRDIR="$CATALOG_ROOT/strchive/current"
INDIR="$STRDIR/finalization"
STRCHIVE_BED="$STRDIR/STRchive-disease-loci.hg38.general.bed"

PLAN_IN="$INDIR/STRchive_corrected_override_plan.tsv"
TARGETS_IN="$INDIR/STRchive_trexplorer_force_targets.tsv"
FORCED_ONLY_IN="$INDIR/TRExplorer_forced_only_retained.tsv"

OUTDIR="$INDIR/v2"
PLAN_OUT="$OUTDIR/STRchive_corrected_override_plan.v2.tsv"
TARGETS_OUT="$OUTDIR/STRchive_trexplorer_force_targets.v2.tsv"
DISEASE_REGIONS="$OUTDIR/STRchive_disease_regions.tsv"
FORCED_ONLY_OUT="$OUTDIR/TRExplorer_forced_only_retained.v2.tsv"
SUMMARY="$OUTDIR/STRchive_corrected_override_plan.v2.summary.tsv"
MANIFEST="$OUTDIR/STRchive_corrected_override_plan.v2.manifest.tsv"

PYTHON_SCRIPT="$OUTDIR/finalize_override_plan_v2.py"

mkdir -p "$OUTDIR"

for path in \
  "$PLAN_IN" \
  "$TARGETS_IN" \
  "$FORCED_ONLY_IN" \
  "$STRCHIVE_BED"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PYTHON_SCRIPT" <<'PY'
import csv
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

(
    plan_in,
    targets_in,
    forced_only_in,
    strchive_bed,
    plan_out,
    targets_out,
    disease_regions_out,
    forced_only_out,
    summary_out,
) = sys.argv[1:]


def read_tsv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        return reader.fieldnames or [], rows


plan_header, plan_rows = read_tsv(plan_in)
target_header, target_rows = read_tsv(targets_in)
forced_header, forced_rows = read_tsv(forced_only_in)

if len(plan_rows) != 80:
    raise RuntimeError(f"Expected 80 STRchive plan rows, found {len(plan_rows)}")

# MUC1 is not an unmatched fallback: the degenerate STRchive motif is
# compatible with a concrete TRExplorer motif. Keep both the TRExplorer
# target and the exact STRchive disease-region boundaries.
for row in plan_rows:
    if row["strchive_id"] == "ADTKD_MUC1":
        row["corrected_action"] = (
            "FORCE_MATCHED_TREXPLORER_LOCUS_IUPAC_PLUS_DISEASE_REGION"
        )
        row["corrected_match_class"] = (
            "IUPAC_DEGENERATE_COMPLEX_REGION_MATCH"
        )

for row in target_rows:
    if row["strchive_id"] == "ADTKD_MUC1":
        row["override_action"] = (
            "FORCE_MATCHED_TREXPLORER_LOCUS_IUPAC_PLUS_DISEASE_REGION"
        )

with open(plan_out, "w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=plan_header,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(plan_rows)

with open(targets_out, "w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=target_header,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(target_rows)

with open(forced_only_out, "w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=forced_header,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(forced_rows)

plan_by_id = {row["strchive_id"]: row for row in plan_rows}

disease_region_header = [
    "disease_region_id",
    "chrom",
    "start",
    "end",
    "region_length_bp",
    "gene",
    "reference_motif",
    "pathogenic_motif",
    "pathogenic_min",
    "inheritance",
    "disease",
    "matched_trexplorer_locus_id",
    "corrected_action",
    "analysis_mode_hint",
    "manual_review_required",
]

disease_rows = []

with open(strchive_bed, encoding="utf-8", newline="") as handle:
    reader = csv.reader(handle, delimiter="\t")

    for fields in reader:
        if not fields or fields[0].startswith("#"):
            continue

        if len(fields) != 10:
            raise RuntimeError(
                f"Unexpected STRchive BED field count: {len(fields)}"
            )

        (
            chrom,
            start_text,
            end_text,
            strchive_id,
            gene,
            reference_motif,
            pathogenic_motif,
            pathogenic_min,
            inheritance,
            disease,
        ) = fields

        start = int(start_text)
        end = int(end_text)
        plan = plan_by_id[strchive_id]

        motif_text = f"{reference_motif}{pathogenic_motif}".upper()
        has_degenerate_symbol = bool(
            re.search(r"[^ACGT,;/|.]", motif_text)
        )
        longest_motif = max(
            [
                len(token)
                for token in re.split(
                    r"[,;/|]",
                    f"{reference_motif},{pathogenic_motif}",
                )
                if token and token not in {"None", "."}
            ]
            or [0]
        )

        is_complex = (
            strchive_id == "ADTKD_MUC1"
            or has_degenerate_symbol
            or longest_motif > 20
            or (end - start) > 500
        )

        if is_complex:
            analysis_mode = "sequence_level_disease_region"
            manual_review = "true"
        else:
            analysis_mode = "repeat_sizing_disease_region"
            manual_review = "false"

        disease_rows.append(
            {
                "disease_region_id": strchive_id,
                "chrom": chrom,
                "start": start,
                "end": end,
                "region_length_bp": end - start,
                "gene": gene,
                "reference_motif": reference_motif,
                "pathogenic_motif": pathogenic_motif,
                "pathogenic_min": pathogenic_min,
                "inheritance": inheritance,
                "disease": disease,
                "matched_trexplorer_locus_id": plan[
                    "best_trexplorer_locus_id"
                ],
                "corrected_action": plan["corrected_action"],
                "analysis_mode_hint": analysis_mode,
                "manual_review_required": manual_review,
            }
        )

with open(
    disease_regions_out,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=disease_region_header,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(disease_rows)

summary = Counter()

for row in plan_rows:
    summary[f"action::{row['corrected_action']}"] += 1
    summary[f"match::{row['corrected_match_class']}"] += 1

summary["force_targets_total"] = len(target_rows)
summary["force_targets_already_in_core"] = sum(
    row["currently_in_static_core"] == "true"
    for row in target_rows
)
summary["force_targets_missing_from_core"] = sum(
    row["currently_in_static_core"] == "false"
    for row in target_rows
)
summary["disease_regions_preserved"] = len(disease_rows)
summary["disease_regions_manual_review"] = sum(
    row["manual_review_required"] == "true"
    for row in disease_rows
)
summary["trexplorer_forced_only_retained"] = len(forced_rows)

already_forced_total = (
    summary["action::ALREADY_FORCED"]
    + summary["action::ALREADY_FORCED_IUPAC"]
)

status = "PASS"

if (
    len(plan_rows) != 80
    or already_forced_total != 70
    or len(target_rows) != 10
    or summary["force_targets_already_in_core"] != 9
    or summary["force_targets_missing_from_core"] != 1
    or len(disease_rows) != 80
    or len(forced_rows) != 14
):
    status = "REVIEW"

with open(summary_out, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(f"strchive_loci\t{len(plan_rows)}\n")

    for key, value in sorted(summary.items()):
        handle.write(f"{key}\t{value}\n")

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Override-plan v2 validation failed")
PY

python "$PYTHON_SCRIPT" \
  "$PLAN_IN" \
  "$TARGETS_IN" \
  "$FORCED_ONLY_IN" \
  "$STRCHIVE_BED" \
  "$PLAN_OUT" \
  "$TARGETS_OUT" \
  "$DISEASE_REGIONS" \
  "$FORCED_ONLY_OUT" \
  "$SUMMARY"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PLAN_OUT" \
      "$TARGETS_OUT" \
      "$DISEASE_REGIONS" \
      "$FORCED_ONLY_OUT"
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

echo "===== V2 OVERRIDE SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== TEN FORCE TARGETS ====="
column -ts $'\t' "$TARGETS_OUT"

echo
echo "===== MUC1 DISEASE REGION ====="
awk -F '\t' '
NR == 1 || $1 == "ADTKD_MUC1"
' "$DISEASE_REGIONS" |
column -ts $'\t'

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$PLAN_OUT"
echo "$TARGETS_OUT"
echo "$DISEASE_REGIONS"
echo "$FORCED_ONLY_OUT"
echo "$SUMMARY"
echo "$MANIFEST"
