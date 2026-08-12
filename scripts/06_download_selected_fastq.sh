#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/mnt/intelssd/rnatr_project}"
RAW_ROOT="${RAW_ROOT:-/media/tokushimaneuro02/T9/rnatr_data}"
EXP="${1:-ENCSR307SHM}"
META="${PROJECT_ROOT}/metadata/encode/${EXP}/files.tsv"
SELECT="${PROJECT_ROOT}/metadata/encode/${EXP}/selected_fastq_accessions.txt"
OUT="${RAW_ROOT}/raw/${EXP}"
BASE="https://www.encodeproject.org"

[[ -s "${META}" ]] || { echo "Missing metadata: ${META}" >&2; exit 1; }
[[ -s "${SELECT}" ]] || {
  echo "Create ${SELECT}, one ENCODE file accession per line." >&2
  exit 1
}

mkdir -p "${OUT}"

while read -r acc; do
  [[ -z "${acc}" || "${acc}" =~ ^# ]] && continue

  row="$(awk -F '\t' -v a="${acc}" 'NR>1 && $1==a {print; exit}' "${META}")"
  [[ -n "${row}" ]] || { echo "Accession not found: ${acc}" >&2; exit 1; }

  href="$(printf '%s\n' "${row}" | awk -F '\t' '{print $12}')"
  md5="$(printf '%s\n' "${row}" | awk -F '\t' '{print $11}')"

  [[ -n "${href}" ]] || { echo "No href for ${acc}" >&2; exit 1; }
  url="${BASE}${href}"
  name="$(basename "${href}")"
  dest="${OUT}/${name}"

  echo "Downloading ${acc}: ${url}"
  aria2c -x 8 -s 8 --continue=true --max-tries=10 \
    --retry-wait=5 -d "${OUT}" -o "${name}" "${url}"

  if [[ -n "${md5}" ]]; then
    echo "${md5}  ${dest}" | md5sum -c -
  fi
done < "${SELECT}"

echo "Downloaded files:"
ls -lh "${OUT}"
