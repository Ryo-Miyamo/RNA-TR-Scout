#!/usr/bin/env bash
set -euo pipefail

PROJECT_ENV="/mnt/intelssd/rnatr_project/config/paths.env"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
VERSION="v0.1.2_caller_parity"

if [[ ! -f "$PROJECT_ENV" ]]; then
  echo "ERROR: missing $PROJECT_ENV" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$PROJECT_ENV"

if [[ "${PROJECT_ROOT:-}" != "/mnt/intelssd/rnatr_project" ]]; then
  echo "ERROR: unexpected PROJECT_ROOT: ${PROJECT_ROOT:-<unset>}" >&2
  exit 1
fi

OUT="$PROJECT_ROOT/qc/15_stage15a_contract_preflight/$RUN_ID/$VERSION"
CONSOLE="$HOME/Downloads/rnatr_stage15a0_caller_parity_v0.1.0.console.log"
BUNDLE="$HOME/Downloads/rnatr_stage15a0_caller_parity_output_v0.1.0.tar.gz"
SHA_FILE="${BUNDLE}.sha256"

QC="$OUT/stage15a0_caller_parity_resolution.qc.tsv"
LOG="$OUT/stage15a0_caller_parity_resolution.log"

for f in "$QC" "$LOG" "$CONSOLE"; do
  if [[ ! -s "$f" ]]; then
    echo "ERROR: required file missing or empty: $f" >&2
    exit 1
  fi
done

AUDIT_STATUS="$(awk -F '\t' '$1=="audit_status"{print $2}' "$QC" | tail -n1)"
NEXT_GATE="$(awk -F '\t' '$1=="next_gate"{print $2}' "$QC" | tail -n1)"

if [[ "$AUDIT_STATUS" != "PASS" ]]; then
  echo "ERROR: audit_status is not PASS: $AUDIT_STATUS" >&2
  exit 1
fi

if [[ "$NEXT_GATE" != "READY_TO_FREEZE_STAGE15A_EXECUTION_BUNDLE" ]]; then
  echo "ERROR: unexpected next_gate: $NEXT_GATE" >&2
  exit 1
fi

cp -f "$CONSOLE" "$OUT/"

rm -f "$BUNDLE" "$SHA_FILE"

tar -czf "$BUNDLE" -C "$OUT" .
sha256sum "$BUNDLE" | tee "$SHA_FILE"

echo
echo "===== Stage 15A0 parity package ====="
echo "audit_status: $AUDIT_STATUS"
echo "next_gate:    $NEXT_GATE"
echo
echo "Bundle:"
echo "$BUNDLE"
echo
echo "SHA file:"
echo "$SHA_FILE"
echo
echo "Contents:"
tar -tzf "$BUNDLE" | sort
echo
echo "DONE"
