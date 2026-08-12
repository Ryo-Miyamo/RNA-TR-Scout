#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
JSON_GZ="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.EH.with_annotations.json.gz"
CLUSTER_GZ="$CATDIR/TRExplorer.variation_clusters_and_isolated_TRs_v2.hg38.TRGT.bed.gz"
AUDITDIR="$CATDIR/audit"

mkdir -p "$AUDITDIR"

JSON_FIRST="$AUDITDIR/TRExplorer_v2.annotation_json.first_record.json"
JSON_KEYS="$AUDITDIR/TRExplorer_v2.annotation_json.first_record_keys.tsv"
JSON_PREVIEW="$AUDITDIR/TRExplorer_v2.annotation_json.raw_prefix.txt"

CLUSTER_FIRST="$AUDITDIR/TRExplorer_v2.cluster_bed.first10.txt"
CLUSTER_FIELDS="$AUDITDIR/TRExplorer_v2.cluster_bed.field_counts.tsv"
CLUSTER_COUNT="$AUDITDIR/TRExplorer_v2.cluster_bed.line_count.txt"
CLUSTER_CONTIGS="$AUDITDIR/TRExplorer_v2.cluster_bed.contigs.txt"

test -s "$JSON_GZ" || {
    echo "ERROR: missing annotation JSON: $JSON_GZ" >&2
    exit 1
}

test -s "$CLUSTER_GZ" || {
    echo "ERROR: missing cluster BED: $CLUSTER_GZ" >&2
    exit 1
}

echo "===== FILES ====="
ls -lh "$JSON_GZ" "$CLUSTER_GZ"

echo
echo "===== GZIP TEST ====="
gzip -t "$JSON_GZ"
echo "annotation JSON gzip: OK"
gzip -t "$CLUSTER_GZ"
echo "cluster BED gzip: OK"

echo
echo "===== JSON RAW PREFIX ====="
gzip -cd "$JSON_GZ" |
head -c 1200 |
tee "$JSON_PREVIEW"
echo
echo

echo "===== EXTRACT FIRST JSON RECORD WITHOUT LOADING WHOLE FILE ====="

python - "$JSON_GZ" "$JSON_FIRST" "$JSON_KEYS" <<'PY'
import gzip
import json
import sys
from pathlib import Path
from typing import Any

input_path, output_path, keys_path = sys.argv[1:]


def read_non_whitespace(stream):
    while True:
        char = stream.read(1)
        if char == "":
            raise RuntimeError("Unexpected end of file before JSON content")
        if not char.isspace():
            return char


def extract_one_value(stream, first_char: str) -> str:
    buffer = [first_char]
    in_string = first_char == '"'
    escaped = False

    if first_char in "[{":
        depth = 1
    elif first_char == '"':
        depth = 0
    else:
        depth = 0

    while True:
        char = stream.read(1)

        if char == "":
            break

        if in_string:
            buffer.append(char)

            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                if depth == 0:
                    break

            continue

        if char == '"':
            in_string = True
            buffer.append(char)
            continue

        if char in "[{":
            depth += 1
            buffer.append(char)
            continue

        if char in "]}":
            if depth == 0:
                break

            depth -= 1
            buffer.append(char)

            if depth == 0:
                break

            continue

        if depth == 0 and char in ",]":
            break

        buffer.append(char)

    return "".join(buffer).strip()


with gzip.open(input_path, "rt", encoding="utf-8") as handle:
    top = read_non_whitespace(handle)

    if top == "[":
        first = read_non_whitespace(handle)

        if first == "]":
            raise RuntimeError("Top-level JSON array is empty")

        raw = extract_one_value(handle, first)
        top_level_type = "array"
    elif top == "{":
        raw = extract_one_value(handle, top)
        top_level_type = "object"
    else:
        raise RuntimeError(
            f"Unsupported top-level JSON token: {top!r}"
        )

record = json.loads(raw)

Path(output_path).write_text(
    json.dumps(record, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)


def scalar_preview(value: Any, limit: int = 180) -> str:
    text = json.dumps(value, ensure_ascii=False)

    if len(text) > limit:
        return text[: limit - 3] + "..."

    return text


rows = []


def walk(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            rows.append(
                (
                    child_path,
                    type(child).__name__,
                    scalar_preview(child)
                    if not isinstance(child, (dict, list))
                    else "",
                )
            )

            if isinstance(child, dict):
                walk(child, child_path)
            elif isinstance(child, list) and child:
                first_child = child[0]
                rows.append(
                    (
                        f"{child_path}[0]",
                        type(first_child).__name__,
                        scalar_preview(first_child)
                        if not isinstance(first_child, (dict, list))
                        else "",
                    )
                )

                if isinstance(first_child, dict):
                    walk(first_child, f"{child_path}[0]")
    elif isinstance(value, list):
        rows.append(("[0]", type(value[0]).__name__, ""))


walk(record)

with open(keys_path, "w", encoding="utf-8") as handle:
    handle.write("json_path\tvalue_type\tvalue_preview\n")
    handle.write(
        f"__top_level__\t{top_level_type}\t"
        f"first_record_type={type(record).__name__}\n"
    )

    for path, value_type, preview in rows:
        handle.write(f"{path}\t{value_type}\t{preview}\n")

print(f"Top-level JSON type: {top_level_type}")
print(f"First record type: {type(record).__name__}")
print(f"First record saved: {output_path}")
print(f"Key inventory saved: {keys_path}")
PY

echo
echo "===== FIRST JSON RECORD ====="
python -m json.tool "$JSON_FIRST" |
sed -n '1,220p'

echo
echo "===== FIRST JSON RECORD KEY INVENTORY ====="
column -ts $'\t' "$JSON_KEYS" |
sed -n '1,220p'

echo
echo "===== CLUSTER BED FIRST 10 LINES ====="
gzip -cd "$CLUSTER_GZ" |
sed -n '1,10p' |
tee "$CLUSTER_FIRST"

echo
echo "===== CLUSTER BED FIELD COUNTS ====="
{
    printf 'field_count\tline_count\n'
    gzip -cd "$CLUSTER_GZ" |
    awk -F '\t' '{ count[NF]++ } END { for (n in count) print n "\t" count[n] }' |
    sort -n -k1,1
} > "$CLUSTER_FIELDS"

column -ts $'\t' "$CLUSTER_FIELDS"

echo
echo "===== CLUSTER BED TOTAL LINES ====="
gzip -cd "$CLUSTER_GZ" |
awk 'END { print NR }' |
tee "$CLUSTER_COUNT"

echo
echo "===== CLUSTER BED CONTIGS ====="
gzip -cd "$CLUSTER_GZ" |
cut -f1 |
sort -u -V |
tee "$CLUSTER_CONTIGS"

echo
echo "Output files:"
printf '%s\n' \
  "$JSON_FIRST" \
  "$JSON_KEYS" \
  "$JSON_PREVIEW" \
  "$CLUSTER_FIRST" \
  "$CLUSTER_FIELDS" \
  "$CLUSTER_COUNT" \
  "$CLUSTER_CONTIGS"
