#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
MASTER="$CATDIR/rnatr_master/TRExplorer_v2.rnatr_locus_master.tsv.gz"
FLAGS="$CATDIR/rnatr_master/gencode_v50/TRExplorer_v2.gencode_v50_locus_flags.canonical.tsv.gz"
REGIONS="$CATDIR/rnatr_master/TRExplorer_v2.rnatr_analysis_regions.tsv.gz"
BASE_BED="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"
FAI="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa.fai"

OUTROOT="$CATDIR/rnatr_pilot_v03"
WORKDIR="$PROJECT_ROOT/tmp/09c_rnatr_priority_tiers"

PRIORITY="$OUTROOT/TRExplorer_v2.rnatr_priority_tiers.tsv.gz"
CORE_TSV="$OUTROOT/TRExplorer_v2.rnatr_pilot_core.tsv.gz"
CORE_BED="$OUTROOT/TRExplorer_v2.rnatr_pilot_core.bed.gz"
DISEASE="$OUTROOT/TRExplorer_v2.rnatr_forced_disease_loci.tsv.gz"

REGION_TSV="$OUTROOT/TRExplorer_v2.rnatr_pilot_analysis_regions.tsv.gz"
REGION_BED="$OUTROOT/TRExplorer_v2.rnatr_pilot_analysis_regions.bed.gz"

SUMMARY="$OUTROOT/TRExplorer_v2.rnatr_pilot_catalog.summary.tsv"
MANIFEST="$OUTROOT/TRExplorer_v2.rnatr_pilot_catalog.manifest.tsv"
DECISIONS="$OUTROOT/RNATR_PILOT_CATALOG_RULES.md"

EXPECTED=5599658

mkdir -p "$OUTROOT" "$WORKDIR"

for path in "$MASTER" "$FLAGS" "$REGIONS" "$BASE_BED" "$FAI"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

for tool in python sort bedtools bgzip tabix; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

EXTRACTOR="$WORKDIR/extract_selected_columns.py"
MERGER="$WORKDIR/merge_priority_tables.py"
REGION_FORMATTER="$WORKDIR/format_selected_regions.py"

MASTER_SELECTED="$WORKDIR/master.selected.tsv"
FLAGS_SELECTED="$WORKDIR/flags.selected.tsv"
MASTER_SORTED="$WORKDIR/master.selected.sorted.tsv"
FLAGS_SORTED="$WORKDIR/flags.selected.sorted.tsv"

CORE_UNSORTED="$WORKDIR/pilot_core.unsorted.bed"
CORE_SORTED="$WORKDIR/pilot_core.sorted.bed"
GENOME="$WORKDIR/trexplorer.genome"

REGIONS_UNSORTED="$WORKDIR/analysis_regions.unsorted.bed"
REGIONS_SORTED="$WORKDIR/analysis_regions.sorted.bed"
SELECTED_REGIONS="$WORKDIR/pilot_analysis_regions.selected.bed"
CORE_WITHOUT_REGION="$WORKDIR/pilot_core_without_analysis_region.bed"
SELECTED_REGIONS_ALL="$WORKDIR/pilot_analysis_regions.with_fallback.bed"

MERGE_SUMMARY="$WORKDIR/priority_merge.summary.tsv"
REGION_SUMMARY="$WORKDIR/region_selection.summary.tsv"

cat > "$EXTRACTOR" <<'PY'
import csv
import gzip
import sys

mode, input_path, output_path = sys.argv[1:]

if mode == "master":
    wanted = [
        "locus_id",
        "chrom",
        "start",
        "end",
        "motif",
        "canonical_motif",
        "motif_length_bp",
        "ambiguous_motif",
        "source",
    ]
elif mode == "flags":
    wanted = [
        "locus_id",
        "primary_region",
        "all_regions",
        "annotation_rna_priority",
    ]
else:
    raise SystemExit(f"Unknown mode: {mode}")

count = 0

with gzip.open(input_path, "rt", encoding="utf-8", newline="") as src:
    reader = csv.DictReader(src, delimiter="\t")

    missing = [name for name in wanted if name not in reader.fieldnames]
    if missing:
        raise RuntimeError(
            f"Missing columns in {input_path}: {missing}"
        )

    with open(output_path, "w", encoding="utf-8", newline="") as dst:
        writer = csv.writer(dst, delimiter="\t", lineterminator="\n")

        for row in reader:
            writer.writerow([row[name] for name in wanted])
            count += 1

            if count % 500_000 == 0:
                print(
                    f"[INFO] extracted {count:,} {mode} rows",
                    file=sys.stderr,
                    flush=True,
                )

print(
    f"[INFO] extracted total {count:,} {mode} rows",
    file=sys.stderr,
)
PY

cat > "$MERGER" <<'PY'
import csv
import gzip
import re
import sys
from collections import Counter

(
    master_path,
    flags_path,
    priority_path,
    core_tsv_path,
    core_bed_path,
    disease_path,
    summary_path,
    expected_text,
) = sys.argv[1:]

expected = int(expected_text)
disease_pattern = re.compile(
    r"KnownDiseaseAssociatedLoci",
    re.IGNORECASE,
)

priority_header = [
    "locus_id",
    "chrom",
    "start",
    "end",
    "motif",
    "canonical_motif",
    "motif_length_bp",
    "ambiguous_motif",
    "source",
    "primary_region",
    "all_regions",
    "annotation_rna_priority",
    "forced_disease",
    "priority_tier",
    "activation_mode",
    "discovery_scope",
    "sizing_mode",
    "static_pilot_include",
]

core_header = priority_header + ["pilot_include_reason"]
disease_header = priority_header

counts = Counter()
rows = 0
mismatched_ids = 0
master_only = 0
flags_only = 0


def next_row(reader):
    try:
        return next(reader)
    except StopIteration:
        return None


with open(master_path, encoding="utf-8", newline="") as m_handle, \
     open(flags_path, encoding="utf-8", newline="") as f_handle, \
     gzip.open(
         priority_path, "wt", encoding="utf-8", newline=""
     ) as p_handle, \
     gzip.open(
         core_tsv_path, "wt", encoding="utf-8", newline=""
     ) as c_handle, \
     open(core_bed_path, "w", encoding="utf-8") as b_handle, \
     gzip.open(
         disease_path, "wt", encoding="utf-8", newline=""
     ) as d_handle:

    m_reader = csv.reader(m_handle, delimiter="\t")
    f_reader = csv.reader(f_handle, delimiter="\t")

    p_writer = csv.writer(
        p_handle, delimiter="\t", lineterminator="\n"
    )
    c_writer = csv.writer(
        c_handle, delimiter="\t", lineterminator="\n"
    )
    d_writer = csv.writer(
        d_handle, delimiter="\t", lineterminator="\n"
    )

    p_writer.writerow(priority_header)
    c_writer.writerow(core_header)
    d_writer.writerow(disease_header)

    master = next_row(m_reader)
    flags = next_row(f_reader)

    while master is not None and flags is not None:
        master_id = master[0]
        flags_id = flags[0]

        if master_id < flags_id:
            master_only += 1
            master = next_row(m_reader)
            continue

        if flags_id < master_id:
            flags_only += 1
            flags = next_row(f_reader)
            continue

        (
            locus_id,
            chrom,
            start,
            end,
            motif,
            canonical_motif,
            motif_length,
            ambiguous_motif,
            source,
        ) = master

        (
            _,
            primary_region,
            all_regions,
            annotation_priority,
        ) = flags

        forced_disease = bool(disease_pattern.search(source))

        if forced_disease:
            tier = "T0_FORCED_DISEASE"
            activation = "static_forced"
            scope = "known_disease"
            include_reason = "forced_disease"
        elif annotation_priority == "high":
            tier = "T1_TRANSCRIPT_CORE"
            activation = "static_annotation"
            scope = "transcript_core"
            include_reason = "annotation_high"
        elif annotation_priority == "medium":
            tier = "T2_INTRON_EVIDENCE"
            activation = "alignment_evidence_required"
            scope = "intron_discovery"
            include_reason = ""
        elif annotation_priority == "low":
            tier = "T3_EXPLORATORY_EVIDENCE"
            activation = "alignment_evidence_required"
            scope = "exploratory_discovery"
            include_reason = ""
        else:
            tier = "T9_UNCLASSIFIED"
            activation = "manual_review"
            scope = "unclassified"
            include_reason = ""

        sizing_mode = (
            "sequence_review_only"
            if ambiguous_motif.lower() == "true"
            else "repeat_sizing_candidate"
        )

        static_include = (
            forced_disease or annotation_priority == "high"
        )

        output_row = [
            locus_id,
            chrom,
            start,
            end,
            motif,
            canonical_motif,
            motif_length,
            ambiguous_motif,
            source,
            primary_region,
            all_regions,
            annotation_priority,
            str(forced_disease).lower(),
            tier,
            activation,
            scope,
            sizing_mode,
            str(static_include).lower(),
        ]

        p_writer.writerow(output_row)
        counts[f"tier::{tier}"] += 1
        counts[f"activation::{activation}"] += 1
        counts[f"priority::{annotation_priority}"] += 1

        if forced_disease:
            d_writer.writerow(output_row)
            counts["forced_disease"] += 1

        if static_include:
            c_writer.writerow(output_row + [include_reason])
            b_handle.write(
                f"{chrom}\t{start}\t{end}\t{locus_id}\t"
                f"{tier}\t{motif}\n"
            )
            counts["static_pilot_core"] += 1

            if ambiguous_motif.lower() == "true":
                counts["ambiguous_motif_in_core"] += 1

        rows += 1

        if rows % 500_000 == 0:
            print(
                f"[INFO] merged {rows:,} priority rows",
                file=sys.stderr,
                flush=True,
            )

        master = next_row(m_reader)
        flags = next_row(f_reader)

    while master is not None:
        master_only += 1
        master = next_row(m_reader)

    while flags is not None:
        flags_only += 1
        flags = next_row(f_reader)

status = "PASS"

if (
    rows != expected
    or master_only
    or flags_only
    or counts["forced_disease"] == 0
    or counts["static_pilot_core"] == 0
):
    status = "REVIEW"

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"expected_loci\t{expected}\n")
    output.write(f"records_merged\t{rows}\n")
    output.write(f"master_only_ids\t{master_only}\n")
    output.write(f"flags_only_ids\t{flags_only}\n")

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Priority-tier merge validation failed")
PY

cat > "$REGION_FORMATTER" <<'PY'
import csv
import gzip
import sys
from collections import Counter

input_path, output_tsv, output_bed, summary_path = sys.argv[1:]
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

with open(input_path, encoding="utf-8", newline="") as src, \
     gzip.open(
         output_tsv, "wt", encoding="utf-8", newline=""
     ) as tsv_out, \
     open(output_bed, "w", encoding="utf-8") as bed_out:

    reader = csv.reader(src, delimiter="\t")
    writer = csv.writer(
        tsv_out, delimiter="\t", lineterminator="\n"
    )
    writer.writerow(header)

    for fields in reader:
        if len(fields) != 9:
            continue

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

        bed_out.write(
            "\t".join(
                [
                    chrom,
                    start,
                    end,
                    region_id,
                    region_type,
                    analysis_mode,
                ]
            )
            + "\n"
        )

        counts[f"region_type::{region_type}"] += 1
        counts[f"analysis_mode::{analysis_mode}"] += 1
        rows += 1

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"selected_analysis_regions\t{rows}\n")

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")
PY

echo "===== 1. EXTRACT JOIN COLUMNS ====="

rm -f \
  "$MASTER_SELECTED" \
  "$FLAGS_SELECTED" \
  "$MASTER_SORTED" \
  "$FLAGS_SORTED" \
  "$PRIORITY" \
  "$CORE_TSV" \
  "$CORE_BED" \
  "$DISEASE" \
  "$REGION_TSV" \
  "$REGION_BED" \
  "$SUMMARY" \
  "$MANIFEST"

python "$EXTRACTOR" master "$MASTER" "$MASTER_SELECTED"
python "$EXTRACTOR" flags "$FLAGS" "$FLAGS_SELECTED"

echo
echo "===== 2. SORT BY LOCUS ID ====="

LC_ALL=C sort \
  --temporary-directory="$WORKDIR" \
  --buffer-size=25% \
  -t $'\t' -k1,1 \
  "$MASTER_SELECTED" \
  > "$MASTER_SORTED"

LC_ALL=C sort \
  --temporary-directory="$WORKDIR" \
  --buffer-size=25% \
  -t $'\t' -k1,1 \
  "$FLAGS_SELECTED" \
  > "$FLAGS_SORTED"

rm -f "$MASTER_SELECTED" "$FLAGS_SELECTED"

echo
echo "===== 3. BUILD PRIORITY TIERS AND STATIC PILOT CORE ====="

python "$MERGER" \
  "$MASTER_SORTED" \
  "$FLAGS_SORTED" \
  "$PRIORITY" \
  "$CORE_TSV" \
  "$CORE_UNSORTED" \
  "$DISEASE" \
  "$MERGE_SUMMARY" \
  "$EXPECTED"

echo
echo "===== PRIORITY SUMMARY ====="
column -ts $'\t' "$MERGE_SUMMARY"

echo
echo "===== 4. BUILD COMMON GENOME ORDER ====="

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

GENOME_CONTIGS="$(wc -l < "$GENOME")"

if [[ "$GENOME_CONTIGS" != "25" ]]; then
    echo "ERROR: expected 25 common contigs" >&2
    exit 1
fi

cat "$GENOME"

echo
echo "===== 5. SORT AND INDEX PILOT CORE ====="

bedtools sort \
  -g "$GENOME" \
  -i "$CORE_UNSORTED" \
  > "$CORE_SORTED"

bgzip -c "$CORE_SORTED" > "$CORE_BED"
tabix -f -p bed "$CORE_BED"

CORE_ROWS="$(wc -l < "$CORE_SORTED")"

echo "Static pilot-core loci: $CORE_ROWS"

echo
echo "===== 6. PREPARE ANALYSIS REGIONS ====="

gzip -cd "$REGIONS" |
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

echo
echo "===== 7. SELECT REGIONS OVERLAPPING PILOT CORE ====="

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

CORE_WITHOUT_COUNT="$(wc -l < "$CORE_WITHOUT_REGION")"

cp "$SELECTED_REGIONS" "$SELECTED_REGIONS_ALL"

if [[ "$CORE_WITHOUT_COUNT" != "0" ]]; then
    echo "[INFO] creating locus-level fallback regions for $CORE_WITHOUT_COUNT core loci"

    awk -F '\t' '
    BEGIN {
        OFS = "\t"
    }
    {
        region_id = $4 "-FALLBACK"
        print $1, $2, $3, region_id, "TR_FALLBACK", ($3 - $2), $4, $6, $4
    }
    ' "$CORE_WITHOUT_REGION" >> "$SELECTED_REGIONS_ALL"
fi

python "$REGION_FORMATTER" \
  "$SELECTED_REGIONS_ALL" \
  "$REGION_TSV" \
  "$WORKDIR/pilot_analysis_regions.unsorted.bed" \
  "$REGION_SUMMARY"

bedtools sort \
  -g "$GENOME" \
  -i "$WORKDIR/pilot_analysis_regions.unsorted.bed" \
  > "$WORKDIR/pilot_analysis_regions.sorted.bed"

bgzip -c \
  "$WORKDIR/pilot_analysis_regions.sorted.bed" \
  > "$REGION_BED"

tabix -f -p bed "$REGION_BED"

echo
echo "===== REGION SUMMARY ====="
column -ts $'\t' "$REGION_SUMMARY"

echo
echo "===== 8. FINAL SUMMARY ====="

{
    cat "$MERGE_SUMMARY"
    tail -n +2 "$REGION_SUMMARY"
    printf 'pilot_core_without_analysis_region\t%s\n' \
      "$CORE_WITHOUT_COUNT"
    printf 'common_contigs\t%s\n' "$GENOME_CONTIGS"
} > "$SUMMARY"

column -ts $'\t' "$SUMMARY"

cat > "$DECISIONS" <<'MD'
# RNA-TR-Scout v0.3 pilot catalog rules

## Immutable universe

All 5,599,658 TRExplorer v2 loci remain in the priority table. No locus is
deleted by RNA annotation.

## Static pilot core

A locus is included before mapping when either:

1. GENCODE v50 annotation priority is `high`
   (`CDS`, `5_prime_UTR`, `3_prime_UTR`, `noncoding_exon`, or `other_exon`), or
2. the TRExplorer source contains `KnownDiseaseAssociatedLoci`.

## Dynamic discovery tiers

- `T2_INTRON_EVIDENCE`: retained in the full universe and activated after
  alignment evidence supports the locus or its flanks.
- `T3_EXPLORATORY_EVIDENCE`: promoter/intergenic loci retained in the full
  universe and activated after alignment evidence supports them.

Absence of RNA evidence must not be interpreted as absence of a DNA repeat
expansion.

## Analysis regions

- `TR`: copy-number-first analysis, followed by sequence review.
- `VC`: sequence-level analysis across the extended variation-cluster region.
- `TR_FALLBACK`: locus-level copy-number-first region used when the recommended
  cluster catalog has no corresponding region (for example, loci on contigs
  omitted from that catalog).

## Ambiguous motifs

Motifs containing non-ACGT symbols remain in the catalog but are marked
`sequence_review_only`.

## Disease overrides

The current static override uses TRExplorer sources containing
`KnownDiseaseAssociatedLoci`. An external STRchive concordance audit will be
added before Step 09 is closed.
MD

echo
echo "===== 9. MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PRIORITY" \
      "$CORE_TSV" \
      "$CORE_BED" \
      "$DISEASE" \
      "$REGION_TSV" \
      "$REGION_BED"
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
echo "===== FIRST 5 PILOT CORE ROWS ====="
gzip -cd "$CORE_TSV" |
awk 'NR <= 6 {print} NR == 6 {exit}' |
column -ts $'\t' || true

echo
echo "===== COMPLETE ====="
echo "$PRIORITY"
echo "$CORE_TSV"
echo "$CORE_BED"
echo "$DISEASE"
echo "$REGION_TSV"
echo "$REGION_BED"
echo "$SUMMARY"
echo "$MANIFEST"
echo "$DECISIONS"
