#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
RELEASE_JSON="$CATDIR/github_release_v2.0.json"

ANNOTATION_NAME="TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.EH.with_annotations.json.gz"
CLUSTER_NAME="TRExplorer.variation_clusters_and_isolated_TRs_v2.hg38.TRGT.bed.gz"

mkdir -p "$CATDIR"

test -s "$RELEASE_JSON" || {
    echo "ERROR: release JSON not found: $RELEASE_JSON" >&2
    exit 1
}

download_and_verify() {
    local name="$1"
    local path="$CATDIR/$name"
    local url expected_size expected_digest actual_size actual_sha

    url="$(
        jq -r --arg name "$name" \
          '.assets[] | select(.name == $name) | .browser_download_url' \
          "$RELEASE_JSON"
    )"

    expected_size="$(
        jq -r --arg name "$name" \
          '.assets[] | select(.name == $name) | .size' \
          "$RELEASE_JSON"
    )"

    expected_digest="$(
        jq -r --arg name "$name" \
          '.assets[] | select(.name == $name) | .digest' \
          "$RELEASE_JSON"
    )"

    if [[ -z "$url" || "$url" == "null" ]]; then
        echo "ERROR: asset not found in release JSON: $name" >&2
        exit 1
    fi

    echo
    echo "===== DOWNLOAD ====="
    echo "Asset:        $name"
    echo "Expected size: $expected_size"
    echo "Digest:       $expected_digest"

    if [[ -s "$path" ]]; then
        echo "Existing file found; aria2c will verify/resume as needed."
    fi

    aria2c \
      --continue=true \
      --max-connection-per-server=4 \
      --split=4 \
      --min-split-size=100M \
      --file-allocation=none \
      --auto-file-renaming=false \
      --allow-overwrite=false \
      --dir="$CATDIR" \
      --out="$name" \
      "$url"

    actual_size="$(stat -c '%s' "$path")"
    actual_sha="$(sha256sum "$path" | awk '{print $1}')"

    echo
    echo "===== VERIFY ====="
    echo "Expected size: $expected_size"
    echo "Actual size:   $actual_size"
    echo "Expected SHA:  $expected_digest"
    echo "Actual SHA:    sha256:$actual_sha"

    [[ "$actual_size" == "$expected_size" ]] || {
        echo "ERROR: size mismatch for $name" >&2
        exit 1
    }

    [[ "sha256:$actual_sha" == "$expected_digest" ]] || {
        echo "ERROR: SHA256 mismatch for $name" >&2
        exit 1
    }

    gzip -t "$path"

    echo "Size: OK"
    echo "SHA256: OK"
    echo "gzip integrity: OK"
}

echo "===== DISK SPACE ====="
df -h "$CATDIR"

download_and_verify "$ANNOTATION_NAME"
download_and_verify "$CLUSTER_NAME"

sha256sum \
  "$CATDIR/$ANNOTATION_NAME" \
  "$CATDIR/$CLUSTER_NAME" \
  > "$CATDIR/TRExplorer_v2.annotation_and_clusters.sha256"

{
    printf 'asset\tbytes\tsha256\tlocal_path\n'
    for name in "$ANNOTATION_NAME" "$CLUSTER_NAME"; do
        path="$CATDIR/$name"
        printf '%s\t%s\t%s\t%s\n' \
          "$name" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$CATDIR/TRExplorer_v2.annotation_and_clusters.manifest.tsv"

echo
echo "===== COMPLETE ====="
column -ts $'\t' \
  "$CATDIR/TRExplorer_v2.annotation_and_clusters.manifest.tsv"
