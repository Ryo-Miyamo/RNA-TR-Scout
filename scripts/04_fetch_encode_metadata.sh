#!/usr/bin/env bash
set -euo pipefail

ACC="${1:?Usage: 04_fetch_encode_metadata.sh ENCSR_ACCESSION}"

source /mnt/intelssd/rnatr_project/config/paths.env

OUTDIR="$PROJECT_ROOT/metadata/encode/$ACC"
BASE_URL="https://www.encodeproject.org"

mkdir -p "$OUTDIR"

EXPERIMENT_JSON="$OUTDIR/${ACC}.experiment.json"
FASTQ_JSON="$OUTDIR/${ACC}.fastq_files.json"
SUMMARY_TSV="$OUTDIR/${ACC}.experiment_summary.tsv"
MANIFEST_TSV="$OUTDIR/${ACC}.fastq_manifest.tsv"

echo "Fetching experiment metadata: $ACC"

curl \
  --fail \
  --location \
  --retry 5 \
  --retry-delay 3 \
  --header 'Accept: application/json' \
  "$BASE_URL/experiments/$ACC/?format=json&frame=embedded" \
  --output "$EXPERIMENT_JSON"

jq empty "$EXPERIMENT_JSON"

echo "Fetching FASTQ file metadata"

curl \
  --fail \
  --location \
  --retry 5 \
  --retry-delay 3 \
  --header 'Accept: application/json' \
  "$BASE_URL/search/?type=File&dataset=%2Fexperiments%2F${ACC}%2F&file_format=fastq&format=json&limit=all&frame=embedded" \
  --output "$FASTQ_JSON"

jq empty "$FASTQ_JSON"

jq -r '
[
  ["field", "value"],
  ["accession", (.accession // "")],
  ["status", (.status // "")],
  ["assay_title", (.assay_title // "")],
  ["biosample_summary", (.biosample_summary // "")],
  ["description", (.description // "")],
  ["date_released", (.date_released // "")],
  ["doi", (.doi // "")]
]
| .[]
| @tsv
' "$EXPERIMENT_JSON" > "$SUMMARY_TSV"

jq -r '
[
  "accession",
  "status",
  "output_type",
  "file_format",
  "file_format_type",
  "biological_replicates",
  "technical_replicates",
  "run_type",
  "paired_end",
  "read_length",
  "read_count",
  "file_size",
  "md5sum",
  "submitted_file_name",
  "download_url"
],
(
  ."@graph"[]?
  |
  [
    (.accession // ""),
    (.status // ""),
    (.output_type // ""),
    (.file_format // ""),
    (.file_format_type // ""),
    (
      (.biological_replicates // [])
      | map(tostring)
      | join(",")
    ),
    (
      (.technical_replicates // [])
      | map(tostring)
      | join(",")
    ),
    (.run_type // ""),
    ((.paired_end // "") | tostring),
    ((.read_length // "") | tostring),
    ((.read_count // "") | tostring),
    ((.file_size // "") | tostring),
    (.md5sum // ""),
    (.submitted_file_name // ""),
    (
      if ((.href // "") | startswith("http"))
      then .href
      else "https://www.encodeproject.org" + (.href // "")
      end
    )
  ]
)
| @tsv
' "$FASTQ_JSON" > "$MANIFEST_TSV"

date -Is > "$OUTDIR/retrieved_at.txt"

sha256sum \
  "$EXPERIMENT_JSON" \
  "$FASTQ_JSON" \
  "$SUMMARY_TSV" \
  "$MANIFEST_TSV" \
  > "$OUTDIR/metadata.sha256"

echo
echo "===== EXPERIMENT SUMMARY ====="
column -t -s $'\t' "$SUMMARY_TSV"

echo
echo "===== FASTQ MANIFEST ====="
column -t -s $'\t' "$MANIFEST_TSV"

echo
printf "FASTQ file count: "
jq '."@graph" | length' "$FASTQ_JSON"

echo
echo "Metadata directory:"
echo "$OUTDIR"
