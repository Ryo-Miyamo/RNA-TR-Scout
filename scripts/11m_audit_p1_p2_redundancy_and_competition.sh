#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

P1="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID/v0.3.3/simple_periodic_evidence.calibrated.v0.3.3.tsv.gz"
P2="$PROJECT_ROOT/results/11_p2_periodic/$RUN_ID/p2_alternate_exact_simple_periodic_evidence.tsv.gz"

OUTDIR="$PROJECT_ROOT/results/11_p1_p2_reconciliation/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p1_p2_reconciliation/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p1_p2_reconciliation/$RUN_ID"

GROUPS="$OUTDIR/p1_p2_exact_span_equivalence_groups.tsv.gz"
READS="$OUTDIR/p1_p2_read_competition.tsv.gz"
EXTREME="$OUTDIR/p2_extreme_nonexact_tracts.top500.tsv"
MULTIMOTIF="$OUTDIR/exact_span_intervals_with_multiple_motifs.tsv"
QC="$QCDIR/p1_p2_reconciliation_qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p1_p2_reconciliation_manifest.tsv"

AUDITOR="$WORKDIR/audit_p1_p2_reconciliation.py"

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
    groups_path,
    reads_path,
    extreme_path,
    multimotif_path,
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


def parse_rows(path, cohort):
    rows = []

    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")

        for row in reader:
            row["_cohort"] = cohort
            rows.append(row)

    return rows


p1_rows = parse_rows(p1_path, "P0_P1")
p2_rows = parse_rows(p2_path, "P2")

all_rows = p1_rows + p2_rows
counts = Counter()

for row in p1_rows:
    counts[f"p1_evidence::{row['evidence_class']}"] += 1

for row in p2_rows:
    counts[f"p2_evidence::{row['evidence_class']}"] += 1
    counts[
        f"p2_assignment_confidence::{row.get('assignment_confidence_label', '.')}"
    ] += 1

# ---------------------------------------------------------------------
# Exact-SPAN equivalence groups:
# Same raw read, same raw-read interval, and same canonical motif.
# These rows represent the same observed sequence evidence even when
# multiple catalog targets claim it.
# ---------------------------------------------------------------------

exact_groups = defaultdict(list)
interval_groups = defaultdict(list)

for row in all_rows:
    if row["evidence_class"] != "SPAN":
        continue

    start = int(row["tract_read_start"])
    end = int(row["tract_read_end"])
    motif = row["canonical_motif"]

    exact_key = (
        row["read_id"],
        start,
        end,
        motif,
    )
    interval_key = (
        row["read_id"],
        start,
        end,
    )

    exact_groups[exact_key].append(row)
    interval_groups[interval_key].append(row)

group_columns = [
    "equivalence_group_id",
    "read_id",
    "tract_read_start",
    "tract_read_end",
    "tract_read_bp",
    "canonical_motif",
    "row_count",
    "p1_row_count",
    "p2_row_count",
    "target_count",
    "target_sources",
    "target_region_ids",
    "representative_locus_ids",
    "assignment_ranks",
    "sequence_statuses",
    "purity_min",
    "purity_max",
    "best_mapq_max",
    "group_class",
]

group_rows = []
duplicate_group_sizes = []
shared_groups = 0
p1_only_groups = 0
p2_only_groups = 0
rows_in_duplicate_groups = 0

for group_index, (key, rows) in enumerate(
    sorted(exact_groups.items()),
    start=1,
):
    read_id, start, end, motif = key
    p1_count = sum(row["_cohort"] == "P0_P1" for row in rows)
    p2_count = sum(row["_cohort"] == "P2" for row in rows)

    if p1_count and p2_count:
        group_class = "P1_P2_SHARED_SEQUENCE_EVIDENCE"
        shared_groups += 1
    elif p1_count:
        group_class = "P1_ONLY_SEQUENCE_EVIDENCE"
        p1_only_groups += 1
    else:
        group_class = "P2_ONLY_SEQUENCE_EVIDENCE"
        p2_only_groups += 1

    if len(rows) > 1:
        duplicate_group_sizes.append(len(rows))
        rows_in_duplicate_groups += len(rows)

    target_pairs = {
        (row["target_source"], row["target_region_id"])
        for row in rows
    }

    sequence_statuses = sorted(
        {
            row.get(
                "exact_span_sequence_status",
                row.get("span_sequence_status", "."),
            )
            for row in rows
        }
    )

    group_rows.append(
        {
            "equivalence_group_id": (
                f"EXACTSPAN_{group_index:09d}"
            ),
            "read_id": read_id,
            "tract_read_start": start,
            "tract_read_end": end,
            "tract_read_bp": end - start,
            "canonical_motif": motif,
            "row_count": len(rows),
            "p1_row_count": p1_count,
            "p2_row_count": p2_count,
            "target_count": len(target_pairs),
            "target_sources": ";".join(
                sorted({row["target_source"] for row in rows})
            ),
            "target_region_ids": ";".join(
                sorted({row["target_region_id"] for row in rows})
            ),
            "representative_locus_ids": ";".join(
                sorted(
                    {
                        row["representative_locus_id"]
                        for row in rows
                    }
                )
            ),
            "assignment_ranks": ";".join(
                sorted(
                    {row["assignment_rank"] for row in rows},
                    key=lambda value: int(value),
                )
            ),
            "sequence_statuses": ";".join(sequence_statuses),
            "purity_min": (
                f"{min(float(row['purity']) for row in rows):.6f}"
            ),
            "purity_max": (
                f"{max(float(row['purity']) for row in rows):.6f}"
            ),
            "best_mapq_max": max(
                int(row["best_mapq"]) for row in rows
            ),
            "group_class": group_class,
        }
    )

with gzip.open(
    groups_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=group_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(group_rows)

# ---------------------------------------------------------------------
# Same read interval but different motif hypotheses.
# ---------------------------------------------------------------------

multimotif_columns = [
    "read_id",
    "tract_read_start",
    "tract_read_end",
    "tract_read_bp",
    "motif_count",
    "canonical_motifs",
    "row_count",
    "p1_row_count",
    "p2_row_count",
    "target_region_ids",
]

multimotif_rows = []

for key, rows in sorted(interval_groups.items()):
    motifs = sorted({row["canonical_motif"] for row in rows})

    if len(motifs) <= 1:
        continue

    read_id, start, end = key

    multimotif_rows.append(
        {
            "read_id": read_id,
            "tract_read_start": start,
            "tract_read_end": end,
            "tract_read_bp": end - start,
            "motif_count": len(motifs),
            "canonical_motifs": ";".join(motifs),
            "row_count": len(rows),
            "p1_row_count": sum(
                row["_cohort"] == "P0_P1" for row in rows
            ),
            "p2_row_count": sum(
                row["_cohort"] == "P2" for row in rows
            ),
            "target_region_ids": ";".join(
                sorted({row["target_region_id"] for row in rows})
            ),
        }
    )

with open(
    multimotif_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=multimotif_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(multimotif_rows)

# ---------------------------------------------------------------------
# Read-level competition.
# ---------------------------------------------------------------------

per_read = defaultdict(
    lambda: {
        "p1_rows": [],
        "p2_rows": [],
        "p1_span": [],
        "p2_span": [],
        "exact_group_ids": set(),
    }
)

group_id_by_key = {
    (
        row["read_id"],
        int(row["tract_read_start"]),
        int(row["tract_read_end"]),
        row["canonical_motif"],
    ): row["equivalence_group_id"]
    for row in group_rows
}

for row in all_rows:
    record = per_read[row["read_id"]]

    if row["_cohort"] == "P0_P1":
        record["p1_rows"].append(row)
    else:
        record["p2_rows"].append(row)

    if row["evidence_class"] == "SPAN":
        if row["_cohort"] == "P0_P1":
            record["p1_span"].append(row)
        else:
            record["p2_span"].append(row)

        key = (
            row["read_id"],
            int(row["tract_read_start"]),
            int(row["tract_read_end"]),
            row["canonical_motif"],
        )
        record["exact_group_ids"].add(group_id_by_key[key])

read_columns = [
    "read_id",
    "p1_row_count",
    "p2_row_count",
    "total_row_count",
    "p1_span_count",
    "p2_span_count",
    "exact_span_equivalence_group_count",
    "has_p1_p2_shared_exact_sequence_group",
    "p2_exact_rows_redundant_with_p1",
    "p2_exact_rows_not_redundant_with_p1",
    "p1_target_region_ids",
    "p2_target_region_ids",
    "read_competition_class",
]

read_rows = []
reads_with_both = 0
reads_with_shared_exact = 0

for read_id, record in sorted(per_read.items()):
    p1_exact_keys = {
        (
            int(row["tract_read_start"]),
            int(row["tract_read_end"]),
            row["canonical_motif"],
        )
        for row in record["p1_span"]
    }
    p2_exact_keys = [
        (
            int(row["tract_read_start"]),
            int(row["tract_read_end"]),
            row["canonical_motif"],
        )
        for row in record["p2_span"]
    ]

    redundant_p2 = sum(
        key in p1_exact_keys for key in p2_exact_keys
    )
    nonredundant_p2 = len(p2_exact_keys) - redundant_p2

    has_p1 = bool(record["p1_rows"])
    has_p2 = bool(record["p2_rows"])
    shared_exact = redundant_p2 > 0

    if has_p1 and has_p2:
        reads_with_both += 1

    if shared_exact:
        reads_with_shared_exact += 1

    if shared_exact and nonredundant_p2:
        competition_class = (
            "P1_SHARED_PLUS_ADDITIONAL_P2_HYPOTHESES"
        )
    elif shared_exact:
        competition_class = "P2_EXACT_FULLY_REDUNDANT_WITH_P1"
    elif has_p1 and record["p2_span"]:
        competition_class = "P1_AND_DISTINCT_P2_EXACT_HYPOTHESES"
    elif has_p1 and has_p2:
        competition_class = "P1_WITH_NONSPAN_P2_HYPOTHESES"
    elif has_p1:
        competition_class = "P1_ONLY"
    else:
        competition_class = "P2_ONLY"

    read_rows.append(
        {
            "read_id": read_id,
            "p1_row_count": len(record["p1_rows"]),
            "p2_row_count": len(record["p2_rows"]),
            "total_row_count": (
                len(record["p1_rows"]) + len(record["p2_rows"])
            ),
            "p1_span_count": len(record["p1_span"]),
            "p2_span_count": len(record["p2_span"]),
            "exact_span_equivalence_group_count": len(
                record["exact_group_ids"]
            ),
            "has_p1_p2_shared_exact_sequence_group": str(
                shared_exact
            ).lower(),
            "p2_exact_rows_redundant_with_p1": redundant_p2,
            "p2_exact_rows_not_redundant_with_p1": (
                nonredundant_p2
            ),
            "p1_target_region_ids": ";".join(
                sorted(
                    {
                        row["target_region_id"]
                        for row in record["p1_rows"]
                    }
                )
            ),
            "p2_target_region_ids": ";".join(
                sorted(
                    {
                        row["target_region_id"]
                        for row in record["p2_rows"]
                    }
                )
            ),
            "read_competition_class": competition_class,
        }
    )
    counts[
        f"read_competition::{competition_class}"
    ] += 1

with gzip.open(
    reads_path,
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

# ---------------------------------------------------------------------
# Extreme P2 non-exact tracts. These are not exact sizes/lower bounds,
# but very long observed tracts need artifact/compound-repeat review.
# ---------------------------------------------------------------------

nonexact_classes = {
    "LEFT_ONLY_INTERNAL",
    "RIGHT_ONLY_INTERNAL",
    "REPEAT_ONLY_UNANCHORED",
    "UNRESOLVED",
}

extreme_rows = [
    row for row in p2_rows
    if row["evidence_class"] in nonexact_classes
]
extreme_rows.sort(
    key=lambda row: (
        int(row["tract_read_bp"]),
        float(row["purity"]),
        int(row["best_mapq"]),
    ),
    reverse=True,
)
extreme_rows = extreme_rows[:500]

extreme_fields = [
    field for field in p2_rows[0].keys()
    if not field.startswith("_")
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
        writer.writerow(
            {
                key: value
                for key, value in row.items()
                if key in extreme_fields
            }
        )

p2_nonexact_lengths = [
    int(row["tract_read_bp"])
    for row in p2_rows
    if row["evidence_class"] in nonexact_classes
]

p2_internal_lengths = [
    int(row["tract_read_bp"])
    for row in p2_rows
    if row["evidence_class"]
    in {"LEFT_ONLY_INTERNAL", "RIGHT_ONLY_INTERNAL"}
]

status = "PASS"

if (
    len(p1_rows) != EXPECTED_P1
    or len(p2_rows) != EXPECTED_P2
    or counts["p1_evidence::SPAN"] != EXPECTED_P1_SPAN
    or counts["p2_evidence::SPAN"] != EXPECTED_P2_SPAN
    or not group_rows
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(f"expected_p1_rows\t{EXPECTED_P1}\n")
    handle.write(f"observed_p1_rows\t{len(p1_rows)}\n")
    handle.write(f"expected_p2_rows\t{EXPECTED_P2}\n")
    handle.write(f"observed_p2_rows\t{len(p2_rows)}\n")
    handle.write(
        f"combined_evidence_rows\t{len(all_rows)}\n"
    )
    handle.write(
        f"p1_span_rows\t{counts['p1_evidence::SPAN']}\n"
    )
    handle.write(
        f"p2_span_rows\t{counts['p2_evidence::SPAN']}\n"
    )
    handle.write(
        f"combined_exact_span_rows\t"
        f"{counts['p1_evidence::SPAN'] + counts['p2_evidence::SPAN']}\n"
    )
    handle.write(
        f"exact_span_equivalence_groups\t{len(group_rows)}\n"
    )
    handle.write(
        f"duplicate_exact_span_groups\t"
        f"{len(duplicate_group_sizes)}\n"
    )
    handle.write(
        f"rows_in_duplicate_exact_span_groups\t"
        f"{rows_in_duplicate_groups}\n"
    )
    handle.write(
        f"p1_p2_shared_exact_groups\t{shared_groups}\n"
    )
    handle.write(
        f"p1_only_exact_groups\t{p1_only_groups}\n"
    )
    handle.write(
        f"p2_only_exact_groups\t{p2_only_groups}\n"
    )
    handle.write(
        f"exact_interval_groups_with_multiple_motifs\t"
        f"{len(multimotif_rows)}\n"
    )
    handle.write(f"combined_unique_reads\t{len(per_read)}\n")
    handle.write(f"reads_with_p1_and_p2\t{reads_with_both}\n")
    handle.write(
        f"reads_with_p1_p2_shared_exact_group\t"
        f"{reads_with_shared_exact}\n"
    )
    handle.write(
        f"p2_internal_tract_ge_1000_bp\t"
        f"{sum(value >= 1000 for value in p2_internal_lengths)}\n"
    )
    handle.write(
        f"p2_internal_tract_ge_5000_bp\t"
        f"{sum(value >= 5000 for value in p2_internal_lengths)}\n"
    )
    handle.write(
        f"p2_internal_tract_max_bp\t"
        f"{max(p2_internal_lengths, default=0)}\n"
    )

    if duplicate_group_sizes:
        handle.write(
            "duplicate_group_size_median\t"
            f"{quantile(duplicate_group_sizes, 0.5):.6f}\n"
        )
        handle.write(
            "duplicate_group_size_p95\t"
            f"{quantile(duplicate_group_sizes, 0.95):.6f}\n"
        )
        handle.write(
            "duplicate_group_size_max\t"
            f"{max(duplicate_group_sizes)}\n"
        )

    if p2_nonexact_lengths:
        for label, probability in [
            ("median", 0.50),
            ("p95", 0.95),
            ("p99", 0.99),
            ("max", 1.00),
        ]:
            handle.write(
                f"p2_nonexact_tract_bp::{label}\t"
                f"{quantile(p2_nonexact_lengths, probability):.6f}\n"
            )

    for key, value in sorted(counts.items()):
        if key.startswith("read_competition::"):
            handle.write(f"{key}\t{value}\n")

    handle.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("P1/P2 reconciliation audit requires review")
PY

echo "===== 1. INPUT INTEGRITY ====="
gzip -t "$P1"
gzip -t "$P2"
echo "Inputs: PASS"

echo
echo "===== 2. AUDIT P1/P2 REDUNDANCY AND COMPETITION ====="

rm -f \
  "$GROUPS" \
  "$READS" \
  "$EXTREME" \
  "$MULTIMOTIF" \
  "$QC" \
  "$MANIFEST"

python "$AUDITOR" \
  "$P1" \
  "$P2" \
  "$GROUPS" \
  "$READS" \
  "$EXTREME" \
  "$MULTIMOTIF" \
  "$QC" \
  "$EXPECTED_P1_ROWS" \
  "$EXPECTED_P2_ROWS" \
  "$EXPECTED_P1_SPAN" \
  "$EXPECTED_P2_SPAN"

gzip -t "$GROUPS"
gzip -t "$READS"

echo
echo "===== RECONCILIATION QC ====="
column -ts $'\t' "$QC"

echo
echo "===== MULTI-MOTIF EXACT INTERVALS (FIRST 30) ====="
column -ts $'\t' "$MULTIMOTIF" | head -n 31

echo
echo "===== EXTREME P2 NON-EXACT TRACTS (FIRST 20) ====="
column -ts $'\t' "$EXTREME" | head -n 21

echo
echo "===== 3. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in "$GROUPS" "$READS"; do
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in "$EXTREME" "$MULTIMOTIF" "$QC"; do
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
echo "$GROUPS"
echo "$READS"
echo "$EXTREME"
echo "$MULTIMOTIF"
echo "$QC"
echo "$MANIFEST"
