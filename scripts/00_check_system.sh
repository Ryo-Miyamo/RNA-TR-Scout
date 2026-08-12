#!/usr/bin/env bash
set -euo pipefail

echo "=== date ==="
date -Is

echo
echo "=== OS ==="
uname -a
if [[ -f /etc/os-release ]]; then
  cat /etc/os-release
fi

echo
echo "=== CPU / RAM ==="
nproc
free -h

echo
echo "=== mounted storage ==="
df -h /mnt/intelssd /mnt/mybookduo 2>&1 || true

echo
echo "=== package managers ==="
for x in micromamba mamba conda; do
  if command -v "$x" >/dev/null 2>&1; then
    echo "$x: $(command -v "$x")"
    "$x" --version || true
  else
    echo "$x: NOT FOUND"
  fi
done

echo
echo "=== pre-existing tools ==="
for x in minimap2 samtools bgzip tabix seqkit bedtools jq curl wget git; do
  if command -v "$x" >/dev/null 2>&1; then
    printf "%-12s %s\n" "$x" "$(command -v "$x")"
  else
    printf "%-12s %s\n" "$x" "NOT FOUND"
  fi
done
