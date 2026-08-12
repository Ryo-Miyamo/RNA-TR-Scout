#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/mnt/intelssd/rnatr_project}"
OUT="${PROJECT_ROOT}/refs/gencode_v50"
BASE="https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_50"

mkdir -p "${OUT}"
cd "${OUT}"

download() {
  local url="$1"
  local out="$2"
  if [[ -s "${out}" ]]; then
    echo "SKIP existing: ${out}"
  else
    echo "DOWNLOAD: ${url}"
    aria2c -x 8 -s 8 --continue=true --max-tries=10 \
      --retry-wait=5 -o "${out}" "${url}"
  fi
}

download "${BASE}/GRCh38.primary_assembly.genome.fa.gz" \
         "GRCh38.primary_assembly.genome.fa.gz"
download "${BASE}/gencode.v50.primary_assembly.annotation.gtf.gz" \
         "gencode.v50.primary_assembly.annotation.gtf.gz"
download "${BASE}/gencode.v50.polyAs.gtf.gz" \
         "gencode.v50.polyAs.gtf.gz"

curl -fL --retry 5 --retry-delay 3 \
  "${BASE}/MD5SUMS" -o MD5SUMS || {
    echo "WARNING: MD5SUMS could not be downloaded; continuing with local SHA256." >&2
  }

if [[ -s MD5SUMS ]]; then
  grep -E 'GRCh38.primary_assembly.genome.fa.gz|gencode.v50.primary_assembly.annotation.gtf.gz|gencode.v50.polyAs.gtf.gz' \
    MD5SUMS > MD5SUMS.selected || true
  if [[ -s MD5SUMS.selected ]]; then
    md5sum -c MD5SUMS.selected
  fi
fi

sha256sum \
  GRCh38.primary_assembly.genome.fa.gz \
  gencode.v50.primary_assembly.annotation.gtf.gz \
  gencode.v50.polyAs.gtf.gz > SHA256SUMS.local

if [[ ! -s GRCh38.primary_assembly.genome.fa ]]; then
  echo "Decompressing genome FASTA..."
  pigz -dc GRCh38.primary_assembly.genome.fa.gz > GRCh38.primary_assembly.genome.fa
fi

if [[ ! -s gencode.v50.primary_assembly.annotation.gtf ]]; then
  pigz -dc gencode.v50.primary_assembly.annotation.gtf.gz \
    > gencode.v50.primary_assembly.annotation.gtf
fi

if [[ ! -s gencode.v50.polyAs.gtf ]]; then
  pigz -dc gencode.v50.polyAs.gtf.gz > gencode.v50.polyAs.gtf
fi

samtools faidx GRCh38.primary_assembly.genome.fa
minimap2 -d GRCh38.primary_assembly.genome.mmi \
  GRCh38.primary_assembly.genome.fa

{
  date -Is
  echo "GENCODE release: 50"
  minimap2 --version
  samtools --version | head -n 2
  sha256sum GRCh38.primary_assembly.genome.fa
  sha256sum gencode.v50.primary_assembly.annotation.gtf
  sha256sum gencode.v50.polyAs.gtf
} > reference_manifest.txt

echo
echo "GENCODE v50 ready in: ${OUT}"
ls -lh
