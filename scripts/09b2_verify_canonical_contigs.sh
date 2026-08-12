#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
BASE_BED="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"

ROOT="$CATDIR/rnatr_master/gencode_v50"
TRACKDIR="$ROOT/tracks"
CANONDIR="$ROOT/tracks_canonical"
WORKDIR="$PROJECT_ROOT/tmp/09b2_verify_canonical_contigs"

OLD_FLAGS="$ROOT/TRExplorer_v2.gencode_v50_locus_flags.tsv.gz"
NEW_FLAGS="$ROOT/TRExplorer_v2.gencode_v50_locus_flags.canonical.tsv.gz"
SUMMARY="$ROOT/TRExplorer_v2.gencode_v50_canonical_contig_verification.tsv"

CONTIGS="$WORKDIR/trexplorer_contigs.txt"
LOCI="$WORKDIR/trexplorer_loci.bed"
FLAGGER="$WORKDIR/build_flags.py"

mkdir -p "$CANONDIR" "$WORKDIR"

test -s "$BASE_BED" || {
    echo "ERROR: missing catalog: $BASE_BED" >&2
    exit 1
}

test -s "$OLD_FLAGS" || {
    echo "ERROR: missing provisional flags: $OLD_FLAGS" >&2
    exit 1
}

cat > "$FLAGGER" <<'PY'
import csv
import gzip
import sys
from collections import Counter

loci_path = sys.argv[1]
output_path = sys.argv[2]
expected = int(sys.argv[3])
track_specs = sys.argv[4:]

tracks = []

for spec in track_specs:
    name, path = spec.split("=", 1)
    handle = open(path, encoding="utf-8")

    def advance(h=handle):
        line = h.readline()
        return line.rstrip("\n") if line else None

    tracks.append(
        {
            "name": name,
            "handle": handle,
            "advance": advance,
            "next": advance(),
        }
    )

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

rows = 0
counts = Counter()

with gzip.open(output_path, "wt", encoding="utf-8", newline="") as out:
    writer = csv.writer(out, delimiter="\t", lineterminator="\n")
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

            other_exon = (
                any_exon
                and not cds
                and not utr5
                and not utr3
                and not noncoding_exon
            )
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

            if cds:
                regions.append("CDS")
            if utr5:
                regions.append("5_prime_UTR")
            if utr3:
                regions.append("3_prime_UTR")
            if noncoding_exon:
                regions.append("noncoding_exon")
            if other_exon:
                regions.append("other_exon")
            if intron_union:
                regions.append("intron")
            if promoter:
                regions.append("promoter")
            if intergenic:
                regions.append("intergenic")

            if any([cds, utr5, utr3, noncoding_exon, other_exon]):
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

            rows += 1
            counts[f"primary::{primary}"] += 1
            counts[f"priority::{priority}"] += 1

            if rows % 500_000 == 0:
                print(
                    f"[INFO] wrote {rows:,} canonical flag rows",
                    file=sys.stderr,
                    flush=True,
                )

for track in tracks:
    if track["next"] is not None:
        raise RuntimeError(
            f"Unconsumed overlap IDs remain for {track['name']}"
        )
    track["handle"].close()

if rows != expected:
    raise RuntimeError(
        f"Expected {expected} rows but wrote {rows}"
    )
PY

echo "===== 1. CANONICAL CONTIG SET ====="

tabix -l "$BASE_BED" > "$CONTIGS"

cat "$CONTIGS"

CONTIG_COUNT="$(wc -l < "$CONTIGS")"

echo "Contigs: $CONTIG_COUNT"

if [[ "$CONTIG_COUNT" != "25" ]]; then
    echo "ERROR: expected 25 TRExplorer contigs" >&2
    exit 1
fi

echo
echo "===== 2. FILTER MERGED TRACKS ====="

for name in cds utr5 utr3 noncoding_exon all_exon gene_body promoter; do
    src="$TRACKDIR/${name}.merged.bed.gz"
    dst="$CANONDIR/${name}.merged.bed.gz"

    test -s "$src" || {
        echo "ERROR: missing track: $src" >&2
        exit 1
    }

    echo "[INFO] filtering $name"

    gzip -cd "$src" |
    awk '
        NR == FNR {
            keep[$1] = 1
            next
        }
        ($1 in keep)
    ' "$CONTIGS" - |
    bgzip -c > "$dst"

    tabix -f -p bed "$dst"
done

echo
echo "===== 3. BUILD LOCUS BED ====="

gzip -cd "$BASE_BED" |
awk -F '\t' '
BEGIN {
    OFS = "\t"
}
{
    chrom_no_prefix = $1
    sub(/^chr/, "", chrom_no_prefix)
    locus_id = chrom_no_prefix "-" $2 "-" $3 "-" $4
    print $1, $2, $3, locus_id
}
' > "$LOCI"

EXPECTED="$(wc -l < "$LOCI")"

echo "Loci: $EXPECTED"

echo
echo "===== 4. RE-RUN INTERSECTIONS ====="

for name in cds utr5 utr3 noncoding_exon all_exon gene_body promoter; do
    echo "[INFO] intersecting $name"

    bedtools intersect \
      -u \
      -a "$LOCI" \
      -b "$CANONDIR/${name}.merged.bed.gz" |
    cut -f4 > "$WORKDIR/${name}.ids"
done

echo
echo "===== 5. REBUILD FLAGS ====="

rm -f "$NEW_FLAGS"

python "$FLAGGER" \
  "$LOCI" \
  "$NEW_FLAGS" \
  "$EXPECTED" \
  "cds=$WORKDIR/cds.ids" \
  "utr5=$WORKDIR/utr5.ids" \
  "utr3=$WORKDIR/utr3.ids" \
  "noncoding_exon=$WORKDIR/noncoding_exon.ids" \
  "all_exon=$WORKDIR/all_exon.ids" \
  "gene_body=$WORKDIR/gene_body.ids" \
  "promoter=$WORKDIR/promoter.ids"

gzip -t "$NEW_FLAGS"

echo
echo "===== 6. CONTENT COMPARISON ====="

OLD_ROWS="$(
    gzip -cd "$OLD_FLAGS" |
    awk 'END {print NR-1}'
)"

NEW_ROWS="$(
    gzip -cd "$NEW_FLAGS" |
    awk 'END {print NR-1}'
)"

OLD_SHA="$(
    gzip -cd "$OLD_FLAGS" |
    sha256sum |
    awk '{print $1}'
)"

NEW_SHA="$(
    gzip -cd "$NEW_FLAGS" |
    sha256sum |
    awk '{print $1}'
)"

IDENTICAL="false"
STATUS="REVIEW"

if [[ "$OLD_SHA" == "$NEW_SHA" ]]; then
    IDENTICAL="true"
    STATUS="PASS"
fi

{
    printf 'metric\tvalue\n'
    printf 'canonical_contigs\t%s\n' "$CONTIG_COUNT"
    printf 'provisional_rows\t%s\n' "$OLD_ROWS"
    printf 'canonical_rows\t%s\n' "$NEW_ROWS"
    printf 'provisional_content_sha256\t%s\n' "$OLD_SHA"
    printf 'canonical_content_sha256\t%s\n' "$NEW_SHA"
    printf 'content_identical\t%s\n' "$IDENTICAL"
    printf 'audit_status\t%s\n' "$STATUS"
} > "$SUMMARY"

column -ts $'\t' "$SUMMARY"

if [[ "$STATUS" != "PASS" ]]; then
    echo "ERROR: canonical-only output differs from provisional output" >&2
    exit 1
fi

echo
echo "===== COMPLETE ====="
echo "$NEW_FLAGS"
echo "$SUMMARY"
