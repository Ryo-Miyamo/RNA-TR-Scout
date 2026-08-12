#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
BASE_BED="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"
JSON_GZ="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.EH.with_annotations.json.gz"
AUDITDIR="$CATDIR/audit"
WORKDIR="$PROJECT_ROOT/tmp/05f_trexplorer_id_audit_v2"

mkdir -p "$AUDITDIR" "$WORKDIR"

EXPECTED=5599658

BASE_SORTED="$AUDITDIR/TRExplorer_v2.base_bed.locus_ids.sorted.txt"
JSON_SORTED="$AUDITDIR/TRExplorer_v2.annotation_json.locus_ids.sorted.txt"
BASE_ONLY="$AUDITDIR/TRExplorer_v2.locus_ids.base_only.txt"
JSON_ONLY="$AUDITDIR/TRExplorer_v2.locus_ids.json_only.txt"
SUMMARY="$AUDITDIR/TRExplorer_v2.full_locus_id_set_audit.tsv"

BASE_TMP="$WORKDIR/base.ids.unsorted.tmp"
JSON_TMP="$WORKDIR/json.ids.unsorted.tmp"
JSON_SORT_TMP="$WORKDIR/json.ids.sorted.tmp"

for path in "$BASE_BED" "$JSON_GZ"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

command -v jq >/dev/null || {
    echo "ERROR: jq not found" >&2
    exit 1
}

echo "===== 1. BASE BED LOCUS IDs ====="

if [[ -s "$BASE_SORTED" ]] && [[ "$(wc -l < "$BASE_SORTED")" == "$EXPECTED" ]]; then
    echo "Reusing verified base-ID file:"
    echo "$BASE_SORTED"
else
    rm -f "$BASE_TMP" "$BASE_SORTED"

    gzip -cd "$BASE_BED" |
    awk -F '\t' '
    BEGIN { OFS = "" }
    {
        chrom = $1
        sub(/^chr/, "", chrom)
        print chrom, "-", $2, "-", $3, "-", $4
        if (NR % 500000 == 0) {
            printf("[INFO] built %d BED IDs\n", NR) > "/dev/stderr"
        }
    }
    ' > "$BASE_TMP"

    LC_ALL=C sort \
      --temporary-directory="$WORKDIR" \
      --buffer-size=25% \
      "$BASE_TMP" \
      > "$BASE_SORTED"

    rm -f "$BASE_TMP"
fi

BASE_TOTAL="$(wc -l < "$BASE_SORTED")"
echo "Base BED IDs: $BASE_TOTAL"

echo
echo "===== 2. STREAM JSON LOCUS IDs WITH jq --stream ====="

rm -f "$JSON_TMP" "$JSON_SORT_TMP"

gzip -cd "$JSON_GZ" |
jq --stream -r '
    select(
        (.[0] | length) == 2
        and .[0][1] == "LocusId"
        and (.[1] | type) == "string"
    )
    | .[1]
' |
awk '
{
    print
    if (NR % 500000 == 0) {
        printf("[INFO] extracted %d JSON LocusIds\n", NR) > "/dev/stderr"
    }
}
END {
    printf("[INFO] total JSON LocusIds: %d\n", NR) > "/dev/stderr"
}
' > "$JSON_TMP"

JSON_TOTAL="$(wc -l < "$JSON_TMP")"
echo "JSON IDs: $JSON_TOTAL"

if [[ "$JSON_TOTAL" != "$EXPECTED" ]]; then
    echo "ERROR: expected $EXPECTED JSON IDs, found $JSON_TOTAL" >&2
    exit 1
fi

echo
echo "===== 3. SORT JSON IDs ====="

LC_ALL=C sort \
  --temporary-directory="$WORKDIR" \
  --buffer-size=25% \
  "$JSON_TMP" \
  > "$JSON_SORT_TMP"

mv "$JSON_SORT_TMP" "$JSON_SORTED"
rm -f "$JSON_TMP"

echo
echo "===== 4. COMPARE COMPLETE ID SETS ====="

BASE_UNIQUE="$(LC_ALL=C uniq "$BASE_SORTED" | wc -l)"
JSON_UNIQUE="$(LC_ALL=C uniq "$JSON_SORTED" | wc -l)"

BASE_DUPLICATES="$((BASE_TOTAL - BASE_UNIQUE))"
JSON_DUPLICATES="$((JSON_TOTAL - JSON_UNIQUE))"

LC_ALL=C comm -23 "$BASE_SORTED" "$JSON_SORTED" > "$BASE_ONLY"
LC_ALL=C comm -13 "$BASE_SORTED" "$JSON_SORTED" > "$JSON_ONLY"

BASE_ONLY_COUNT="$(wc -l < "$BASE_ONLY")"
JSON_ONLY_COUNT="$(wc -l < "$JSON_ONLY")"

STATUS="REVIEW"

if [[ \
    "$BASE_TOTAL" == "$EXPECTED" \
    && "$JSON_TOTAL" == "$EXPECTED" \
    && "$BASE_DUPLICATES" == "0" \
    && "$JSON_DUPLICATES" == "0" \
    && "$BASE_ONLY_COUNT" == "0" \
    && "$JSON_ONLY_COUNT" == "0" \
]]; then
    STATUS="PASS"
fi

{
    printf 'metric\tvalue\n'
    printf 'base_total_ids\t%s\n' "$BASE_TOTAL"
    printf 'base_unique_ids\t%s\n' "$BASE_UNIQUE"
    printf 'base_duplicate_ids\t%s\n' "$BASE_DUPLICATES"
    printf 'json_total_ids\t%s\n' "$JSON_TOTAL"
    printf 'json_unique_ids\t%s\n' "$JSON_UNIQUE"
    printf 'json_duplicate_ids\t%s\n' "$JSON_DUPLICATES"
    printf 'base_only_ids\t%s\n' "$BASE_ONLY_COUNT"
    printf 'json_only_ids\t%s\n' "$JSON_ONLY_COUNT"
    printf 'audit_status\t%s\n' "$STATUS"
} > "$SUMMARY"

echo
echo "===== FULL LOCUS-ID SET AUDIT ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== BASE-ONLY EXAMPLES ====="
if [[ "$BASE_ONLY_COUNT" == "0" ]]; then
    echo "None"
else
    head -n 20 "$BASE_ONLY"
fi

echo
echo "===== JSON-ONLY EXAMPLES ====="
if [[ "$JSON_ONLY_COUNT" == "0" ]]; then
    echo "None"
else
    head -n 20 "$JSON_ONLY"
fi

echo
echo "===== COMPLETE ====="
echo "$SUMMARY"
