#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

GTF="$PROJECT_ROOT/refs/gencode_v50/gencode.v50.primary_assembly.annotation.gtf"
FAI="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa.fai"
BASE_BED="$CATALOG_ROOT/trexplorer_v2/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"

OUTDIR="$CATALOG_ROOT/trexplorer_v2/rnatr_master/gencode_v50"
WORKDIR="$PROJECT_ROOT/tmp/09b_gencode_v50_annotation"

TRACKDIR="$OUTDIR/tracks"
OVERLAPDIR="$WORKDIR/overlaps"

FLAGS="$OUTDIR/TRExplorer_v2.gencode_v50_locus_flags.tsv.gz"
SUMMARY="$OUTDIR/TRExplorer_v2.gencode_v50_locus_flags.summary.tsv"
TRACK_SUMMARY="$OUTDIR/gencode_v50_tracks.summary.tsv"
MANIFEST="$OUTDIR/gencode_v50_annotation.manifest.tsv"
GENES="$OUTDIR/gencode_v50.genes.bed.gz"

EXPECTED_LOCI=5599658
PROMOTER_UPSTREAM=1000
PROMOTER_DOWNSTREAM=100

mkdir -p "$OUTDIR" "$WORKDIR" "$TRACKDIR" "$OVERLAPDIR"

for path in "$GTF" "$FAI" "$BASE_BED"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

for tool in bedtools bgzip tabix python; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

PARSER="$WORKDIR/build_gencode_tracks.py"
FLAGGER="$WORKDIR/build_locus_flags.py"

cat > "$PARSER" <<'PY'
import re
import sys
from collections import Counter
from pathlib import Path

gtf_path, fai_path, workdir, promoter_up_text, promoter_down_text = sys.argv[1:]
workdir = Path(workdir)
promoter_up = int(promoter_up_text)
promoter_down = int(promoter_down_text)

contig_lengths = {}
with open(fai_path, encoding="utf-8") as handle:
    for line in handle:
        fields = line.rstrip("\n").split("\t")
        contig_lengths[fields[0]] = int(fields[1])

attribute_pattern = re.compile(r'(\S+) "([^"]*)";')

def parse_attributes(text):
    return dict(attribute_pattern.findall(text))

paths = {
    "cds": workdir / "cds.raw.bed",
    "utr_raw": workdir / "utr.raw.tsv",
    "all_exon": workdir / "all_exon.raw.bed",
    "noncoding_exon": workdir / "noncoding_exon.raw.bed",
    "gene_body": workdir / "gene_body.raw.bed",
    "promoter": workdir / "promoter.raw.bed",
    "genes": workdir / "genes.raw.bed",
    "utr5": workdir / "utr5.raw.bed",
    "utr3": workdir / "utr3.raw.bed",
    "utr_unresolved": workdir / "utr_unresolved.raw.bed",
}

handles = {
    key: open(path, "w", encoding="utf-8")
    for key, path in paths.items()
    if key not in {"utr5", "utr3", "utr_unresolved"}
}

cds_bounds = {}
counts = Counter()
data_lines = 0

with open(gtf_path, encoding="utf-8") as gtf:
    for line in gtf:
        if not line or line.startswith("#"):
            continue

        fields = line.rstrip("\n").split("\t")
        if len(fields) != 9:
            counts["malformed_gtf_rows"] += 1
            continue

        chrom, source, feature, start_text, end_text, score, strand, frame, attr_text = fields

        try:
            start0 = int(start_text) - 1
            end = int(end_text)
        except ValueError:
            counts["invalid_coordinate_rows"] += 1
            continue

        if start0 < 0 or end <= start0:
            counts["invalid_coordinate_rows"] += 1
            continue

        attrs = parse_attributes(attr_text)
        gene_id = attrs.get("gene_id", "")
        transcript_id = attrs.get("transcript_id", "")
        gene_type = attrs.get("gene_type", "")
        transcript_type = attrs.get("transcript_type", "")
        gene_name = attrs.get("gene_name", "")

        data_lines += 1
        counts[f"feature::{feature}"] += 1

        if feature == "CDS":
            handles["cds"].write(f"{chrom}\t{start0}\t{end}\n")
            if transcript_id:
                previous = cds_bounds.get(transcript_id)
                if previous is None:
                    cds_bounds[transcript_id] = [chrom, start0, end, strand]
                else:
                    previous[1] = min(previous[1], start0)
                    previous[2] = max(previous[2], end)

        elif feature == "UTR":
            handles["utr_raw"].write(
                f"{transcript_id}\t{chrom}\t{start0}\t{end}\t{strand}\n"
            )

        elif feature == "exon":
            handles["all_exon"].write(f"{chrom}\t{start0}\t{end}\n")
            if transcript_type != "protein_coding":
                handles["noncoding_exon"].write(
                    f"{chrom}\t{start0}\t{end}\n"
                )

        elif feature == "gene":
            handles["gene_body"].write(f"{chrom}\t{start0}\t{end}\n")
            gene_id_noversion = gene_id.split(".", 1)[0] if gene_id else ""
            handles["genes"].write(
                "\t".join(
                    [
                        chrom,
                        str(start0),
                        str(end),
                        gene_id or ".",
                        gene_id_noversion or ".",
                        gene_name or ".",
                        gene_type or ".",
                        strand,
                    ]
                )
                + "\n"
            )

            contig_length = contig_lengths.get(chrom)
            if contig_length is None:
                counts["gene_on_unknown_contig"] += 1
                continue

            if strand == "+":
                tss = start0
                promoter_start = max(0, tss - promoter_up)
                promoter_end = min(contig_length, tss + promoter_down)
            elif strand == "-":
                tss = end
                promoter_start = max(0, tss - promoter_down)
                promoter_end = min(contig_length, tss + promoter_up)
            else:
                counts["gene_unknown_strand"] += 1
                continue

            if promoter_end > promoter_start:
                handles["promoter"].write(
                    f"{chrom}\t{promoter_start}\t{promoter_end}\n"
                )

        if data_lines % 1_000_000 == 0:
            print(
                f"[INFO] parsed {data_lines:,} GTF data rows",
                file=sys.stderr,
                flush=True,
            )

for handle in handles.values():
    handle.close()

utr5 = open(paths["utr5"], "w", encoding="utf-8")
utr3 = open(paths["utr3"], "w", encoding="utf-8")
unresolved = open(paths["utr_unresolved"], "w", encoding="utf-8")

with open(paths["utr_raw"], encoding="utf-8") as handle:
    for line in handle:
        transcript_id, chrom, start_text, end_text, strand = line.rstrip("\n").split("\t")
        start0 = int(start_text)
        end = int(end_text)

        bounds = cds_bounds.get(transcript_id)
        if bounds is None:
            unresolved.write(f"{chrom}\t{start0}\t{end}\n")
            counts["utr_without_cds_bounds"] += 1
            continue

        _, cds_start, cds_end, cds_strand = bounds
        if strand != cds_strand:
            unresolved.write(f"{chrom}\t{start0}\t{end}\n")
            counts["utr_cds_strand_mismatch"] += 1
            continue

        if strand == "+":
            if end <= cds_start:
                utr5.write(f"{chrom}\t{start0}\t{end}\n")
                counts["utr5_rows"] += 1
            elif start0 >= cds_end:
                utr3.write(f"{chrom}\t{start0}\t{end}\n")
                counts["utr3_rows"] += 1
            else:
                unresolved.write(f"{chrom}\t{start0}\t{end}\n")
                counts["utr_overlaps_cds_bounds"] += 1
        elif strand == "-":
            if start0 >= cds_end:
                utr5.write(f"{chrom}\t{start0}\t{end}\n")
                counts["utr5_rows"] += 1
            elif end <= cds_start:
                utr3.write(f"{chrom}\t{start0}\t{end}\n")
                counts["utr3_rows"] += 1
            else:
                unresolved.write(f"{chrom}\t{start0}\t{end}\n")
                counts["utr_overlaps_cds_bounds"] += 1
        else:
            unresolved.write(f"{chrom}\t{start0}\t{end}\n")
            counts["utr_unknown_strand"] += 1

utr5.close()
utr3.close()
unresolved.close()

summary_path = workdir / "gtf_parse.summary.tsv"
with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"gtf_data_rows\t{data_lines}\n")
    output.write(f"transcripts_with_cds_bounds\t{len(cds_bounds)}\n")
    output.write(f"promoter_upstream_bp\t{promoter_up}\n")
    output.write(f"promoter_downstream_bp\t{promoter_down}\n")
    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")

print(f"[INFO] GTF parsing complete: {data_lines:,} data rows", file=sys.stderr)
PY

cat > "$FLAGGER" <<'PY'
import csv
import gzip
import sys
from collections import Counter

loci_path = sys.argv[1]
output_path = sys.argv[2]
summary_path = sys.argv[3]
expected = int(sys.argv[4])
track_specs = sys.argv[5:]

tracks = []
for specification in track_specs:
    name, path = specification.split("=", 1)
    handle = open(path, encoding="utf-8")

    def advance(h=handle):
        line = h.readline()
        return line.rstrip("\n") if line else None

    tracks.append({"name": name, "handle": handle, "next": advance(), "advance": advance})

header = [
    "locus_id",
    "overlap_cds",
    "overlap_5_prime_utr",
    "overlap_3_prime_utr",
    "overlap_noncoding_exon",
    "overlap_any_exon",
    "overlap_gene_body",
    "overlap_promoter",
    "other_exon",
    "intron_union",
    "intergenic",
    "primary_region",
    "all_regions",
    "annotation_rna_priority",
]

counts = Counter()
rows = 0

with gzip.open(output_path, "wt", encoding="utf-8", newline="") as output:
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(header)

    with open(loci_path, encoding="utf-8") as loci:
        for line in loci:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 4:
                continue

            locus_id = fields[3]
            flags = {}

            for track in tracks:
                matched = track["next"] == locus_id
                flags[track["name"]] = matched
                if matched:
                    track["next"] = track["advance"]()

            cds = flags["cds"]
            utr5 = flags["utr5"]
            utr3 = flags["utr3"]
            noncoding_exon = flags["noncoding_exon"]
            any_exon = flags["all_exon"]
            gene_body = flags["gene_body"]
            promoter = flags["promoter"]

            other_exon = any_exon and not cds and not utr5 and not utr3 and not noncoding_exon
            intron_union = gene_body and not any_exon
            intergenic = not gene_body and not promoter

            if cds:
                primary = "CDS"
            elif utr5:
                primary = "5_prime_UTR"
            elif utr3:
                primary = "3_prime_UTR"
            elif noncoding_exon:
                primary = "noncoding_exon"
            elif other_exon:
                primary = "other_exon"
            elif intron_union:
                primary = "intron"
            elif promoter:
                primary = "promoter"
            else:
                primary = "intergenic"

            regions = []
            if cds: regions.append("CDS")
            if utr5: regions.append("5_prime_UTR")
            if utr3: regions.append("3_prime_UTR")
            if noncoding_exon: regions.append("noncoding_exon")
            if other_exon: regions.append("other_exon")
            if intron_union: regions.append("intron")
            if promoter: regions.append("promoter")
            if intergenic: regions.append("intergenic")

            if cds or utr5 or utr3 or noncoding_exon or other_exon:
                priority = "high"
            elif intron_union:
                priority = "medium"
            else:
                priority = "low"

            writer.writerow(
                [
                    locus_id,
                    str(cds).lower(),
                    str(utr5).lower(),
                    str(utr3).lower(),
                    str(noncoding_exon).lower(),
                    str(any_exon).lower(),
                    str(gene_body).lower(),
                    str(promoter).lower(),
                    str(other_exon).lower(),
                    str(intron_union).lower(),
                    str(intergenic).lower(),
                    primary,
                    ",".join(regions),
                    priority,
                ]
            )

            counts[f"primary::{primary}"] += 1
            counts[f"priority::{priority}"] += 1
            rows += 1

            if rows % 500_000 == 0:
                print(
                    f"[INFO] wrote {rows:,} locus-flag rows",
                    file=sys.stderr,
                    flush=True,
                )

for track in tracks:
    if track["next"] is not None:
        raise RuntimeError(f"Unconsumed overlap IDs remain for track {track['name']}")
    track["handle"].close()

status = "PASS" if rows == expected else "REVIEW"

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"expected_loci\t{expected}\n")
    output.write(f"records_written\t{rows}\n")
    output.write(f"audit_status\t{status}\n")
    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")

if status != "PASS":
    raise SystemExit("Locus-flag validation failed")
PY

echo "===== 1. PARSE GENCODE v50 GTF ====="
echo "Promoter definition: ${PROMOTER_UPSTREAM} bp upstream and ${PROMOTER_DOWNSTREAM} bp downstream of transcript-direction TSS."

rm -f "$WORKDIR"/*.raw.bed "$WORKDIR"/utr.raw.tsv "$WORKDIR"/gtf_parse.summary.tsv \
  "$FLAGS" "$SUMMARY" "$TRACK_SUMMARY" "$MANIFEST"

python "$PARSER" \
  "$GTF" \
  "$FAI" \
  "$WORKDIR" \
  "$PROMOTER_UPSTREAM" \
  "$PROMOTER_DOWNSTREAM"

echo
echo "===== GTF PARSE SUMMARY ====="
column -ts $'\t' "$WORKDIR/gtf_parse.summary.tsv" | sed -n '1,60p'

merge_track() {
    local name="$1"
    local raw="$2"
    local output="$TRACKDIR/${name}.merged.bed.gz"

    echo "[INFO] sorting and merging track: $name" >&2

    LC_ALL=C sort \
      --temporary-directory="$WORKDIR" \
      --buffer-size=20% \
      -k1,1V -k2,2n -k3,3n \
      "$raw" |
    bedtools merge -i - |
    bgzip -c > "$output"

    tabix -f -p bed "$output"
}

echo
echo "===== 2. SORT AND MERGE REGION TRACKS ====="

merge_track cds "$WORKDIR/cds.raw.bed"
merge_track utr5 "$WORKDIR/utr5.raw.bed"
merge_track utr3 "$WORKDIR/utr3.raw.bed"
merge_track utr_unresolved "$WORKDIR/utr_unresolved.raw.bed"
merge_track noncoding_exon "$WORKDIR/noncoding_exon.raw.bed"
merge_track all_exon "$WORKDIR/all_exon.raw.bed"
merge_track gene_body "$WORKDIR/gene_body.raw.bed"
merge_track promoter "$WORKDIR/promoter.raw.bed"

LC_ALL=C sort \
  --temporary-directory="$WORKDIR" \
  --buffer-size=20% \
  -k1,1V -k2,2n -k3,3n \
  "$WORKDIR/genes.raw.bed" |
bgzip -c > "$GENES"

tabix -f -p bed "$GENES"

{
    printf 'track\tmerged_intervals\tbytes\tsha256\tpath\n'
    for path in "$TRACKDIR"/*.merged.bed.gz; do
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path" .merged.bed.gz)" \
          "$(gzip -cd "$path" | awk 'END {print NR}')" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$TRACK_SUMMARY"

echo
echo "===== TRACK SUMMARY ====="
column -ts $'\t' "$TRACK_SUMMARY"

echo
echo "===== 3. BUILD SORTED LOCUS BED ====="

LOCI_BED="$WORKDIR/trexplorer_v2.loci.bed"

gzip -cd "$BASE_BED" |
awk -F '\t' '
BEGIN { OFS = "\t" }
{
    chrom_no_prefix = $1
    sub(/^chr/, "", chrom_no_prefix)
    locus_id = chrom_no_prefix "-" $2 "-" $3 "-" $4
    print $1, $2, $3, locus_id
}
' > "$LOCI_BED"

LOCI_COUNT="$(wc -l < "$LOCI_BED")"

if [[ "$LOCI_COUNT" != "$EXPECTED_LOCI" ]]; then
    echo "ERROR: locus BED count mismatch: $LOCI_COUNT" >&2
    exit 1
fi

echo "Loci: $LOCI_COUNT"

echo
echo "===== 4. INTERSECT LOCI WITH GENCODE TRACKS ====="

for name in cds utr5 utr3 noncoding_exon all_exon gene_body promoter; do
    echo "[INFO] intersecting track: $name" >&2
    bedtools intersect \
      -u \
      -a "$LOCI_BED" \
      -b "$TRACKDIR/${name}.merged.bed.gz" |
    cut -f4 > "$OVERLAPDIR/${name}.ids"
done

echo
echo "===== 5. BUILD LOCUS-LEVEL FLAGS ====="

python "$FLAGGER" \
  "$LOCI_BED" \
  "$FLAGS" \
  "$SUMMARY" \
  "$EXPECTED_LOCI" \
  "cds=$OVERLAPDIR/cds.ids" \
  "utr5=$OVERLAPDIR/utr5.ids" \
  "utr3=$OVERLAPDIR/utr3.ids" \
  "noncoding_exon=$OVERLAPDIR/noncoding_exon.ids" \
  "all_exon=$OVERLAPDIR/all_exon.ids" \
  "gene_body=$OVERLAPDIR/gene_body.ids" \
  "promoter=$OVERLAPDIR/promoter.ids"

gzip -t "$FLAGS"

echo
echo "===== LOCUS FLAG SUMMARY ====="
column -ts $'\t' "$SUMMARY"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$FLAGS")" \
      "$(gzip -cd "$FLAGS" | awk 'END {print NR-1}')" \
      "$(stat -c '%s' "$FLAGS")" \
      "$(sha256sum "$FLAGS" | awk '{print $1}')" \
      "$FLAGS"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$GENES")" \
      "$(gzip -cd "$GENES" | awk 'END {print NR}')" \
      "$(stat -c '%s' "$GENES")" \
      "$(sha256sum "$GENES" | awk '{print $1}')" \
      "$GENES"
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== FIRST 5 FLAG ROWS ====="
gzip -cd "$FLAGS" |
awk 'NR <= 6 {print} NR == 6 {exit}' |
column -ts $'\t' || true

echo
echo "===== COMPLETE ====="
echo "$FLAGS"
echo "$SUMMARY"
echo "$TRACK_SUMMARY"
echo "$GENES"
echo "$MANIFEST"
