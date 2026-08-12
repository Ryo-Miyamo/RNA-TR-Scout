#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

P1="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID/v0.3.3/simple_periodic_evidence.calibrated.v0.3.3.tsv.gz"
P2="$PROJECT_ROOT/results/11_p2_periodic/$RUN_ID/p2_alternate_exact_simple_periodic_evidence.tsv.gz"

OUTDIR="$PROJECT_ROOT/results/11_p2_relationship/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p2_relationship/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p2_relationship/$RUN_ID"

RELATIONSHIPS="$OUTDIR/p2_exact_span_relationship_to_p1.tsv.gz"
SUMMARY="$OUTDIR/p2_exact_span_relationship_summary.tsv"
READ_SUMMARY="$OUTDIR/read_level_distinct_exact_repeat_events.tsv.gz"
EXTREME="$OUTDIR/p2_nonexact_tracts_ge1000bp.tsv"
QC="$QCDIR/p2_exact_span_relationship_qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p2_relationship_manifest.tsv"

AUDITOR="$WORKDIR/classify_p2_relationships.py"

EXPECTED_P1_ROWS=49793
EXPECTED_P2_ROWS=108595
EXPECTED_P1_SPAN=23867
EXPECTED_P2_SPAN=79985

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$P1" "$P2"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$AUDITOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import math
import sys
from collections import Counter, defaultdict

(
    p1_path,
    p2_path,
    relationships_path,
    summary_path,
    read_summary_path,
    extreme_path,
    qc_path,
    expected_p1_text,
    expected_p2_text,
    expected_p1_span_text,
    expected_p2_span_text,
) = sys.argv[1:]

EXPECTED_P1 = int(expected_p1_text)
EXPECTED_P2 = int(expected_p2_text)
EXPECTED_P1_SPAN = int(expected_p1_span_text)
EXPECTED_P2_SPAN = int(expected_p2_span_text)


def overlap(a_start, a_end, b_start, b_end):
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def distance(a_start, a_end, b_start, b_end):
    if overlap(a_start, a_end, b_start, b_end) > 0:
        return 0
    if a_end <= b_start:
        return b_start - a_end
    return a_start - b_end


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
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def load(path, cohort):
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            row["_cohort"] = cohort
            rows.append(row)
    return rows


p1_rows = load(p1_path, "P1")
p2_rows = load(p2_path, "P2")

p1_spans_by_read = defaultdict(list)
p2_spans = []

for row in p1_rows:
    if row["evidence_class"] == "SPAN":
        p1_spans_by_read[row["read_id"]].append(row)

for row in p2_rows:
    if row["evidence_class"] == "SPAN":
        p2_spans.append(row)

relationship_columns = [
    "p2_projection_id",
    "read_id",
    "p2_target_region_id",
    "p2_representative_locus_id",
    "p2_motif",
    "p2_start",
    "p2_end",
    "p2_span_bp",
    "p2_assignment_rank",
    "p1_span_count_on_read",
    "best_p1_projection_id",
    "best_p1_target_region_id",
    "best_p1_representative_locus_id",
    "best_p1_motif",
    "best_p1_start",
    "best_p1_end",
    "best_p1_span_bp",
    "overlap_bp",
    "p2_overlap_fraction",
    "p1_overlap_fraction",
    "interval_distance_bp",
    "same_motif",
    "relationship_class",
    "sequence_interpretation",
]

relationship_rows = []
counts = Counter()
per_read_exact_intervals = defaultdict(list)

for row in p1_rows:
    if row["evidence_class"] == "SPAN":
        per_read_exact_intervals[row["read_id"]].append(
            (
                int(row["tract_read_start"]),
                int(row["tract_read_end"]),
                row["canonical_motif"],
                "P1",
                row["projection_id"],
            )
        )

for p2 in p2_spans:
    read_id = p2["read_id"]
    p2_start = int(p2["tract_read_start"])
    p2_end = int(p2["tract_read_end"])
    p2_bp = p2_end - p2_start
    p2_motif = p2["canonical_motif"]
    candidates = p1_spans_by_read.get(read_id, [])

    per_read_exact_intervals[read_id].append(
        (
            p2_start,
            p2_end,
            p2_motif,
            "P2",
            p2["projection_id"],
        )
    )

    best = None

    for p1 in candidates:
        p1_start = int(p1["tract_read_start"])
        p1_end = int(p1["tract_read_end"])
        p1_bp = p1_end - p1_start
        ov = overlap(p2_start, p2_end, p1_start, p1_end)
        p2_fraction = ov / p2_bp if p2_bp else 0.0
        p1_fraction = ov / p1_bp if p1_bp else 0.0
        dist = distance(p2_start, p2_end, p1_start, p1_end)
        same_motif = p2_motif == p1["canonical_motif"]

        score = (
            1 if ov > 0 else 0,
            min(p2_fraction, p1_fraction),
            ov,
            1 if same_motif else 0,
            -dist,
        )

        if best is None or score > best["score"]:
            best = {
                "row": p1,
                "start": p1_start,
                "end": p1_end,
                "bp": p1_bp,
                "overlap": ov,
                "p2_fraction": p2_fraction,
                "p1_fraction": p1_fraction,
                "distance": dist,
                "same_motif": same_motif,
                "score": score,
            }

    if best is None:
        relationship = "NO_P1_SPAN_ON_READ"
        interpretation = "P2_ONLY_EXACT_REPEAT_EVENT"
        best_values = {
            "projection_id": ".",
            "target_region_id": ".",
            "representative_locus_id": ".",
            "canonical_motif": ".",
        }
        best_start = best_end = best_bp = "."
        ov = 0
        p2_fraction = p1_fraction = 0.0
        dist = "."
        same_motif_text = "."
    else:
        p1 = best["row"]
        best_values = p1
        best_start = best["start"]
        best_end = best["end"]
        best_bp = best["bp"]
        ov = best["overlap"]
        p2_fraction = best["p2_fraction"]
        p1_fraction = best["p1_fraction"]
        dist = best["distance"]
        same_motif_text = str(best["same_motif"]).lower()

        exact_interval = (
            p2_start == best_start and p2_end == best_end
        )

        if exact_interval and best["same_motif"]:
            relationship = "EXACT_SAME_INTERVAL_SAME_MOTIF"
            interpretation = "REDUNDANT_SEQUENCE_EVIDENCE"

        elif exact_interval and not best["same_motif"]:
            relationship = "EXACT_SAME_INTERVAL_DIFFERENT_MOTIF"
            interpretation = "COMPETING_MOTIF_MODEL_SAME_SEQUENCE"

        elif (
            ov > 0
            and min(p2_fraction, p1_fraction) >= 0.80
            and best["same_motif"]
        ):
            relationship = "HIGH_OVERLAP_SAME_MOTIF"
            interpretation = "BOUNDARY_VARIANT_SAME_REPEAT_EVENT"

        elif (
            ov > 0
            and min(p2_fraction, p1_fraction) >= 0.80
            and not best["same_motif"]
        ):
            relationship = "HIGH_OVERLAP_DIFFERENT_MOTIF"
            interpretation = "COMPETING_REPEAT_MODEL"

        elif ov > 0 and best["same_motif"]:
            relationship = "PARTIAL_OVERLAP_SAME_MOTIF"
            interpretation = "POSSIBLE_NESTED_OR_SPLIT_REPEAT_MODEL"

        elif ov > 0:
            relationship = "PARTIAL_OVERLAP_DIFFERENT_MOTIF"
            interpretation = "OVERLAPPING_DISTINCT_REPEAT_MODELS"

        else:
            relationship = "DISTINCT_NONOVERLAPPING_INTERVAL"
            interpretation = "DISTINCT_REPEAT_EVENT_ON_SAME_READ"

    counts[f"relationship::{relationship}"] += 1
    counts[f"interpretation::{interpretation}"] += 1

    relationship_rows.append(
        {
            "p2_projection_id": p2["projection_id"],
            "read_id": read_id,
            "p2_target_region_id": p2["target_region_id"],
            "p2_representative_locus_id": p2[
                "representative_locus_id"
            ],
            "p2_motif": p2_motif,
            "p2_start": p2_start,
            "p2_end": p2_end,
            "p2_span_bp": p2_bp,
            "p2_assignment_rank": p2["assignment_rank"],
            "p1_span_count_on_read": len(candidates),
            "best_p1_projection_id": best_values["projection_id"],
            "best_p1_target_region_id": best_values[
                "target_region_id"
            ],
            "best_p1_representative_locus_id": best_values[
                "representative_locus_id"
            ],
            "best_p1_motif": best_values["canonical_motif"],
            "best_p1_start": best_start,
            "best_p1_end": best_end,
            "best_p1_span_bp": best_bp,
            "overlap_bp": ov,
            "p2_overlap_fraction": f"{p2_fraction:.6f}",
            "p1_overlap_fraction": f"{p1_fraction:.6f}",
            "interval_distance_bp": dist,
            "same_motif": same_motif_text,
            "relationship_class": relationship,
            "sequence_interpretation": interpretation,
        }
    )

with gzip.open(
    relationships_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=relationship_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(relationship_rows)

# Cluster exact intervals on each read into distinct raw-read repeat events.
read_columns = [
    "read_id",
    "p1_exact_span_rows",
    "p2_exact_span_rows",
    "all_exact_span_rows",
    "distinct_nonoverlapping_event_count",
    "event_count_with_multiple_motifs",
    "event_count_with_p1_and_p2",
    "event_intervals",
]

read_rows = []

for read_id, intervals in sorted(per_read_exact_intervals.items()):
    intervals = sorted(intervals, key=lambda item: (item[0], item[1]))
    events = []

    for start, end, motif, cohort, projection_id in intervals:
        overlapping_events = [
            event
            for event in events
            if overlap(start, end, event["start"], event["end"]) > 0
        ]

        if not overlapping_events:
            events.append(
                {
                    "start": start,
                    "end": end,
                    "motifs": {motif},
                    "cohorts": {cohort},
                    "projection_ids": {projection_id},
                }
            )
        else:
            event = max(
                overlapping_events,
                key=lambda value: overlap(
                    start, end, value["start"], value["end"]
                ),
            )
            event["start"] = min(event["start"], start)
            event["end"] = max(event["end"], end)
            event["motifs"].add(motif)
            event["cohorts"].add(cohort)
            event["projection_ids"].add(projection_id)

    read_rows.append(
        {
            "read_id": read_id,
            "p1_exact_span_rows": sum(
                cohort == "P1"
                for *_prefix, cohort, _projection_id in intervals
            ),
            "p2_exact_span_rows": sum(
                cohort == "P2"
                for *_prefix, cohort, _projection_id in intervals
            ),
            "all_exact_span_rows": len(intervals),
            "distinct_nonoverlapping_event_count": len(events),
            "event_count_with_multiple_motifs": sum(
                len(event["motifs"]) > 1 for event in events
            ),
            "event_count_with_p1_and_p2": sum(
                event["cohorts"] == {"P1", "P2"}
                for event in events
            ),
            "event_intervals": ";".join(
                (
                    f"{event['start']}-{event['end']}:"
                    f"{','.join(sorted(event['motifs']))}:"
                    f"{','.join(sorted(event['cohorts']))}"
                )
                for event in events
            ),
        }
    )

with gzip.open(
    read_summary_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=read_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(read_rows)

# Extract extreme non-exact P2 tracts.
nonexact_classes = {
    "LEFT_ONLY_INTERNAL",
    "RIGHT_ONLY_INTERNAL",
    "REPEAT_ONLY_UNANCHORED",
    "UNRESOLVED",
}
extreme_rows = [
    row for row in p2_rows
    if (
        row["evidence_class"] in nonexact_classes
        and int(row["tract_read_bp"]) >= 1000
    )
]
extreme_rows.sort(
    key=lambda row: int(row["tract_read_bp"]),
    reverse=True,
)

extreme_fields = [
    field for field in p2_rows[0].keys()
    if not field.startswith("_")
] + [
    "tract_fraction_of_read",
    "touches_raw_start",
    "touches_raw_end",
]

with open(
    extreme_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=extreme_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for row in extreme_rows:
        start = int(row["tract_read_start"])
        end = int(row["tract_read_end"])
        read_length = int(row["read_length_bp"])
        output_row = {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
        }
        output_row.update(
            {
                "tract_fraction_of_read": (
                    f"{int(row['tract_read_bp']) / read_length:.6f}"
                ),
                "touches_raw_start": str(start <= 10).lower(),
                "touches_raw_end": str(
                    read_length - end <= 10
                ).lower(),
            }
        )
        writer.writerow(output_row)

summary_groups = defaultdict(list)
for row in relationship_rows:
    summary_groups[row["relationship_class"]].append(row)

summary_columns = [
    "relationship_class",
    "p2_span_rows",
    "unique_reads",
    "unique_p2_targets",
    "p2_span_bp_median",
    "p2_span_bp_p95",
    "interval_distance_bp_median",
]

with open(
    summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=summary_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for relationship in sorted(summary_groups):
        rows = summary_groups[relationship]
        span_lengths = [int(row["p2_span_bp"]) for row in rows]
        distances = [
            int(row["interval_distance_bp"])
            for row in rows
            if row["interval_distance_bp"] != "."
        ]
        writer.writerow(
            {
                "relationship_class": relationship,
                "p2_span_rows": len(rows),
                "unique_reads": len(
                    {row["read_id"] for row in rows}
                ),
                "unique_p2_targets": len(
                    {row["p2_target_region_id"] for row in rows}
                ),
                "p2_span_bp_median": (
                    f"{quantile(span_lengths, 0.5):.6f}"
                ),
                "p2_span_bp_p95": (
                    f"{quantile(span_lengths, 0.95):.6f}"
                ),
                "interval_distance_bp_median": (
                    "."
                    if not distances
                    else f"{quantile(distances, 0.5):.6f}"
                ),
            }
        )

event_counts = [
    int(row["distinct_nonoverlapping_event_count"])
    for row in read_rows
]

status = "PASS"
if (
    len(p1_rows) != EXPECTED_P1
    or len(p2_rows) != EXPECTED_P2
    or sum(
        row["evidence_class"] == "SPAN" for row in p1_rows
    ) != EXPECTED_P1_SPAN
    or len(p2_spans) != EXPECTED_P2_SPAN
    or len(relationship_rows) != EXPECTED_P2_SPAN
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(f"expected_p1_rows\t{EXPECTED_P1}\n")
    handle.write(f"observed_p1_rows\t{len(p1_rows)}\n")
    handle.write(f"expected_p2_rows\t{EXPECTED_P2}\n")
    handle.write(f"observed_p2_rows\t{len(p2_rows)}\n")
    handle.write(f"expected_p1_span\t{EXPECTED_P1_SPAN}\n")
    handle.write(
        "observed_p1_span\t"
        f"{sum(row['evidence_class'] == 'SPAN' for row in p1_rows)}\n"
    )
    handle.write(f"expected_p2_span\t{EXPECTED_P2_SPAN}\n")
    handle.write(f"observed_p2_span\t{len(p2_spans)}\n")
    handle.write(
        f"relationship_rows_written\t{len(relationship_rows)}\n"
    )
    handle.write(f"read_summary_rows\t{len(read_rows)}\n")
    handle.write(
        f"extreme_nonexact_tracts_ge1000bp\t"
        f"{len(extreme_rows)}\n"
    )
    handle.write(
        f"reads_with_multiple_distinct_exact_events\t"
        f"{sum(value > 1 for value in event_counts)}\n"
    )
    handle.write(
        f"distinct_exact_event_count_median\t"
        f"{quantile(event_counts, 0.5):.6f}\n"
    )
    handle.write(
        f"distinct_exact_event_count_p95\t"
        f"{quantile(event_counts, 0.95):.6f}\n"
    )
    handle.write(
        f"distinct_exact_event_count_max\t"
        f"{max(event_counts, default=0)}\n"
    )

    for key, value in sorted(counts.items()):
        handle.write(f"{key}\t{value}\n")

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("P2 relationship classification requires review")
PY

echo "===== INPUT INTEGRITY ====="
gzip -t "$P1"
gzip -t "$P2"

rm -f \
  "$RELATIONSHIPS" \
  "$SUMMARY" \
  "$READ_SUMMARY" \
  "$EXTREME" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== CLASSIFY P2 RELATIONSHIPS TO P1 ====="

python "$AUDITOR" \
  "$P1" \
  "$P2" \
  "$RELATIONSHIPS" \
  "$SUMMARY" \
  "$READ_SUMMARY" \
  "$EXTREME" \
  "$QC" \
  "$EXPECTED_P1_ROWS" \
  "$EXPECTED_P2_ROWS" \
  "$EXPECTED_P1_SPAN" \
  "$EXPECTED_P2_SPAN"

gzip -t "$RELATIONSHIPS"
gzip -t "$READ_SUMMARY"

echo
echo "===== RELATIONSHIP QC ====="
column -ts $'\t' "$QC"

echo
echo "===== RELATIONSHIP SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== EXTREME NON-EXACT TRACTS ====="
column -ts $'\t' "$EXTREME"

echo
echo "===== OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in "$RELATIONSHIPS" "$READ_SUMMARY"; do
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in "$SUMMARY" "$EXTREME" "$QC"; do
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
echo "$RELATIONSHIPS"
echo "$SUMMARY"
echo "$READ_SUMMARY"
echo "$EXTREME"
echo "$QC"
echo "$MANIFEST"
