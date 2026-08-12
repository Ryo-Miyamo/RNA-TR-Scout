#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

CALLS="$PROJECT_ROOT/results/11_periodic_baseline/$RUN_ID/high_confidence_simple_periodic_calls.tsv.gz"
PROJECTION="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3/read_target_projection.v0.3.3.tsv.gz"

OUTDIR="$PROJECT_ROOT/results/11_periodic_baseline_audit/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_periodic_baseline_audit/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_periodic_baseline_audit/$RUN_ID"

AUDIT="$OUTDIR/periodic_baseline_target_concordance.tsv.gz"
SUSPICIOUS="$OUTDIR/periodic_baseline_suspicious_calls.top500.tsv"
REFINEMENT="$OUTDIR/periodic_baseline_refinement_candidates.top500.tsv"
QC="$QCDIR/periodic_baseline_target_concordance_qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.periodic_baseline_audit_manifest.tsv"

AUDITOR="$WORKDIR/audit_periodic_baseline.py"

EXPECTED_CALLS=49793
EXPECTED_PROJECTIONS=388571

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$CALLS" "$PROJECTION"; do
    test -s "$path" || {
        echo "ERROR: required input missing: $path" >&2
        exit 1
    }
done

cat > "$AUDITOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import math
import statistics
import sys
from collections import Counter

(
    calls_path,
    projection_path,
    audit_path,
    suspicious_path,
    refinement_path,
    qc_path,
    expected_calls_text,
    expected_projections_text,
) = sys.argv[1:]

expected_calls = int(expected_calls_text)
expected_projections = int(expected_projections_text)


def parse_optional_int(value):
    if value in {"", "."}:
        return None
    return int(value)


def overlap(start_a, end_a, start_b, end_b):
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def distance(start_a, end_a, start_b, end_b):
    if overlap(start_a, end_a, start_b, end_b) > 0:
        return 0
    if end_a <= start_b:
        return start_b - end_a
    return start_a - end_b


def quantile(values, probability):
    if not values:
        return 0.0

    values = sorted(values)

    if len(values) == 1:
        return float(values[0])

    position = probability * (len(values) - 1)
    low = math.floor(position)
    high = math.ceil(position)

    if low == high:
        return float(values[low])

    fraction = position - low
    return (
        values[low] * (1.0 - fraction)
        + values[high] * fraction
    )


projection_lookup = {}
projection_rows = 0

with gzip.open(
    projection_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        projection_rows += 1
        projection_id = row["projection_id"]

        if projection_id in projection_lookup:
            raise RuntimeError(
                f"Duplicate projection_id: {projection_id}"
            )

        projection_lookup[projection_id] = {
            "window_start": parse_optional_int(
                row["candidate_window_read_start"]
            ),
            "window_end": parse_optional_int(
                row["candidate_window_read_end"]
            ),
            "projected_start": parse_optional_int(
                row["projected_target_read_start"]
            ),
            "projected_end": parse_optional_int(
                row["projected_target_read_end"]
            ),
            "geometry_class": row["geometry_class"],
            "projection_status": row["projection_status"],
            "genomic_left_anchor_bp": int(
                row["genomic_left_anchor_bp"]
            ),
            "genomic_right_anchor_bp": int(
                row["genomic_right_anchor_bp"]
            ),
        }

audit_columns = [
    "projection_id",
    "read_id",
    "target_region_id",
    "target_source",
    "region_type",
    "geometry_class",
    "baseline_call_status",
    "motif",
    "motif_length_bp",
    "window_length_bp",
    "tract_read_start",
    "tract_read_end",
    "tract_read_bp",
    "projected_target_window_start",
    "projected_target_window_end",
    "projected_target_window_bp",
    "tract_target_overlap_bp",
    "tract_target_distance_bp",
    "tract_overlap_fraction",
    "target_coverage_fraction",
    "repeat_units_motif_path",
    "repeat_units_observed_read",
    "motif_path_to_read_units_ratio",
    "matches",
    "mismatches",
    "insertions",
    "deletions",
    "edit_fraction",
    "insertion_fraction",
    "deletion_fraction",
    "purity",
    "score_per_motif_position",
    "technical_audit_class",
    "technical_audit_flags",
]

rows = []
counts = Counter()
missing_projection_ids = set()
values = {
    "tract_overlap_fraction": [],
    "target_coverage_fraction": [],
    "unit_inflation": [],
    "edit_fraction": [],
    "insertion_fraction": [],
    "deletion_fraction": [],
    "score_density": [],
}

with gzip.open(
    calls_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for call in reader:
        counts["calls_read"] += 1
        projection_id = call["projection_id"]
        projection = projection_lookup.get(projection_id)

        if projection is None:
            missing_projection_ids.add(projection_id)
            continue

        tract_start = parse_optional_int(call["tract_read_start"])
        tract_end = parse_optional_int(call["tract_read_end"])
        tract_bp = int(call["tract_read_bp"])
        motif_length = int(call["motif_length_bp"])

        window_start = projection["window_start"]
        projected_start = projection["projected_start"]
        projected_end = projection["projected_end"]

        if (
            window_start is not None
            and projected_start is not None
            and projected_end is not None
        ):
            target_window_start = projected_start - window_start
            target_window_end = projected_end - window_start
            target_window_bp = (
                target_window_end - target_window_start
            )
        else:
            target_window_start = None
            target_window_end = None
            target_window_bp = None

        if (
            tract_start is not None
            and tract_end is not None
            and target_window_start is not None
            and target_window_end is not None
        ):
            target_overlap = overlap(
                tract_start,
                tract_end,
                target_window_start,
                target_window_end,
            )
            target_distance = distance(
                tract_start,
                tract_end,
                target_window_start,
                target_window_end,
            )
            tract_overlap_fraction = (
                target_overlap / tract_bp
                if tract_bp > 0 else 0.0
            )
            target_coverage_fraction = (
                target_overlap / target_window_bp
                if target_window_bp > 0 else 0.0
            )
        else:
            target_overlap = None
            target_distance = None
            tract_overlap_fraction = None
            target_coverage_fraction = None

        motif_path_units = float(
            call["repeat_units_estimate"]
        )
        observed_read_units = (
            tract_bp / motif_length
            if motif_length > 0 else 0.0
        )
        unit_inflation = (
            motif_path_units / observed_read_units
            if observed_read_units > 0 else 0.0
        )

        matches = int(call["matches"])
        mismatches = int(call["mismatches"])
        insertions = int(call["insertions"])
        deletions = int(call["deletions"])
        denominator = (
            matches + mismatches + insertions + deletions
        )

        edit_fraction = (
            (mismatches + insertions + deletions) / denominator
            if denominator else 1.0
        )
        insertion_fraction = (
            insertions / denominator
            if denominator else 0.0
        )
        deletion_fraction = (
            deletions / denominator
            if denominator else 0.0
        )
        purity = float(call["purity"])
        score_density = float(
            call["score_per_motif_position"]
        )

        flags = []

        if target_window_start is None:
            flags.append("NO_PROJECTED_TARGET_INTERVAL")
        elif target_overlap == 0:
            flags.append("TRACT_DOES_NOT_OVERLAP_TARGET")

        if unit_inflation > 1.25:
            flags.append("MOTIF_PATH_UNITS_GT_READ_UNITS_1_25")

        if edit_fraction > 0.30:
            flags.append("EDIT_FRACTION_GT_0_30")

        if insertion_fraction > 0.15:
            flags.append("INSERTION_FRACTION_GT_0_15")

        if deletion_fraction > 0.15:
            flags.append("DELETION_FRACTION_GT_0_15")

        if score_density < 0.75:
            flags.append("SCORE_DENSITY_LT_0_75")

        if purity < 0.70:
            flags.append("PURITY_LT_0_70")

        if call["baseline_call_status"] != "PASS":
            technical_class = "BASELINE_LOW_CONFIDENCE"
        elif target_window_start is None:
            technical_class = "TARGET_COORDINATE_REVIEW"
        elif target_overlap == 0:
            technical_class = "OFF_TARGET_TRACT"
        elif (
            unit_inflation > 1.25
            or edit_fraction > 0.30
            or insertion_fraction > 0.15
            or deletion_fraction > 0.15
            or score_density < 0.75
        ):
            technical_class = "GAP_OR_SCORE_REVIEW"
        else:
            technical_class = "KEEP_FOR_TARGET_CONSTRAINED_REFINEMENT"

        row = {
            "projection_id": projection_id,
            "read_id": call["read_id"],
            "target_region_id": call["target_region_id"],
            "target_source": call["target_source"],
            "region_type": call["region_type"],
            "geometry_class": call["geometry_class"],
            "baseline_call_status": call[
                "baseline_call_status"
            ],
            "motif": call["motif"],
            "motif_length_bp": motif_length,
            "window_length_bp": call["window_length_bp"],
            "tract_read_start": (
                "." if tract_start is None else tract_start
            ),
            "tract_read_end": (
                "." if tract_end is None else tract_end
            ),
            "tract_read_bp": tract_bp,
            "projected_target_window_start": (
                "."
                if target_window_start is None
                else target_window_start
            ),
            "projected_target_window_end": (
                "."
                if target_window_end is None
                else target_window_end
            ),
            "projected_target_window_bp": (
                "."
                if target_window_bp is None
                else target_window_bp
            ),
            "tract_target_overlap_bp": (
                "." if target_overlap is None else target_overlap
            ),
            "tract_target_distance_bp": (
                "." if target_distance is None else target_distance
            ),
            "tract_overlap_fraction": (
                "."
                if tract_overlap_fraction is None
                else f"{tract_overlap_fraction:.6f}"
            ),
            "target_coverage_fraction": (
                "."
                if target_coverage_fraction is None
                else f"{target_coverage_fraction:.6f}"
            ),
            "repeat_units_motif_path": (
                f"{motif_path_units:.6f}"
            ),
            "repeat_units_observed_read": (
                f"{observed_read_units:.6f}"
            ),
            "motif_path_to_read_units_ratio": (
                f"{unit_inflation:.6f}"
            ),
            "matches": matches,
            "mismatches": mismatches,
            "insertions": insertions,
            "deletions": deletions,
            "edit_fraction": f"{edit_fraction:.6f}",
            "insertion_fraction": (
                f"{insertion_fraction:.6f}"
            ),
            "deletion_fraction": (
                f"{deletion_fraction:.6f}"
            ),
            "purity": f"{purity:.6f}",
            "score_per_motif_position": (
                f"{score_density:.6f}"
            ),
            "technical_audit_class": technical_class,
            "technical_audit_flags": (
                ";".join(flags) if flags else "."
            ),
        }
        rows.append(row)

        counts[f"class::{technical_class}"] += 1
        counts[
            f"baseline_status::{call['baseline_call_status']}"
        ] += 1
        counts[
            f"geometry::{call['geometry_class']}"
        ] += 1

        for flag in flags:
            counts[f"flag::{flag}"] += 1

        values["unit_inflation"].append(unit_inflation)
        values["edit_fraction"].append(edit_fraction)
        values["insertion_fraction"].append(
            insertion_fraction
        )
        values["deletion_fraction"].append(
            deletion_fraction
        )
        values["score_density"].append(score_density)

        if tract_overlap_fraction is not None:
            values["tract_overlap_fraction"].append(
                tract_overlap_fraction
            )

        if target_coverage_fraction is not None:
            values["target_coverage_fraction"].append(
                target_coverage_fraction
            )

with gzip.open(
    audit_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=audit_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

suspicious_classes = {
    "OFF_TARGET_TRACT",
    "GAP_OR_SCORE_REVIEW",
}

suspicious = [
    row for row in rows
    if row["technical_audit_class"] in suspicious_classes
]
suspicious.sort(
    key=lambda row: (
        float(row["repeat_units_motif_path"]),
        float(row["motif_path_to_read_units_ratio"]),
        float(row["edit_fraction"]),
    ),
    reverse=True,
)

refinement = [
    row for row in rows
    if row["technical_audit_class"]
    == "KEEP_FOR_TARGET_CONSTRAINED_REFINEMENT"
]
refinement.sort(
    key=lambda row: (
        float(row["repeat_units_observed_read"]),
        float(row["purity"]),
        float(row["target_coverage_fraction"]),
    ),
    reverse=True,
)

for path, selected in [
    (suspicious_path, suspicious[:500]),
    (refinement_path, refinement[:500]),
]:
    with open(
        path,
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=audit_columns,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(selected)

status = "PASS"

if (
    projection_rows != expected_projections
    or counts["calls_read"] != expected_calls
    or len(rows) != expected_calls
    or missing_projection_ids
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        f"expected_projection_rows\t"
        f"{expected_projections}\n"
    )
    handle.write(
        f"observed_projection_rows\t{projection_rows}\n"
    )
    handle.write(f"expected_calls\t{expected_calls}\n")
    handle.write(
        f"observed_calls\t{counts['calls_read']}\n"
    )
    handle.write(
        f"missing_projection_ids\t"
        f"{len(missing_projection_ids)}\n"
    )

    for key, value in sorted(counts.items()):
        if key == "calls_read":
            continue
        handle.write(f"{key}\t{value}\n")

    for metric_name, metric_values in values.items():
        for label, probability in [
            ("min", 0.0),
            ("p05", 0.05),
            ("p25", 0.25),
            ("median", 0.50),
            ("p75", 0.75),
            ("p95", 0.95),
            ("p99", 0.99),
            ("max", 1.0),
        ]:
            handle.write(
                f"{metric_name}::{label}\t"
                f"{quantile(metric_values, probability):.6f}\n"
            )

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit(
        "Periodic baseline target-concordance audit failed"
    )
PY

echo "===== 1. INPUT INTEGRITY ====="
gzip -t "$CALLS"
gzip -t "$PROJECTION"
echo "Inputs: PASS"

echo
echo "===== 2. AUDIT TARGET CONCORDANCE AND GAP INFLATION ====="

rm -f \
  "$AUDIT" \
  "$SUSPICIOUS" \
  "$REFINEMENT" \
  "$QC" \
  "$MANIFEST"

python "$AUDITOR" \
  "$CALLS" \
  "$PROJECTION" \
  "$AUDIT" \
  "$SUSPICIOUS" \
  "$REFINEMENT" \
  "$QC" \
  "$EXPECTED_CALLS" \
  "$EXPECTED_PROJECTIONS"

gzip -t "$AUDIT"

echo
echo "===== BASELINE TECHNICAL AUDIT QC ====="
column -ts $'\t' "$QC"

echo
echo "===== TOP SUSPICIOUS CALLS ====="
column -ts $'\t' "$SUSPICIOUS" | head -n 21

echo
echo "===== 3. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    rows="$(gzip -cd "$AUDIT" | awk 'END {print NR-1}')"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$AUDIT")" \
      "$rows" \
      "$(stat -c '%s' "$AUDIT")" \
      "$(sha256sum "$AUDIT" | awk '{print $1}')" \
      "$AUDIT"

    for path in "$SUSPICIOUS" "$REFINEMENT" "$QC"; do
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
echo "$AUDIT"
echo "$SUSPICIOUS"
echo "$REFINEMENT"
echo "$QC"
echo "$MANIFEST"
