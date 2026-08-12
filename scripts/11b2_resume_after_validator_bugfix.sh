#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
SCHEMA_DIR="$PROJECT_ROOT/config/evidence_schema/v0.3"
SCHEMA_JSON="$SCHEMA_DIR/schema/rnatr_v03_table_schema.json"

OUTDIR="$PROJECT_ROOT/results/11_assignment/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_assignment/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_assignment/$RUN_ID"
PATCHDIR="$SCHEMA_DIR/patches/validator_v0.3.1"

TARGET_BED="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz"

ALIGNMENT_SEGMENTS="$OUTDIR/alignment_segments.tsv.gz"
ALIGNMENT_TARGETS="$OUTDIR/alignment_target_candidates.tsv.gz"
READ_TARGETS="$OUTDIR/read_target_candidates.tsv.gz"

BLOCKS_PADDED="$WORKDIR/alignment_blocks.padded.bed"
INTERSECTIONS="$WORKDIR/alignment_blocks_vs_targets.tsv"

DISTRIBUTION_QC="$QCDIR/alignment_distribution_qc.tsv"
ASSIGNMENT_QC="$QCDIR/target_assignment_qc.tsv"
PARAMETERS="$OUTDIR/rnatr_target_assignment_v0.3.1.parameters.tsv"
OUTPUT_MANIFEST="$OUTDIR/${RUN_ID}.assignment_output_manifest.tsv"

VALIDATOR_FIXED="$PATCHDIR/rnatr_v03_validate_tsv_validator_v0.3.1.py"
PATCH_RECORD="$PATCHDIR/VALIDATOR_PATCH.tsv"
AGGREGATOR="$WORKDIR/aggregate_target_candidates.resume.py"

TARGET_PADDING_BP="${TARGET_PADDING_BP:-500}"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR" "$PATCHDIR"

for path in \
  "$SCHEMA_JSON" \
  "$TARGET_BED" \
  "${TARGET_BED}.tbi" \
  "$ALIGNMENT_SEGMENTS" \
  "$BLOCKS_PADDED" \
  "$DISTRIBUTION_QC" \
  "$PARAMETERS"
do
    test -s "$path" || {
        echo "ERROR: missing required input: $path" >&2
        exit 1
    }
done

cat > "$VALIDATOR_FIXED" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from pathlib import Path

VALIDATOR_VERSION = "0.3.1"
BOOLEAN_VALUES = {"true", "false"}


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def validate_value(value: str, spec: dict, enums: dict) -> str | None:
    dtype = spec["type"]

    # Bugfix v0.3.1:
    # "." is globally used as the missing token, but it is also an explicit
    # allowed value of the strand enum for unmapped records. An explicit enum
    # value takes precedence over the global missing-token interpretation.
    if dtype == "enum":
        allowed = set(enums[spec["enum"]])
        if value in allowed:
            return None

    if value in {"", "."}:
        if spec["required"]:
            return "required value is missing"
        return None

    if dtype == "integer":
        try:
            int(value)
        except ValueError:
            return f"expected integer, got {value!r}"

    elif dtype == "float":
        try:
            number = float(value)
            if not math.isfinite(number):
                return f"expected finite float, got {value!r}"
        except ValueError:
            return f"expected float, got {value!r}"

    elif dtype == "boolean":
        if value not in BOOLEAN_VALUES:
            return f"expected true/false, got {value!r}"

    elif dtype == "enum":
        allowed = set(enums[spec["enum"]])
        return f"value {value!r} not in enum {spec['enum']}"

    elif dtype == "datetime":
        if "T" not in value:
            return "expected ISO-8601 datetime"

    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--table", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--max-rows", type=int, default=100000)
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))

    if args.table not in schema["tables"]:
        raise SystemExit(f"Unknown table: {args.table}")

    table = schema["tables"][args.table]
    specs = table["columns"]
    expected_header = [column["name"] for column in specs]

    errors = []
    rows_checked = 0

    with open_text(args.input) as handle:
        reader = csv.reader(handle, delimiter="\t")

        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit("Input is empty")

        if header != expected_header:
            errors.append(
                "Header mismatch.\n"
                f"Expected: {expected_header}\n"
                f"Observed: {header}"
            )

        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(specs):
                errors.append(
                    f"line {line_number}: expected {len(specs)} fields, "
                    f"got {len(row)}"
                )
            else:
                for value, spec in zip(row, specs):
                    message = validate_value(
                        value,
                        spec,
                        schema["enums"],
                    )
                    if message:
                        errors.append(
                            f"line {line_number}, {spec['name']}: "
                            f"{message}"
                        )

            rows_checked += 1

            if rows_checked >= args.max_rows or len(errors) >= 100:
                break

    print(f"validator_version={VALIDATOR_VERSION}")
    print(f"table={args.table}")
    print(f"rows_checked={rows_checked}")
    print(f"errors={len(errors)}")

    for error in errors[:100]:
        print(error, file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

chmod +x "$VALIDATOR_FIXED"

cat > "$PATCH_RECORD" <<EOF
field	value
validator_version	0.3.1
schema_version	0.3.0
patched_at	$(date -Is)
bug	global missing token "." incorrectly took precedence over explicit enum value "."
affected_field	alignment_segments.strand
affected_records	unmapped alignment records
schema_change	false
data_change	false
validator_sha256	$(sha256sum "$VALIDATOR_FIXED" | awk '{print $1}')
EOF

cat > "$AGGREGATOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter, defaultdict

(
    intersections_path,
    alignment_output,
    read_output,
    summary_output,
    padding_text,
) = sys.argv[1:]

padding = int(padding_text)
alignment_candidates = {}

with open(
    intersections_path,
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.reader(handle, delimiter="\t")

    for fields in reader:
        if len(fields) != 20:
            raise RuntimeError(
                f"Expected 20 fields from bedtools, got {len(fields)}"
            )

        (
            _chrom,
            _padded_start,
            _padded_end,
            alignment_id,
            block_index,
            block_start,
            block_end,
            read_id,
            alignment_class,
            mapq,
            strand,
            softclip_total,
            target_chrom,
            target_start,
            target_end,
            target_region_id,
            target_source,
            region_type,
            analysis_mode,
            representative_locus_id,
        ) = fields

        block_start_i = int(block_start)
        block_end_i = int(block_end)
        target_start_i = int(target_start)
        target_end_i = int(target_end)

        overlap = max(
            0,
            min(block_end_i, target_end_i)
            - max(block_start_i, target_start_i),
        )

        if overlap > 0:
            distance = 0
        elif block_end_i <= target_start_i:
            distance = target_start_i - block_end_i
        else:
            distance = block_start_i - target_end_i

        if distance > padding:
            continue

        key = (
            alignment_id,
            target_source,
            target_region_id,
        )

        record = alignment_candidates.get(key)

        if record is None:
            record = {
                "read_id": read_id,
                "alignment_id": alignment_id,
                "alignment_class": alignment_class,
                "mapq": int(mapq),
                "strand": strand,
                "softclip_total_bp": int(softclip_total),
                "target_region_id": target_region_id,
                "target_source": target_source,
                "region_type": region_type,
                "analysis_mode": analysis_mode,
                "representative_locus_id": representative_locus_id,
                "target_chrom": target_chrom,
                "target_start": target_start_i,
                "target_end": target_end_i,
                "target_overlap_bp": 0,
                "target_distance_bp": distance,
                "supporting_blocks": set(),
            }
            alignment_candidates[key] = record

        record["target_overlap_bp"] += overlap
        record["target_distance_bp"] = min(
            record["target_distance_bp"],
            distance,
        )
        record["supporting_blocks"].add(int(block_index))

alignment_columns = [
    "read_id",
    "alignment_id",
    "alignment_class",
    "mapq",
    "strand",
    "softclip_total_bp",
    "target_region_id",
    "target_source",
    "region_type",
    "analysis_mode",
    "representative_locus_id",
    "target_chrom",
    "target_start",
    "target_end",
    "target_overlap_bp",
    "target_distance_bp",
    "candidate_basis",
    "supporting_block_count",
]

read_candidates = {}
counts = Counter()
targets_seen = set()
reads_with_exact = set()
reads_with_any = set()

with gzip.open(
    alignment_output,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=alignment_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for record in alignment_candidates.values():
        record["candidate_basis"] = (
            "exact_overlap"
            if record["target_overlap_bp"] > 0
            else "proximal_within_padding"
        )
        record["supporting_block_count"] = len(
            record["supporting_blocks"]
        )

        output_record = {
            key: value
            for key, value in record.items()
            if key != "supporting_blocks"
        }
        writer.writerow(output_record)

        counts["alignment_target_candidates"] += 1
        counts[
            f"alignment_candidate_basis::{record['candidate_basis']}"
        ] += 1
        counts[
            f"alignment_class::{record['alignment_class']}"
        ] += 1
        counts[f"target_source::{record['target_source']}"] += 1
        counts[f"region_type::{record['region_type']}"] += 1

        read_id = record["read_id"]
        reads_with_any.add(read_id)

        if record["target_overlap_bp"] > 0:
            reads_with_exact.add(read_id)

        targets_seen.add(
            (
                record["target_source"],
                record["target_region_id"],
            )
        )

        read_key = (
            read_id,
            record["target_source"],
            record["target_region_id"],
        )
        aggregate = read_candidates.get(read_key)

        if aggregate is None:
            aggregate = {
                "read_id": read_id,
                "target_region_id": record["target_region_id"],
                "target_source": record["target_source"],
                "region_type": record["region_type"],
                "analysis_mode": record["analysis_mode"],
                "representative_locus_id": record[
                    "representative_locus_id"
                ],
                "supporting_alignment_count": 0,
                "primary_support": False,
                "supplementary_support": False,
                "secondary_support": False,
                "best_record": None,
            }
            read_candidates[read_key] = aggregate

        aggregate["supporting_alignment_count"] += 1

        if record["alignment_class"] == "primary":
            aggregate["primary_support"] = True
        elif record["alignment_class"] == "supplementary":
            aggregate["supplementary_support"] = True
        elif record["alignment_class"] == "secondary":
            aggregate["secondary_support"] = True

        class_priority = {
            "primary": 3,
            "supplementary": 2,
            "secondary": 1,
        }.get(record["alignment_class"], 0)

        score = (
            1 if record["target_overlap_bp"] > 0 else 0,
            record["target_overlap_bp"],
            -record["target_distance_bp"],
            class_priority,
            record["mapq"],
            record["softclip_total_bp"],
        )

        best_record = aggregate["best_record"]

        if best_record is None or score > best_record["_score"]:
            selected = dict(record)
            selected["_score"] = score
            aggregate["best_record"] = selected

read_groups = defaultdict(list)

for aggregate in read_candidates.values():
    read_groups[aggregate["read_id"]].append(aggregate)

read_columns = [
    "read_id",
    "target_region_id",
    "target_source",
    "region_type",
    "analysis_mode",
    "representative_locus_id",
    "assignment_rank",
    "read_candidate_target_count",
    "best_alignment_id",
    "best_alignment_class",
    "best_mapq",
    "strand",
    "best_softclip_total_bp",
    "target_overlap_bp",
    "target_distance_bp",
    "candidate_basis",
    "supporting_alignment_count",
    "primary_support",
    "supplementary_support",
    "secondary_support",
]

with gzip.open(
    read_output,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=read_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for read_id, candidates in read_groups.items():
        def rank_key(aggregate):
            record = aggregate["best_record"]
            class_priority = {
                "primary": 3,
                "supplementary": 2,
                "secondary": 1,
            }.get(record["alignment_class"], 0)

            return (
                1 if record["target_overlap_bp"] > 0 else 0,
                record["target_overlap_bp"],
                -record["target_distance_bp"],
                class_priority,
                record["mapq"],
                record["softclip_total_bp"],
            )

        candidates.sort(key=rank_key, reverse=True)
        candidate_count = len(candidates)

        for rank, aggregate in enumerate(candidates, start=1):
            record = aggregate["best_record"]

            writer.writerow(
                {
                    "read_id": read_id,
                    "target_region_id": aggregate[
                        "target_region_id"
                    ],
                    "target_source": aggregate["target_source"],
                    "region_type": aggregate["region_type"],
                    "analysis_mode": aggregate["analysis_mode"],
                    "representative_locus_id": aggregate[
                        "representative_locus_id"
                    ],
                    "assignment_rank": rank,
                    "read_candidate_target_count": candidate_count,
                    "best_alignment_id": record["alignment_id"],
                    "best_alignment_class": record[
                        "alignment_class"
                    ],
                    "best_mapq": record["mapq"],
                    "strand": record["strand"],
                    "best_softclip_total_bp": record[
                        "softclip_total_bp"
                    ],
                    "target_overlap_bp": record[
                        "target_overlap_bp"
                    ],
                    "target_distance_bp": record[
                        "target_distance_bp"
                    ],
                    "candidate_basis": record[
                        "candidate_basis"
                    ],
                    "supporting_alignment_count": aggregate[
                        "supporting_alignment_count"
                    ],
                    "primary_support": str(
                        aggregate["primary_support"]
                    ).lower(),
                    "supplementary_support": str(
                        aggregate["supplementary_support"]
                    ).lower(),
                    "secondary_support": str(
                        aggregate["secondary_support"]
                    ).lower(),
                }
            )
            counts["read_target_candidates"] += 1
            counts[
                f"read_candidate_basis::{record['candidate_basis']}"
            ] += 1

reads_only_proximal = reads_with_any - reads_with_exact

with open(summary_output, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"target_padding_bp\t{padding}\n")
    output.write(
        f"alignment_target_candidates\t"
        f"{counts['alignment_target_candidates']}\n"
    )
    output.write(
        f"read_target_candidates\t"
        f"{counts['read_target_candidates']}\n"
    )
    output.write(f"reads_with_any_candidate\t{len(reads_with_any)}\n")
    output.write(
        f"reads_with_exact_overlap_candidate\t"
        f"{len(reads_with_exact)}\n"
    )
    output.write(
        f"reads_with_only_proximal_candidate\t"
        f"{len(reads_only_proximal)}\n"
    )
    output.write(
        f"unique_target_regions_observed\t{len(targets_seen)}\n"
    )

    for key, value in sorted(counts.items()):
        if key in {
            "alignment_target_candidates",
            "read_target_candidates",
        }:
            continue
        output.write(f"{key}\t{value}\n")

    output.write("audit_status\tPASS\n")
PY

echo "===== 1. VALIDATOR BUGFIX RECORD ====="
column -ts $'\t' "$PATCH_RECORD"

echo
echo "===== 2. VALIDATE EXISTING ALIGNMENT SEGMENTS ====="

python "$VALIDATOR_FIXED" \
  --schema "$SCHEMA_JSON" \
  --table alignment_segments \
  --input "$ALIGNMENT_SEGMENTS" \
  --max-rows 250000

ALIGNMENT_ROWS="$(
    gzip -cd "$ALIGNMENT_SEGMENTS" |
    awk 'END {print NR-1}'
)"
BLOCK_ROWS="$(wc -l < "$BLOCKS_PADDED")"

echo "Alignment rows: $ALIGNMENT_ROWS"
echo "Alignment blocks: $BLOCK_ROWS"

if [[ "$ALIGNMENT_ROWS" != "184820" ]]; then
    echo "ERROR: expected 184820 alignment rows" >&2
    exit 1
fi

if [[ "$BLOCK_ROWS" != "441940" ]]; then
    echo "ERROR: expected 441940 alignment blocks" >&2
    exit 1
fi

echo
echo "===== 3. INTERSECT BLOCKS WITH TARGETS ====="

rm -f \
  "$INTERSECTIONS" \
  "$ALIGNMENT_TARGETS" \
  "$READ_TARGETS" \
  "$ASSIGNMENT_QC" \
  "$OUTPUT_MANIFEST"

bedtools intersect \
  -wa \
  -wb \
  -a "$BLOCKS_PADDED" \
  -b "$TARGET_BED" \
  > "$INTERSECTIONS"

INTERSECTION_ROWS="$(wc -l < "$INTERSECTIONS")"
echo "Raw block-target intersections: $INTERSECTION_ROWS"

echo
echo "===== 4. AGGREGATE TARGET CANDIDATES ====="

python "$AGGREGATOR" \
  "$INTERSECTIONS" \
  "$ALIGNMENT_TARGETS" \
  "$READ_TARGETS" \
  "$ASSIGNMENT_QC" \
  "$TARGET_PADDING_BP"

column -ts $'\t' "$ASSIGNMENT_QC"

echo
echo "===== 5. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$ALIGNMENT_SEGMENTS" \
      "$ALIGNMENT_TARGETS" \
      "$READ_TARGETS"
    do
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in \
      "$DISTRIBUTION_QC" \
      "$ASSIGNMENT_QC" \
      "$PARAMETERS" \
      "$PATCH_RECORD"
    do
        rows="$(awk 'END {print NR-1}' "$path")"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$OUTPUT_MANIFEST"

column -ts $'\t' "$OUTPUT_MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$ALIGNMENT_TARGETS"
echo "$READ_TARGETS"
echo "$ASSIGNMENT_QC"
echo "$OUTPUT_MANIFEST"
