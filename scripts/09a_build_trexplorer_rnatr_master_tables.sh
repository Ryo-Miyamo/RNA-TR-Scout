#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
JSON_GZ="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.EH.with_annotations.json.gz"
CLUSTER_GZ="$CATDIR/TRExplorer.variation_clusters_and_isolated_TRs_v2.hg38.TRGT.bed.gz"

OUTDIR="$CATDIR/rnatr_master"
TMPDIR_LOCAL="$PROJECT_ROOT/tmp/09a_build_trexplorer_master"

LOCUS_MASTER="$OUTDIR/TRExplorer_v2.rnatr_locus_master.tsv.gz"
REGION_MASTER="$OUTDIR/TRExplorer_v2.rnatr_analysis_regions.tsv.gz"
LOCUS_SUMMARY="$OUTDIR/TRExplorer_v2.rnatr_locus_master.summary.tsv"
REGION_SUMMARY="$OUTDIR/TRExplorer_v2.rnatr_analysis_regions.summary.tsv"
MANIFEST="$OUTDIR/TRExplorer_v2.rnatr_master.manifest.tsv"

EXPECTED_LOCI=5599658
EXPECTED_REGIONS=5339786

mkdir -p "$OUTDIR" "$TMPDIR_LOCAL"

for path in "$JSON_GZ" "$CLUSTER_GZ"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

command -v jq >/dev/null || {
    echo "ERROR: jq not found" >&2
    exit 1
}

echo "===== INPUTS ====="
ls -lh "$JSON_GZ" "$CLUSTER_GZ"

echo
echo "===== 1. BUILD LOCUS MASTER FROM ANNOTATION JSON ====="

rm -f "$LOCUS_MASTER" "$LOCUS_SUMMARY"

gzip -cd "$JSON_GZ" |
jq --stream -r '
    select(
        (.[0] | length) == 2
        and (.[0][0] | type) == "number"
        and (.[0][1] | type) == "string"
    )
    | [
        .[0][0],
        .[0][1],
        (
            if (.[1] | type) == "string"
            then .[1]
            else (.[1] | tostring)
            end
        )
      ]
    | @tsv
' |
python - "$LOCUS_MASTER" "$LOCUS_SUMMARY" "$EXPECTED_LOCI" <<'PY'
import csv
import gzip
import re
import sys
from collections import Counter

output_path, summary_path, expected_text = sys.argv[1:]
expected = int(expected_text)

wanted = [
    "LocusId",
    "ReferenceRegion",
    "LocusStructure",
    "VariantType",
    "Source",
    "Motif",
    "CanonicalMotif",
    "NumRepeatsInReference",
    "ReferenceRepeatPurity",
    "NsInFlanks",
    "LeftFlankMappability",
    "FlanksAndLocusMappability",
    "RightFlankMappability",
    "GencodeGeneRegion",
    "GencodeGeneId",
    "GencodeGeneName",
    "GencodeTranscriptId",
    "RefseqGeneRegion",
    "ManeGeneRegion",
    "VariationClusterFilterReason",
    "NonOverlappingPurestLocus",
    "NonOverlappingLongestLocus",
    "TRsInRegion",
]

wanted_set = set(wanted)

header = [
    "locus_id",
    "chrom",
    "start",
    "end",
    "motif",
    "canonical_motif",
    "motif_length_bp",
    "reference_repeat_count",
    "reference_repeat_purity",
    "ambiguous_motif",
    "locus_structure",
    "variant_type",
    "source",
    "ns_in_flanks",
    "left_flank_mappability",
    "flanks_and_locus_mappability",
    "right_flank_mappability",
    "trexplorer_gencode_region",
    "trexplorer_gencode_gene_id",
    "trexplorer_gencode_gene_name",
    "trexplorer_gencode_transcript_id",
    "trexplorer_refseq_region",
    "trexplorer_mane_region",
    "variation_cluster_filter_reason",
    "nonoverlapping_purest_locus",
    "nonoverlapping_longest_locus",
    "trs_in_region",
]

region_pattern = re.compile(r"^([^:]+):(\d+)-(\d+)$")
dna_pattern = re.compile(r"^[ACGT]+$")

records_written = 0
missing_locus_id = 0
bad_reference_region = 0
ambiguous_motif_count = 0
region_counts = Counter()
motif_length_counts = Counter()

current_index = None
record = {}


def clean(value):
    if value in ("null", "None"):
        return ""
    return value


def emit(row, writer):
    global records_written
    global missing_locus_id
    global bad_reference_region
    global ambiguous_motif_count

    locus_id = clean(row.get("LocusId", ""))
    reference_region = clean(row.get("ReferenceRegion", ""))
    motif = clean(row.get("Motif", "")).upper()
    canonical = clean(row.get("CanonicalMotif", "")).upper()

    if not locus_id:
        missing_locus_id += 1

    match = region_pattern.match(reference_region)

    if match:
        chrom = match.group(1)
        start = match.group(2)
        end = match.group(3)
    else:
        chrom = ""
        start = ""
        end = ""
        bad_reference_region += 1

    ambiguous = "true" if not dna_pattern.fullmatch(motif) else "false"

    if ambiguous == "true":
        ambiguous_motif_count += 1

    motif_length = str(len(motif)) if motif else ""

    region = clean(row.get("GencodeGeneRegion", ""))
    region_counts[region or "<missing>"] += 1

    if motif_length:
        motif_length_counts[int(motif_length)] += 1

    values = [
        locus_id,
        chrom,
        start,
        end,
        motif,
        canonical,
        motif_length,
        clean(row.get("NumRepeatsInReference", "")),
        clean(row.get("ReferenceRepeatPurity", "")),
        ambiguous,
        clean(row.get("LocusStructure", "")),
        clean(row.get("VariantType", "")),
        clean(row.get("Source", "")),
        clean(row.get("NsInFlanks", "")),
        clean(row.get("LeftFlankMappability", "")),
        clean(row.get("FlanksAndLocusMappability", "")),
        clean(row.get("RightFlankMappability", "")),
        region,
        clean(row.get("GencodeGeneId", "")),
        clean(row.get("GencodeGeneName", "")),
        clean(row.get("GencodeTranscriptId", "")),
        clean(row.get("RefseqGeneRegion", "")),
        clean(row.get("ManeGeneRegion", "")),
        clean(row.get("VariationClusterFilterReason", "")),
        clean(row.get("NonOverlappingPurestLocus", "")),
        clean(row.get("NonOverlappingLongestLocus", "")),
        clean(row.get("TRsInRegion", "")),
    ]

    writer.writerow(values)
    records_written += 1

    if records_written % 500_000 == 0:
        print(
            f"[INFO] wrote {records_written:,} locus-master rows",
            file=sys.stderr,
            flush=True,
        )


reader = csv.reader(sys.stdin, delimiter="\t")

with gzip.open(output_path, "wt", encoding="utf-8", newline="") as output:
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(header)

    for fields in reader:
        if len(fields) != 3:
            continue

        index_text, key, value = fields

        try:
            index = int(index_text)
        except ValueError:
            continue

        if current_index is None:
            current_index = index

        if index != current_index:
            emit(record, writer)
            record = {}
            current_index = index

        if key in wanted_set:
            record[key] = value

    if current_index is not None:
        emit(record, writer)

status = "PASS"
if records_written != expected or missing_locus_id or bad_reference_region:
    status = "REVIEW"

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"expected_loci\t{expected}\n")
    output.write(f"records_written\t{records_written}\n")
    output.write(f"missing_locus_id\t{missing_locus_id}\n")
    output.write(f"bad_reference_region\t{bad_reference_region}\n")
    output.write(f"ambiguous_motif_count\t{ambiguous_motif_count}\n")
    output.write(f"audit_status\t{status}\n")

    for region, count in sorted(
        region_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        output.write(f"trexplorer_region::{region}\t{count}\n")

    for length, count in sorted(motif_length_counts.items()):
        output.write(f"motif_length::{length}\t{count}\n")

if status != "PASS":
    raise SystemExit("Locus master validation failed")
PY

echo
echo "===== LOCUS MASTER SUMMARY ====="
sed -n '1,30p' "$LOCUS_SUMMARY" | column -ts $'\t'

echo
echo "===== 2. BUILD NORMALIZED ANALYSIS-REGION TABLE ====="

rm -f "$REGION_MASTER" "$REGION_SUMMARY"

gzip -cd "$CLUSTER_GZ" |
python - "$REGION_MASTER" "$REGION_SUMMARY" "$EXPECTED_REGIONS" <<'PY'
import csv
import gzip
import re
import sys
from collections import Counter

output_path, summary_path, expected_text = sys.argv[1:]
expected = int(expected_text)

attribute_pattern = re.compile(
    r"^ID=([^;]+);MOTIFS=([^;]+);STRUC=<([^:>]+):([^>]+)>$"
)

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
]

rows_written = 0
malformed = 0
type_counts = Counter()
contains_representative = 0
equals_representative = 0

with gzip.open(output_path, "wt", encoding="utf-8", newline="") as output:
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(header)

    for line_number, line in enumerate(sys.stdin, start=1):
        fields = line.rstrip("\n").split("\t")

        if len(fields) != 4:
            malformed += 1
            continue

        chrom, start_text, end_text, attributes = fields

        try:
            start = int(start_text)
            end = int(end_text)
        except ValueError:
            malformed += 1
            continue

        match = attribute_pattern.match(attributes)

        if not match:
            malformed += 1
            continue

        representative_locus_id, motifs, region_type, structure_token = (
            match.groups()
        )

        analysis_region_id = (
            f"{chrom.removeprefix('chr')}-{start}-{end}-{region_type}"
        )

        writer.writerow(
            [
                analysis_region_id,
                region_type,
                chrom,
                start,
                end,
                end - start,
                representative_locus_id,
                motifs,
                structure_token,
            ]
        )

        rows_written += 1
        type_counts[region_type] += 1

        parts = representative_locus_id.split("-", 3)

        if len(parts) >= 3:
            try:
                locus_start = int(parts[1])
                locus_end = int(parts[2])

                if start == locus_start and end == locus_end:
                    equals_representative += 1
                elif start <= locus_start and end >= locus_end:
                    contains_representative += 1
            except ValueError:
                pass

        if rows_written % 500_000 == 0:
            print(
                f"[INFO] wrote {rows_written:,} analysis-region rows",
                file=sys.stderr,
                flush=True,
            )

status = "PASS"
if rows_written != expected or malformed:
    status = "REVIEW"

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"expected_regions\t{expected}\n")
    output.write(f"records_written\t{rows_written}\n")
    output.write(f"malformed_rows\t{malformed}\n")
    output.write(f"TR_rows\t{type_counts.get('TR', 0)}\n")
    output.write(f"VC_rows\t{type_counts.get('VC', 0)}\n")
    output.write(
        f"region_equals_representative_locus\t{equals_representative}\n"
    )
    output.write(
        f"region_contains_representative_locus\t"
        f"{contains_representative}\n"
    )
    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Analysis-region table validation failed")
PY

echo
echo "===== ANALYSIS-REGION SUMMARY ====="
column -ts $'\t' "$REGION_SUMMARY"

echo
echo "===== 3. OUTPUT INTEGRITY ====="

gzip -t "$LOCUS_MASTER"
gzip -t "$REGION_MASTER"

LOCUS_DATA_ROWS="$(
    gzip -cd "$LOCUS_MASTER" |
    awk 'END {print NR-1}'
)"

REGION_DATA_ROWS="$(
    gzip -cd "$REGION_MASTER" |
    awk 'END {print NR-1}'
)"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tlocal_path\n'

    for path in "$LOCUS_MASTER" "$REGION_MASTER"; do
        if [[ "$path" == "$LOCUS_MASTER" ]]; then
            rows="$LOCUS_DATA_ROWS"
        else
            rows="$REGION_DATA_ROWS"
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
echo "===== FIRST 5 LOCUS-MASTER ROWS ====="
gzip -cd "$LOCUS_MASTER" |
awk 'NR <= 6 {print} NR == 6 {exit}' |
column -ts $'\t' || true

echo
echo "===== FIRST 5 ANALYSIS-REGION ROWS ====="
gzip -cd "$REGION_MASTER" |
awk 'NR <= 6 {print} NR == 6 {exit}' |
column -ts $'\t' || true

echo
echo "===== COMPLETE ====="
echo "$LOCUS_MASTER"
echo "$REGION_MASTER"
echo "$MANIFEST"
