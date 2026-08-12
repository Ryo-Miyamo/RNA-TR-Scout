#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
BED="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"
AUDITDIR="$CATDIR/audit"

mkdir -p "$AUDITDIR"

SUMMARY="$AUDITDIR/TRExplorer_v2.structural_audit.tsv"
CONTIGS="$AUDITDIR/TRExplorer_v2.loci_per_contig.tsv"
MOTIF_LENGTHS="$AUDITDIR/TRExplorer_v2.motif_length_distribution.tsv"
FIFTH_COL="$AUDITDIR/TRExplorer_v2.column5_values.tsv"

test -s "$BED" || {
    echo "ERROR: catalog not found: $BED" >&2
    exit 1
}

echo "Auditing: $BED"

gzip -cd "$BED" |
awk -F '\t' '
BEGIN {
    OFS = "\t"
    min_motif = -1
    min_interval = -1
}
{
    total++

    if (NF != 5) {
        bad_field_count++
        next
    }

    chrom = $1
    start = $2
    end = $3
    motif = toupper($4)
    column5 = $5

    if (start !~ /^[0-9]+$/ || end !~ /^[0-9]+$/) {
        non_integer_coordinate++
        next
    }

    start += 0
    end += 0

    if (start < 0 || end <= start) {
        invalid_coordinate++
        next
    }

    interval_length = end - start
    motif_length = length(motif)
    valid_rows++

    if (min_interval < 0 || interval_length < min_interval) {
        min_interval = interval_length
    }
    if (interval_length > max_interval) {
        max_interval = interval_length
    }

    if (min_motif < 0 || motif_length < min_motif) {
        min_motif = motif_length
    }
    if (motif_length > max_motif) {
        max_motif = motif_length
    }

    if (motif_length < 1 || motif_length > 1000) {
        motif_length_out_of_range++
    }

    if (motif !~ /^[ACGT]+$/) {
        non_acgt_motif++
    }

    if (motif_length > 0) {
        if (interval_length % motif_length == 0) {
            interval_multiple_of_motif++
        } else {
            interval_not_multiple_of_motif++
        }
    }

    if (column5 == ".") {
        column5_dot++
    } else {
        column5_non_dot++
    }

    if (chrom == previous_chrom) {
        if (start < previous_start) {
            unsorted_within_contig++
        }

        if (start < previous_end) {
            adjacent_overlap++
        }

        if (start == previous_start && end == previous_end) {
            repeated_coordinate_adjacent++
        }

        if (start == previous_start && end == previous_end && motif == previous_motif) {
            repeated_locus_adjacent++
        }
    }

    previous_chrom = chrom
    previous_start = start
    previous_end = end
    previous_motif = motif
}
END {
    print "metric", "value"
    print "total_rows", total
    print "valid_rows", valid_rows
    print "bad_field_count", bad_field_count + 0
    print "non_integer_coordinate", non_integer_coordinate + 0
    print "invalid_coordinate", invalid_coordinate + 0
    print "min_interval_length_bp", min_interval
    print "max_interval_length_bp", max_interval
    print "min_motif_length_bp", min_motif
    print "max_motif_length_bp", max_motif
    print "motif_length_out_of_range", motif_length_out_of_range + 0
    print "non_acgt_motif", non_acgt_motif + 0
    print "interval_multiple_of_motif", interval_multiple_of_motif + 0
    print "interval_not_multiple_of_motif", interval_not_multiple_of_motif + 0
    print "column5_dot", column5_dot + 0
    print "column5_non_dot", column5_non_dot + 0
    print "unsorted_within_contig", unsorted_within_contig + 0
    print "adjacent_overlap", adjacent_overlap + 0
    print "repeated_coordinate_adjacent", repeated_coordinate_adjacent + 0
    print "repeated_locus_adjacent", repeated_locus_adjacent + 0
}
' > "$SUMMARY"

{
    printf 'contig\tlocus_count\n'
    gzip -cd "$BED" |
    awk -F '\t' '{ count[$1]++ } END { for (c in count) print c "\t" count[c] }' |
    sort -V -k1,1
} > "$CONTIGS"

{
    printf 'motif_length_bp\tlocus_count\n'
    gzip -cd "$BED" |
    awk -F '\t' '{ count[length($4)]++ } END { for (n in count) print n "\t" count[n] }' |
    sort -n -k1,1
} > "$MOTIF_LENGTHS"

{
    printf 'locus_count\tcolumn5_value\n'
    gzip -cd "$BED" |
    cut -f5 |
    LC_ALL=C sort |
    uniq -c |
    awk 'BEGIN { OFS="\t" } { count=$1; $1=""; sub(/^ +/, "", $0); print count, $0 }'
} > "$FIFTH_COL"

echo
echo "===== STRUCTURAL AUDIT ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== LOCI PER CONTIG ====="
column -ts $'\t' "$CONTIGS"

echo
echo "===== COLUMN 5 VALUES ====="
column -ts $'\t' "$FIFTH_COL"

echo
echo "===== MOTIF LENGTHS 1-30 BP ====="
awk -F '\t' 'NR == 1 || $1 <= 30' "$MOTIF_LENGTHS" |
column -ts $'\t'

echo
echo "Audit files:"
printf '%s\n' \
  "$SUMMARY" \
  "$CONTIGS" \
  "$MOTIF_LENGTHS" \
  "$FIFTH_COL"
