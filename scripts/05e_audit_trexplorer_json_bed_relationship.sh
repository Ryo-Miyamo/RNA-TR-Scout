#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
BASE_BED="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"
JSON_GZ="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.EH.with_annotations.json.gz"
CLUSTER_GZ="$CATDIR/TRExplorer.variation_clusters_and_isolated_TRs_v2.hg38.TRGT.bed.gz"
AUDITDIR="$CATDIR/audit"

mkdir -p "$AUDITDIR"

CLUSTER_SUMMARY="$AUDITDIR/TRExplorer_v2.cluster_structure_summary.tsv"
JSON_SUMMARY="$AUDITDIR/TRExplorer_v2.json_vs_base_bed.first10000.summary.tsv"
JSON_KEYS="$AUDITDIR/TRExplorer_v2.annotation_keys.first10000.tsv"
GENE_REGION_COUNTS="$AUDITDIR/TRExplorer_v2.gencode_gene_region.first10000.tsv"
MISMATCHES="$AUDITDIR/TRExplorer_v2.json_vs_base_bed.first10000.mismatches.tsv"

for path in "$BASE_BED" "$JSON_GZ" "$CLUSTER_GZ"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

echo "===== 1. CLUSTER BED STRUCTURE AUDIT ====="

gzip -cd "$CLUSTER_GZ" |
awk -F '\t' '
BEGIN {
    OFS = "\t"
    min_span = -1
    min_tr_span = -1
    min_vc_span = -1
}
{
    total++

    if (NF != 4) {
        bad_field_count++
        next
    }

    start = $2 + 0
    end = $3 + 0
    span = end - start

    if (span <= 0) {
        invalid_span++
        next
    }

    if (min_span < 0 || span < min_span) min_span = span
    if (span > max_span) max_span = span
    sum_span += span

    attrs = $4

    has_id = match(attrs, /(^|;)ID=[^;]+/)
    has_motifs = match(attrs, /(^|;)MOTIFS=[^;]+/)
    has_struc = match(attrs, /(^|;)STRUC=<[^>]+>/)

    if (!has_id || !has_motifs || !has_struc) {
        malformed_attributes++
    }

    if (attrs ~ /(^|;)STRUC=<TR:/) {
        tr_rows++
        if (min_tr_span < 0 || span < min_tr_span) min_tr_span = span
        if (span > max_tr_span) max_tr_span = span
        sum_tr_span += span
    } else if (attrs ~ /(^|;)STRUC=<VC:/) {
        vc_rows++
        if (min_vc_span < 0 || span < min_vc_span) min_vc_span = span
        if (span > max_vc_span) max_vc_span = span
        sum_vc_span += span
    } else {
        other_structure_rows++
    }

    id = attrs
    sub(/^.*(^|;)ID=/, "", id)
    sub(/;.*/, "", id)

    n = split(id, parts, "-")

    if (n >= 4 && parts[2] ~ /^[0-9]+$/ && parts[3] ~ /^[0-9]+$/) {
        id_start = parts[2] + 0
        id_end = parts[3] + 0

        if (start == id_start && end == id_end) {
            region_equals_id++
        } else if (start <= id_start && end >= id_end) {
            region_contains_id++
        } else {
            id_outside_region++
        }
    } else {
        unparsed_id++
    }
}
END {
    print "metric", "value"
    print "total_rows", total
    print "bad_field_count", bad_field_count + 0
    print "invalid_span", invalid_span + 0
    print "malformed_attributes", malformed_attributes + 0
    print "structure_TR_rows", tr_rows + 0
    print "structure_VC_rows", vc_rows + 0
    print "structure_other_rows", other_structure_rows + 0
    print "region_equals_ID_coordinates", region_equals_id + 0
    print "region_contains_ID_coordinates", region_contains_id + 0
    print "ID_outside_region", id_outside_region + 0
    print "unparsed_ID", unparsed_id + 0
    print "all_span_min_bp", min_span
    print "all_span_max_bp", max_span
    print "all_span_mean_bp", (total ? sum_span / total : 0)
    print "TR_span_min_bp", min_tr_span
    print "TR_span_max_bp", max_tr_span
    print "TR_span_mean_bp", (tr_rows ? sum_tr_span / tr_rows : 0)
    print "VC_span_min_bp", min_vc_span
    print "VC_span_max_bp", max_vc_span
    print "VC_span_mean_bp", (vc_rows ? sum_vc_span / vc_rows : 0)
}
' > "$CLUSTER_SUMMARY"

column -ts $'\t' "$CLUSTER_SUMMARY"

echo
echo "===== 2. JSON ↔ BASE BED CHECK: FIRST 10,000 RECORDS ====="

python - \
  "$JSON_GZ" \
  "$BASE_BED" \
  "$JSON_SUMMARY" \
  "$JSON_KEYS" \
  "$GENE_REGION_COUNTS" \
  "$MISMATCHES" <<'PY'
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

(
    json_path,
    bed_path,
    summary_path,
    keys_path,
    gene_region_path,
    mismatch_path,
) = sys.argv[1:]

limit = 10_000
decoder = json.JSONDecoder()


def iter_json_array(path, chunk_size=1 << 20):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        buffer = ""

        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                raise RuntimeError("Unexpected EOF before top-level JSON array")
            buffer += chunk
            stripped = buffer.lstrip()
            if stripped:
                if stripped[0] != "[":
                    raise RuntimeError("Top-level JSON value is not an array")
                buffer = stripped[1:]
                break

        while True:
            buffer = buffer.lstrip()

            if buffer.startswith(","):
                buffer = buffer[1:]
                continue

            if buffer.startswith("]"):
                return

            while True:
                try:
                    value, used = decoder.raw_decode(buffer)
                    break
                except json.JSONDecodeError:
                    chunk = handle.read(chunk_size)
                    if not chunk:
                        raise RuntimeError(
                            "Unexpected EOF while parsing JSON record"
                        )
                    buffer += chunk

            yield value
            buffer = buffer[used:]


key_counts = Counter()
gene_region_counts = Counter()

coordinate_mismatch = 0
motif_mismatch = 0
locus_id_mismatch = 0
missing_required_field = 0
checked = 0
mismatch_rows = []

region_pattern = re.compile(r"^([^:]+):(\d+)-(\d+)$")

with gzip.open(bed_path, "rt", encoding="utf-8") as bed_handle:
    for index, record in enumerate(iter_json_array(json_path), start=1):
        if index > limit:
            break

        bed_line = bed_handle.readline()
        if not bed_line:
            raise RuntimeError("Base BED ended before JSON sample")

        fields = bed_line.rstrip("\n").split("\t")
        if len(fields) != 5:
            raise RuntimeError(
                f"Unexpected BED field count at sampled line {index}"
            )

        chrom, start_text, end_text, motif, _ = fields
        start = int(start_text)
        end = int(end_text)

        checked += 1

        for key in record:
            key_counts[key] += 1

        gene_region_counts[str(record.get("GencodeGeneRegion", "<missing>"))] += 1

        required = ("ReferenceRegion", "Motif", "LocusId")
        if any(key not in record for key in required):
            missing_required_field += 1
            if len(mismatch_rows) < 30:
                mismatch_rows.append(
                    (
                        index,
                        chrom,
                        start,
                        end,
                        motif,
                        "missing_required_field",
                        json.dumps(record, ensure_ascii=False)[:500],
                    )
                )
            continue

        reference_region = str(record["ReferenceRegion"])
        match = region_pattern.match(reference_region)

        coordinate_ok = False
        if match:
            json_chrom = match.group(1)
            json_start = int(match.group(2))
            json_end = int(match.group(3))
            coordinate_ok = (
                json_chrom == chrom
                and json_start == start
                and json_end == end
            )

        if not coordinate_ok:
            coordinate_mismatch += 1
            if len(mismatch_rows) < 30:
                mismatch_rows.append(
                    (
                        index,
                        chrom,
                        start,
                        end,
                        motif,
                        "coordinate_mismatch",
                        reference_region,
                    )
                )

        json_motif = str(record["Motif"])
        if json_motif != motif:
            motif_mismatch += 1
            if len(mismatch_rows) < 30:
                mismatch_rows.append(
                    (
                        index,
                        chrom,
                        start,
                        end,
                        motif,
                        "motif_mismatch",
                        json_motif,
                    )
                )

        expected_locus_id = (
            f"{chrom.removeprefix('chr')}-{start}-{end}-{motif}"
        )
        json_locus_id = str(record["LocusId"])

        if json_locus_id != expected_locus_id:
            locus_id_mismatch += 1
            if len(mismatch_rows) < 30:
                mismatch_rows.append(
                    (
                        index,
                        chrom,
                        start,
                        end,
                        motif,
                        "locus_id_mismatch",
                        json_locus_id,
                    )
                )

with open(summary_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(f"records_requested\t{limit}\n")
    handle.write(f"records_checked\t{checked}\n")
    handle.write(f"missing_required_field\t{missing_required_field}\n")
    handle.write(f"coordinate_mismatch\t{coordinate_mismatch}\n")
    handle.write(f"motif_mismatch\t{motif_mismatch}\n")
    handle.write(f"locus_id_mismatch\t{locus_id_mismatch}\n")

with open(keys_path, "w", encoding="utf-8") as handle:
    handle.write("key\trecords_present\tpercent_of_sample\n")
    for key, count in sorted(
        key_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        percent = 100.0 * count / checked if checked else 0.0
        handle.write(f"{key}\t{count}\t{percent:.2f}\n")

with open(gene_region_path, "w", encoding="utf-8") as handle:
    handle.write("GencodeGeneRegion\trecord_count\n")
    for value, count in sorted(
        gene_region_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        handle.write(f"{value}\t{count}\n")

with open(mismatch_path, "w", encoding="utf-8") as handle:
    handle.write(
        "record_number\tchrom\tstart\tend\tbed_motif\t"
        "mismatch_type\tjson_value\n"
    )
    for row in mismatch_rows:
        handle.write("\t".join(map(str, row)) + "\n")
PY

echo
echo "JSON/BED summary:"
column -ts $'\t' "$JSON_SUMMARY"

echo
echo "GencodeGeneRegion counts:"
column -ts $'\t' "$GENE_REGION_COUNTS"

echo
echo "Most common annotation keys:"
head -n 31 "$JSON_KEYS" | column -ts $'\t'

echo
echo "Recorded mismatches:"
awk 'END {print NR-1}' "$MISMATCHES"

echo
echo "Output files:"
printf '%s\n' \
  "$CLUSTER_SUMMARY" \
  "$JSON_SUMMARY" \
  "$JSON_KEYS" \
  "$GENE_REGION_COUNTS" \
  "$MISMATCHES"
