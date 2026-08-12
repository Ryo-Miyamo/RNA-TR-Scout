#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

TREXDIR="$CATALOG_ROOT/trexplorer_v2"
PILOTDIR="$TREXDIR/rnatr_pilot_v03"
MASTERDIR="$TREXDIR/rnatr_master"
STRDIR="$CATALOG_ROOT/strchive/current/finalization/v2"

REGIONS_ALL="$MASTERDIR/TRExplorer_v2.rnatr_analysis_regions.tsv.gz"
BASE_BED="$TREXDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"
FAI="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa.fai"
DISEASE_REGIONS_IN="$STRDIR/STRchive_disease_regions.tsv"

OUTDIR="$PILOTDIR/final"
WORKDIR="$PROJECT_ROOT/tmp/09f2_resume_finalize_pilot_catalog"

PRIORITY_OUT="$OUTDIR/TRExplorer_v2.rnatr_priority_tiers.final.tsv.gz"
CORE_TSV="$OUTDIR/TRExplorer_v2.rnatr_pilot_core.final.tsv.gz"
CORE_BED="$OUTDIR/TRExplorer_v2.rnatr_pilot_core.final.bed.gz"
FORCED_TSV="$OUTDIR/TRExplorer_v2.rnatr_forced_disease_loci.final.tsv.gz"

ANALYSIS_TSV="$OUTDIR/TRExplorer_v2.rnatr_pilot_analysis_regions.final.tsv.gz"
ANALYSIS_BED="$OUTDIR/TRExplorer_v2.rnatr_pilot_analysis_regions.final.bed.gz"

DISEASE_TSV="$OUTDIR/STRchive_disease_regions.final.tsv.gz"
DISEASE_BED="$OUTDIR/STRchive_disease_regions.final.bed.gz"

TARGET_TSV="$OUTDIR/RNA-TR-Scout_v0.3.mapping_target_regions.tsv.gz"
TARGET_BED="$OUTDIR/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz"

SUMMARY="$OUTDIR/RNA-TR-Scout_v0.3.pilot_catalog.final.summary.tsv"
MANIFEST="$OUTDIR/RNA-TR-Scout_v0.3.pilot_catalog.final.manifest.tsv"
RULES="$OUTDIR/RNA-TR-Scout_v0.3.pilot_catalog.final.rules.md"

PRIORITY_SUMMARY="$WORKDIR/priority.summary.tsv"
ANALYSIS_SUMMARY="$WORKDIR/analysis.summary.tsv"
DISEASE_SUMMARY="$WORKDIR/disease.summary.tsv"
TARGET_SUMMARY="$WORKDIR/targets.summary.tsv"

GENOME="$WORKDIR/common.genome"
REGIONS_RAW="$WORKDIR/regions.with_unique_ids.raw.bed"
REGIONS_SORTED="$WORKDIR/regions.with_unique_ids.sorted.bed"
SELECTED_REGIONS="$WORKDIR/regions.selected.bed"
CORE_WITHOUT_REGION="$WORKDIR/core_without_original_region.bed"
FALLBACK_REGIONS="$WORKDIR/fallback_regions.bed"
FINAL_REGIONS_RAW="$WORKDIR/final_regions.raw.bed"
FINAL_REGIONS_SORTED="$WORKDIR/final_regions.sorted.bed"

DISEASE_BED_RAW="$WORKDIR/disease_regions.raw.bed"
DISEASE_BED_SORTED="$WORKDIR/disease_regions.sorted.bed"

TARGET_RAW="$WORKDIR/mapping_targets.raw.bed"
TARGET_SORTED="$WORKDIR/mapping_targets.sorted.bed"

VALIDATOR="$WORKDIR/validate_successful_step1.py"
REGION_BUILDER="$WORKDIR/build_unique_analysis_regions.py"
DISEASE_BUILDER="$WORKDIR/build_disease_regions.py"
TARGET_BUILDER="$WORKDIR/build_mapping_targets.py"

EXPECTED_LOCI=5599658
EXPECTED_FORCED=100
EXPECTED_CORE=347234
EXPECTED_DISEASE=80

mkdir -p "$OUTDIR" "$WORKDIR"

for path in \
  "$PRIORITY_OUT" \
  "$CORE_TSV" \
  "$CORE_BED" \
  "${CORE_BED}.tbi" \
  "$FORCED_TSV" \
  "$REGIONS_ALL" \
  "$BASE_BED" \
  "${BASE_BED}.tbi" \
  "$FAI" \
  "$DISEASE_REGIONS_IN"
do
    test -s "$path" || {
        echo "ERROR: missing required file: $path" >&2
        exit 1
    }
done

for tool in python bedtools bgzip tabix sha256sum; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

cat > "$VALIDATOR" <<'PY'
import csv
import gzip
import sys
from collections import Counter

(
    priority_path,
    core_path,
    forced_path,
    summary_path,
    expected_loci_text,
    expected_forced_text,
    expected_core_text,
) = sys.argv[1:]

expected_loci = int(expected_loci_text)
expected_forced = int(expected_forced_text)
expected_core = int(expected_core_text)

counts = Counter()
rows = 0
duplicate_ids = 0
seen = set()

with gzip.open(priority_path, "rt", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        locus_id = row["locus_id"]

        if locus_id in seen:
            duplicate_ids += 1
        else:
            seen.add(locus_id)

        counts[f"tier::{row['priority_tier']}"] += 1
        counts[f"activation::{row['activation_mode']}"] += 1
        counts[
            f"annotation_priority::{row['annotation_rna_priority']}"
        ] += 1

        if row["forced_disease"] == "true":
            counts[
                f"forced_source::{row['disease_override_source']}"
            ] += 1
            counts["forced_total"] += 1

        if row["static_pilot_include"] == "true":
            counts["static_core_from_priority"] += 1

        rows += 1

def data_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return max(sum(1 for _ in handle) - 1, 0)

core_rows = data_rows(core_path)
forced_rows = data_rows(forced_path)

status = "PASS"

if (
    rows != expected_loci
    or duplicate_ids
    or counts["forced_total"] != expected_forced
    or forced_rows != expected_forced
    or counts["static_core_from_priority"] != expected_core
    or core_rows != expected_core
):
    status = "REVIEW"

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"expected_loci\t{expected_loci}\n")
    output.write(f"records_written\t{rows}\n")
    output.write(f"duplicate_locus_ids\t{duplicate_ids}\n")
    output.write(f"expected_final_forced\t{expected_forced}\n")
    output.write(f"final_forced_loci\t{forced_rows}\n")
    output.write(f"expected_final_core\t{expected_core}\n")
    output.write(f"final_static_core\t{core_rows}\n")

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Successful Step 1 output validation failed")
PY

cat > "$REGION_BUILDER" <<'PY'
import csv
import gzip
import sys
from collections import Counter

input_path, raw_bed_path = sys.argv[1:]
rows = 0
duplicate_ids = 0
seen = set()
counts = Counter()

with gzip.open(input_path, "rt", encoding="utf-8", newline="") as src, open(
    raw_bed_path,
    "w",
    encoding="utf-8",
    newline="",
) as dst:
    reader = csv.DictReader(src, delimiter="\t")
    writer = csv.writer(dst, delimiter="\t", lineterminator="\n")

    for row in reader:
        chrom = row["chrom"]
        start = row["region_start"]
        end = row["region_end"]
        region_type = row["region_type"]
        representative = row["representative_locus_id"]

        # Coordinate-only IDs collided when two motif models shared a region.
        # Adding representative_locus_id makes the analysis-region ID unique.
        unique_id = (
            f"{region_type}:"
            f"{chrom.removeprefix('chr')}-{start}-{end}:"
            f"{representative}"
        )

        if unique_id in seen:
            duplicate_ids += 1
        else:
            seen.add(unique_id)

        writer.writerow(
            [
                chrom,
                start,
                end,
                unique_id,
                region_type,
                row["region_length_bp"],
                representative,
                row["motifs"],
                row["structure_token"],
            ]
        )

        counts[f"region_type::{region_type}"] += 1
        rows += 1

if duplicate_ids:
    raise RuntimeError(
        f"Unique analysis-region ID collisions remain: {duplicate_ids}"
    )

print(f"[INFO] normalized {rows:,} analysis regions", file=sys.stderr)
PY

cat > "$DISEASE_BUILDER" <<'PY'
import csv
import gzip
import sys
from collections import Counter

input_path, output_tsv, raw_bed, summary_path, expected_text = sys.argv[1:]
expected = int(expected_text)
counts = Counter()
rows = 0

with open(input_path, encoding="utf-8", newline="") as src, gzip.open(
    output_tsv,
    "wt",
    encoding="utf-8",
    newline="",
) as tsv_handle, open(
    raw_bed,
    "w",
    encoding="utf-8",
    newline="",
) as bed_handle:
    reader = csv.DictReader(src, delimiter="\t")
    fields = reader.fieldnames or []

    writer = csv.DictWriter(
        tsv_handle,
        fieldnames=fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for row in reader:
        writer.writerow(row)

        bed_handle.write(
            "\t".join(
                [
                    row["chrom"],
                    row["start"],
                    row["end"],
                    row["disease_region_id"],
                    "STRCHIVE_DISEASE",
                    row["analysis_mode_hint"],
                    row["matched_trexplorer_locus_id"] or ".",
                    row["gene"],
                ]
            )
            + "\n"
        )

        counts[
            f"analysis_mode::{row['analysis_mode_hint']}"
        ] += 1
        counts[
            f"manual_review::{row['manual_review_required']}"
        ] += 1
        rows += 1

status = "PASS" if rows == expected else "REVIEW"

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"expected_disease_regions\t{expected}\n")
    output.write(f"disease_regions_written\t{rows}\n")

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Disease-region validation failed")
PY

cat > "$TARGET_BUILDER" <<'PY'
import csv
import gzip
import sys
from collections import Counter

analysis_path, disease_path, raw_bed, summary_path = sys.argv[1:]
counts = Counter()
rows = 0

with open(raw_bed, "w", encoding="utf-8", newline="") as output:
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")

    with gzip.open(
        analysis_path,
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")

        for row in reader:
            writer.writerow(
                [
                    row["chrom"],
                    row["region_start"],
                    row["region_end"],
                    row["analysis_region_id"],
                    "TRExplorer",
                    row["region_type"],
                    row["analysis_mode"],
                    row["representative_locus_id"],
                ]
            )
            counts["source::TRExplorer"] += 1
            rows += 1

    with gzip.open(
        disease_path,
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")

        for row in reader:
            writer.writerow(
                [
                    row["chrom"],
                    row["start"],
                    row["end"],
                    row["disease_region_id"],
                    "STRchive",
                    "DISEASE_REGION",
                    row["analysis_mode_hint"],
                    row["matched_trexplorer_locus_id"] or ".",
                ]
            )
            counts["source::STRchive"] += 1
            rows += 1

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"mapping_target_regions\t{rows}\n")

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")
PY

echo "===== 1. VALIDATE SUCCESSFUL STEP 1 OUTPUTS ====="

python "$VALIDATOR" \
  "$PRIORITY_OUT" \
  "$CORE_TSV" \
  "$FORCED_TSV" \
  "$PRIORITY_SUMMARY" \
  "$EXPECTED_LOCI" \
  "$EXPECTED_FORCED" \
  "$EXPECTED_CORE"

column -ts $'\t' "$PRIORITY_SUMMARY"

echo
echo "===== 2. BUILD COMMON GENOME ORDER ====="

tabix -l "$BASE_BED" > "$WORKDIR/catalog_contigs.txt"

awk '
    NR == FNR {
        keep[$1] = 1
        next
    }
    ($1 in keep) {
        print $1 "\t" $2
    }
' "$WORKDIR/catalog_contigs.txt" "$FAI" > "$GENOME"

if [[ "$(wc -l < "$GENOME")" != "25" ]]; then
    echo "ERROR: expected 25 common contigs" >&2
    exit 1
fi

echo
echo "===== 3. NORMALIZE ANALYSIS-REGION IDS ====="

python "$REGION_BUILDER" \
  "$REGIONS_ALL" \
  "$REGIONS_RAW"

bedtools sort \
  -g "$GENOME" \
  -i "$REGIONS_RAW" \
  > "$REGIONS_SORTED"

echo
echo "===== 4. SELECT REGIONS FOR FINAL CORE ====="

bedtools intersect \
  -sorted \
  -g "$GENOME" \
  -u \
  -a "$REGIONS_SORTED" \
  -b "$CORE_BED" \
  > "$SELECTED_REGIONS"

bedtools intersect \
  -sorted \
  -g "$GENOME" \
  -v \
  -a "$CORE_BED" \
  -b "$REGIONS_SORTED" \
  > "$CORE_WITHOUT_REGION"

FALLBACK_COUNT="$(wc -l < "$CORE_WITHOUT_REGION")"

echo "Core loci without original analysis region: $FALLBACK_COUNT"

awk -F '\t' '
BEGIN {
    OFS = "\t"
}
{
    chrom = $1
    start = $2
    end = $3
    locus_id = $4
    motif = $6
    region_id = \
      "TR_FALLBACK:" \
      chrom \
      ":" \
      start \
      "-" \
      end \
      ":" \
      locus_id

    print \
      chrom, \
      start, \
      end, \
      region_id, \
      "TR_FALLBACK", \
      end - start, \
      locus_id, \
      motif, \
      locus_id
}
' "$CORE_WITHOUT_REGION" > "$FALLBACK_REGIONS"

cat \
  "$SELECTED_REGIONS" \
  "$FALLBACK_REGIONS" \
  > "$FINAL_REGIONS_RAW"

bedtools sort \
  -g "$GENOME" \
  -i "$FINAL_REGIONS_RAW" \
  > "$FINAL_REGIONS_SORTED"

echo
echo "===== 5. WRITE FINAL ANALYSIS-REGION TABLE ====="

python - \
  "$FINAL_REGIONS_SORTED" \
  "$ANALYSIS_TSV" \
  "$ANALYSIS_SUMMARY" <<'PY'
import csv
import gzip
import sys
from collections import Counter

input_bed, output_tsv, summary_path = sys.argv[1:]
counts = Counter()
seen = set()
rows = 0

header = [
    "analysis_region_id",
    "region_type",
    "chrom",
    "region_start",
    "region_end",
    "region_length_bp",
    "representative_locus_id",
    "motifs",
    "structure_token",
    "analysis_mode",
]

with open(input_bed, encoding="utf-8", newline="") as src, gzip.open(
    output_tsv,
    "wt",
    encoding="utf-8",
    newline="",
) as dst:
    reader = csv.reader(src, delimiter="\t")
    writer = csv.writer(dst, delimiter="\t", lineterminator="\n")
    writer.writerow(header)

    for fields in reader:
        if len(fields) != 9:
            raise RuntimeError(
                f"Unexpected region field count: {len(fields)}"
            )

        (
            chrom,
            start,
            end,
            region_id,
            region_type,
            region_length,
            representative,
            motifs,
            structure_token,
        ) = fields

        if region_id in seen:
            raise RuntimeError(
                f"Duplicate final analysis_region_id: {region_id}"
            )
        seen.add(region_id)

        analysis_mode = (
            "sequence_level"
            if region_type == "VC"
            else "copy_number_first"
        )

        writer.writerow(
            [
                region_id,
                region_type,
                chrom,
                start,
                end,
                region_length,
                representative,
                motifs,
                structure_token,
                analysis_mode,
            ]
        )

        counts[f"region_type::{region_type}"] += 1
        counts[f"analysis_mode::{analysis_mode}"] += 1
        rows += 1

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"final_analysis_regions\t{rows}\n")
    output.write(f"duplicate_analysis_region_ids\t0\n")

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")

    output.write("audit_status\tPASS\n")
PY

awk -F '\t' '
BEGIN {
    OFS = "\t"
}
{
    mode = ($5 == "VC") ? "sequence_level" : "copy_number_first"
    print $1, $2, $3, $4, $5, mode
}
' "$FINAL_REGIONS_SORTED" |
bgzip -c > "$ANALYSIS_BED"

tabix -f -p bed "$ANALYSIS_BED"

column -ts $'\t' "$ANALYSIS_SUMMARY"

echo
echo "===== 6. PRESERVE STRchive DISEASE REGIONS ====="

python "$DISEASE_BUILDER" \
  "$DISEASE_REGIONS_IN" \
  "$DISEASE_TSV" \
  "$DISEASE_BED_RAW" \
  "$DISEASE_SUMMARY" \
  "$EXPECTED_DISEASE"

bedtools sort \
  -g "$GENOME" \
  -i "$DISEASE_BED_RAW" \
  > "$DISEASE_BED_SORTED"

bgzip -c "$DISEASE_BED_SORTED" > "$DISEASE_BED"
tabix -f -p bed "$DISEASE_BED"

column -ts $'\t' "$DISEASE_SUMMARY"

echo
echo "===== 7. BUILD COMBINED MAPPING TARGETS ====="

python "$TARGET_BUILDER" \
  "$ANALYSIS_TSV" \
  "$DISEASE_TSV" \
  "$TARGET_RAW" \
  "$TARGET_SUMMARY"

bedtools sort \
  -g "$GENOME" \
  -i "$TARGET_RAW" \
  > "$TARGET_SORTED"

{
    printf 'chrom\tstart\tend\ttarget_region_id\ttarget_source\tregion_type\tanalysis_mode\trepresentative_locus_id\n'
    cat "$TARGET_SORTED"
} |
bgzip -c > "$TARGET_TSV"

bgzip -c "$TARGET_SORTED" > "$TARGET_BED"
tabix -f -p bed "$TARGET_BED"

column -ts $'\t' "$TARGET_SUMMARY"

echo
echo "===== 8. FINAL SUMMARY ====="

{
    printf 'section\tmetric\tvalue\n'

    awk -F '\t' 'NR > 1 {print "priority\t" $1 "\t" $2}' \
      "$PRIORITY_SUMMARY"

    awk -F '\t' 'NR > 1 {print "analysis_regions\t" $1 "\t" $2}' \
      "$ANALYSIS_SUMMARY"

    awk -F '\t' 'NR > 1 {print "disease_regions\t" $1 "\t" $2}' \
      "$DISEASE_SUMMARY"

    awk -F '\t' 'NR > 1 {print "mapping_targets\t" $1 "\t" $2}' \
      "$TARGET_SUMMARY"

    printf 'analysis_regions\tfallback_regions_created\t%s\n' \
      "$FALLBACK_COUNT"
    printf 'analysis_regions\tcore_loci_uncovered_after_fallback\t0\n'
    printf 'reference\tcommon_contigs\t25\n'
} > "$SUMMARY"

column -ts $'\t' "$SUMMARY"

cat > "$RULES" <<'MD'
# RNA-TR-Scout v0.3 final pilot-catalog rules

## Catalog universe

All 5,599,658 TRExplorer v2 loci remain in the final priority table.

## Static pilot core

The final static core contains 347,234 loci:

1. GENCODE v50 transcript-core loci;
2. all TRExplorer disease-source loci;
3. all STRchive loci mapped to a motif-compatible TRExplorer locus.

## Disease resources

- 100 TRExplorer loci are `T0_FORCED_DISEASE`.
- All 80 STRchive hg38 disease regions are preserved independently.
- MUC1 retains both a matched TRExplorer locus and its broader STRchive
  disease region.

## Dynamic tiers

- `T2_INTRON_EVIDENCE`: activated after alignment evidence.
- `T3_EXPLORATORY_EVIDENCE`: activated after alignment evidence.

RNA non-observation is not evidence against a DNA repeat expansion.

## Analysis-region identifiers

Final analysis-region IDs include the representative locus ID. This avoids
collisions where multiple motif models share identical genomic boundaries.

## Analysis modes

- `TR` and `TR_FALLBACK`: copy-number-first, followed by sequence review.
- `VC`: sequence-level analysis.
- STRchive disease regions retain disease-specific analysis-mode hints.
MD

echo
echo "===== 9. MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PRIORITY_OUT" \
      "$CORE_TSV" \
      "$CORE_BED" \
      "$FORCED_TSV" \
      "$ANALYSIS_TSV" \
      "$ANALYSIS_BED" \
      "$DISEASE_TSV" \
      "$DISEASE_BED" \
      "$TARGET_TSV" \
      "$TARGET_BED"
    do
        if [[ "$path" == *.tsv.gz ]]; then
            rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"
        else
            rows="$(gzip -cd "$path" | awk 'END {print NR}')"
        fi

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
echo "$PRIORITY_OUT"
echo "$CORE_TSV"
echo "$CORE_BED"
echo "$FORCED_TSV"
echo "$ANALYSIS_TSV"
echo "$ANALYSIS_BED"
echo "$DISEASE_TSV"
echo "$DISEASE_BED"
echo "$TARGET_TSV"
echo "$TARGET_BED"
echo "$SUMMARY"
echo "$MANIFEST"
echo "$RULES"
