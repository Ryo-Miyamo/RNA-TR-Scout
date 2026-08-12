#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
RULESET_ID="rnatr_nonexact_locus_support_v0.3.2"

INPUT="$PROJECT_ROOT/results/11_extreme_nonexact_events/$RUN_ID/extreme_nonexact_events.tsv"

OUTDIR="$PROJECT_ROOT/results/11_extreme_nonexact_refined/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_extreme_nonexact_refined/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_extreme_nonexact_refined/$RUN_ID"

OUTPUT="$OUTDIR/extreme_nonexact_events.refined.tsv"
JOBS="$OUTDIR/reference_comparison_jobs.tsv"
LOCUS_SUMMARY="$OUTDIR/refined_locus_summary.tsv"
QC="$QCDIR/extreme_nonexact_refined_triage.qc.tsv"
PARAMETERS="$OUTDIR/${RULESET_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.extreme_nonexact_refined.manifest.tsv"
PY="$WORKDIR/refine_nonexact_triage.py"

EXPECTED_EVENTS=32
EXPECTED_SOURCE_ROWS=37
EXPECTED_REFERENCE_JOBS=2

MIN_MAPQ=20
MIN_TARGET_OVERLAP_BP=12
MIN_TRACT_OVERLAP_FRACTION=0.80
LOCAL_OVEREXTENSION_FRACTION=0.20
HIGH_PERIODICITY_PURITY=0.80
MIN_RECURRENT_EVENTS=2

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

test -s "$INPUT" || {
    echo "ERROR: missing input: $INPUT" >&2
    exit 1
}

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
ruleset_id	$RULESET_ID	Refined non-exact locus-support triage
min_mapq	$MIN_MAPQ	Minimum mapping quality for locus-supported review
min_target_overlap_bp	$MIN_TARGET_OVERLAP_BP	Minimum absolute target overlap
min_tract_overlap_fraction	$MIN_TRACT_OVERLAP_FRACTION	Minimum fraction of detected tract supported by target
local_overextension_fraction	$LOCAL_OVEREXTENSION_FRACTION	Below this fraction, classify as local periodic overextension
high_periodicity_purity	$HIGH_PERIODICITY_PURITY	High-periodicity review threshold
min_recurrent_events	$MIN_RECURRENT_EVENTS	Independent nonchimeric events required for recurrent compound review
reference_job_semantics	reference_comparison_not_expansion_call	Output is eligible for reference-aware comparison only
EOF

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict

(
    input_path,
    output_path,
    jobs_path,
    locus_summary_path,
    qc_path,
    ruleset_id,
    expected_events_text,
    expected_source_rows_text,
    expected_jobs_text,
    min_mapq_text,
    min_overlap_bp_text,
    min_overlap_fraction_text,
    overextension_fraction_text,
    high_purity_text,
    min_recurrent_text,
) = sys.argv[1:]

EXPECTED_EVENTS = int(expected_events_text)
EXPECTED_SOURCE_ROWS = int(expected_source_rows_text)
EXPECTED_JOBS = int(expected_jobs_text)

MIN_MAPQ = int(min_mapq_text)
MIN_OVERLAP_BP = int(min_overlap_bp_text)
MIN_OVERLAP_FRACTION = float(min_overlap_fraction_text)
OVEREXTENSION_FRACTION = float(overextension_fraction_text)
HIGH_PURITY = float(high_purity_text)
MIN_RECURRENT = int(min_recurrent_text)

with open(
    input_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    input_fields = reader.fieldnames or []
    rows = list(reader)

required = {
    "event_id",
    "read_id",
    "source_row_count",
    "locus_cluster_ids",
    "target_region_ids",
    "motifs",
    "maximum_tract_bp",
    "maximum_purity",
    "maximum_mapq",
    "maximum_target_overlap_bp",
    "any_chimeric_or_multichromosome",
    "recurrent_nonchimeric_events_at_locus",
    "triage_disposition",
}

missing = sorted(required - set(input_fields))
if missing:
    raise RuntimeError(
        "Missing input fields: " + ",".join(missing)
    )

extra_fields = [
    "refined_ruleset_id",
    "target_overlap_fraction_of_tract",
    "mapping_support_status",
    "locus_support_status",
    "previous_triage_disposition",
    "refined_triage_disposition",
    "refined_triage_rationale",
    "reference_comparison_eligible",
]

output_fields = input_fields + extra_fields
output_rows = []
job_rows = []
counts = Counter()

reference_dispositions = {
    "RETAIN_REFERENCE_COMPARISON_HIGH_PERIODICITY",
    "RETAIN_REFERENCE_COMPARISON_RECURRENT_COMPOUND",
}

for row in rows:
    tract_bp = int(row["maximum_tract_bp"])
    overlap_bp = int(row["maximum_target_overlap_bp"])
    mapq = int(row["maximum_mapq"])
    purity = float(row["maximum_purity"])
    recurrent = int(
        row["recurrent_nonchimeric_events_at_locus"]
    )
    chimeric = (
        row["any_chimeric_or_multichromosome"].lower()
        == "true"
    )

    overlap_fraction = (
        overlap_bp / tract_bp
        if tract_bp > 0
        else 0.0
    )

    if chimeric:
        mapping_status = "CHIMERIC_OR_MULTISEGMENT"
    elif mapq < MIN_MAPQ:
        mapping_status = "LOW_OR_AMBIGUOUS_MAPQ"
    else:
        mapping_status = "MAPQ_SUPPORTED"

    if overlap_bp <= 0:
        locus_status = "NO_TARGET_OVERLAP"
    elif overlap_fraction < OVEREXTENSION_FRACTION:
        locus_status = "LOCAL_PERIODIC_OVEREXTENSION"
    elif overlap_fraction < MIN_OVERLAP_FRACTION:
        locus_status = "PARTIAL_TARGET_SUPPORT"
    else:
        locus_status = "TRACT_MOSTLY_TARGET_SUPPORTED"

    if chimeric:
        disposition = "EXCLUDE_CHIMERIC_OR_MULTISEGMENT"
        rationale = (
            "Chimeric, supplementary, or multi-chromosome "
            "mapping evidence prevents reliable locus assignment"
        )

    elif mapq < MIN_MAPQ:
        disposition = "EXCLUDE_AMBIGUOUS_MAPPING"
        rationale = (
            "Maximum MAPQ is below the locus-support threshold"
        )

    elif overlap_bp <= 0:
        disposition = "EXCLUDE_NO_TARGET_SUPPORT"
        rationale = (
            "Detected local tract has no overlap with the target"
        )

    elif overlap_fraction < OVEREXTENSION_FRACTION:
        disposition = "EXCLUDE_LOCAL_PERIODIC_OVEREXTENSION"
        rationale = (
            "Only a small fraction of the detected tract overlaps "
            "the target; recurrence cannot rescue local overextension"
        )

    elif overlap_fraction < MIN_OVERLAP_FRACTION:
        disposition = "NO_CALL_PARTIAL_TARGET_SUPPORT"
        rationale = (
            "The tract has some target overlap but most of the local "
            "periodic alignment lies outside the target"
        )

    elif (
        overlap_bp >= MIN_OVERLAP_BP
        and purity >= HIGH_PURITY
    ):
        disposition = (
            "RETAIN_REFERENCE_COMPARISON_HIGH_PERIODICITY"
        )
        rationale = (
            "Most of the tract is target-supported with high motif "
            "periodicity and adequate mapping quality"
        )

    elif (
        overlap_bp >= MIN_OVERLAP_BP
        and recurrent >= MIN_RECURRENT
    ):
        disposition = (
            "RETAIN_REFERENCE_COMPARISON_RECURRENT_COMPOUND"
        )
        rationale = (
            "Most of the tract is target-supported and the locus is "
            "recurrent across independent nonchimeric reads"
        )

    else:
        disposition = (
            "NO_CALL_SINGLE_COMPLEX_TARGET_SUPPORTED"
        )
        rationale = (
            "Target-supported complex local tract lacks either high "
            "periodicity or independent recurrence"
        )

    eligible = disposition in reference_dispositions

    output_row = dict(row)
    output_row.update(
        {
            "refined_ruleset_id": ruleset_id,
            "target_overlap_fraction_of_tract": (
                f"{overlap_fraction:.6f}"
            ),
            "mapping_support_status": mapping_status,
            "locus_support_status": locus_status,
            "previous_triage_disposition": row[
                "triage_disposition"
            ],
            "refined_triage_disposition": disposition,
            "refined_triage_rationale": rationale,
            "reference_comparison_eligible": str(
                eligible
            ).lower(),
        }
    )
    output_rows.append(output_row)

    counts[f"triage::{disposition}"] += 1
    counts[f"mapping::{mapping_status}"] += 1
    counts[f"locus_support::{locus_status}"] += 1

    if eligible:
        job_rows.append(
            {
                "event_id": row["event_id"],
                "read_id": row["read_id"],
                "locus_cluster_ids": row[
                    "locus_cluster_ids"
                ],
                "target_region_ids": row[
                    "target_region_ids"
                ],
                "motifs": row["motifs"],
                "maximum_tract_bp": tract_bp,
                "maximum_purity": row[
                    "maximum_purity"
                ],
                "maximum_mapq": mapq,
                "maximum_target_overlap_bp": overlap_bp,
                "target_overlap_fraction_of_tract": (
                    f"{overlap_fraction:.6f}"
                ),
                "recurrent_nonchimeric_events_at_locus": (
                    recurrent
                ),
                "reference_comparison_class": disposition,
                "reference_comparison_goal": (
                    "Compare observed RNA tract with reference "
                    "sequence and reference repeat architecture"
                ),
            }
        )

with open(
    output_path,
    "w",
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

job_fields = [
    "event_id",
    "read_id",
    "locus_cluster_ids",
    "target_region_ids",
    "motifs",
    "maximum_tract_bp",
    "maximum_purity",
    "maximum_mapq",
    "maximum_target_overlap_bp",
    "target_overlap_fraction_of_tract",
    "recurrent_nonchimeric_events_at_locus",
    "reference_comparison_class",
    "reference_comparison_goal",
]

with open(
    jobs_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=job_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(job_rows)

locus_groups = defaultdict(list)

for row in output_rows:
    for cluster_id in row["locus_cluster_ids"].split(";"):
        locus_groups[cluster_id].append(row)

locus_fields = [
    "locus_cluster_id",
    "event_count",
    "unique_read_count",
    "reference_eligible_event_count",
    "maximum_tract_bp",
    "maximum_target_overlap_fraction",
    "maximum_mapq",
    "motifs",
    "refined_dispositions",
]

locus_rows = []

for cluster_id in sorted(locus_groups):
    group = locus_groups[cluster_id]
    locus_rows.append(
        {
            "locus_cluster_id": cluster_id,
            "event_count": len(group),
            "unique_read_count": len(
                {row["read_id"] for row in group}
            ),
            "reference_eligible_event_count": sum(
                row["reference_comparison_eligible"]
                == "true"
                for row in group
            ),
            "maximum_tract_bp": max(
                int(row["maximum_tract_bp"])
                for row in group
            ),
            "maximum_target_overlap_fraction": (
                f"{max(
                    float(
                        row[
                            'target_overlap_fraction_of_tract'
                        ]
                    )
                    for row in group
                ):.6f}"
            ),
            "maximum_mapq": max(
                int(row["maximum_mapq"])
                for row in group
            ),
            "motifs": ";".join(
                sorted(
                    {
                        motif
                        for row in group
                        for motif in row["motifs"].split(";")
                    }
                )
            ),
            "refined_dispositions": ";".join(
                sorted(
                    {
                        row["refined_triage_disposition"]
                        for row in group
                    }
                )
            ),
        }
    )

with open(
    locus_summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=locus_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(locus_rows)

source_rows = sum(
    int(row["source_row_count"])
    for row in rows
)

status = "PASS"

if (
    len(rows) != EXPECTED_EVENTS
    or source_rows != EXPECTED_SOURCE_ROWS
    or len(output_rows) != EXPECTED_EVENTS
    or len(job_rows) != EXPECTED_JOBS
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        f"expected_events\t{EXPECTED_EVENTS}\n"
    )
    handle.write(
        f"observed_events\t{len(rows)}\n"
    )
    handle.write(
        f"expected_source_rows\t{EXPECTED_SOURCE_ROWS}\n"
    )
    handle.write(
        f"observed_source_rows\t{source_rows}\n"
    )
    handle.write(
        f"expected_reference_jobs\t{EXPECTED_JOBS}\n"
    )
    handle.write(
        f"reference_jobs_written\t{len(job_rows)}\n"
    )
    handle.write(
        f"locus_clusters\t{len(locus_rows)}\n"
    )

    for key, value in sorted(counts.items()):
        handle.write(f"{key}\t{value}\n")

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit(
        "Refined non-exact triage requires review"
    )
PY

echo "===== SCRIPT SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

echo
echo "===== INPUT INTEGRITY ====="
test -s "$INPUT"
echo "Input: PASS"

rm -f \
  "$OUTPUT" \
  "$JOBS" \
  "$LOCUS_SUMMARY" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== REFINE NON-EXACT LOCUS SUPPORT ====="

python "$PY" \
  "$INPUT" \
  "$OUTPUT" \
  "$JOBS" \
  "$LOCUS_SUMMARY" \
  "$QC" \
  "$RULESET_ID" \
  "$EXPECTED_EVENTS" \
  "$EXPECTED_SOURCE_ROWS" \
  "$EXPECTED_REFERENCE_JOBS" \
  "$MIN_MAPQ" \
  "$MIN_TARGET_OVERLAP_BP" \
  "$MIN_TRACT_OVERLAP_FRACTION" \
  "$LOCAL_OVEREXTENSION_FRACTION" \
  "$HIGH_PERIODICITY_PURITY" \
  "$MIN_RECURRENT_EVENTS"

echo
echo "===== REFINED TRIAGE QC ====="
column -ts $'\t' "$QC"

echo
echo "===== REFERENCE COMPARISON JOBS ====="
column -ts $'\t' "$JOBS"

echo
echo "===== LOCUS SUMMARY ====="
column -ts $'\t' "$LOCUS_SUMMARY"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$OUTPUT" \
      "$JOBS" \
      "$LOCUS_SUMMARY" \
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

echo
echo "===== COMPLETE ====="
echo "$OUTPUT"
echo "$JOBS"
echo "$LOCUS_SUMMARY"
echo "$QC"
