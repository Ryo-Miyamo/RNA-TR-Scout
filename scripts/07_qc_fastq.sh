#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/mnt/intelssd/rnatr_project}"
RAW_ROOT="${RAW_ROOT:-/media/tokushimaneuro02/T9/rnatr_data}"
EXP="${1:-ENCSR307SHM}"
IN="${RAW_ROOT}/raw/${EXP}"
OUT="${PROJECT_ROOT}/qc/${EXP}"

mkdir -p "${OUT}"
shopt -s nullglob
files=("${IN}"/*.fastq.gz "${IN}"/*.fq.gz)

if (( ${#files[@]} == 0 )); then
  echo "No FASTQ.GZ found in ${IN}" >&2
  exit 1
fi

seqkit stats -a -T -j "$(nproc)" "${files[@]}" > "${OUT}/seqkit_stats.tsv"
sha256sum "${files[@]}" > "${OUT}/SHA256SUMS.fastq"

echo "=== seqkit stats ==="
column -t -s $'\t' "${OUT}/seqkit_stats.tsv"
echo
echo "QC saved in: ${OUT}"
