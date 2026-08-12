#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/mnt/intelssd/rnatr_project}"
RAW_ROOT="${RAW_ROOT:-/media/tokushimaneuro02/T9/rnatr_data}"

mkdir -p \
  "${PROJECT_ROOT}"/{code,config,env,metadata,refs,catalogs,scripts,results,logs,tmp,qc} \
  "${RAW_ROOT}"/{raw,downloads}

cat > "${PROJECT_ROOT}/config/paths.env" <<EOF
export PROJECT_ROOT="${PROJECT_ROOT}"
export RAW_ROOT="${RAW_ROOT}"
export REF_ROOT="${PROJECT_ROOT}/refs"
export CATALOG_ROOT="${PROJECT_ROOT}/catalogs"
export METADATA_ROOT="${PROJECT_ROOT}/metadata"
export RESULT_ROOT="${PROJECT_ROOT}/results"
export TMPDIR="${PROJECT_ROOT}/tmp"
EOF

cp -f "$(dirname "$0")"/*.sh "${PROJECT_ROOT}/scripts/" 2>/dev/null || true
cp -f "$(dirname "$0")"/environment.yml "${PROJECT_ROOT}/env/" 2>/dev/null || true

echo "Created:"
echo "  PROJECT_ROOT=${PROJECT_ROOT}"
echo "  RAW_ROOT=${RAW_ROOT}"
echo
echo "Configuration:"
echo "  ${PROJECT_ROOT}/config/paths.env"
