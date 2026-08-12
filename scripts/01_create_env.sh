#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/environment.yml"
ENV_NAME="rnatr-v03"

if command -v micromamba >/dev/null 2>&1; then
  PM=micromamba
elif command -v mamba >/dev/null 2>&1; then
  PM=mamba
elif command -v conda >/dev/null 2>&1; then
  PM=conda
else
  echo "ERROR: micromamba / mamba / conda が見つかりません。" >&2
  echo "まず 00_check_system.sh の出力を確認してください。" >&2
  exit 1
fi

echo "Using package manager: ${PM}"
"${PM}" env create -f "${ENV_FILE}" || {
  echo "Environment creation failed. If the environment already exists, run:" >&2
  echo "  ${PM} env update -n ${ENV_NAME} -f ${ENV_FILE} --prune" >&2
  exit 1
}

echo
echo "Environment created: ${ENV_NAME}"
echo "Activate with:"
echo "  conda activate ${ENV_NAME}"
