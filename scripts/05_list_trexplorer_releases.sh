#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/mnt/intelssd/rnatr_project}"
OUT="${PROJECT_ROOT}/metadata/trexplorer"
API="https://api.github.com/repos/broadinstitute/trexplorer-catalog/releases"

mkdir -p "${OUT}"
cd "${OUT}"

curl -fL --retry 8 --retry-delay 5 \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "${API}" -o releases.json

{
  printf "tag\trelease_name\tpublished_at\tasset_name\tasset_size\tbrowser_download_url\n"
  jq -r '
    .[] as $r |
    ($r.assets // [])[] |
    [
      ($r.tag_name // ""),
      ($r.name // ""),
      ($r.published_at // ""),
      (.name // ""),
      ((.size // 0) | tostring),
      (.browser_download_url // "")
    ] | @tsv
  ' releases.json
} > release_assets.tsv

echo "=== TRExplorer catalog release assets ==="
column -t -s $'\t' release_assets.tsv | sed -n '1,120p'

echo
echo "Saved: ${OUT}/release_assets.tsv"
echo "Do not auto-select an asset until the names and build are inspected."
