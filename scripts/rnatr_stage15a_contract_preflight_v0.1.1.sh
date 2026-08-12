#!/usr/bin/env bash
set -Eeuo pipefail

# RNA-TR-Scout Stage 15A0
# Read-only contract-completeness and replay-readiness audit.
# Writes only under qc/15_stage15a_contract_preflight.

STAGE_VERSION="rnatr_stage15a_contract_preflight_v0.1.1"
PROJECT_ROOT="${PROJECT_ROOT:-/mnt/intelssd/rnatr_project}"
RUN_ID="${RUN_ID:-ENCSR307SHM_pilot100k_mm2splice_v1}"
SAMPLE_ID="${SAMPLE_ID:-ENCSR307SHM}"
EXPECTED_BAM_SHA256="0b1ec4e051ac1067fe7207c076e1eff10e45335b49190902944496a9461300e6"

PATHS_ENV="$PROJECT_ROOT/config/paths.env"
if [[ ! -s "$PATHS_ENV" ]]; then
    echo "ERROR: missing paths.env: $PATHS_ENV" >&2
    exit 2
fi

# Use the project environment without changing the active pipeline.
if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
    conda activate rnatr-v03
fi
# shellcheck disable=SC1090
source "$PATHS_ENV"

: "${PROJECT_ROOT:?PROJECT_ROOT is not set after sourcing paths.env}"
: "${RAW_ROOT:?RAW_ROOT is not set after sourcing paths.env}"
: "${CATALOG_ROOT:?CATALOG_ROOT is not set after sourcing paths.env}"

OUTDIR="$PROJECT_ROOT/qc/15_stage15a_contract_preflight/$RUN_ID/v0.1.1"
mkdir -p "$OUTDIR"
LOG="$OUTDIR/stage15a_contract_preflight.log"
exec > >(tee "$LOG") 2>&1

ARTIFACTS="$OUTDIR/stage15a_required_artifacts.tsv"
DISCOVERED="$OUTDIR/stage15a_discovered_components.tsv"
ENVIRONMENT="$OUTDIR/stage15a_environment.tsv"
FROZEN_AUDIT="$OUTDIR/stage15a_frozen_artifacts_and_lockstep.qc.tsv"
SUMMARY="$OUTDIR/stage15a_contract_preflight.qc.tsv"

printf 'role\tcritical\tpath\texists\tbytes\tobserved_sha256\texpected_sha256\tstatus\n' > "$ARTIFACTS"
printf 'category\tpath\tbytes\tsha256\n' > "$DISCOVERED"
printf 'metric\tvalue\n' > "$ENVIRONMENT"

sha256_or_dot() {
    local path="$1"
    if [[ -f "$path" ]]; then
        sha256sum "$path" | awk '{print $1}'
    else
        printf '.\n'
    fi
}

bytes_or_zero() {
    local path="$1"
    if [[ -e "$path" ]]; then
        stat -c '%s' "$path"
    else
        printf '0\n'
    fi
}

record_artifact() {
    local role="$1"
    local critical="$2"
    local path="$3"
    local expected_sha="${4:-.}"
    local exists=false
    local observed='.'
    local bytes=0
    local status

    if [[ -s "$path" ]]; then
        exists=true
        bytes="$(bytes_or_zero "$path")"
        observed="$(sha256_or_dot "$path")"
        if [[ "$expected_sha" != "." && "$observed" != "$expected_sha" ]]; then
            status="SHA_MISMATCH"
        elif [[ "$expected_sha" != "." ]]; then
            status="PASS"
        else
            status="PRESENT_UNPINNED"
        fi
    else
        status="MISSING_OR_EMPTY"
    fi

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$role" "$critical" "$path" "$exists" "$bytes" \
        "$observed" "$expected_sha" "$status" >> "$ARTIFACTS"
}

record_discovered_file() {
    local category="$1"
    local path="$2"
    [[ -f "$path" ]] || return 0
    printf '%s\t%s\t%s\t%s\n' \
        "$category" "$path" "$(stat -c '%s' "$path")" \
        "$(sha256sum "$path" | awk '{print $1}')" >> "$DISCOVERED"
}

first_line_version() {
    local tool="$1"
    if command -v "$tool" >/dev/null 2>&1; then
        ("$tool" --version 2>&1 || true) | head -n 1 | tr '\t' ' '
    else
        printf 'NOT_FOUND\n'
    fi
}

echo "===== Stage 15A0 contract preflight ====="
echo "stage_version: $STAGE_VERSION"
echo "project_root:  $PROJECT_ROOT"
echo "run_id:        $RUN_ID"
echo "output:        $OUTDIR"

# -----------------------------------------------------------------------------
# 1. Exact artifacts already frozen by Stage 14L2 / handover bundle
# -----------------------------------------------------------------------------
BAM="$PROJECT_ROOT/results/11_mapping/$RUN_ID/${RUN_ID}.sorted.bam"
BAI="${BAM}.bai"
MAP_RUN_MANIFEST="$PROJECT_ROOT/results/11_mapping/$RUN_ID/run_manifest.tsv"
CANDIDATE_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

TARGET_BED="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz"
TARGET_TBI="${TARGET_BED}.tbi"
TARGET_TSV="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.tsv.gz"
ANALYSIS_REGIONS="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/TRExplorer_v2.rnatr_pilot_analysis_regions.final.tsv.gz"
DISEASE_REGIONS="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/STRchive_disease_regions.final.tsv.gz"

SCHEMA_V03="$PROJECT_ROOT/config/evidence_schema/v0.3/schema/rnatr_v03_table_schema.json"
VALIDATOR_V03_EFFECTIVE="$PROJECT_ROOT/config/evidence_schema/v0.3/rnatr_v03_validate_tsv.py"
VALIDATOR_V03_LEDGER="$PROJECT_ROOT/config/evidence_schema/v0.3/patches/validator_v0.3.1/rnatr_v03_validate_tsv_validator_v0.3.1.py"
SCHEMA_DIR="$PROJECT_ROOT/config/evidence_schema/v0.4.2"
SCHEMA_V042="$SCHEMA_DIR/schema/rnatr_v04_table_schema.json"
SCHEMA_FREEZE_MANIFEST="$PROJECT_ROOT/metadata/evidence_schema/evidence_schema_v0.4.2.freeze_manifest.tsv"
VALIDATION_SCHEMA_DIR="$PROJECT_ROOT/validation/schema_v0.4.2"
VALIDATOR_V042_TSV="$SCHEMA_DIR/rnatr_v042_validate_tsv.py"
VALIDATOR_V042_PACKAGE="$SCHEMA_DIR/rnatr_v042_validate_package.py"
SCHEMA_V042_QC="$PROJECT_ROOT/qc/14_schema_v042_flank_uniqueness_patch/$RUN_ID/v0.1.0/schema_v042_flank_uniqueness_patch.qc.tsv"

CALLER_V041="$PROJECT_ROOT/src/rnatr_scout/general_caller/native_v0.4.1/rnatr_general_repeat_caller_ref_v0.4.1.py"
CALLER_V021="$(dirname "$CALLER_V041")/rnatr_general_repeat_caller_ref_v0.2.1.py"
MATERIALIZER_V012="$PROJECT_ROOT/src/rnatr_scout/materialization/rnatr_materialize_native_v041_to_evidence_v042_v0.1.2.py"
RELEASE_GATES="$PROJECT_ROOT/validation/release_gates_v0.2.2.tsv"
ORIGINAL_CALLER_INTEGRATION_DRIVER="$PROJECT_ROOT/results/14_general_caller_100k_integration/$RUN_ID/v0.1.0/run_general_caller_100k_integration.py"
DETERMINISTIC_CALLER_ROOT="$PROJECT_ROOT/results/14_deterministic_general_caller/$RUN_ID/v0.4.1_validation_v0.1.0"
STAGE14G_NATIVE_CALLER_INTEGRATION_DRIVER="$DETERMINISTIC_CALLER_ROOT/integration_native_100k/driver.py"
PROMOTED_CALLER_INTEGRATION_DRIVER="$PROJECT_ROOT/results/14_v041_schema_v041_100k_end_to_end/$RUN_ID/v0.1.0/run_native_v041_100k.py"
CALLER_INTEGRATION_DRIVER="$PROMOTED_CALLER_INTEGRATION_DRIVER"
CALLER_INTEGRATION_QC="$DETERMINISTIC_CALLER_ROOT/integration_native_100k/general_repeat_integration.qc.tsv"
DETERMINISTIC_REFERENCE_CALLS="$DETERMINISTIC_CALLER_ROOT/integration_native_100k/general_repeat_calls.v0.4.0.tsv.gz"
DETERMINISTIC_CALLER_QC="$PROJECT_ROOT/qc/14_deterministic_general_caller/$RUN_ID/v0.4.1_validation_v0.1.0/deterministic_v041_validation.qc.tsv"

STAGE14K2_QC="$PROJECT_ROOT/qc/14_v041_schema_v042_100k_end_to_end/$RUN_ID/v0.1.1/stage14k2_100k_end_to_end.qc.tsv"
FROZEN_PACKAGE="$PROJECT_ROOT/results/14_v041_schema_v042_100k_end_to_end/$RUN_ID/v0.1.1/package"
FROZEN_PACKAGE_MANIFEST="$FROZEN_PACKAGE/package_manifest.tsv"
FAILURE_CONTRACT="$PROJECT_ROOT/results/14_schema_v042_promotion/$RUN_ID/v0.1.2/FAILURE_CODE_QC_FLAGS_MATERIALIZATION_CONTRACT_v0.1.0.md"
FAILURE_AUDIT="$PROJECT_ROOT/results/14_schema_v042_promotion/$RUN_ID/v0.1.2/failure_materialization_semantics.audit.tsv"

# Read-only format checks. Failures are counted as critical preflight failures.
FORMAT_QC="$OUTDIR/stage15a_input_format_checks.qc.tsv"
{
    printf 'metric\tvalue\n'
    if command -v samtools >/dev/null 2>&1 && samtools quickcheck -v "$BAM" >/dev/null 2>&1; then
        printf 'bam_quickcheck\tPASS\n'
    else
        printf 'bam_quickcheck\tFAIL\n'
    fi
    if command -v samtools >/dev/null 2>&1 && samtools idxstats "$BAM" >/dev/null 2>&1; then
        printf 'bam_index_readable\tPASS\n'
    else
        printf 'bam_index_readable\tFAIL\n'
    fi
    if gzip -t "$CANDIDATE_FASTQ" >/dev/null 2>&1; then
        printf 'candidate_fastq_gzip\tPASS\n'
    else
        printf 'candidate_fastq_gzip\tFAIL\n'
    fi
} > "$FORMAT_QC"

record_artifact TARGET_100K_BAM true "$BAM" "$EXPECTED_BAM_SHA256"
record_artifact TARGET_100K_BAI true "$BAI"
record_artifact MAPPING_RUN_MANIFEST true "$MAP_RUN_MANIFEST"
record_artifact CANDIDATE_RAW_FASTQ true "$CANDIDATE_FASTQ"
record_artifact MAPPING_TARGET_BED true "$TARGET_BED"
record_artifact MAPPING_TARGET_TBI true "$TARGET_TBI"
record_artifact MAPPING_TARGET_TSV true "$TARGET_TSV"
record_artifact ANALYSIS_REGIONS true "$ANALYSIS_REGIONS"
record_artifact DISEASE_REGIONS true "$DISEASE_REGIONS"
record_artifact SCHEMA_V03 true "$SCHEMA_V03"
record_artifact VALIDATOR_V03_EFFECTIVE true "$VALIDATOR_V03_EFFECTIVE"
record_artifact VALIDATOR_V03_LEDGER true "$VALIDATOR_V03_LEDGER" "10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9"
record_artifact SCHEMA_V042 true "$SCHEMA_V042"
record_artifact SCHEMA_V042_FREEZE_MANIFEST true "$SCHEMA_FREEZE_MANIFEST" "8077691e0498d2ad8c3f5490d295832b38100391ac5ccd34c72eea064fcf493c"
record_artifact SCHEMA_V042_QC true "$SCHEMA_V042_QC" "b278ae3816aecd0a0a862aad21f6077376f5517c99a41059138c00e1787b078c"
record_artifact VALIDATOR_V042_TSV true "$VALIDATOR_V042_TSV"
record_artifact VALIDATOR_V042_PACKAGE true "$VALIDATOR_V042_PACKAGE"
record_artifact GENERAL_CALLER_V041 true "$CALLER_V041" "d5a2e0545afa5d97026c3a6ac0be6bc355e87f4c130bc512b0b3bf9a5bf32351"
record_artifact GENERAL_CALLER_V021_DEPENDENCY true "$CALLER_V021"
record_artifact MATERIALIZER_V012 true "$MATERIALIZER_V012" "18a67ef312e74257549570ae81a6cca364055240f519d29dc7664e2ea1c429ea"
record_artifact RELEASE_GATES_V022 true "$RELEASE_GATES" "f3c390b48a46bd2ef8b1e8b272ee65b2afad93f3a9cd7135db67aa2aefac354b"
record_artifact ORIGINAL_CALLER_INTEGRATION_DRIVER false "$ORIGINAL_CALLER_INTEGRATION_DRIVER"
record_artifact STAGE14G_NATIVE_CALLER_INTEGRATION_DRIVER false "$STAGE14G_NATIVE_CALLER_INTEGRATION_DRIVER"
record_artifact PROMOTED_NATIVE_V041_CALLER_INTEGRATION_DRIVER true "$CALLER_INTEGRATION_DRIVER"
record_artifact NATIVE_V041_CALLER_INTEGRATION_QC true "$CALLER_INTEGRATION_QC"
record_artifact DETERMINISTIC_REFERENCE_CALLS true "$DETERMINISTIC_REFERENCE_CALLS"
record_artifact DETERMINISTIC_CALLER_VALIDATION_QC true "$DETERMINISTIC_CALLER_QC"
record_artifact STAGE14K2_QC true "$STAGE14K2_QC" "1a5371656f5a8f768b27da879fc7cfad0f1c2b25bf9da893c38e6c62c23789b9"
record_artifact FROZEN_PACKAGE_MANIFEST true "$FROZEN_PACKAGE_MANIFEST" "352a0d74bdb6968d1d5e0f4a7f7e0f033d66f55b641480e6a7d289c8b2507246"
record_artifact FAILURE_MATERIALIZATION_CONTRACT true "$FAILURE_CONTRACT" "d973abc94f6863dc09ca6e4ab4b818841e34652c34283b6929a626e72b653c71"
record_artifact FAILURE_MATERIALIZATION_AUDIT true "$FAILURE_AUDIT" "66e870fb318502aa2dff0f4bd7cf9be3740e28a10401643dc4a5a96773604c2e"

# Frozen active upstream scripts.
record_artifact ACTIVE_11B true "$PROJECT_ROOT/scripts/11b_extract_alignment_segments_and_target_candidates.sh" "e00bdaad48080d7cfed01e1b961e0617af0f2239e014cd6fe8924460aa9afd56"
record_artifact ACTIVE_11D3 true "$PROJECT_ROOT/scripts/11d3_project_targets_to_raw_reads_secondary_seq_fixed.sh" "9df2998915e49da27ecf80f24a733d55a498c2ba32b278df881fdefa901a83e2"
record_artifact ACTIVE_11E true "$PROJECT_ROOT/scripts/11e_prepare_motif_scan_jobs.sh" "2cc13e2b95711e0d21c05eba1bec3ec26e249d3ec3e80f6ebce4c8157245038a"

# Record every file named by the v0.4.2 freeze manifest and package manifest.
# The schema freeze manifest uses logical relative roots; resolve them exactly as
# Stage 14K2 did instead of interpreting them relative to the current directory.
python - \
    "$SCHEMA_FREEZE_MANIFEST" \
    "$FROZEN_PACKAGE_MANIFEST" \
    "$ARTIFACTS" \
    "$PROJECT_ROOT" \
    "$SCHEMA_DIR" \
    "$VALIDATION_SCHEMA_DIR" <<'PY'
from __future__ import annotations
import csv, hashlib, sys
from pathlib import Path

schema_manifest = Path(sys.argv[1])
package_manifest = Path(sys.argv[2])
out = Path(sys.argv[3])
project_root = Path(sys.argv[4])
schema_root = Path(sys.argv[5])
validation_root = Path(sys.argv[6])

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def append(role: str, path: Path, expected: str | None, critical: str = 'true') -> None:
    exists = path.is_file() and path.stat().st_size > 0
    observed = sha(path) if exists else '.'
    size = path.stat().st_size if exists else 0
    if not exists:
        status = 'MISSING_OR_EMPTY'
    elif expected and observed != expected:
        status = 'SHA_MISMATCH'
    elif expected:
        status = 'PASS'
    else:
        status = 'PRESENT_UNPINNED'
    with out.open('a', encoding='utf-8', newline='') as handle:
        w = csv.writer(handle, delimiter='\t', lineterminator='\n')
        w.writerow([role, critical, str(path), str(exists).lower(), size, observed, expected or '.', status])

def resolve_schema_member(text: str) -> Path:
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    parts = candidate.parts
    if parts and parts[0] == 'evidence_schema_v0.4.2':
        return schema_root.joinpath(*parts[1:])
    if parts and parts[0] == 'validation_schema_v0.4.2':
        return validation_root.joinpath(*parts[1:])
    return project_root / candidate

if schema_manifest.is_file():
    with schema_manifest.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))
    for i, row in enumerate(rows, 1):
        ptxt = row.get('path') or row.get('file') or row.get('artifact_path')
        expected = row.get('sha256') or row.get('file_sha256')
        if ptxt:
            append(
                f'SCHEMA_FREEZE_MEMBER_{i:03d}',
                resolve_schema_member(ptxt),
                expected,
            )

if package_manifest.is_file():
    with package_manifest.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))
    for i, row in enumerate(rows, 1):
        ptxt = row.get('path')
        expected = row.get('sha256')
        if ptxt:
            append(f'FROZEN_PACKAGE_MEMBER_{i:02d}', Path(ptxt), expected)
PY

# Native dependencies/extensions colocated with the caller are part of the executable contract.
CALLER_DIR="$(dirname "$CALLER_V041")"
if [[ -d "$CALLER_DIR" ]]; then
    while IFS= read -r path; do
        record_discovered_file CALLER_RUNTIME_DEPENDENCY "$path"
    done < <(find "$CALLER_DIR" -maxdepth 2 -type f \( -name '*.py' -o -name '*.so' -o -name '*.json' \) -print | sort)
fi

# -----------------------------------------------------------------------------
# 2. Freeze the exact Stage 14 glue and inspect its executable contract.
# The driver and v0.4.2 validators now have exact host paths. Their observed
# SHA-256 values are captured above; Stage 15A1 will copy them read-only into the
# isolated execution bundle and pin those observed hashes.
# -----------------------------------------------------------------------------
record_discovered_file ORIGINAL_CALLER_INTEGRATION_DRIVER "$ORIGINAL_CALLER_INTEGRATION_DRIVER"
record_discovered_file STAGE14G_NATIVE_CALLER_INTEGRATION_DRIVER "$STAGE14G_NATIVE_CALLER_INTEGRATION_DRIVER"
record_discovered_file PROMOTED_NATIVE_V041_CALLER_INTEGRATION_DRIVER "$CALLER_INTEGRATION_DRIVER"
record_discovered_file NATIVE_V041_CALLER_INTEGRATION_QC "$CALLER_INTEGRATION_QC"
record_discovered_file VALIDATOR_V042_TSV "$VALIDATOR_V042_TSV"
record_discovered_file VALIDATOR_V042_PACKAGE "$VALIDATOR_V042_PACKAGE"

# Non-critical provenance producers are discovered for audit only. Their absence
# does not block Stage 15A because the executable driver/validators are pinned.
for path in \
    "$PROJECT_ROOT/scripts/14k2_patch_best_caller_version_and_resume_v0.1.0.sh" \
    "$PROJECT_ROOT/scripts/14l2_finalize_schema_v042_promotion_v0.1.0.sh"
do
    [[ -f "$path" ]] && record_discovered_file STAGE14_PRODUCER "$path"
done

DRIVER_CONTRACT="$OUTDIR/stage15a_caller_driver_contract.qc.tsv"
python - "$CALLER_INTEGRATION_DRIVER" "$DRIVER_CONTRACT" <<'PY'
from __future__ import annotations
import csv, sys
from pathlib import Path

source = Path(sys.argv[1])
out = Path(sys.argv[2])
text = source.read_text(encoding='utf-8') if source.is_file() else ''
checks = [
    ('driver_present', source.is_file() and source.stat().st_size > 0),
    ('cli_project_root', '--project-root' in text),
    ('cli_outdir', '--outdir' in text),
    ('cli_workers', '--workers' in text),
    ('output_general_calls_v040', 'general_repeat_calls.v0.4.0.tsv.gz' in text),
    ('motif_jobs_dependency', '11_motif_jobs' in text or 'motif_scan_jobs.tsv.gz' in text),
    ('projection_window_dependency', 'rnatr_target_windows' in text or '11_projection' in text),
    ('caller_path_patch_anchor', 'general_repeat_caller' in text),
    ('native_v041_caller_anchor', 'native_v0.4.1' in text or 'rnatr_general_repeat_caller_ref_v0.4.1.py' in text),
]
with out.open('w', encoding='utf-8', newline='') as handle:
    writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
    writer.writerow(['metric', 'value'])
    for key, value in checks:
        writer.writerow([key, str(bool(value)).lower()])
    writer.writerow(['all_required_checks_pass', str(all(v for _, v in checks)).lower()])
PY

# -----------------------------------------------------------------------------
# 3. Environment and capacity audit
# -----------------------------------------------------------------------------
{
    printf 'stage_version\t%s\n' "$STAGE_VERSION"
    printf 'timestamp_utc\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'project_root\t%s\n' "$PROJECT_ROOT"
    printf 'raw_root\t%s\n' "$RAW_ROOT"
    printf 'catalog_root\t%s\n' "$CATALOG_ROOT"
    printf 'run_id\t%s\n' "$RUN_ID"
    printf 'sample_id\t%s\n' "$SAMPLE_ID"
    printf 'hostname\t%s\n' "$(hostname)"
    printf 'kernel\t%s\n' "$(uname -srmo | tr '\t' ' ')"
    printf 'nproc\t%s\n' "$(nproc)"
    printf 'python\t%s\n' "$(python --version 2>&1 | tr '\t' ' ')"
    printf 'samtools\t%s\n' "$(first_line_version samtools)"
    printf 'bedtools\t%s\n' "$(first_line_version bedtools)"
    printf 'bgzip\t%s\n' "$(first_line_version bgzip)"
    printf 'tabix\t%s\n' "$(first_line_version tabix)"
    printf 'gzip\t%s\n' "$(first_line_version gzip)"
    printf 'sha256sum\t%s\n' "$(first_line_version sha256sum)"
    printf 'sort\t%s\n' "$(first_line_version sort)"
    printf 'pigz\t%s\n' "$(first_line_version pigz)"
    printf 'parallel\t%s\n' "$(first_line_version parallel)"
    printf 'memory_bytes\t%s\n' "$(awk '/MemTotal/ {print $2 * 1024}' /proc/meminfo)"
    printf 'project_fs_available_kb\t%s\n' "$(df -Pk "$PROJECT_ROOT" | awk 'NR==2 {print $4}')"
    printf 'raw_fs_available_kb\t%s\n' "$(df -Pk "$RAW_ROOT" | awk 'NR==2 {print $4}')"
    printf 'ulimit_nofile\t%s\n' "$(ulimit -n)"
    python - <<'PY'
try:
    import pysam
    print(f'pysam\t{pysam.__version__}')
except Exception as exc:
    print(f'pysam\tERROR:{exc}')
try:
    import psutil
    print(f'psutil\t{psutil.__version__}')
except Exception:
    print('psutil\tNOT_INSTALLED')
try:
    import duckdb
    print(f'duckdb\t{duckdb.__version__}')
except Exception:
    print('duckdb\tNOT_INSTALLED')
try:
    import polars
    print(f'polars\t{polars.__version__}')
except Exception:
    print('polars\tNOT_INSTALLED')
PY
} >> "$ENVIRONMENT"

# -----------------------------------------------------------------------------
# 4. Frozen upstream/package semantic audit and projection-job lockstep proof.
# -----------------------------------------------------------------------------
FROZEN_ASSIGNMENT="$PROJECT_ROOT/results/11_assignment/$RUN_ID/read_target_candidates.tsv.gz"
FROZEN_PROJECTION="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3/read_target_projection.v0.3.3.tsv.gz"
FROZEN_JOBS="$PROJECT_ROOT/results/11_motif_jobs/$RUN_ID/motif_scan_jobs.tsv.gz"
FROZEN_WINDOWS="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_projection_v0.3.3/ENCFF260PGB.pilot_100k.rnatr_target_windows.v0.3.3.fastq.gz"
FROZEN_GENERAL="$FROZEN_PACKAGE/general_repeat_calls.tsv.gz"

python - \
    "$FROZEN_ASSIGNMENT" \
    "$FROZEN_PROJECTION" \
    "$FROZEN_JOBS" \
    "$FROZEN_WINDOWS" \
    "$FROZEN_GENERAL" \
    "$DETERMINISTIC_REFERENCE_CALLS" \
    "$FROZEN_AUDIT" <<'PY'
from __future__ import annotations
import csv, gzip, hashlib, itertools, sys
from pathlib import Path

assignment, projection, jobs, windows, general, reference_calls, output = map(Path, sys.argv[1:])
metrics: list[tuple[str, object]] = []

def add(k, v):
    metrics.append((k, v))

def semantic_sha(path: Path) -> tuple[int, str, str]:
    raw = hashlib.sha256()
    content = hashlib.sha256()
    rows = -1
    with path.open('rb') as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b''):
            raw.update(block)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b''):
            content.update(block)
    with opener(path, 'rt', encoding='utf-8', newline='') as fh:
        rows = sum(1 for _ in fh) - 1
    return rows, raw.hexdigest(), content.hexdigest()

for label, path in [
    ('assignment', assignment),
    ('projection', projection),
    ('motif_jobs', jobs),
    ('general_repeat_calls', general),
]:
    if not path.is_file():
        add(f'{label}_present', 'false')
        continue
    rows, raw_sha, semantic = semantic_sha(path)
    add(f'{label}_present', 'true')
    add(f'{label}_rows', rows)
    add(f'{label}_raw_sha256', raw_sha)
    add(f'{label}_decompressed_sha256', semantic)

# Projection -> motif jobs must be one-to-one and in the same order for the
# planned lockstep, no-global-dictionary materializer fast path.
if projection.is_file() and jobs.is_file():
    order_mismatch = 0
    first_mismatch = '.'
    p_ids: set[str] = set()
    j_ids: set[str] = set()
    with gzip.open(projection, 'rt', encoding='utf-8', newline='') as ph, \
         gzip.open(jobs, 'rt', encoding='utf-8', newline='') as jh:
        pr = csv.DictReader(ph, delimiter='\t')
        jr = csv.DictReader(jh, delimiter='\t')
        p_count = j_count = 0
        for index, pair in enumerate(itertools.zip_longest(pr, jr), 1):
            p, j = pair
            if p is not None:
                p_count += 1
                p_id = p['projection_id']
                p_ids.add(p_id)
            else:
                p_id = '<EOF>'
            if j is not None:
                j_count += 1
                j_id = j['projection_id']
                j_ids.add(j_id)
            else:
                j_id = '<EOF>'
            if p_id != j_id:
                order_mismatch += 1
                if first_mismatch == '.':
                    first_mismatch = f'{index}:{p_id}!={j_id}'
    add('projection_rows_lockstep', p_count)
    add('motif_job_rows_lockstep', j_count)
    add('projection_job_order_mismatch_rows', order_mismatch)
    add('projection_job_first_order_mismatch', first_mismatch)
    add('projection_job_id_set_equal', str(p_ids == j_ids).lower())
    add('projection_job_order_lockstep', str(order_mismatch == 0 and p_count == j_count).lower())

# FASTQ completeness/read count.
if windows.is_file():
    try:
        import pysam
        ids = set()
        duplicate = 0
        records = 0
        with pysam.FastxFile(str(windows)) as source:
            for entry in source:
                records += 1
                if entry.name in ids:
                    duplicate += 1
                ids.add(entry.name)
        add('window_fastq_records', records)
        add('window_fastq_unique_ids', len(ids))
        add('window_fastq_duplicate_ids', duplicate)
    except Exception as exc:
        add('window_fastq_audit_error', repr(exc))
else:
    add('window_fastq_present', 'false')

# Exact 77-column caller-input suffix reference extracted from the frozen
# 85-column materialized general_repeat_calls table.
if general.is_file():
    suffix_hash = hashlib.sha256()
    row_count = 0
    expected_prefix = [
        'schema_version', 'run_id', 'sample_id', 'caller_record_id',
        'evidence_id', 'materialization_status', 'repeat_event_id',
        'primary_repeat_call_id',
    ]
    with gzip.open(general, 'rt', encoding='utf-8', newline='') as handle:
        reader = csv.reader(handle, delimiter='\t')
        header = next(reader)
        prefix_ok = header[:8] == expected_prefix
        suffix = header[8:]
        suffix_hash.update(('\t'.join(suffix) + '\n').encode())
        for row in reader:
            row_count += 1
            suffix_hash.update(('\t'.join(row[8:]) + '\n').encode())
    add('frozen_general_prefix_contract_ok', str(prefix_ok).lower())
    add('frozen_caller_suffix_columns', len(suffix))
    add('frozen_caller_suffix_rows', row_count)
    frozen_suffix_sha = suffix_hash.hexdigest()
    add('frozen_caller_suffix_tsv_sha256', frozen_suffix_sha)

    if reference_calls.is_file():
        reference_hash = hashlib.sha256()
        reference_rows = 0
        with gzip.open(reference_calls, 'rt', encoding='utf-8', newline='') as ref:
            for line in ref:
                reference_hash.update(line.encode())
                reference_rows += 1
        reference_rows = max(0, reference_rows - 1)
        reference_sha = reference_hash.hexdigest()
        add('deterministic_reference_rows', reference_rows)
        add('deterministic_reference_tsv_sha256', reference_sha)
        add(
            'frozen_package_suffix_exact_reference_match',
            str(reference_rows == row_count and reference_sha == frozen_suffix_sha).lower(),
        )

with output.open('w', encoding='utf-8', newline='') as handle:
    writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
    writer.writerow(['metric', 'value'])
    writer.writerows(metrics)
PY

# -----------------------------------------------------------------------------
# 5. Summarize blocking conditions.
# -----------------------------------------------------------------------------
critical_bad="$(awk -F '\t' 'NR>1 && $2=="true" && $8!="PASS" && $8!="PRESENT_UNPINNED" {n++} END{print n+0}' "$ARTIFACTS")"
format_failures="$(awk -F '\t' 'NR>1 && $2!="PASS" {n++} END{print n+0}' "$FORMAT_QC")"
critical_bad="$((critical_bad + format_failures))"
sha_mismatch="$(awk -F '\t' 'NR>1 && $8=="SHA_MISMATCH" {n++} END{print n+0}' "$ARTIFACTS")"
missing="$(awk -F '\t' 'NR>1 && $8=="MISSING_OR_EMPTY" {n++} END{print n+0}' "$ARTIFACTS")"
driver_contract_pass="$(awk -F '\t' '$1=="all_required_checks_pass" {print $2}' "$DRIVER_CONTRACT" 2>/dev/null || true)"
validator_exact_count="$(awk -F '\t' 'NR>1 && ($1=="VALIDATOR_V042_TSV" || $1=="VALIDATOR_V042_PACKAGE") && ($8=="PASS" || $8=="PRESENT_UNPINNED") {n++} END{print n+0}' "$ARTIFACTS")"
lockstep="$(awk -F '\t' '$1=="projection_job_order_lockstep" {print $2}' "$FROZEN_AUDIT" 2>/dev/null || true)"
caller_suffix_columns="$(awk -F '\t' '$1=="frozen_caller_suffix_columns" {print $2}' "$FROZEN_AUDIT" 2>/dev/null || true)"
caller_suffix_rows="$(awk -F '\t' '$1=="frozen_caller_suffix_rows" {print $2}' "$FROZEN_AUDIT" 2>/dev/null || true)"
reference_match="$(awk -F '\t' '$1=="frozen_package_suffix_exact_reference_match" {print $2}' "$FROZEN_AUDIT" 2>/dev/null || true)"
deterministic_caller_qc_status="$(awk -F '\t' '$1=="audit_status" {print $2}' "$DETERMINISTIC_CALLER_QC" 2>/dev/null | tr -d '\r' | tail -n1 || true)"

status="PASS"
next_gate="READY_TO_FREEZE_STAGE15A_EXECUTION_BUNDLE"
if (( critical_bad > 0 )); then
    status="BLOCKED"
    next_gate="RESOLVE_MISSING_OR_MISMATCHED_CRITICAL_ARTIFACTS"
elif [[ "$deterministic_caller_qc_status" != "PASS" ]]; then
    status="BLOCKED"
    next_gate="RESOLVE_STAGE14G_DETERMINISTIC_CALLER_VALIDATION_QC"
elif [[ "$driver_contract_pass" != "true" ]]; then
    status="BLOCKED"
    next_gate="RESOLVE_PROMOTED_NATIVE_V041_CALLER_INTEGRATION_DRIVER_CONTRACT"
elif (( validator_exact_count != 2 )); then
    status="BLOCKED"
    next_gate="RESOLVE_EXACT_SCHEMA_V042_VALIDATORS"
elif [[ "$lockstep" != "true" ]]; then
    status="REVIEW"
    next_gate="DESIGN_NON_LOCKSTEP_JOIN_OR_EXPLAIN_ORDER_DRIFT"
elif [[ "$caller_suffix_columns" != "77" || "$caller_suffix_rows" != "388571" ]]; then
    status="REVIEW"
    next_gate="RESOLVE_FROZEN_CALLER_SUFFIX_CONTRACT"
elif [[ "$reference_match" != "true" ]]; then
    status="REVIEW"
    next_gate="RESOLVE_DETERMINISTIC_CALLER_REFERENCE_PARITY"
fi

{
    printf 'metric\tvalue\n'
    printf 'stage_version\t%s\n' "$STAGE_VERSION"
    printf 'run_id\t%s\n' "$RUN_ID"
    printf 'target_bam\t%s\n' "$BAM"
    printf 'target_bam_expected_sha256\t%s\n' "$EXPECTED_BAM_SHA256"
    printf 'critical_artifact_or_format_failures\t%s\n' "$critical_bad"
    printf 'input_format_failures\t%s\n' "$format_failures"
    printf 'missing_or_empty_artifacts\t%s\n' "$missing"
    printf 'sha_mismatch_artifacts\t%s\n' "$sha_mismatch"
    printf 'deterministic_caller_validation_qc_status\t%s\n' "${deterministic_caller_qc_status:-.}"
    printf 'caller_driver_contract_pass\t%s\n' "${driver_contract_pass:-.}"
    printf 'exact_v042_validators_present\t%s\n' "$validator_exact_count"
    printf 'projection_job_order_lockstep\t%s\n' "${lockstep:-.}"
    printf 'frozen_caller_suffix_columns\t%s\n' "${caller_suffix_columns:-.}"
    printf 'frozen_caller_suffix_rows\t%s\n' "${caller_suffix_rows:-.}"
    printf 'frozen_package_suffix_exact_reference_match\t%s\n' "${reference_match:-.}"
    printf 'active_pipeline_modified\tfalse\n'
    printf 'full_5_31m_run_started\tfalse\n'
    printf 'preflight_status\t%s\n' "$status"
    printf 'next_gate\t%s\n' "$next_gate"
} > "$SUMMARY"

echo
echo "===== SUMMARY ====="
if command -v column >/dev/null 2>&1; then
    column -ts $'\t' "$SUMMARY"
else
    cat "$SUMMARY"
fi
echo
echo "Artifacts:  $ARTIFACTS"
echo "Format QC:  $FORMAT_QC"
echo "Components: $DISCOVERED"
echo "Driver QC:  $DRIVER_CONTRACT"
echo "Environment:$ENVIRONMENT"
echo "Frozen audit:$FROZEN_AUDIT"
echo "Log:        $LOG"

if [[ "$status" == "BLOCKED" ]]; then
    exit 2
elif [[ "$status" == "REVIEW" ]]; then
    exit 3
fi
