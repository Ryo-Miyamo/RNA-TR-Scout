#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_VERSION="rnatr_exact_repeat_event_model_v0.3.1"

P1="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID/v0.3.3/simple_periodic_evidence.calibrated.v0.3.3.tsv.gz"
P2="$PROJECT_ROOT/results/11_p2_periodic/$RUN_ID/p2_alternate_exact_simple_periodic_evidence.tsv.gz"

OUTDIR="$PROJECT_ROOT/results/11_exact_events/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_exact_events/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_exact_events/$RUN_ID"

EVENTS="$OUTDIR/exact_repeat_events.tsv.gz"
HYPOTHESES="$OUTDIR/exact_repeat_event_hypotheses.tsv.gz"
MEMBERSHIP="$OUTDIR/exact_repeat_event_membership.tsv.gz"
SUMMARY="$OUTDIR/exact_repeat_event_summary.tsv"
QC="$QCDIR/exact_repeat_event_model_qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.exact_repeat_event_model.manifest.tsv"

BUILDER="$WORKDIR/build_exact_repeat_events.py"

EXPECTED_P1_ROWS=49793
EXPECTED_P2_ROWS=108595
EXPECTED_EXACT_ROWS=103852
EXPECTED_SEQUENCE_HYPOTHESES=97509
EXPECTED_READS_MULTIPLE_EVENTS=20692
EXPECTED_MAX_EVENTS_PER_READ=26

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$P1" "$P2"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$BUILDER" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import math
import sys
from collections import Counter, defaultdict

(
    p1_path,
    p2_path,
    events_path,
    hypotheses_path,
    membership_path,
    summary_path,
    qc_path,
    model_version,
    expected_p1_text,
    expected_p2_text,
    expected_exact_text,
    expected_hypotheses_text,
    expected_multiple_reads_text,
    expected_max_events_text,
) = sys.argv[1:]

EXPECTED_P1 = int(expected_p1_text)
EXPECTED_P2 = int(expected_p2_text)
EXPECTED_EXACT = int(expected_exact_text)
EXPECTED_HYPOTHESES = int(expected_hypotheses_text)
EXPECTED_MULTIPLE_READS = int(expected_multiple_reads_text)
EXPECTED_MAX_EVENTS = int(expected_max_events_text)


def overlap(a_start, a_end, b_start, b_end):
    return max(0, min(a_end, b_end) - max(a_start, b_start))


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


def load_exact(path, cohort):
    all_rows = 0
    exact_rows = []

    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")

        for row in reader:
            all_rows += 1

            if row["evidence_class"] != "SPAN":
                continue

            row["_cohort"] = cohort
            row["_start"] = int(row["tract_read_start"])
            row["_end"] = int(row["tract_read_end"])
            row["_motif"] = row["canonical_motif"]
            exact_rows.append(row)

    return all_rows, exact_rows


p1_all, p1_exact = load_exact(p1_path, "P0_P1")
p2_all, p2_exact = load_exact(p2_path, "P2")
all_exact = p1_exact + p2_exact

by_read = defaultdict(list)

for row in all_exact:
    by_read[row["read_id"]].append(row)

event_rows = []
hypothesis_rows = []
membership_rows = []
counts = Counter()
events_per_read = []
unique_sequence_hypotheses = 0

event_columns = [
    "event_id",
    "event_model_version",
    "read_id",
    "event_index_on_read",
    "event_start",
    "event_end",
    "event_span_bp",
    "original_evidence_row_count",
    "sequence_hypothesis_count",
    "target_hypothesis_count",
    "motif_count",
    "canonical_motifs",
    "cohort_composition",
    "contains_p1",
    "contains_p2",
    "event_class",
    "locus_assignment_status",
    "sequence_evidence_status",
    "representative_hypothesis_id",
    "representative_start",
    "representative_end",
    "representative_span_bp",
    "representative_motif",
    "representative_purity",
    "representative_mapq",
    "representative_sequence_status",
    "target_region_ids",
    "representative_locus_ids",
]

hypothesis_columns = [
    "hypothesis_id",
    "event_id",
    "read_id",
    "hypothesis_start",
    "hypothesis_end",
    "hypothesis_span_bp",
    "canonical_motif",
    "source_row_count",
    "p1_row_count",
    "p2_row_count",
    "target_hypothesis_count",
    "target_region_ids",
    "target_sources",
    "representative_locus_ids",
    "assignment_ranks",
    "sequence_statuses",
    "purity_min",
    "purity_max",
    "best_mapq_max",
    "hypothesis_role",
]

membership_columns = [
    "event_id",
    "hypothesis_id",
    "cohort",
    "projection_id",
    "read_id",
    "target_region_id",
    "target_source",
    "representative_locus_id",
    "assignment_rank",
    "tract_read_start",
    "tract_read_end",
    "tract_read_bp",
    "canonical_motif",
    "purity",
    "best_mapq",
    "sequence_status",
    "original_assignment_status",
]

sequence_status_priority = {
    "PERIODIC_EXACT_SPAN": 3,
    "SHORT_EXACT_SPAN": 2,
    "COMPLEX_OR_LOW_PERIODICITY_EXACT_SPAN": 1,
    ".": 0,
}

confidence_priority = {
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    ".": 0,
}


def sequence_status(row):
    return row.get(
        "exact_span_sequence_status",
        row.get("span_sequence_status", "."),
    )


def row_rank(row):
    status = sequence_status(row)
    confidence = row.get(
        "confidence_label",
        row.get("sequence_confidence_label", "."),
    )
    return (
        sequence_status_priority.get(status, 0),
        confidence_priority.get(confidence, 0),
        float(row["purity"]),
        int(row["best_mapq"]),
        -int(row["assignment_rank"]),
        1 if row["_cohort"] == "P0_P1" else 0,
    )


for read_id in sorted(by_read):
    read_rows = sorted(
        by_read[read_id],
        key=lambda row: (
            row["_start"],
            row["_end"],
            row["_motif"],
            int(row["assignment_rank"]),
        ),
    )

    # Connected components of positively overlapping exact intervals.
    components = []

    for row in read_rows:
        overlapping = [
            component
            for component in components
            if overlap(
                row["_start"],
                row["_end"],
                component["start"],
                component["end"],
            ) > 0
        ]

        if not overlapping:
            components.append(
                {
                    "start": row["_start"],
                    "end": row["_end"],
                    "rows": [row],
                }
            )
            continue

        primary = overlapping[0]
        primary["start"] = min(primary["start"], row["_start"])
        primary["end"] = max(primary["end"], row["_end"])
        primary["rows"].append(row)

        # Merge any components connected transitively by this interval.
        for other in overlapping[1:]:
            primary["start"] = min(primary["start"], other["start"])
            primary["end"] = max(primary["end"], other["end"])
            primary["rows"].extend(other["rows"])
            components.remove(other)

    components.sort(key=lambda component: (component["start"], component["end"]))
    events_per_read.append(len(components))

    if len(components) > 1:
        counts["reads_with_multiple_events"] += 1

    for event_index, component in enumerate(components, start=1):
        component_rows = component["rows"]
        event_id = hashlib.sha256(
            (
                f"{read_id}|{component['start']}|"
                f"{component['end']}|{event_index}"
            ).encode()
        ).hexdigest()[:24]

        # Unique raw-sequence hypotheses: same interval and motif.
        hypothesis_groups = defaultdict(list)

        for row in component_rows:
            key = (
                row["_start"],
                row["_end"],
                row["_motif"],
            )
            hypothesis_groups[key].append(row)

        unique_sequence_hypotheses += len(hypothesis_groups)

        hypothesis_ids = {}
        event_motifs = set()
        event_targets = set()
        event_loci = set()
        event_cohorts = set()

        for hypothesis_index, (key, rows) in enumerate(
            sorted(hypothesis_groups.items()),
            start=1,
        ):
            start, end, motif = key
            hypothesis_id = hashlib.sha256(
                (
                    f"{event_id}|{start}|{end}|{motif}|"
                    f"{hypothesis_index}"
                ).encode()
            ).hexdigest()[:24]
            hypothesis_ids[key] = hypothesis_id

            targets = {
                (row["target_source"], row["target_region_id"])
                for row in rows
            }
            loci = {
                row["representative_locus_id"]
                for row in rows
            }
            cohorts = {row["_cohort"] for row in rows}
            statuses = {sequence_status(row) for row in rows}

            event_motifs.add(motif)
            event_targets.update(targets)
            event_loci.update(loci)
            event_cohorts.update(cohorts)

            if len(rows) > 1:
                hypothesis_role = (
                    "SAME_SEQUENCE_MULTIPLE_SOURCE_ROWS"
                )
            else:
                hypothesis_role = "SINGLE_SOURCE_ROW"

            hypothesis_rows.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "event_id": event_id,
                    "read_id": read_id,
                    "hypothesis_start": start,
                    "hypothesis_end": end,
                    "hypothesis_span_bp": end - start,
                    "canonical_motif": motif,
                    "source_row_count": len(rows),
                    "p1_row_count": sum(
                        row["_cohort"] == "P0_P1"
                        for row in rows
                    ),
                    "p2_row_count": sum(
                        row["_cohort"] == "P2"
                        for row in rows
                    ),
                    "target_hypothesis_count": len(targets),
                    "target_region_ids": ";".join(
                        sorted(target for _source, target in targets)
                    ),
                    "target_sources": ";".join(
                        sorted(source for source, _target in targets)
                    ),
                    "representative_locus_ids": ";".join(
                        sorted(loci)
                    ),
                    "assignment_ranks": ";".join(
                        sorted(
                            {row["assignment_rank"] for row in rows},
                            key=lambda value: int(value),
                        )
                    ),
                    "sequence_statuses": ";".join(sorted(statuses)),
                    "purity_min": (
                        f"{min(float(row['purity']) for row in rows):.6f}"
                    ),
                    "purity_max": (
                        f"{max(float(row['purity']) for row in rows):.6f}"
                    ),
                    "best_mapq_max": max(
                        int(row["best_mapq"]) for row in rows
                    ),
                    "hypothesis_role": hypothesis_role,
                }
            )

            for row in rows:
                membership_rows.append(
                    {
                        "event_id": event_id,
                        "hypothesis_id": hypothesis_id,
                        "cohort": row["_cohort"],
                        "projection_id": row["projection_id"],
                        "read_id": read_id,
                        "target_region_id": row["target_region_id"],
                        "target_source": row["target_source"],
                        "representative_locus_id": row[
                            "representative_locus_id"
                        ],
                        "assignment_rank": row["assignment_rank"],
                        "tract_read_start": row["_start"],
                        "tract_read_end": row["_end"],
                        "tract_read_bp": (
                            row["_end"] - row["_start"]
                        ),
                        "canonical_motif": row["_motif"],
                        "purity": row["purity"],
                        "best_mapq": row["best_mapq"],
                        "sequence_status": sequence_status(row),
                        "original_assignment_status": row.get(
                            "assignment_status",
                            "rank1_or_disease_target",
                        ),
                    }
                )

        # Event class and locus-assignment status.
        unique_intervals = {
            (key[0], key[1])
            for key in hypothesis_groups
        }

        if len(hypothesis_groups) == 1:
            if len(event_targets) == 1:
                event_class = "SINGLE_EXACT_REPEAT_EVENT"
                locus_status = "UNIQUE_TARGET_HYPOTHESIS"
            else:
                event_class = (
                    "SAME_SEQUENCE_MULTIPLE_TARGET_HYPOTHESES"
                )
                locus_status = (
                    "MULTIPLE_TARGETS_SAME_SEQUENCE_EVIDENCE"
                )

        elif len(unique_intervals) == 1:
            event_class = "SAME_INTERVAL_COMPETING_MOTIFS"
            locus_status = "COMPETING_MOTIF_MODELS"

        elif len(event_motifs) == 1:
            event_class = "BOUNDARY_VARIANTS_SAME_MOTIF"
            locus_status = "BOUNDARY_AMBIGUOUS_SAME_MOTIF"

        else:
            event_class = "OVERLAPPING_MULTIPLE_REPEAT_MODELS"
            locus_status = "COMPETING_OVERLAPPING_MODELS"

        representative = max(component_rows, key=row_rank)
        representative_key = (
            representative["_start"],
            representative["_end"],
            representative["_motif"],
        )

        event_rows.append(
            {
                "event_id": event_id,
                "event_model_version": model_version,
                "read_id": read_id,
                "event_index_on_read": event_index,
                "event_start": component["start"],
                "event_end": component["end"],
                "event_span_bp": (
                    component["end"] - component["start"]
                ),
                "original_evidence_row_count": len(component_rows),
                "sequence_hypothesis_count": len(
                    hypothesis_groups
                ),
                "target_hypothesis_count": len(event_targets),
                "motif_count": len(event_motifs),
                "canonical_motifs": ";".join(
                    sorted(event_motifs)
                ),
                "cohort_composition": ";".join(
                    sorted(event_cohorts)
                ),
                "contains_p1": str(
                    "P0_P1" in event_cohorts
                ).lower(),
                "contains_p2": str(
                    "P2" in event_cohorts
                ).lower(),
                "event_class": event_class,
                "locus_assignment_status": locus_status,
                "sequence_evidence_status": (
                    "EXACT_FLANK_BOUNDED"
                ),
                "representative_hypothesis_id": hypothesis_ids[
                    representative_key
                ],
                "representative_start": representative["_start"],
                "representative_end": representative["_end"],
                "representative_span_bp": (
                    representative["_end"]
                    - representative["_start"]
                ),
                "representative_motif": representative["_motif"],
                "representative_purity": representative["purity"],
                "representative_mapq": representative["best_mapq"],
                "representative_sequence_status": sequence_status(
                    representative
                ),
                "target_region_ids": ";".join(
                    sorted(target for _source, target in event_targets)
                ),
                "representative_locus_ids": ";".join(
                    sorted(event_loci)
                ),
            }
        )

        counts[f"event_class::{event_class}"] += 1
        counts[f"locus_status::{locus_status}"] += 1
        counts[
            f"cohort_composition::{';'.join(sorted(event_cohorts))}"
        ] += 1

with gzip.open(
    events_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=event_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(event_rows)

with gzip.open(
    hypotheses_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=hypothesis_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(hypothesis_rows)

with gzip.open(
    membership_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=membership_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(membership_rows)

summary_columns = [
    "group",
    "events",
    "unique_reads",
    "event_span_bp_median",
    "event_span_bp_p95",
    "sequence_hypotheses",
    "target_hypotheses",
]

summary_groups = defaultdict(list)

for row in event_rows:
    summary_groups["ALL"].append(row)
    summary_groups[
        f"event_class::{row['event_class']}"
    ].append(row)
    summary_groups[
        f"locus_status::{row['locus_assignment_status']}"
    ].append(row)
    summary_groups[
        f"cohort::{row['cohort_composition']}"
    ].append(row)

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

    for group_name in sorted(summary_groups):
        rows = summary_groups[group_name]
        span_values = [int(row["event_span_bp"]) for row in rows]

        writer.writerow(
            {
                "group": group_name,
                "events": len(rows),
                "unique_reads": len(
                    {row["read_id"] for row in rows}
                ),
                "event_span_bp_median": (
                    f"{quantile(span_values, 0.5):.6f}"
                ),
                "event_span_bp_p95": (
                    f"{quantile(span_values, 0.95):.6f}"
                ),
                "sequence_hypotheses": sum(
                    int(row["sequence_hypothesis_count"])
                    for row in rows
                ),
                "target_hypotheses": sum(
                    int(row["target_hypothesis_count"])
                    for row in rows
                ),
            }
        )

status = "PASS"

if (
    p1_all != EXPECTED_P1
    or p2_all != EXPECTED_P2
    or len(all_exact) != EXPECTED_EXACT
    or len(membership_rows) != EXPECTED_EXACT
    or unique_sequence_hypotheses != EXPECTED_HYPOTHESES
    or len(hypothesis_rows) != EXPECTED_HYPOTHESES
    or counts["reads_with_multiple_events"]
       != EXPECTED_MULTIPLE_READS
    or max(events_per_read, default=0) != EXPECTED_MAX_EVENTS
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(f"expected_p1_rows\t{EXPECTED_P1}\n")
    handle.write(f"observed_p1_rows\t{p1_all}\n")
    handle.write(f"expected_p2_rows\t{EXPECTED_P2}\n")
    handle.write(f"observed_p2_rows\t{p2_all}\n")
    handle.write(
        f"expected_exact_evidence_rows\t{EXPECTED_EXACT}\n"
    )
    handle.write(
        f"exact_evidence_rows_loaded\t{len(all_exact)}\n"
    )
    handle.write(
        f"membership_rows_written\t{len(membership_rows)}\n"
    )
    handle.write(
        f"expected_sequence_hypotheses\t"
        f"{EXPECTED_HYPOTHESES}\n"
    )
    handle.write(
        f"sequence_hypotheses_written\t"
        f"{len(hypothesis_rows)}\n"
    )
    handle.write(f"exact_repeat_events\t{len(event_rows)}\n")
    handle.write(f"reads_with_exact_events\t{len(by_read)}\n")
    handle.write(
        f"reads_with_multiple_events\t"
        f"{counts['reads_with_multiple_events']}\n"
    )
    handle.write(
        f"events_per_read_median\t"
        f"{quantile(events_per_read, 0.5):.6f}\n"
    )
    handle.write(
        f"events_per_read_p95\t"
        f"{quantile(events_per_read, 0.95):.6f}\n"
    )
    handle.write(
        f"events_per_read_max\t"
        f"{max(events_per_read, default=0)}\n"
    )

    for key, value in sorted(counts.items()):
        if key == "reads_with_multiple_events":
            continue
        handle.write(f"{key}\t{value}\n")

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Exact repeat event model requires review")
PY

echo "===== INPUT INTEGRITY ====="
gzip -t "$P1"
gzip -t "$P2"

rm -f \
  "$EVENTS" \
  "$HYPOTHESES" \
  "$MEMBERSHIP" \
  "$SUMMARY" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== BUILD EVENT-CENTRIC EXACT REPEAT MODEL ====="

python "$BUILDER" \
  "$P1" \
  "$P2" \
  "$EVENTS" \
  "$HYPOTHESES" \
  "$MEMBERSHIP" \
  "$SUMMARY" \
  "$QC" \
  "$MODEL_VERSION" \
  "$EXPECTED_P1_ROWS" \
  "$EXPECTED_P2_ROWS" \
  "$EXPECTED_EXACT_ROWS" \
  "$EXPECTED_SEQUENCE_HYPOTHESES" \
  "$EXPECTED_READS_MULTIPLE_EVENTS" \
  "$EXPECTED_MAX_EVENTS_PER_READ"

gzip -t "$EVENTS"
gzip -t "$HYPOTHESES"
gzip -t "$MEMBERSHIP"

echo
echo "===== EVENT MODEL QC ====="
column -ts $'\t' "$QC"

echo
echo "===== EVENT SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in "$EVENTS" "$HYPOTHESES" "$MEMBERSHIP"; do
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in "$SUMMARY" "$QC"; do
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
echo "$EVENTS"
echo "$HYPOTHESES"
echo "$MEMBERSHIP"
echo "$SUMMARY"
echo "$QC"
echo "$MANIFEST"
