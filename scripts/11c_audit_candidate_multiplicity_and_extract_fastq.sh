#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
SAMPLE_ID="ENCSR307SHM"
PARAMETER_SET_ID="rnatr_candidate_materialization_v0.3.1"

INPUT_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/ENCFF260PGB.pilot_100k.seed20260803.fastq.gz"
READ_TARGETS="$PROJECT_ROOT/results/11_assignment/$RUN_ID/read_target_candidates.tsv.gz"

OUTDIR="$PROJECT_ROOT/results/11_candidates/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_candidates/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_candidates/$RUN_ID"

DATA_OUTDIR="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1"

MULTIPLICITY="$OUTDIR/candidate_read_multiplicity.tsv.gz"
DISEASE_SUMMARY="$OUTDIR/strchive_candidate_regions.tsv"
ALL_IDS="$OUTDIR/candidate_read_ids.all.tsv.gz"
EXACT_IDS="$OUTDIR/candidate_read_ids.exact.tsv.gz"

ALL_FASTQ="$DATA_OUTDIR/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
EXACT_FASTQ="$DATA_OUTDIR/ENCFF260PGB.pilot_100k.rnatr_candidate_exact.fastq.gz"

QC_SUMMARY="$QCDIR/candidate_materialization_qc.tsv"
PARAMETERS="$OUTDIR/${PARAMETER_SET_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.candidate_materialization_manifest.tsv"

AUDITOR="$WORKDIR/audit_candidates.py"
EXTRACTOR="$WORKDIR/extract_candidate_fastq.py"

EXPECTED_INPUT_READS=100000
EXPECTED_CANDIDATE_READS=79176
EXPECTED_EXACT_READS=56656
EXPECTED_ONLY_PROXIMAL_READS=22520
EXPECTED_READ_TARGET_ROWS=388571

mkdir -p \
  "$OUTDIR" \
  "$QCDIR" \
  "$WORKDIR" \
  "$DATA_OUTDIR"

for path in "$INPUT_FASTQ" "$READ_TARGETS"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

for tool in python sha256sum md5sum; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
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
from collections import Counter, defaultdict

(
    candidates_path,
    multiplicity_path,
    all_ids_path,
    exact_ids_path,
    disease_summary_path,
    qc_path,
    expected_rows_text,
    expected_reads_text,
    expected_exact_text,
    expected_proximal_text,
) = sys.argv[1:]

expected_rows = int(expected_rows_text)
expected_reads = int(expected_reads_text)
expected_exact = int(expected_exact_text)
expected_proximal = int(expected_proximal_text)

per_read = {}
disease = defaultdict(
    lambda: {
        "gene": "",
        "region_type": "",
        "analysis_mode": "",
        "candidate_rows": 0,
        "exact_rows": 0,
        "proximal_rows": 0,
        "reads": set(),
        "exact_reads": set(),
        "proximal_reads": set(),
    }
)
counts = Counter()

with gzip.open(
    candidates_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        counts["read_target_rows"] += 1
        read_id = row["read_id"]
        basis = row["candidate_basis"]
        target_source = row["target_source"]
        region_type = row["region_type"]
        best_class = row["best_alignment_class"]
        rank = int(row["assignment_rank"])
        candidate_count = int(row["read_candidate_target_count"])
        overlap = int(row["target_overlap_bp"])
        distance = int(row["target_distance_bp"])
        mapq = int(row["best_mapq"])

        record = per_read.get(read_id)

        if record is None:
            record = {
                "read_id": read_id,
                "candidate_target_count": candidate_count,
                "exact_candidate_count": 0,
                "proximal_candidate_count": 0,
                "tr_candidate_count": 0,
                "vc_candidate_count": 0,
                "fallback_candidate_count": 0,
                "disease_candidate_count": 0,
                "primary_supported_candidate_count": 0,
                "supplementary_supported_candidate_count": 0,
                "secondary_supported_candidate_count": 0,
                "rank1_basis": "",
                "rank1_target_region_id": "",
                "rank1_target_source": "",
                "rank1_region_type": "",
                "rank1_best_alignment_class": "",
                "rank1_mapq": 0,
                "rank1_overlap_bp": 0,
                "rank1_distance_bp": 0,
            }
            per_read[read_id] = record
        elif record["candidate_target_count"] != candidate_count:
            raise RuntimeError(
                f"Inconsistent candidate count for read {read_id}"
            )

        if basis == "exact_overlap":
            record["exact_candidate_count"] += 1
        elif basis == "proximal_within_padding":
            record["proximal_candidate_count"] += 1
        else:
            raise RuntimeError(f"Unexpected candidate basis: {basis}")

        if region_type == "TR":
            record["tr_candidate_count"] += 1
        elif region_type == "VC":
            record["vc_candidate_count"] += 1
        elif region_type == "TR_FALLBACK":
            record["fallback_candidate_count"] += 1
        elif region_type == "DISEASE_REGION":
            record["disease_candidate_count"] += 1

        if row["primary_support"] == "true":
            record["primary_supported_candidate_count"] += 1
        if row["supplementary_support"] == "true":
            record["supplementary_supported_candidate_count"] += 1
        if row["secondary_support"] == "true":
            record["secondary_supported_candidate_count"] += 1

        if rank == 1:
            record["rank1_basis"] = basis
            record["rank1_target_region_id"] = row["target_region_id"]
            record["rank1_target_source"] = target_source
            record["rank1_region_type"] = region_type
            record["rank1_best_alignment_class"] = best_class
            record["rank1_mapq"] = mapq
            record["rank1_overlap_bp"] = overlap
            record["rank1_distance_bp"] = distance

        if target_source == "STRchive":
            disease_record = disease[row["target_region_id"]]
            disease_record["region_type"] = region_type
            disease_record["analysis_mode"] = row["analysis_mode"]
            disease_record["candidate_rows"] += 1
            disease_record["reads"].add(read_id)

            if basis == "exact_overlap":
                disease_record["exact_rows"] += 1
                disease_record["exact_reads"].add(read_id)
            else:
                disease_record["proximal_rows"] += 1
                disease_record["proximal_reads"].add(read_id)

candidate_counts = [
    record["candidate_target_count"]
    for record in per_read.values()
]
exact_reads = {
    read_id
    for read_id, record in per_read.items()
    if record["exact_candidate_count"] > 0
}
only_proximal_reads = set(per_read) - exact_reads

def quantile(values, probability):
    ordered = sorted(values)

    if not ordered:
        return 0.0

    if len(ordered) == 1:
        return float(ordered[0])

    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return float(ordered[lower])

    fraction = position - lower
    return (
        ordered[lower] * (1.0 - fraction)
        + ordered[upper] * fraction
    )

multiplicity_header = [
    "read_id",
    "candidate_target_count",
    "exact_candidate_count",
    "proximal_candidate_count",
    "tr_candidate_count",
    "vc_candidate_count",
    "fallback_candidate_count",
    "disease_candidate_count",
    "primary_supported_candidate_count",
    "supplementary_supported_candidate_count",
    "secondary_supported_candidate_count",
    "rank1_basis",
    "rank1_target_region_id",
    "rank1_target_source",
    "rank1_region_type",
    "rank1_best_alignment_class",
    "rank1_mapq",
    "rank1_overlap_bp",
    "rank1_distance_bp",
]

with gzip.open(
    multiplicity_path,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=multiplicity_header,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for read_id in sorted(per_read):
        writer.writerow(per_read[read_id])

with gzip.open(
    all_ids_path,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    output.write("read_id\n")
    for read_id in sorted(per_read):
        output.write(f"{read_id}\n")

with gzip.open(
    exact_ids_path,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    output.write("read_id\n")
    for read_id in sorted(exact_reads):
        output.write(f"{read_id}\n")

disease_header = [
    "strchive_region_id",
    "analysis_mode",
    "candidate_rows",
    "candidate_reads",
    "exact_rows",
    "exact_reads",
    "proximal_rows",
    "proximal_reads",
]

with open(
    disease_summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=disease_header,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for region_id in sorted(disease):
        record = disease[region_id]
        writer.writerow(
            {
                "strchive_region_id": region_id,
                "analysis_mode": record["analysis_mode"],
                "candidate_rows": record["candidate_rows"],
                "candidate_reads": len(record["reads"]),
                "exact_rows": record["exact_rows"],
                "exact_reads": len(record["exact_reads"]),
                "proximal_rows": record["proximal_rows"],
                "proximal_reads": len(record["proximal_reads"]),
            }
        )

status = "PASS"

if (
    counts["read_target_rows"] != expected_rows
    or len(per_read) != expected_reads
    or len(exact_reads) != expected_exact
    or len(only_proximal_reads) != expected_proximal
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(
        f"expected_read_target_rows\t{expected_rows}\n"
    )
    output.write(
        f"observed_read_target_rows\t"
        f"{counts['read_target_rows']}\n"
    )
    output.write(
        f"candidate_reads\t{len(per_read)}\n"
    )
    output.write(
        f"candidate_reads_with_any_exact\t{len(exact_reads)}\n"
    )
    output.write(
        f"candidate_reads_only_proximal\t"
        f"{len(only_proximal_reads)}\n"
    )
    output.write(
        f"mean_candidates_per_candidate_read\t"
        f"{statistics.mean(candidate_counts):.6f}\n"
    )

    for label, probability in [
        ("min", 0.0),
        ("p05", 0.05),
        ("p25", 0.25),
        ("median", 0.5),
        ("p75", 0.75),
        ("p95", 0.95),
        ("p99", 0.99),
        ("max", 1.0),
    ]:
        output.write(
            f"candidate_count::{label}\t"
            f"{quantile(candidate_counts, probability):.6f}\n"
        )

    bins = [
        ("1", lambda value: value == 1),
        ("2", lambda value: value == 2),
        ("3_to_5", lambda value: 3 <= value <= 5),
        ("6_to_10", lambda value: 6 <= value <= 10),
        ("11_to_20", lambda value: 11 <= value <= 20),
        ("21_to_50", lambda value: 21 <= value <= 50),
        ("gt_50", lambda value: value > 50),
    ]

    for label, predicate in bins:
        count = sum(predicate(value) for value in candidate_counts)
        percent = 100.0 * count / len(candidate_counts)
        output.write(
            f"candidate_multiplicity_bin::{label}\t{count}\n"
        )
        output.write(
            f"candidate_multiplicity_bin_percent::{label}\t"
            f"{percent:.6f}\n"
        )

    rank1_exact = sum(
        record["rank1_basis"] == "exact_overlap"
        for record in per_read.values()
    )
    rank1_primary = sum(
        record["rank1_best_alignment_class"] == "primary"
        for record in per_read.values()
    )
    disease_reads = sum(
        record["disease_candidate_count"] > 0
        for record in per_read.values()
    )

    output.write(f"rank1_exact_reads\t{rank1_exact}\n")
    output.write(f"rank1_primary_reads\t{rank1_primary}\n")
    output.write(f"reads_with_strchive_candidate\t{disease_reads}\n")
    output.write(
        f"strchive_regions_observed\t{len(disease)}\n"
    )
    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Candidate multiplicity audit failed")
PY

cat > "$EXTRACTOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys

import pysam

(
    input_fastq,
    all_ids_path,
    exact_ids_path,
    all_output,
    exact_output,
    qc_output,
    expected_input_text,
    expected_all_text,
    expected_exact_text,
) = sys.argv[1:]

expected_input = int(expected_input_text)
expected_all = int(expected_all_text)
expected_exact = int(expected_exact_text)

def load_ids(path):
    values = set()

    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            values.add(row["read_id"])

    return values

all_ids = load_ids(all_ids_path)
exact_ids = load_ids(exact_ids_path)

if not exact_ids.issubset(all_ids):
    raise RuntimeError("Exact candidate IDs are not a subset of all IDs")

input_count = 0
all_count = 0
exact_count = 0
found_all = set()
found_exact = set()

with pysam.FastxFile(input_fastq) as source, gzip.open(
    all_output,
    "wt",
    encoding="utf-8",
) as all_handle, gzip.open(
    exact_output,
    "wt",
    encoding="utf-8",
) as exact_handle:
    for entry in source:
        input_count += 1
        read_id = entry.name

        header = f"@{entry.name}"
        if entry.comment:
            header += f" {entry.comment}"

        fastq_record = (
            f"{header}\n"
            f"{entry.sequence}\n"
            f"+\n"
            f"{entry.quality}\n"
        )

        if read_id in all_ids:
            all_handle.write(fastq_record)
            all_count += 1
            found_all.add(read_id)

        if read_id in exact_ids:
            exact_handle.write(fastq_record)
            exact_count += 1
            found_exact.add(read_id)

missing_all = all_ids - found_all
missing_exact = exact_ids - found_exact

status = "PASS"

if (
    input_count != expected_input
    or all_count != expected_all
    or exact_count != expected_exact
    or missing_all
    or missing_exact
):
    status = "REVIEW"

with open(qc_output, "a", encoding="utf-8") as output:
    output.write(f"input_fastq_reads\t{input_count}\n")
    output.write(f"candidate_all_fastq_reads\t{all_count}\n")
    output.write(f"candidate_exact_fastq_reads\t{exact_count}\n")
    output.write(f"candidate_all_missing_ids\t{len(missing_all)}\n")
    output.write(
        f"candidate_exact_missing_ids\t{len(missing_exact)}\n"
    )
    output.write(f"fastq_extraction_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Candidate FASTQ extraction failed")
PY

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
parameter_set_id	$PARAMETER_SET_ID	Candidate materialization parameter set
candidate_all_definition	any_exact_or_proximal	Any read with at least one target candidate
candidate_exact_definition	any_exact_overlap	Any read with at least one exact target overlap
proximal_definition	within_500_bp_of_nonsplice_alignment_block	Recall-oriented candidates
input_fastq_reads	$EXPECTED_INPUT_READS	Fixed-seed pilot input
candidate_fastq_preserves_quality	true	FASTQ sequence and quality retained
candidate_fastq_preserves_comment	true	FASTQ comment retained when present
candidate_status	not_final_call	These reads are not repeat-expansion calls
EOF

echo "===== 1. CANDIDATE MULTIPLICITY AUDIT ====="

rm -f \
  "$MULTIPLICITY" \
  "$DISEASE_SUMMARY" \
  "$ALL_IDS" \
  "$EXACT_IDS" \
  "$ALL_FASTQ" \
  "$EXACT_FASTQ" \
  "$QC_SUMMARY" \
  "$MANIFEST"

python "$AUDITOR" \
  "$READ_TARGETS" \
  "$MULTIPLICITY" \
  "$ALL_IDS" \
  "$EXACT_IDS" \
  "$DISEASE_SUMMARY" \
  "$QC_SUMMARY" \
  "$EXPECTED_READ_TARGET_ROWS" \
  "$EXPECTED_CANDIDATE_READS" \
  "$EXPECTED_EXACT_READS" \
  "$EXPECTED_ONLY_PROXIMAL_READS"

column -ts $'\t' "$QC_SUMMARY"

echo
echo "===== 2. EXTRACT RAW FASTQ CANDIDATES ====="

python "$EXTRACTOR" \
  "$INPUT_FASTQ" \
  "$ALL_IDS" \
  "$EXACT_IDS" \
  "$ALL_FASTQ" \
  "$EXACT_FASTQ" \
  "$QC_SUMMARY" \
  "$EXPECTED_INPUT_READS" \
  "$EXPECTED_CANDIDATE_READS" \
  "$EXPECTED_EXACT_READS"

gzip -t "$ALL_FASTQ"
gzip -t "$EXACT_FASTQ"

echo "Candidate FASTQ gzip integrity: PASS"

echo
echo "===== FINAL QC ====="
column -ts $'\t' "$QC_SUMMARY"

echo
echo "===== STRchive CANDIDATE REGIONS ====="
column -ts $'\t' "$DISEASE_SUMMARY"

echo
echo "===== 3. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$MULTIPLICITY" \
      "$ALL_IDS" \
      "$EXACT_IDS"
    do
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in "$ALL_FASTQ" "$EXACT_FASTQ"; do
        rows="$(gzip -cd "$path" | awk 'END {print NR/4}')"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in \
      "$DISEASE_SUMMARY" \
      "$QC_SUMMARY" \
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

column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$MULTIPLICITY"
echo "$DISEASE_SUMMARY"
echo "$ALL_FASTQ"
echo "$EXACT_FASTQ"
echo "$QC_SUMMARY"
echo "$MANIFEST"
