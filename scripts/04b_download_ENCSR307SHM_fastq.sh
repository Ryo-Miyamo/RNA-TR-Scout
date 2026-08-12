#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

EXP="ENCSR307SHM"
FILE_ACC="ENCFF260PGB"
EXPECTED_SIZE="8995223210"
EXPECTED_MD5="23270f6b994db147df2f2f4c53f8358b"

OUTDIR="$RAW_ROOT/downloads/$EXP"
FINAL="$OUTDIR/${FILE_ACC}.fastq.gz"
URL="https://www.encodeproject.org/files/${FILE_ACC}/@@download/${FILE_ACC}.fastq.gz"

mkdir -p "$OUTDIR"

echo "===== DOWNLOAD TARGET ====="
echo "Experiment:    $EXP"
echo "File:          $FILE_ACC"
echo "URL:           $URL"
echo "Destination:   $FINAL"
echo "Expected size: $EXPECTED_SIZE"
echo "Expected MD5:  $EXPECTED_MD5"
echo

df -h "$RAW_ROOT"

echo
echo "===== DOWNLOAD ====="

aria2c \
  --continue=true \
  --max-connection-per-server=4 \
  --split=4 \
  --min-split-size=100M \
  --file-allocation=none \
  --auto-file-renaming=false \
  --allow-overwrite=false \
  --dir="$OUTDIR" \
  --out="${FILE_ACC}.fastq.gz" \
  "$URL"

echo
echo "===== FILE SIZE CHECK ====="

ACTUAL_SIZE="$(stat -c '%s' "$FINAL")"

echo "Expected: $EXPECTED_SIZE"
echo "Actual:   $ACTUAL_SIZE"

if [[ "$ACTUAL_SIZE" != "$EXPECTED_SIZE" ]]; then
    echo "ERROR: file-size mismatch" >&2
    exit 1
fi

echo "File size: OK"

echo
echo "===== MD5 CHECK ====="

ACTUAL_MD5="$(md5sum "$FINAL" | awk '{print $1}')"

echo "Expected: $EXPECTED_MD5"
echo "Actual:   $ACTUAL_MD5"

if [[ "$ACTUAL_MD5" != "$EXPECTED_MD5" ]]; then
    echo "ERROR: MD5 mismatch" >&2
    exit 1
fi

echo "MD5: OK"

echo
echo "===== GZIP CHECK ====="

gzip -t "$FINAL"
echo "gzip integrity: OK"

echo
echo "===== COMPLETE ====="

ls -lh "$FINAL"
date -Is
