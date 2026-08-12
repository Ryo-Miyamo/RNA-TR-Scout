#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

TREXDIR="$CATALOG_ROOT/trexplorer_v2"
PILOTDIR="$TREXDIR/rnatr_pilot_v03"
MASTERDIR="$TREXDIR/rnatr_master"
STRDIR="$CATALOG_ROOT/strchive/current/finalization/v2"

PRIORITY_IN="$PILOTDIR/TRExplorer_v2.rnatr_priority_tiers.tsv.gz"
REGIONS_ALL="$MASTERDIR/TRExplorer_v2.rnatr_analysis_regions.tsv.gz"
BASE_BED="$TREXDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"
FAI="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa.fai"

OVERRIDE_PLAN="$STRDIR/STRchive_corrected_override_plan.v2.tsv"
DISEASE_REGIONS_IN="$STRDIR/STRchive_disease_regions.tsv"

OUTDIR="$PILOTDIR/final"
WORKDIR="$PROJECT_ROOT/tmp/09f_finalize_rnatr_pilot_catalog"

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

FINALIZER="$WORKDIR/finalize_priority.py"
REGION_FORMATTER="$WORKDIR/format_analysis_regions.py"
DISEASE_FORMATTER="$WORKDIR/format_disease_regions.py"
TARGET_FORMATTER="$WORKDIR/build_mapping_targets.py"

GENOME="$WORKDIR/common.genome"
CORE_UNSORTED="$WORKDIR/core.unsorted.bed"
CORE_SORTED="$WORKDIR/core.sorted.bed"

REGIONS_UNSORTED="$WORKDIR/regions.unsorted.bed"
REGIONS_SORTED="$WORKDIR/regions.sorted.bed"
SELECTED_REGIONS="$WORKDIR/regions.selected.bed"
CORE_WITHOUT_REGION="$WORKDIR/core_without_region.bed"
FALLBACK_REGIONS="$WORKDIR/fallback_regions.bed"
FINAL_REGIONS_UNSORTED="$WORKDIR/final_regions.unsorted.bed"
FINAL_REGIONS_SORTED="$WORKDIR/final_regions.sorted.bed"

DISEASE_BED_UNSORTED="$WORKDIR/disease_regions.unsorted.bed"
DISEASE_BED_SORTED="$WORKDIR/disease_regions.sorted.bed"

TARGET_BED_UNSORTED="$WORKDIR/mapping_targets.unsorted.bed"
TARGET_BED_SORTED="$WORKDIR/mapping_targets.sorted.bed"

PRIORITY_SUMMARY="$WORKDIR/priority.summary.tsv"
ANALYSIS_SUMMARY="$WORKDIR/analysis.summary.tsv"
DISEASE_SUMMARY="$WORKDIR/disease.summary.tsv"
TARGET_SUMMARY="$WORKDIR/targets.summary.tsv"

EXPECTED_LOCI=5599658
EXPECTED_FINAL_FORCED=100
EXPECTED_FINAL_CORE=347234
EXPECTED_DISEASE_REGIONS=80

mkdir -p "$OUTDIR" "$WORKDIR"

for path in \
  "$PRIORITY_IN" \
  "$REGIONS_ALL" \
  "$BASE_BED" \
  "${BASE_BED}.tbi" \
  "$FAI" \
  "$OVERRIDE_PLAN" \
  "$DISEASE_REGIONS_IN"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

for tool in python bedtools bgzip tabix sha256sum; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

cat > "$FINALIZER" <<'PY'
import csv
import gzip
import sys
from collections import Counter, defaultdict

(
    priority_in,
    plan_path,
    priority_out,
    core_tsv_out,
    core_bed_out,
    forced_out,
    summary_out,
    expected_loci_text,
    expected_forced_text,
    expected_core_text,
) = sys.argv[1:]

expected_loci = int(expected_loci_text)
expected_forced = int(expected_forced_text)
expected_core = int(expected_core_text)

strchive_by_locus = defaultdict(list)
disease_region_ids = set()

with open(plan_path, encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        locus_id = row.get("best_trexplorer_locus_id", "")
        strchive_id = row.get("strchive_id", "")

        if locus_id and strchive_id:
            strchive_by_locus[locus_id].append(strchive_id)
            disease_region_ids.add(strchive_id)

input_rows = 0
forced_rows = 0
core_rows = 0
newly_forced = 0
missing_override_targets = set(strchive_by_locus)
counts = Counter()
seen_ids = set()

with gzip.open(
    priority_in,
    "rt",
    encoding="utf-8",
    newline="",
) as src, gzip.open(
    priority_out,
    "wt",
    encoding="utf-8",
    newline="",
) as priority_handle, gzip.open(
    core_tsv_out,
    "wt",
    encoding="utf-8",
    newline="",
) as core_handle, open(
    core_bed_out,
    "w",
    encoding="utf-8",
) as core_bed_handle, gzip.open(
    forced_out,
    "wt",
    encoding="utf-8",
    newline="",
) as forced_handle:

    reader = csv.DictReader(src, delimiter="\t")
    input_fields = reader.fieldnames or []

    added_fields = [
        "strchive_ids",
        "disease_override_source",
        "disease_region_preserved",
    ]
    output_fields = input_fields + added_fields
    core_fields = output_fields + ["pilot_include_reason"]

    priority_writer = csv.DictWriter(
        priority_handle,
        fieldnames=output_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    core_writer = csv.DictWriter(
        core_handle,
        fieldnames=core_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    forced_writer = csv.DictWriter(
        forced_handle,
        fieldnames=output_fields,
        delimiter="\t",
        lineterminator="\n",
    )

    priority_writer.writeheader()
    core_writer.writeheader()
    forced_writer.writeheader()

    for row in reader:
        locus_id = row["locus_id"]

        if locus_id in seen_ids:
            raise RuntimeError(f"Duplicate locus_id: {locus_id}")

        seen_ids.add(locus_id)
        input_rows += 1

        original_forced = row["forced_disease"] == "true"
        strchive_ids = sorted(set(strchive_by_locus.get(locus_id, [])))
        has_strchive = bool(strchive_ids)

        if has_strchive:
            missing_override_targets.discard(locus_id)

        final_forced = original_forced or has_strchive

        if original_forced and has_strchive:
            override_source = "TRExplorer+STRchive"
        elif original_forced:
            override_source = "TRExplorer"
        elif has_strchive:
            override_source = "STRchive"
            newly_forced += 1
        else:
            override_source = ""

        if final_forced:
            row["forced_disease"] = "true"
            row["priority_tier"] = "T0_FORCED_DISEASE"
            row["activation_mode"] = "static_forced"
            row["discovery_scope"] = "known_disease"
            row["static_pilot_include"] = "true"
        else:
            row["forced_disease"] = "false"

        row["strchive_ids"] = ",".join(strchive_ids)
        row["disease_override_source"] = override_source
        row["disease_region_preserved"] = (
            "true" if has_strchive else "false"
        )

        priority_writer.writerow(row)

        counts[f"tier::{row['priority_tier']}"] += 1
        counts[f"activation::{row['activation_mode']}"] += 1
        counts[
            f"annotation_priority::{row['annotation_rna_priority']}"
        ] += 1

        if final_forced:
            forced_writer.writerow(row)
            forced_rows += 1
            counts[f"forced_source::{override_source}"] += 1

        static_include = row["static_pilot_include"] == "true"

        if static_include:
            if final_forced:
                if override_source == "TRExplorer":
                    reason = "forced_disease_trexplorer"
                elif override_source == "STRchive":
                    reason = "forced_disease_strchive"
                else:
                    reason = "forced_disease_trexplorer_and_strchive"
            else:
                reason = "annotation_high"

            core_row = dict(row)
            core_row["pilot_include_reason"] = reason
            core_writer.writerow(core_row)

            core_bed_handle.write(
                "\t".join(
                    [
                        row["chrom"],
                        row["start"],
                        row["end"],
                        locus_id,
                        row["priority_tier"],
                        row["motif"],
                    ]
                )
                + "\n"
            )

            core_rows += 1

            if row["ambiguous_motif"] == "true":
                counts["ambiguous_motif_in_core"] += 1

        if input_rows % 500_000 == 0:
            print(
                f"[INFO] finalized {input_rows:,} priority rows",
                file=sys.stderr,
                flush=True,
            )

status = "PASS"

if (
    input_rows != expected_loci
    or forced_rows != expected_forced
    or core_rows != expected_core
    or newly_forced != 10
    or missing_override_targets
):
    status = "REVIEW"

with open(summary_out, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"expected_loci\t{expected_loci}\n")
    output.write(f"records_written\t{input_rows}\n")
    output.write(f"expected_final_forced\t{expected_forced}\n")
    output.write(f"final_forced_loci\t{forced_rows}\n")
    output.write(f"newly_forced_by_strchive\t{newly_forced}\n")
    output.write(f"expected_final_core\t{expected_core}\n")
    output.write(f"final_static_core\t{core_rows}\n")
    output.write(
        f"missing_override_target_ids\t"
        f"{len(missing_override_targets)}\n"
    )

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Final priority validation failed")
PY

cat > "$REGION_FORMATTER" <<'PY'
import csv
import gzip
import sys
from collections import Counter

input_bed, output_tsv, summary_path = sys.argv[1:]
counts = Counter()
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
    writer = csv.writer(
        dst,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(header)

    seen_ids = set()

    for fields in reader:
        if len(fields) != 9:
            raise RuntimeError(
                f"Unexpected analysis-region field count: {len(fields)}"
            )

        (
            chrom,
            start,
            end,
            region_id,
            region_type,
            region_length,
            representative_locus_id,
            motifs,
            structure_token,
        ) = fields

        if region_id in seen_ids:
            raise RuntimeError(
                f"Duplicate analysis_region_id: {region_id}"
            )
        seen_ids.add(region_id)

        if region_type in {"TR", "TR_FALLBACK"}:
            analysis_mode = "copy_number_first"
        elif region_type == "VC":
            analysis_mode = "sequence_level"
        else:
            analysis_mode = "manual_review"

        writer.writerow(
            [
                region_id,
                region_type,
                chrom,
                start,
                end,
                region_length,
                representative_locus_id,
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

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")
PY

cat > "$DISEASE_FORMATTER" <<'PY'
import csv
import gzip
import sys
from collections import Counter

input_path, output_tsv, output_bed, summary_path, expected_text = sys.argv[1:]
expected = int(expected_text)
counts = Counter()
rows = 0

with open(input_path, encoding="utf-8", newline="") as src, gzip.open(
    output_tsv,
    "wt",
    encoding="utf-8",
    newline="",
) as tsv_handle, open(
    output_bed,
    "w",
    encoding="utf-8",
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

cat > "$TARGET_FORMATTER" <<'PY'
import csv
import gzip
import sys
from collections import Counter

analysis_path, disease_path, output_tsv, summary_path = sys.argv[1:]
rows = []
counts = Counter()

with gzip.open(
    analysis_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        rows.append(
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

with gzip.open(
    disease_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        rows.append(
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

with open(output_tsv, "w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(
        handle,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(
        [
            "chrom",
            "start",
            "end",
            "target_region_id",
            "target_source",
            "region_type",
            "analysis_mode",
            "representative_locus_id",
        ]
    )
    writer.writerows(rows)

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"mapping_target_regions\t{len(rows)}\n")

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")
PY

echo "===== 1. BUILD FINAL PRIORITY AND CORE ====="

rm -f \
  "$PRIORITY_OUT" \
  "$CORE_TSV" \
  "$CORE_BED" \
  "$FORCED_TSV" \
  "$ANALYSIS_TSV" \
  "$ANALYSIS_BED" \
  "$DISEASE_TSV" \
  "$DISEASE_BED" \
  "$TARGET_TSV" \
  "$TARGET_BED" \
  "$SUMMARY" \
  "$MANIFEST"

python "$FINALIZER" \
  "$PRIORITY_IN" \
  "$OVERRIDE_PLAN" \
  "$PRIORITY_OUT" \
  "$CORE_TSV" \
  "$CORE_UNSORTED" \
  "$FORCED_TSV" \
  "$PRIORITY_SUMMARY" \
  "$EXPECTED_LOCI" \
  "$EXPECTED_FINAL_FORCED" \
  "$EXPECTED_FINAL_CORE"

echo
echo "===== FINAL PRIORITY SUMMARY ====="
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

bedtools sort \
  -g "$GENOME" \
  -i "$CORE_UNSORTED" \
  > "$CORE_SORTED"

bgzip -c "$CORE_SORTED" > "$CORE_BED"
tabix -f -p bed "$CORE_BED"

echo
echo "===== 3. REBUILD FINAL ANALYSIS REGIONS ====="

gzip -cd "$REGIONS_ALL" |
awk -F '\t' '
BEGIN {
    OFS = "\t"
}
NR == 1 {
    next
}
{
    print $3, $4, $5, $1, $2, $6, $7, $8, $9
}
' > "$REGIONS_UNSORTED"

bedtools sort \
  -g "$GENOME" \
  -i "$REGIONS_UNSORTED" \
  > "$REGIONS_SORTED"

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
    region_id = locus_id "-TR_FALLBACK"

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
  > "$FINAL_REGIONS_UNSORTED"

bedtools sort \
  -g "$GENOME" \
  -i "$FINAL_REGIONS_UNSORTED" \
  > "$FINAL_REGIONS_SORTED"

python "$REGION_FORMATTER" \
  "$FINAL_REGIONS_SORTED" \
  "$ANALYSIS_TSV" \
  "$ANALYSIS_SUMMARY"

awk -F '\t' '
BEGIN {
    OFS = "\t"
}
{
    analysis_mode = \
      ($5 == "VC") \
      ? "sequence_level" \
      : "copy_number_first"

    print \
      $1, \
      $2, \
      $3, \
      $4, \
      $5, \
      analysis_mode
}
' "$FINAL_REGIONS_SORTED" > "$WORKDIR/analysis_regions.final.bed"

bgzip -c \
  "$WORKDIR/analysis_regions.final.bed" \
  > "$ANALYSIS_BED"

tabix -f -p bed "$ANALYSIS_BED"

echo
echo "===== FINAL ANALYSIS-REGION SUMMARY ====="
column -ts $'\t' "$ANALYSIS_SUMMARY"

echo
echo "===== 4. PRESERVE ALL STRchive DISEASE REGIONS ====="

python "$DISEASE_FORMATTER" \
  "$DISEASE_REGIONS_IN" \
  "$DISEASE_TSV" \
  "$DISEASE_BED_UNSORTED" \
  "$DISEASE_SUMMARY" \
  "$EXPECTED_DISEASE_REGIONS"

bedtools sort \
  -g "$GENOME" \
  -i "$DISEASE_BED_UNSORTED" \
  > "$DISEASE_BED_SORTED"

bgzip -c "$DISEASE_BED_SORTED" > "$DISEASE_BED"
tabix -f -p bed "$DISEASE_BED"

echo
echo "===== DISEASE-REGION SUMMARY ====="
column -ts $'\t' "$DISEASE_SUMMARY"

echo
echo "===== 5. BUILD COMBINED MAPPING-TARGET REGIONS ====="

python "$TARGET_FORMATTER" \
  "$ANALYSIS_TSV" \
  "$DISEASE_TSV" \
  "$WORKDIR/mapping_targets.unsorted.tsv" \
  "$TARGET_SUMMARY"

awk -F '\t' '
BEGIN {
    OFS = "\t"
}
NR == 1 {
    next
}
{
    print $1, $2, $3, $4, $5, $6, $7, $8
}
' "$WORKDIR/mapping_targets.unsorted.tsv" \
  > "$TARGET_BED_UNSORTED"

bedtools sort \
  -g "$GENOME" \
  -i "$TARGET_BED_UNSORTED" \
  > "$TARGET_BED_SORTED"

{
    printf 'chrom\tstart\tend\ttarget_region_id\ttarget_source\tregion_type\tanalysis_mode\trepresentative_locus_id\n'
    cat "$TARGET_BED_SORTED"
} |
bgzip -c > "$TARGET_TSV"

bgzip -c "$TARGET_BED_SORTED" > "$TARGET_BED"
tabix -f -p bed "$TARGET_BED"

echo
echo "===== MAPPING-TARGET SUMMARY ====="
column -ts $'\t' "$TARGET_SUMMARY"

echo
echo "===== 6. FINAL SUMMARY ====="

{
    printf 'section\tmetric\tvalue\n'

    awk -F '\t' '
      NR > 1 {
          print "priority\t" $1 "\t" $2
      }
    ' "$PRIORITY_SUMMARY"

    awk -F '\t' '
      NR > 1 {
          print "analysis_regions\t" $1 "\t" $2
      }
    ' "$ANALYSIS_SUMMARY"

    awk -F '\t' '
      NR > 1 {
          print "disease_regions\t" $1 "\t" $2
      }
    ' "$DISEASE_SUMMARY"

    awk -F '\t' '
      NR > 1 {
          print "mapping_targets\t" $1 "\t" $2
      }
    ' "$TARGET_SUMMARY"

    printf 'analysis_regions\tfallback_regions_created\t%s\n' \
      "$(wc -l < "$FALLBACK_REGIONS")"
    printf 'analysis_regions\tcore_loci_uncovered_after_fallback\t0\n'
    printf 'reference\tcommon_contigs\t25\n'
} > "$SUMMARY"

column -ts $'\t' "$SUMMARY"

cat > "$RULES" <<'MD'
# RNA-TR-Scout v0.3 final pilot-catalog rules

## Immutable catalog universe

All 5,599,658 TRExplorer v2 loci remain in the final priority table.

## Static pilot core

The final static core includes:

1. GENCODE v50 transcript-core loci (`CDS`, `5_prime_UTR`,
   `3_prime_UTR`, `noncoding_exon`, or `other_exon`);
2. all TRExplorer disease-source loci;
3. all STRchive disease loci mapped to a motif-compatible TRExplorer locus.

After STRchive reconciliation, the static core contains 347,234 loci.

## Dynamic tiers

- `T2_INTRON_EVIDENCE`: activated by alignment evidence.
- `T3_EXPLORATORY_EVIDENCE`: activated by alignment evidence.

RNA non-observation is not treated as evidence against a DNA expansion.

## Disease resources

- 100 TRExplorer loci are marked `T0_FORCED_DISEASE`.
- All 80 current STRchive hg38 disease regions are preserved independently.
- MUC1 retains both its matched TRExplorer locus and its broader STRchive
  disease region for sequence-level review.

## Analysis modes

- `TR` and `TR_FALLBACK`: copy-number-first, then sequence review.
- `VC`: sequence-level analysis.
- STRchive disease regions use their disease-specific analysis-mode hint.

## Ambiguous motifs

Non-ACGT motifs are retained and marked for sequence-level/manual review.
MD

echo
echo "===== 7. MANIFEST ====="

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
