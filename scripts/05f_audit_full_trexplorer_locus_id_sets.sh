#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
BASE_BED="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"
JSON_GZ="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.EH.with_annotations.json.gz"
AUDITDIR="$CATDIR/audit"
WORKDIR="$PROJECT_ROOT/tmp/05f_trexplorer_id_audit"

mkdir -p "$AUDITDIR" "$WORKDIR"

BASE_UNSORTED="$WORKDIR/base_bed.ids.unsorted.txt"
JSON_UNSORTED="$WORKDIR/annotation_json.ids.unsorted.txt"
BASE_SORTED="$AUDITDIR/TRExplorer_v2.base_bed.locus_ids.sorted.txt"
JSON_SORTED="$AUDITDIR/TRExplorer_v2.annotation_json.locus_ids.sorted.txt"
BASE_ONLY="$AUDITDIR/TRExplorer_v2.locus_ids.base_only.txt"
JSON_ONLY="$AUDITDIR/TRExplorer_v2.locus_ids.json_only.txt"
SUMMARY="$AUDITDIR/TRExplorer_v2.full_locus_id_set_audit.tsv"

for path in "$BASE_BED" "$JSON_GZ"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

echo "===== DISK SPACE ====="
df -h "$PROJECT_ROOT" "$WORKDIR"

echo
echo "===== 1. BUILD LOCUS IDs FROM BASE BED ====="

gzip -cd "$BASE_BED" |
awk -F '\t' '
BEGIN {
    OFS = ""
}
{
    chrom = $1
    sub(/^chr/, "", chrom)
    print chrom, "-", $2, "-", $3, "-", $4
}
' > "$BASE_UNSORTED"

BASE_TOTAL="$(wc -l < "$BASE_UNSORTED")"
echo "Base BED IDs: $BASE_TOTAL"

LC_ALL=C sort \
  --temporary-directory="$WORKDIR" \
  --buffer-size=25% \
  "$BASE_UNSORTED" \
  > "$BASE_SORTED"

rm -f "$BASE_UNSORTED"

echo
echo "===== 2. STREAM LOCUS IDs FROM ANNOTATION JSON ====="

python - "$JSON_GZ" "$JSON_UNSORTED" <<'PY'
import gzip
import json
import sys

input_path, output_path = sys.argv[1:]
decoder = json.JSONDecoder()
chunk_size = 4 * 1024 * 1024


def iter_json_array(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        buffer = ""

        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                raise RuntimeError(
                    "Unexpected EOF before the top-level JSON array"
                )

            buffer += chunk
            stripped = buffer.lstrip()

            if stripped:
                if stripped[0] != "[":
                    raise RuntimeError(
                        "Top-level JSON value is not an array"
                    )
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
                    record, consumed = decoder.raw_decode(buffer)
                    break
                except json.JSONDecodeError:
                    chunk = handle.read(chunk_size)
                    if not chunk:
                        raise RuntimeError(
                            "Unexpected EOF while parsing a JSON record"
                        )
                    buffer += chunk

            yield record
            buffer = buffer[consumed:]


count = 0
missing = 0

with open(output_path, "w", encoding="utf-8") as output:
    for record in iter_json_array(input_path):
        count += 1
        locus_id = record.get("LocusId")

        if locus_id is None:
            missing += 1
            continue

        output.write(str(locus_id))
        output.write("\n")

        if count % 500_000 == 0:
            print(
                f"[INFO] parsed {count:,} JSON records",
                file=sys.stderr,
                flush=True,
            )

print(
    f"[INFO] JSON records parsed: {count:,}",
    file=sys.stderr,
)
print(
    f"[INFO] records missing LocusId: {missing:,}",
    file=sys.stderr,
)
PY

JSON_TOTAL="$(wc -l < "$JSON_UNSORTED")"
echo "JSON IDs: $JSON_TOTAL"

LC_ALL=C sort \
  --temporary-directory="$WORKDIR" \
  --buffer-size=25% \
  "$JSON_UNSORTED" \
  > "$JSON_SORTED"

rm -f "$JSON_UNSORTED"

echo
echo "===== 3. COMPARE SORTED ID SETS ====="

BASE_UNIQUE="$(LC_ALL=C uniq "$BASE_SORTED" | wc -l)"
JSON_UNIQUE="$(LC_ALL=C uniq "$JSON_SORTED" | wc -l)"

BASE_DUPLICATES="$((BASE_TOTAL - BASE_UNIQUE))"
JSON_DUPLICATES="$((JSON_TOTAL - JSON_UNIQUE))"

LC_ALL=C comm -23 "$BASE_SORTED" "$JSON_SORTED" > "$BASE_ONLY"
LC_ALL=C comm -13 "$BASE_SORTED" "$JSON_SORTED" > "$JSON_ONLY"

BASE_ONLY_COUNT="$(wc -l < "$BASE_ONLY")"
JSON_ONLY_COUNT="$(wc -l < "$JSON_ONLY")"

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

    if [[ \
        "$BASE_TOTAL" == "$JSON_TOTAL" \
        && "$BASE_DUPLICATES" == "0" \
        && "$JSON_DUPLICATES" == "0" \
        && "$BASE_ONLY_COUNT" == "0" \
        && "$JSON_ONLY_COUNT" == "0" \
    ]]; then
        printf 'audit_status\tPASS\n'
    else
        printf 'audit_status\tREVIEW\n'
    fi
} > "$SUMMARY"

echo
echo "===== FULL LOCUS-ID SET AUDIT ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== BASE-ONLY ID EXAMPLES ====="
if [[ "$BASE_ONLY_COUNT" == "0" ]]; then
    echo "None"
else
    head -n 20 "$BASE_ONLY"
fi

echo
echo "===== JSON-ONLY ID EXAMPLES ====="
if [[ "$JSON_ONLY_COUNT" == "0" ]]; then
    echo "None"
else
    head -n 20 "$JSON_ONLY"
fi

echo
echo "===== OUTPUT FILES ====="
printf '%s\n' \
  "$SUMMARY" \
  "$BASE_SORTED" \
  "$JSON_SORTED" \
  "$BASE_ONLY" \
  "$JSON_ONLY"
