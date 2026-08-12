#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

AUDIT="$PROJECT_ROOT/results/11_extreme_nonexact/$RUN_ID/p2_nonexact_tracts_ge1000bp.audit.tsv"

OUTDIR="$PROJECT_ROOT/results/11_extreme_nonexact_events/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_extreme_nonexact_events/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_extreme_nonexact_events/$RUN_ID"

EVENTS="$OUTDIR/extreme_nonexact_events.tsv"
LOCUS_CLUSTERS="$OUTDIR/extreme_nonexact_locus_clusters.tsv"
FOCUS="$OUTDIR/extreme_nonexact_focus_candidates.tsv"
QC="$QCDIR/extreme_nonexact_event_triage.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.extreme_nonexact_event_triage.manifest.tsv"
PY="$WORKDIR/build_extreme_nonexact_events.py"

EXPECTED_INPUT_ROWS=37
EXPECTED_EVENTS=32

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

test -s "$AUDIT" || {
    echo "ERROR: missing input: $AUDIT" >&2
    exit 1
}

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import hashlib
import sys
from collections import Counter, defaultdict

(
    audit_path,
    events_path,
    clusters_path,
    focus_path,
    qc_path,
    expected_rows_text,
    expected_events_text,
) = sys.argv[1:]

EXPECTED_ROWS = int(expected_rows_text)
EXPECTED_EVENTS = int(expected_events_text)


def overlap(a_start, a_end, b_start, b_end):
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def parse_target(target_region_id):
    # Expected:
    # TR:15-64951270-64955063:15-64951270-64955063-TCT
    first = target_region_id.split(":", 2)[1]
    chrom, start, end = first.rsplit("-", 2)
    return chrom, int(start), int(end)


with open(
    audit_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))

for row in rows:
    row["_start"] = int(row["tract_read_start"])
    row["_end"] = int(row["tract_read_end"])
    row["_tract_bp"] = int(row["tract_read_bp"])
    row["_purity"] = float(row["purity"])
    row["_mapq"] = int(row["best_mapq"])
    row["_target_overlap"] = int(row["target_overlap_bp"])
    row["_chimeric"] = (
        int(row["chimeric_candidate_records"]) > 0
        or int(row["unique_alignment_chromosomes"]) > 1
    )
    row["_supplementary"] = (
        int(row["supplementary_alignments"]) > 0
    )
    row["_chrom"], row["_target_start"], row["_target_end"] = (
        parse_target(row["target_region_id"])
    )

# ------------------------------------------------------------------
# Build genomic locus clusters from overlapping target intervals.
# ------------------------------------------------------------------

unique_targets = {}

for row in rows:
    key = (
        row["_chrom"],
        row["_target_start"],
        row["_target_end"],
        row["target_region_id"],
    )
    unique_targets[key] = row

targets_by_chrom = defaultdict(list)

for key in unique_targets:
    chrom, start, end, target_id = key
    targets_by_chrom[chrom].append(
        {
            "chrom": chrom,
            "start": start,
            "end": end,
            "target_ids": {target_id},
        }
    )

clusters = []

for chrom in sorted(targets_by_chrom):
    intervals = sorted(
        targets_by_chrom[chrom],
        key=lambda item: (item["start"], item["end"]),
    )

    chrom_clusters = []

    for interval in intervals:
        overlapping = [
            cluster
            for cluster in chrom_clusters
            if overlap(
                interval["start"],
                interval["end"],
                cluster["start"],
                cluster["end"],
            ) > 0
        ]

        if not overlapping:
            chrom_clusters.append(interval)
            continue

        primary = overlapping[0]
        primary["start"] = min(
            primary["start"],
            interval["start"],
        )
        primary["end"] = max(
            primary["end"],
            interval["end"],
        )
        primary["target_ids"].update(
            interval["target_ids"]
        )

        for other in overlapping[1:]:
            primary["start"] = min(
                primary["start"],
                other["start"],
            )
            primary["end"] = max(
                primary["end"],
                other["end"],
            )
            primary["target_ids"].update(
                other["target_ids"]
            )
            chrom_clusters.remove(other)

    clusters.extend(chrom_clusters)

clusters.sort(
    key=lambda item: (
        item["chrom"],
        item["start"],
        item["end"],
    )
)

target_to_cluster = {}
cluster_records = {}

for index, cluster in enumerate(clusters, start=1):
    cluster_id = (
        f"EXTLOC_{index:05d}_"
        f"{cluster['chrom']}_{cluster['start']}_{cluster['end']}"
    )
    cluster["cluster_id"] = cluster_id
    cluster_records[cluster_id] = cluster

    for target_id in cluster["target_ids"]:
        target_to_cluster[target_id] = cluster_id

# ------------------------------------------------------------------
# Build overlapping raw-read events.
# ------------------------------------------------------------------

rows_by_read = defaultdict(list)

for row in rows:
    rows_by_read[row["read_id"]].append(row)

events = []

for read_id in sorted(rows_by_read):
    read_rows = sorted(
        rows_by_read[read_id],
        key=lambda row: (
            row["_start"],
            row["_end"],
        ),
    )

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
        primary["start"] = min(
            primary["start"],
            row["_start"],
        )
        primary["end"] = max(
            primary["end"],
            row["_end"],
        )
        primary["rows"].append(row)

        for other in overlapping[1:]:
            primary["start"] = min(
                primary["start"],
                other["start"],
            )
            primary["end"] = max(
                primary["end"],
                other["end"],
            )
            primary["rows"].extend(other["rows"])
            components.remove(other)

    components.sort(
        key=lambda component: (
            component["start"],
            component["end"],
        )
    )

    for event_index, component in enumerate(
        components,
        start=1,
    ):
        event_id = hashlib.sha256(
            (
                f"{read_id}|{component['start']}|"
                f"{component['end']}|{event_index}"
            ).encode()
        ).hexdigest()[:24]

        event_rows = component["rows"]
        cluster_ids = sorted(
            {
                target_to_cluster[row["target_region_id"]]
                for row in event_rows
            }
        )

        events.append(
            {
                "event_id": event_id,
                "read_id": read_id,
                "event_index_on_read": event_index,
                "event_start": component["start"],
                "event_end": component["end"],
                "event_span_bp": (
                    component["end"] - component["start"]
                ),
                "source_row_count": len(event_rows),
                "projection_ids": ";".join(
                    sorted(
                        row["projection_id"]
                        for row in event_rows
                    )
                ),
                "evidence_classes": ";".join(
                    sorted(
                        {
                            row["evidence_class"]
                            for row in event_rows
                        }
                    )
                ),
                "target_region_ids": ";".join(
                    sorted(
                        {
                            row["target_region_id"]
                            for row in event_rows
                        }
                    )
                ),
                "locus_cluster_ids": ";".join(
                    cluster_ids
                ),
                "motifs": ";".join(
                    sorted(
                        {
                            row["motif"]
                            for row in event_rows
                        }
                    )
                ),
                "maximum_tract_bp": max(
                    row["_tract_bp"]
                    for row in event_rows
                ),
                "maximum_purity": max(
                    row["_purity"]
                    for row in event_rows
                ),
                "maximum_mapq": max(
                    row["_mapq"]
                    for row in event_rows
                ),
                "maximum_target_overlap_bp": max(
                    row["_target_overlap"]
                    for row in event_rows
                ),
                "any_chimeric_or_multichromosome": any(
                    row["_chimeric"]
                    for row in event_rows
                ),
                "any_supplementary_alignment": any(
                    row["_supplementary"]
                    for row in event_rows
                ),
                "any_low_complexity_review": any(
                    row["review_class"]
                    == "LOW_COMPLEXITY_LONG_TRACT_REVIEW"
                    for row in event_rows
                ),
                "any_high_purity_review": any(
                    row["review_class"]
                    == "HIGH_PURITY_LONG_PERIODIC_TRACT_REVIEW"
                    for row in event_rows
                ),
                "_rows": event_rows,
                "_cluster_ids": cluster_ids,
            }
        )

# ------------------------------------------------------------------
# Cluster-level recurrence statistics.
# ------------------------------------------------------------------

events_by_cluster = defaultdict(list)

for event in events:
    for cluster_id in event["_cluster_ids"]:
        events_by_cluster[cluster_id].append(event)

cluster_rows = []

for cluster_id in sorted(cluster_records):
    cluster = cluster_records[cluster_id]
    cluster_events = events_by_cluster.get(
        cluster_id,
        [],
    )
    nonchimeric = [
        event
        for event in cluster_events
        if not event["any_chimeric_or_multichromosome"]
    ]

    cluster_rows.append(
        {
            "locus_cluster_id": cluster_id,
            "chrom": cluster["chrom"],
            "cluster_start": cluster["start"],
            "cluster_end": cluster["end"],
            "cluster_span_bp": (
                cluster["end"] - cluster["start"]
            ),
            "target_count": len(cluster["target_ids"]),
            "target_region_ids": ";".join(
                sorted(cluster["target_ids"])
            ),
            "event_count": len(cluster_events),
            "unique_read_count": len(
                {
                    event["read_id"]
                    for event in cluster_events
                }
            ),
            "nonchimeric_event_count": len(
                nonchimeric
            ),
            "nonchimeric_unique_read_count": len(
                {
                    event["read_id"]
                    for event in nonchimeric
                }
            ),
            "maximum_tract_bp": max(
                (
                    event["maximum_tract_bp"]
                    for event in cluster_events
                ),
                default=0,
            ),
            "maximum_purity": (
                f"{max(
                    (
                        event["maximum_purity"]
                        for event in cluster_events
                    ),
                    default=0.0,
                ):.6f}"
            ),
            "maximum_target_overlap_bp": max(
                (
                    event["maximum_target_overlap_bp"]
                    for event in cluster_events
                ),
                default=0,
            ),
            "motifs": ";".join(
                sorted(
                    {
                        motif
                        for event in cluster_events
                        for motif in event["motifs"].split(";")
                    }
                )
            ),
        }
    )

cluster_nonchimeric_counts = {
    row["locus_cluster_id"]:
    int(row["nonchimeric_event_count"])
    for row in cluster_rows
}

# ------------------------------------------------------------------
# Final event-level triage.
# ------------------------------------------------------------------

for event in events:
    recurrent_nonchimeric = max(
        (
            cluster_nonchimeric_counts[cluster_id]
            for cluster_id in event["_cluster_ids"]
        ),
        default=0,
    )

    if event["any_chimeric_or_multichromosome"]:
        disposition = "EXCLUDE_CHIMERIC_OR_MULTISEGMENT"
        priority = 5
        rationale = (
            "Supplementary/chimeric or multi-chromosome "
            "alignment evidence"
        )

    elif event["maximum_target_overlap_bp"] == 0:
        disposition = "EXCLUDE_NO_TARGET_SUPPORT"
        priority = 5
        rationale = "Detected tract does not overlap target"

    elif (
        event["maximum_purity"] >= 0.80
        and event["maximum_mapq"] >= 20
        and event["maximum_target_overlap_bp"] >= 12
    ):
        disposition = "RETAIN_LONG_PERIODIC_LOCUS_REVIEW"
        priority = 1
        rationale = (
            "High-purity long target-overlapping tract "
            "with nonchimeric high-MAPQ alignment"
        )

    elif recurrent_nonchimeric >= 2:
        disposition = "RETAIN_RECURRENT_COMPLEX_LOCUS_REVIEW"
        priority = 2
        rationale = (
            "Same genomic locus cluster observed in at least "
            "two independent nonchimeric reads"
        )

    elif event["any_low_complexity_review"]:
        disposition = "RETAIN_LOW_COMPLEXITY_END_REVIEW"
        priority = 3
        rationale = (
            "Long target-overlapping low-complexity tract "
            "requires end/adaptor assessment"
        )

    else:
        disposition = "NO_CALL_UNRESOLVED_LONG_LOCAL_ALIGNMENT"
        priority = 4
        rationale = (
            "Long local periodic alignment does not satisfy "
            "validated repeat-call criteria"
        )

    event["recurrent_nonchimeric_events_at_locus"] = (
        recurrent_nonchimeric
    )
    event["triage_priority"] = priority
    event["triage_disposition"] = disposition
    event["triage_rationale"] = rationale

event_columns = [
    "event_id",
    "read_id",
    "event_index_on_read",
    "event_start",
    "event_end",
    "event_span_bp",
    "source_row_count",
    "projection_ids",
    "evidence_classes",
    "target_region_ids",
    "locus_cluster_ids",
    "motifs",
    "maximum_tract_bp",
    "maximum_purity",
    "maximum_mapq",
    "maximum_target_overlap_bp",
    "any_chimeric_or_multichromosome",
    "any_supplementary_alignment",
    "recurrent_nonchimeric_events_at_locus",
    "triage_priority",
    "triage_disposition",
    "triage_rationale",
]

events.sort(
    key=lambda event: (
        event["triage_priority"],
        -event["maximum_purity"],
        -event["maximum_tract_bp"],
    )
)

with open(
    events_path,
    "w",
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

    for event in events:
        writer.writerow(
            {
                key: (
                    str(value).lower()
                    if isinstance(value, bool)
                    else value
                )
                for key, value in event.items()
                if key in event_columns
            }
        )

cluster_columns = list(cluster_rows[0].keys())

with open(
    clusters_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=cluster_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(cluster_rows)

focus_dispositions = {
    "RETAIN_LONG_PERIODIC_LOCUS_REVIEW",
    "RETAIN_RECURRENT_COMPLEX_LOCUS_REVIEW",
    "RETAIN_LOW_COMPLEXITY_END_REVIEW",
}

focus_events = [
    event
    for event in events
    if event["triage_disposition"] in focus_dispositions
]

with open(
    focus_path,
    "w",
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

    for event in focus_events:
        writer.writerow(
            {
                key: (
                    str(value).lower()
                    if isinstance(value, bool)
                    else value
                )
                for key, value in event.items()
                if key in event_columns
            }
        )

counts = Counter(
    event["triage_disposition"]
    for event in events
)

status = "PASS"

if (
    len(rows) != EXPECTED_ROWS
    or len(events) != EXPECTED_EVENTS
    or sum(
        event["source_row_count"]
        for event in events
    ) != EXPECTED_ROWS
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        f"expected_input_rows\t{EXPECTED_ROWS}\n"
    )
    handle.write(f"observed_input_rows\t{len(rows)}\n")
    handle.write(
        f"expected_raw_read_events\t{EXPECTED_EVENTS}\n"
    )
    handle.write(
        f"observed_raw_read_events\t{len(events)}\n"
    )
    handle.write(
        "source_rows_represented_in_events\t"
        f"{sum(event['source_row_count'] for event in events)}\n"
    )
    handle.write(
        f"genomic_locus_clusters\t{len(cluster_rows)}\n"
    )
    handle.write(
        f"focus_events\t{len(focus_events)}\n"
    )

    for disposition, count in sorted(counts.items()):
        handle.write(
            f"triage::{disposition}\t{count}\n"
        )

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit(
        "Extreme non-exact event triage requires review"
    )
PY

echo "===== INPUT INTEGRITY ====="
test -s "$AUDIT"

rm -f \
  "$EVENTS" \
  "$LOCUS_CLUSTERS" \
  "$FOCUS" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$AUDIT" \
  "$EVENTS" \
  "$LOCUS_CLUSTERS" \
  "$FOCUS" \
  "$QC" \
  "$EXPECTED_INPUT_ROWS" \
  "$EXPECTED_EVENTS"

echo
echo "===== EVENT TRIAGE QC ====="
column -ts $'\t' "$QC"

echo
echo "===== FOCUS EVENTS ====="
column -ts $'\t' "$FOCUS"

echo
echo "===== RECURRENT LOCUS CLUSTERS ====="
awk -F '\t' '
    NR == 1 || $8 >= 2
' "$LOCUS_CLUSTERS" | column -ts $'\t'

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'
    for path in \
      "$EVENTS" \
      "$LOCUS_CLUSTERS" \
      "$FOCUS" \
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
