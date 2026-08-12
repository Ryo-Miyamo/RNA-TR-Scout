#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

PROJECT_ROOT="/mnt/intelssd/rnatr_project"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
UPDATE_VERSION="rnatr_stage15a_ssot_performance_registration_v0.1.0"
STAGE_KEY="15A_BAM_TO_FINAL_PERFORMANCE"
IMPL_V0201="impl_stage15a_performance_v0_2_0_1"
IMPL_V021="impl_stage15a_performance_v0_2_1"
IMPL_V0221="impl_stage15a_performance_v0_2_2_1"

SSOT_ROOT="$PROJECT_ROOT/metadata/ssot"
SSOT_CLI="$SSOT_ROOT/rnatr_ssot.py"
SSOT_DB="$SSOT_ROOT/rnatr_ssot.sqlite"
SSOT_SUMMARY="$SSOT_ROOT/CURRENT_STATE.md"
SSOT_EXPORTS="$SSOT_ROOT/exports"
SSOT_BACKUPS="$SSOT_ROOT/backups"
LOCK_PATH="$SSOT_ROOT/.stage15a_performance_ssot_update.lock"

BASE_QC="$PROJECT_ROOT/qc/15_stage15a_bam_to_final/$RUN_ID"
BASE_RESULTS="$PROJECT_ROOT/results/15_stage15a_bam_to_final/$RUN_ID"

V020_FAILURE="$BASE_QC/v0.2.0_performance/stage15a_performance_100k.failure.txt"
V0201_QC="$BASE_QC/v0.2.0.1_performance/stage15a_performance_100k.qc.tsv"
V0201_TIMING="$BASE_QC/v0.2.0.1_performance/stage15a_performance_timing.tsv"
V0201_RUNNER="$PROJECT_ROOT/scripts/rnatr_stage15a_run_performance_100k_v0.2.0.1.py"

V021_QC="$BASE_QC/v0.2.1_performance/stage15a_performance_100k.qc.tsv"
V021_TIMING="$BASE_QC/v0.2.1_performance/stage15a_performance_timing.tsv"
V021_RUNNER="$PROJECT_ROOT/scripts/rnatr_stage15a_run_performance_100k_v0.2.1.py"

V022_FAILURE="$BASE_QC/v0.2.2_performance/stage15a_performance_100k.failure.txt"
V022_VALIDATOR_LOG="$BASE_QC/v0.2.2_performance/logs/validators/package_prepublication.log"
V022_RUNNER="$PROJECT_ROOT/scripts/rnatr_stage15a_run_performance_100k_v0.2.2.py"

V0221_QC="$BASE_QC/v0.2.2.1_performance/stage15a_performance_100k.qc.tsv"
V0221_TIMING="$BASE_QC/v0.2.2.1_performance/stage15a_performance_timing.tsv"
V0221_COMPARISON="$BASE_QC/v0.2.2.1_performance/comparison/stage15a_performance_package_comparison.tsv"
V0221_POST_AUDIT="$BASE_QC/v0.2.2.1_performance/stage15a_performance_post_timer_audit.qc.tsv"
V0221_VALIDATORS="$BASE_QC/v0.2.2.1_performance/stage15a_performance_validators.tsv"
V0221_ATOMIC="$BASE_QC/v0.2.2.1_performance/stage15a_performance_atomic_publication.tsv"
V0221_PACKAGE="$BASE_RESULTS/v0.2.2.1_performance/package_performance"
V0221_MANIFEST="$V0221_PACKAGE/package_manifest.tsv"
V0221_RUNNER="$PROJECT_ROOT/scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
V0221_PARALLEL_VALIDATOR="$PROJECT_ROOT/scripts/rnatr_stage15a_validate_package_parallel_v0.2.2.1.py"

FROZEN_TSV_VALIDATOR="$PROJECT_ROOT/config/evidence_schema/v0.4.2/rnatr_v042_validate_tsv.py"
FROZEN_PACKAGE_VALIDATOR="$PROJECT_ROOT/config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py"

SCRIPT_INSTALL="$PROJECT_ROOT/scripts/rnatr_stage15a_update_ssot_performance_v0.2.2.1_v0.1.0.sh"
DESIGN_INSTALL="$PROJECT_ROOT/docs/stage15a/RNA_TR_Scout_Stage15A_performance_SSOT_registration_v0.2.2.1.md"
META_INSTALL="$PROJECT_ROOT/metadata/stage15a/ssot_updates/performance_v0.2.2.1_v0.1.0"
UPDATE_QC_INSTALL="$PROJECT_ROOT/qc/15_stage15a_ssot_update/$RUN_ID/performance_v0.2.2.1_v0.1.0"

DOWNLOADS="$HOME/Downloads"
OUTPUT_BUNDLE="$DOWNLOADS/rnatr_stage15a_ssot_update_performance_v0.2.2.1_output_v0.1.0.tar.gz"
OUTPUT_BUNDLE_SHA="$OUTPUT_BUNDLE.sha256"
FAILURE_BUNDLE="$DOWNLOADS/rnatr_stage15a_ssot_update_performance_v0.2.2.1_failure_v0.1.0.tar.gz"
FAILURE_BUNDLE_SHA="$FAILURE_BUNDLE.sha256"

EXPECTED_BASELINE_CLI_SHA="e559c56afabb004cb17915ee21bf5eb7f03d5b018cc5d1d794342cce4c3d3bcf"
EXPECTED_BASELINE_DB_SHA="6f7251db6d32758f61f1078d6ea6e69dd847df6c937c0aee3c75bb5a10c43854"
REFERENCE_MARKER="# Stage 15A reference SSOT registration v0.1.0"
PATCH_MARKER="# Stage 15A performance SSOT registration v0.2.2.1"

PYTHON_BIN="${PYTHON_BIN:-python}"
SELF="$(readlink -f "$0")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK_PARENT="$PROJECT_ROOT/tmp/15_stage15a_ssot_update/$RUN_ID"
WORK_ROOT="$WORK_PARENT/performance_v0221.$STAMP.$$"
LOG_ROOT="$WORK_ROOT/logs"
BUNDLE_ROOT="$WORK_ROOT/rnatr_stage15a_ssot_update_performance_v0.2.2.1_output_v0.1.0"
BACKUP_DIR=""
MUTATION_STARTED=false
SUCCESS=false
PREEXISTING_EXPORTS=false

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; return 2; }
sha256_file() { sha256sum "$1" | awk '{print $1}'; }

restore_ssot() {
    [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || return 0
    say "Restoring pre-update SSOT state..."
    cp -a "$BACKUP_DIR/rnatr_ssot.py" "$SSOT_CLI" 2>/dev/null || true
    cp -a "$BACKUP_DIR/rnatr_ssot.sqlite" "$SSOT_DB" 2>/dev/null || true
    if [[ -f "$BACKUP_DIR/CURRENT_STATE.md" ]]; then
        cp -a "$BACKUP_DIR/CURRENT_STATE.md" "$SSOT_SUMMARY" 2>/dev/null || true
    else
        rm -f -- "$SSOT_SUMMARY" 2>/dev/null || true
    fi
    if [[ -d "$BACKUP_DIR/exports" ]]; then
        rm -rf -- "$SSOT_EXPORTS" 2>/dev/null || true
        cp -a "$BACKUP_DIR/exports" "$SSOT_EXPORTS" 2>/dev/null || true
    elif [[ "$PREEXISTING_EXPORTS" == "false" ]]; then
        rm -rf -- "$SSOT_EXPORTS" 2>/dev/null || true
    fi
}

create_failure_bundle() {
    local rc="$1"
    local line="$2"
    local command_text="$3"
    set +e
    mkdir -p "$WORK_ROOT/failure" "$DOWNLOADS"
    {
        printf 'metric\tvalue\n'
        printf 'update_version\t%s\n' "$UPDATE_VERSION"
        printf 'run_id\t%s\n' "$RUN_ID"
        printf 'exit_code\t%s\n' "$rc"
        printf 'line\t%s\n' "$line"
        printf 'command\t%s\n' "$command_text"
        printf 'mutation_started\t%s\n' "$MUTATION_STARTED"
        printf 'timestamp_utc\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "$WORK_ROOT/failure/failure.tsv"
    tar -C "$WORK_PARENT" -czf "$FAILURE_BUNDLE.part" "$(basename "$WORK_ROOT")" 2>/dev/null || true
    if [[ -s "$FAILURE_BUNDLE.part" ]]; then
        mv -f "$FAILURE_BUNDLE.part" "$FAILURE_BUNDLE"
        printf '%s  %s\n' "$(sha256_file "$FAILURE_BUNDLE")" "$(basename "$FAILURE_BUNDLE")" > "$FAILURE_BUNDLE_SHA"
        printf 'Failure bundle: %s\n' "$FAILURE_BUNDLE" >&2
        printf 'Failure SHA256: %s\n' "$FAILURE_BUNDLE_SHA" >&2
    fi
}

on_error() {
    local rc="$1"
    local line="$2"
    local command_text="$3"
    trap - ERR
    set +e
    printf 'ERROR: Stage 15A performance SSOT update failed at line %s (exit %s): %s\n' "$line" "$rc" "$command_text" >&2
    if [[ "$MUTATION_STARTED" == "true" ]]; then
        restore_ssot
    fi
    create_failure_bundle "$rc" "$line" "$command_text"
    exit "$rc"
}
trap 'on_error "$?" "$LINENO" "$BASH_COMMAND"' ERR

[[ "$PROJECT_ROOT" == "/mnt/intelssd/rnatr_project" ]] || die "unexpected PROJECT_ROOT"
[[ -d "$PROJECT_ROOT" ]] || die "project root not found"
mkdir -p "$WORK_PARENT" "$WORK_ROOT" "$LOG_ROOT" "$BUNDLE_ROOT" "$DOWNLOADS" "$SSOT_BACKUPS"

for command_name in "$PYTHON_BIN" sha256sum tar flock awk grep find stat cmp cp mv readlink; do
    command -v "$command_name" >/dev/null 2>&1 || die "required command not found: $command_name"
done

SELF_SHA="$(sha256_file "$SELF")"
exec 9>"$LOCK_PATH"
flock -n 9 || die "another SSOT update holds $LOCK_PATH"

say "===== STAGE 15A PERFORMANCE SSOT UPDATE PREFLIGHT ====="
say "update version:              $UPDATE_VERSION"
say "update script SHA-256:        $SELF_SHA"
say "100k performance v0.2.2.1:   REGISTER PASS"
say "60-minute status:            REGISTER 100K LINEAR-PROJECTION PASS"
say "30-minute status:            KEEP TARGET_NOT_MET"
say "restart/250k scaling:         KEEP OPEN"
say "active pipeline switch:      PROHIBITED"
say "full 5.31M run:              PROHIBITED"
say "SSOT rollback:               ENABLED"

for required_path in \
    "$SSOT_CLI" "$SSOT_DB" \
    "$V020_FAILURE" \
    "$V0201_QC" "$V0201_TIMING" "$V0201_RUNNER" \
    "$V021_QC" "$V021_TIMING" "$V021_RUNNER" \
    "$V022_FAILURE" "$V022_VALIDATOR_LOG" "$V022_RUNNER" \
    "$V0221_QC" "$V0221_TIMING" "$V0221_COMPARISON" "$V0221_POST_AUDIT" \
    "$V0221_VALIDATORS" "$V0221_ATOMIC" "$V0221_MANIFEST" \
    "$V0221_RUNNER" "$V0221_PARALLEL_VALIDATOR" \
    "$FROZEN_TSV_VALIDATOR" "$FROZEN_PACKAGE_VALIDATOR"
do
    [[ -s "$required_path" ]] || die "required file missing or empty: $required_path"
done

BASELINE_CLI_SHA="$(sha256_file "$SSOT_CLI")"
BASELINE_DB_SHA="$(sha256_file "$SSOT_DB")"

if grep -Fq "$PATCH_MARKER" "$SSOT_CLI"; then
    SOURCE_ALREADY_PATCHED=true
else
    SOURCE_ALREADY_PATCHED=false
    [[ "$BASELINE_CLI_SHA" == "$EXPECTED_BASELINE_CLI_SHA" ]] || die "unexpected SSOT source SHA: $BASELINE_CLI_SHA"
    [[ "$BASELINE_DB_SHA" == "$EXPECTED_BASELINE_DB_SHA" ]] || die "unexpected SSOT DB SHA: $BASELINE_DB_SHA"
fi
grep -Fq "$REFERENCE_MARKER" "$SSOT_CLI" || die "Stage 15A reference SSOT marker is absent"

"$PYTHON_BIN" "$SSOT_CLI" --project-root "$PROJECT_ROOT" validate \
    2>&1 | tee "$LOG_ROOT/ssot_validate_before.log"

cat > "$WORK_ROOT/RNA_TR_Scout_Stage15A_performance_SSOT_registration_v0.2.2.1.md" <<'EOF_DOC'
# RNA-TR-Scout Stage 15A performance SSOT registration v0.2.2.1

Stage 15A v0.2.2.1 completed the isolated 100k BAM-to-final performance lane with exact logical package parity, frozen validators, post-publication frozen validation, failure-parity testing, and atomic publication.

Registered state:

- 100k BAM-to-final performance implementation: PASS
- measured production timer: 65.76363927999046 seconds
- reference-lane speedup: 5.078519507992296-fold
- conservative 5.31M linear projection: 58.230370558041365 minutes
- 60-minute hard-ceiling projection: PASS
- 30-minute target: TARGET_NOT_MET
- restart/resume validation: OPEN
- deterministic 250k scaling: OPEN
- empirical full 5.31M runtime: NOT RUN
- active pipeline: UNCHANGED

The 58.23-minute value is a 100k-derived linear projection, not an observed 5.31M runtime. Stage 15A therefore remains IN_PROGRESS and the full 5.31M run remains prohibited until restartability and intermediate-scale scaling are validated.
EOF_DOC

"$PYTHON_BIN" - \
    "$PROJECT_ROOT" "$SSOT_DB" "$WORK_ROOT/current_pipeline.before.tsv" \
    "$WORK_ROOT/preflight.qc.tsv" \
    "$V020_FAILURE" \
    "$V0201_QC" "$V0201_TIMING" "$V0201_RUNNER" \
    "$V021_QC" "$V021_TIMING" "$V021_RUNNER" \
    "$V022_FAILURE" "$V022_VALIDATOR_LOG" "$V022_RUNNER" \
    "$V0221_QC" "$V0221_TIMING" "$V0221_COMPARISON" "$V0221_POST_AUDIT" \
    "$V0221_VALIDATORS" "$V0221_ATOMIC" "$V0221_MANIFEST" "$V0221_PACKAGE" \
    "$V0221_RUNNER" "$V0221_PARALLEL_VALIDATOR" \
    "$FROZEN_TSV_VALIDATOR" "$FROZEN_PACKAGE_VALIDATOR" <<'PY_PREFLIGHT'
from __future__ import annotations
import csv, gzip, hashlib, sqlite3, sys
from pathlib import Path

(
    project_root_text, db_text, pipeline_out_text, preflight_out_text,
    v020_failure_text,
    v0201_qc_text, v0201_timing_text, v0201_runner_text,
    v021_qc_text, v021_timing_text, v021_runner_text,
    v022_failure_text, v022_validator_log_text, v022_runner_text,
    v0221_qc_text, v0221_timing_text, v0221_comparison_text,
    v0221_post_audit_text, v0221_validators_text, v0221_atomic_text,
    v0221_manifest_text, v0221_package_text, v0221_runner_text,
    v0221_parallel_validator_text, frozen_tsv_validator_text,
    frozen_package_validator_text,
) = sys.argv[1:]

PROJECT_ROOT = Path(project_root_text).resolve()
DB = Path(db_text)
PIPELINE_OUT = Path(pipeline_out_text)
PREFLIGHT_OUT = Path(preflight_out_text)
V0221_PACKAGE = Path(v0221_package_text).resolve()

paths = {
    Path(v020_failure_text): "82b0ce0beee7a7f1bc6d07501bba57dcc738302288ef835ab04d92a71b507115",
    Path(v0201_qc_text): "c634e60d79b96f0bb4513593410b9f1dec005d2d080216d103819b674e23c909",
    Path(v0201_timing_text): "7ec30246eed790296c8647a85c50014ee16fab011b014a36cde350817c465035",
    Path(v0201_runner_text): "568c51aeefb78dd3da7244837377e28cb96735bd5afa4a34e99efcdc8200a747",
    Path(v021_qc_text): "5d4d40beecd2326082b1a7656144a7fb904cb078664afdbd1aca9e0d4f1d26ce",
    Path(v021_timing_text): "4c8cba890f5545e5080b7af8dec04ea868398cd48ba2a081fe1bdb1a837d9570",
    Path(v021_runner_text): "371bc8fd3d02d96adf295d891948f09488caaec05511e29e1fd874898de7294c",
    Path(v022_failure_text): "241557dd8f3f16ec03007b6895a30423cb7584fe71d562268ba1972645f6646f",
    Path(v022_validator_log_text): "5dfb8f13066343aeb0a76ec8ce54c8001b26ca9ddc0eb67033dde932364c7904",
    Path(v022_runner_text): "2ac29866d08bb0e70d7d169d90346386eb9623c63f011cc0a68471822528f96f",
    Path(v0221_qc_text): "401cfa9d9e524ceebfef9f6665d0f2b435627133c40cfcb6b8df7d989e4ac733",
    Path(v0221_timing_text): "dbe46beaa7f555c4d7454c3fb95851d4ddd9b05df8a8ca2b56e00479c57b8b42",
    Path(v0221_comparison_text): "28df037888876656e9a4f5a2b460bc09613cd0ae4badf757e362f5f39f271661",
    Path(v0221_post_audit_text): "46e698553f4dea7b953600a2d0ef68bdd81031c131d0a3ca67c526cded4893fe",
    Path(v0221_validators_text): "ff15379adcba8ab063f10e721ee7ca04861e34c0a0853650b2537202ef5eab9b",
    Path(v0221_atomic_text): "8214f65b7c27ca509ade30b973cfe0cbe00c1c0c4ce7fb5aae13901447f2b63a",
    Path(v0221_manifest_text): "0e74e2eaf8cac0bc75ca0c89a725576946ac61476bce4cf4e76951402f4c13e3",
    Path(v0221_runner_text): "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8",
    Path(v0221_parallel_validator_text): "b635ed213b65cee005914f0fded9337871903a7e5682f9a897dff9cbc9bb0b09",
    Path(frozen_tsv_validator_text): "10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9",
    Path(frozen_package_validator_text): "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

for path, expected in paths.items():
    if not path.is_file():
        raise SystemExit(f"missing evidence: {path}")
    observed = sha256(path)
    if observed != expected:
        raise SystemExit(f"evidence SHA mismatch: {path}: {observed} != {expected}")

def read_metric(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["metric", "value"]:
            raise SystemExit(f"unexpected metric header: {path}: {reader.fieldnames}")
        return {row["metric"]: row["value"] for row in reader}

expected_subsets = {
    Path(v0201_qc_text): {
        "stage_version": "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.0.1",
        "performance_candidate_bam_to_final_seconds": "99.7883502789773",
        "conservative_linear_5_31m_projection_minutes": "88.3575282289536",
        "five_m_hard_ceiling_60min": "FAIL",
        "correctness_status": "PASS",
        "performance_implementation_status": "PASS",
    },
    Path(v021_qc_text): {
        "stage_version": "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.1",
        "performance_candidate_bam_to_final_seconds": "81.39999548299238",
        "conservative_linear_5_31m_projection_minutes": "72.07557173375194",
        "five_m_hard_ceiling_60min": "FAIL",
        "correctness_status": "PASS",
        "performance_implementation_status": "PASS",
    },
    Path(v0221_qc_text): {
        "stage_version": "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2.1",
        "performance_candidate_bam_to_final_seconds": "65.76363927999046",
        "conservative_linear_5_31m_projection_minutes": "58.230370558041365",
        "five_m_hard_ceiling_60min": "PASS",
        "five_m_target_30min": "TARGET_NOT_MET",
        "package_exact_logical_parity": "true",
        "frozen_tsv_validators": "PASS",
        "parallel_exact_component_package_validator_prepublication": "PASS",
        "frozen_package_validator_postpublication": "PASS",
        "parallel_validator_missing_artifact_failure_parity": "PASS",
        "atomic_publication": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "correctness_status": "PASS",
        "performance_implementation_status": "PASS",
        "stage15a_overall_status": "IN_PROGRESS",
        "next_gate": "RUN_STAGE15A_RESTART_AND_DETERMINISTIC_250K_SCALING_NOT_FULL_5_31M",
    },
}
for path, expected in expected_subsets.items():
    values = read_metric(path)
    for key, wanted in expected.items():
        if values.get(key) != wanted:
            raise SystemExit(f"QC mismatch {path} {key}: {values.get(key)!r} != {wanted!r}")

manifest = Path(v0221_manifest_text)
verified_artifacts = 0
with manifest.open("r", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    expected_header = ["artifact", "table", "rows", "bytes", "sha256", "path"]
    if reader.fieldnames != expected_header:
        raise SystemExit(f"package manifest header mismatch: {reader.fieldnames}")
    rows = list(reader)
if len(rows) != 10:
    raise SystemExit(f"expected 10 package artifacts, observed {len(rows)}")
for row in rows:
    artifact = Path(row["path"]).resolve()
    try:
        artifact.relative_to(V0221_PACKAGE)
    except ValueError:
        raise SystemExit(f"package artifact escapes package root: {artifact}")
    if not artifact.is_file():
        raise SystemExit(f"package artifact missing: {artifact}")
    if artifact.stat().st_size != int(row["bytes"]):
        raise SystemExit(f"package artifact byte mismatch: {artifact}")
    if sha256(artifact) != row["sha256"]:
        raise SystemExit(f"package artifact SHA mismatch: {artifact}")
    verified_artifacts += 1

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
try:
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("SQLite integrity check failed")
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        raise SystemExit("SQLite foreign-key check failed")
    rows = conn.execute("SELECT * FROM current_pipeline ORDER BY stage_order,stage_key").fetchall()
    if len(rows) != 11:
        raise SystemExit(f"unexpected current_pipeline rows: {len(rows)}")
    if any(str(row["stage_key"]).startswith("15A_") for row in rows):
        raise SystemExit("Stage 15A unexpectedly present in current_pipeline")
    PIPELINE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with PIPELINE_OUT.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow([row[key] for key in row.keys()])
finally:
    conn.close()

qc_rows = [
    ("preflight_status", "PASS"),
    ("evidence_files_verified", str(len(paths))),
    ("package_artifacts_verified", str(verified_artifacts)),
    ("active_pipeline_stages", "11"),
    ("stage15a_current_pipeline_present", "false"),
    ("v0201_seconds", "99.7883502789773"),
    ("v021_seconds", "81.39999548299238"),
    ("v0221_seconds", "65.76363927999046"),
    ("v0221_projection_minutes", "58.230370558041365"),
    ("v0221_60min_projection", "PASS"),
    ("v0221_30min_target", "TARGET_NOT_MET"),
]
with PREFLIGHT_OUT.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["metric", "value"])
    writer.writerows(qc_rows)
print("STAGE15A_PERFORMANCE_SSOT_PREFLIGHT_PASS")
PY_PREFLIGHT

say "Preflight evidence/package verification: PASS"

cat > "$WORK_ROOT/source_insertion.pyfrag" <<'PYFRAG'
    # Stage 15A performance SSOT registration v0.2.2.1
    stage15a_perf_effective_at = "2026-08-08T11:31:27+00:00"
    stage15a_perf_run_id = "ENCSR307SHM_pilot100k_mm2splice_v1"
    stage15a_perf_stage_key = "15A_BAM_TO_FINAL_PERFORMANCE"

    stage15a_perf_v020_failure = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.0_performance/stage15a_performance_100k.failure.txt"
    stage15a_perf_v0201_qc = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.0.1_performance/stage15a_performance_100k.qc.tsv"
    stage15a_perf_v0201_timing = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.0.1_performance/stage15a_performance_timing.tsv"
    stage15a_perf_v0201_runner = project_root / "scripts/rnatr_stage15a_run_performance_100k_v0.2.0.1.py"
    stage15a_perf_v021_qc = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.1_performance/stage15a_performance_100k.qc.tsv"
    stage15a_perf_v021_timing = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.1_performance/stage15a_performance_timing.tsv"
    stage15a_perf_v021_runner = project_root / "scripts/rnatr_stage15a_run_performance_100k_v0.2.1.py"
    stage15a_perf_v022_failure = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2_performance/stage15a_performance_100k.failure.txt"
    stage15a_perf_v022_validator_log = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2_performance/logs/validators/package_prepublication.log"
    stage15a_perf_v022_runner = project_root / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.py"
    stage15a_perf_v0221_qc = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_100k.qc.tsv"
    stage15a_perf_v0221_timing = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_timing.tsv"
    stage15a_perf_v0221_comparison = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/comparison/stage15a_performance_package_comparison.tsv"
    stage15a_perf_v0221_post_audit = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_post_timer_audit.qc.tsv"
    stage15a_perf_v0221_validators = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_validators.tsv"
    stage15a_perf_v0221_atomic = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_atomic_publication.tsv"
    stage15a_perf_v0221_manifest = project_root / "results/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/package_performance/package_manifest.tsv"
    stage15a_perf_v0221_runner = project_root / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
    stage15a_perf_v0221_parallel_validator = project_root / "scripts/rnatr_stage15a_validate_package_parallel_v0.2.2.1.py"
    stage15a_perf_frozen_package_validator = project_root / "config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py"

    stage15a_perf_required_hashes = {
        stage15a_perf_v020_failure: "82b0ce0beee7a7f1bc6d07501bba57dcc738302288ef835ab04d92a71b507115",
        stage15a_perf_v0201_qc: "c634e60d79b96f0bb4513593410b9f1dec005d2d080216d103819b674e23c909",
        stage15a_perf_v0201_timing: "7ec30246eed790296c8647a85c50014ee16fab011b014a36cde350817c465035",
        stage15a_perf_v0201_runner: "568c51aeefb78dd3da7244837377e28cb96735bd5afa4a34e99efcdc8200a747",
        stage15a_perf_v021_qc: "5d4d40beecd2326082b1a7656144a7fb904cb078664afdbd1aca9e0d4f1d26ce",
        stage15a_perf_v021_timing: "4c8cba890f5545e5080b7af8dec04ea868398cd48ba2a081fe1bdb1a837d9570",
        stage15a_perf_v021_runner: "371bc8fd3d02d96adf295d891948f09488caaec05511e29e1fd874898de7294c",
        stage15a_perf_v022_failure: "241557dd8f3f16ec03007b6895a30423cb7584fe71d562268ba1972645f6646f",
        stage15a_perf_v022_validator_log: "5dfb8f13066343aeb0a76ec8ce54c8001b26ca9ddc0eb67033dde932364c7904",
        stage15a_perf_v022_runner: "2ac29866d08bb0e70d7d169d90346386eb9623c63f011cc0a68471822528f96f",
        stage15a_perf_v0221_qc: "401cfa9d9e524ceebfef9f6665d0f2b435627133c40cfcb6b8df7d989e4ac733",
        stage15a_perf_v0221_timing: "dbe46beaa7f555c4d7454c3fb95851d4ddd9b05df8a8ca2b56e00479c57b8b42",
        stage15a_perf_v0221_comparison: "28df037888876656e9a4f5a2b460bc09613cd0ae4badf757e362f5f39f271661",
        stage15a_perf_v0221_post_audit: "46e698553f4dea7b953600a2d0ef68bdd81031c131d0a3ca67c526cded4893fe",
        stage15a_perf_v0221_validators: "ff15379adcba8ab063f10e721ee7ca04861e34c0a0853650b2537202ef5eab9b",
        stage15a_perf_v0221_atomic: "8214f65b7c27ca509ade30b973cfe0cbe00c1c0c4ce7fb5aae13901447f2b63a",
        stage15a_perf_v0221_manifest: "0e74e2eaf8cac0bc75ca0c89a725576946ac61476bce4cf4e76951402f4c13e3",
        stage15a_perf_v0221_runner: "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8",
        stage15a_perf_v0221_parallel_validator: "b635ed213b65cee005914f0fded9337871903a7e5682f9a897dff9cbc9bb0b09",
        stage15a_perf_frozen_package_validator: "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
    }
    for stage15a_perf_path, stage15a_perf_expected_sha in stage15a_perf_required_hashes.items():
        if not stage15a_perf_path.is_file():
            raise SSOTError(f"Stage 15A performance artifact missing: {stage15a_perf_path}")
        stage15a_perf_observed_sha = sha256_file(stage15a_perf_path)
        if stage15a_perf_observed_sha != stage15a_perf_expected_sha:
            raise SSOTError(
                f"Stage 15A performance artifact SHA mismatch: {stage15a_perf_path}: "
                f"{stage15a_perf_observed_sha} != {stage15a_perf_expected_sha}"
            )

    def stage15a_perf_read_metrics(stage15a_perf_path):
        stage15a_perf_values = {}
        with stage15a_perf_path.open("r", encoding="utf-8", newline="") as stage15a_perf_handle:
            stage15a_perf_reader = csv.DictReader(stage15a_perf_handle, delimiter="\t")
            if stage15a_perf_reader.fieldnames != ["metric", "value"]:
                raise SSOTError(f"Stage 15A performance QC header mismatch: {stage15a_perf_path}")
            for stage15a_perf_row in stage15a_perf_reader:
                stage15a_perf_values[stage15a_perf_row["metric"]] = stage15a_perf_row["value"]
        return stage15a_perf_values

    stage15a_perf_v0201_values = stage15a_perf_read_metrics(stage15a_perf_v0201_qc)
    stage15a_perf_v021_values = stage15a_perf_read_metrics(stage15a_perf_v021_qc)
    stage15a_perf_v0221_values = stage15a_perf_read_metrics(stage15a_perf_v0221_qc)

    stage15a_perf_expected = {
        "stage_version": "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2.1",
        "run_id": stage15a_perf_run_id,
        "performance_candidate_bam_to_final_seconds": "65.76363927999046",
        "performance_candidate_speedup": "5.078519507992296",
        "conservative_linear_5_31m_projection_minutes": "58.230370558041365",
        "five_m_hard_ceiling_60min": "PASS",
        "five_m_target_30min": "TARGET_NOT_MET",
        "package_exact_logical_parity": "true",
        "frozen_tsv_validators": "PASS",
        "parallel_exact_component_package_validator_prepublication": "PASS",
        "frozen_package_validator_postpublication": "PASS",
        "parallel_validator_missing_artifact_failure_parity": "PASS",
        "atomic_publication": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "correctness_status": "PASS",
        "performance_implementation_status": "PASS",
        "stage15a_overall_status": "IN_PROGRESS",
        "next_gate": "RUN_STAGE15A_RESTART_AND_DETERMINISTIC_250K_SCALING_NOT_FULL_5_31M",
    }
    for stage15a_perf_metric, stage15a_perf_wanted in stage15a_perf_expected.items():
        stage15a_perf_observed = stage15a_perf_v0221_values.get(stage15a_perf_metric)
        if stage15a_perf_observed != stage15a_perf_wanted:
            raise SSOTError(
                f"Stage 15A v0.2.2.1 QC mismatch {stage15a_perf_metric}: "
                f"{stage15a_perf_observed!r} != {stage15a_perf_wanted!r}"
            )

    if conn.execute("SELECT COUNT(*) FROM runs WHERE run_id=?", (stage15a_perf_run_id,)).fetchone()[0] != 1:
        raise SSOTError(f"Stage 15A performance target run is not uniquely registered: {stage15a_perf_run_id}")

    conn.execute(
        """
        INSERT OR REPLACE INTO stage_definitions(
            stage_key,stage_order,name,purpose,category,implementation_status,notes
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            stage15a_perf_stage_key,
            151.0,
            "Stage 15A isolated BAM-to-final performance lane",
            "Develop and validate an exact-parity, read-coherently sharded, restartable production candidate for mapping-complete BAM plus associated raw-read sequence store to schema v0.4.2 package.",
            "performance_validation",
            "IMPLEMENTED_WITH_GATE",
            "v0.2.2.1 passes the 100k correctness and conservative 60-minute linear-projection gate. Restart/resume, deterministic 250k scaling, empirical full-scale runtime, and the 30-minute target remain open.",
        ),
    )

    stage15a_perf_impl_rows = [
        (
            "impl_stage15a_performance_v0_2_0_1",
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.0.1",
            stage15a_perf_v0201_runner,
            "SUPERSEDED",
            None,
            stage15a_perf_v0201_qc,
            "First exact-parity sharded performance implementation; superseded after 99.788-second 100k result projected 88.358 minutes.",
        ),
        (
            "impl_stage15a_performance_v0_2_1",
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.1",
            stage15a_perf_v021_runner,
            "SUPERSEDED",
            "impl_stage15a_performance_v0_2_0_1",
            stage15a_perf_v021_qc,
            "Low-risk critical-path revision; superseded after 81.400-second 100k result projected 72.076 minutes.",
        ),
        (
            "impl_stage15a_performance_v0_2_2_1",
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2.1",
            stage15a_perf_v0221_runner,
            "PROVISIONAL",
            "impl_stage15a_performance_v0_2_1",
            stage15a_perf_v0221_qc,
            "Accepted as the current isolated performance candidate because exact logical parity, validators, failure-parity testing, atomic publication, and a conservative 58.230-minute 5.31M projection passed. It is not ACTIVE.",
        ),
    ]
    for (
        stage15a_perf_impl_id,
        stage15a_perf_version,
        stage15a_perf_runner,
        stage15a_perf_lifecycle,
        stage15a_perf_supersedes,
        stage15a_perf_evidence,
        stage15a_perf_rationale,
    ) in stage15a_perf_impl_rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO implementations(
                implementation_id,stage_key,version,script_path,script_sha256,
                validator_path,validator_sha256,package_version,parameters_json,
                lifecycle_status,supersedes_implementation_id,rationale,
                evidence_path,effective_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_impl_id,
                stage15a_perf_stage_key,
                stage15a_perf_version,
                str(stage15a_perf_runner),
                sha256_file(stage15a_perf_runner),
                str(stage15a_perf_v0221_parallel_validator if stage15a_perf_impl_id.endswith("2_2_1") else stage15a_perf_frozen_package_validator),
                sha256_file(stage15a_perf_v0221_parallel_validator if stage15a_perf_impl_id.endswith("2_2_1") else stage15a_perf_frozen_package_validator),
                "evidence_schema_v0.4.2",
                json.dumps(
                    {
                        "input_contract": "sorted_mapping_complete_BAM+associated_raw_read_sequence_store",
                        "run_id": stage15a_perf_run_id,
                        "read_coherent_sharding": True,
                        "shard_count": 12 if stage15a_perf_impl_id != "impl_stage15a_performance_v0_2_0_1" else 6,
                        "caller_workers_total": 24,
                        "native_caller": "v0.4.1",
                        "materializer_semantics": "v0.1.2",
                        "schema": "v0.4.2",
                        "active_pipeline_switch": False,
                        "full_5_31m_run": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                stage15a_perf_lifecycle,
                stage15a_perf_supersedes,
                stage15a_perf_rationale,
                str(stage15a_perf_evidence),
                stage15a_perf_effective_at,
            ),
        )

    stage15a_perf_run_rows = [
        ("impl_stage15a_performance_v0_2_0_1", "v0.2.0.1", "PASS", stage15a_perf_v0201_qc, "PASS", "2026-08-08T08:18:56+00:00", "Exact-parity performance baseline; hard-ceiling projection failed."),
        ("impl_stage15a_performance_v0_2_1", "v0.2.1", "PASS", stage15a_perf_v021_qc, "PASS", "2026-08-08T08:51:31+00:00", "Critical-path optimization; hard-ceiling projection remained above 60 minutes."),
        (None, "v0.2.2", "FAIL", stage15a_perf_v022_failure, "FAIL", "2026-08-08T09:24:43+00:00", "Performance computation reached final validation but the new parallel validator passed an incorrect CLI argument to the flank-uniqueness component."),
        ("impl_stage15a_performance_v0_2_2_1", "v0.2.2.1", "PASS", stage15a_perf_v0221_qc, "PASS", stage15a_perf_effective_at, "Corrected validator wiring; 100k exact-parity production timer passed the conservative 60-minute linear-projection gate."),
    ]
    for (
        stage15a_perf_impl_id,
        stage15a_perf_attempt,
        stage15a_perf_status,
        stage15a_perf_qc_path,
        stage15a_perf_qc_status,
        stage15a_perf_ended_at,
        stage15a_perf_notes,
    ) in stage15a_perf_run_rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO run_stages(
                run_id,stage_key,implementation_id,attempt_tag,status,
                command_text,qc_path,qc_status,started_at,ended_at,notes
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_run_id,
                stage15a_perf_stage_key,
                stage15a_perf_impl_id,
                stage15a_perf_attempt,
                stage15a_perf_status,
                None if stage15a_perf_impl_id is None else f"python {dict((row[0], row[2]) for row in stage15a_perf_impl_rows)[stage15a_perf_impl_id]}",
                str(stage15a_perf_qc_path),
                stage15a_perf_qc_status,
                None,
                stage15a_perf_ended_at,
                stage15a_perf_notes,
            ),
        )

    stage15a_perf_observed_metrics = [
        ("v0_2_0_1_bam_to_final_seconds", stage15a_perf_v0201_values["performance_candidate_bam_to_final_seconds"], "seconds", 100000.0, stage15a_perf_v0201_qc),
        ("v0_2_0_1_projection_minutes", stage15a_perf_v0201_values["conservative_linear_5_31m_projection_minutes"], "minutes", 5312696.0, stage15a_perf_v0201_qc),
        ("v0_2_1_bam_to_final_seconds", stage15a_perf_v021_values["performance_candidate_bam_to_final_seconds"], "seconds", 100000.0, stage15a_perf_v021_qc),
        ("v0_2_1_projection_minutes", stage15a_perf_v021_values["conservative_linear_5_31m_projection_minutes"], "minutes", 5312696.0, stage15a_perf_v021_qc),
    ]
    for stage15a_perf_name, stage15a_perf_text, stage15a_perf_unit, stage15a_perf_denominator, stage15a_perf_source in stage15a_perf_observed_metrics:
        conn.execute(
            """
            INSERT OR REPLACE INTO metrics(
                run_id,stage_key,metric_name,value_text,value_num,unit,
                denominator_num,source_path,metric_status,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_run_id,
                stage15a_perf_stage_key,
                stage15a_perf_name,
                stage15a_perf_text,
                float(stage15a_perf_text),
                stage15a_perf_unit,
                stage15a_perf_denominator,
                str(stage15a_perf_source),
                "OBSERVED",
                stage15a_perf_effective_at,
            ),
        )

    stage15a_perf_current_metrics = [
        ("stage15a_performance_100k_status", "PASS", None, None, 100000.0),
        ("stage15a_overall_status", "IN_PROGRESS", None, None, None),
        ("bam_to_final_100k_performance_validated", "true", 1.0, "boolean", 100000.0),
        ("restart_resume_validated", "false", 0.0, "boolean", None),
        ("deterministic_250k_scaling_validated", "false", 0.0, "boolean", 250000.0),
        ("full_5_31m_empirical_runtime_validated", "false", 0.0, "boolean", 5312696.0),
        ("active_pipeline_switched_to_v042", "false", 0.0, "boolean", None),
        ("full_5_31m_run_started", "false", 0.0, "boolean", 5312696.0),
        ("package_exact_logical_parity", "true", 1.0, "boolean", 388571.0),
        ("general_repeat_calls_rows", stage15a_perf_v0221_values["general_repeat_calls_rows"], float(stage15a_perf_v0221_values["general_repeat_calls_rows"]), "rows", None),
        ("read_evidence_rows", stage15a_perf_v0221_values["read_evidence_rows"], float(stage15a_perf_v0221_values["read_evidence_rows"]), "rows", None),
        ("repeat_event_rows", stage15a_perf_v0221_values["repeat_event_rows"], float(stage15a_perf_v0221_values["repeat_event_rows"]), "rows", None),
        ("repeat_segment_rows", stage15a_perf_v0221_values["repeat_segment_rows"], float(stage15a_perf_v0221_values["repeat_segment_rows"]), "rows", None),
        ("repeat_interruption_rows", stage15a_perf_v0221_values["repeat_interruption_rows"], float(stage15a_perf_v0221_values["repeat_interruption_rows"]), "rows", None),
        ("performance_candidate_bam_to_final_seconds", stage15a_perf_v0221_values["performance_candidate_bam_to_final_seconds"], float(stage15a_perf_v0221_values["performance_candidate_bam_to_final_seconds"]), "seconds", 100000.0),
        ("performance_candidate_speedup", stage15a_perf_v0221_values["performance_candidate_speedup"], float(stage15a_perf_v0221_values["performance_candidate_speedup"]), "fold", 100000.0),
        ("conservative_linear_5_31m_projection_minutes", stage15a_perf_v0221_values["conservative_linear_5_31m_projection_minutes"], float(stage15a_perf_v0221_values["conservative_linear_5_31m_projection_minutes"]), "minutes", 5312696.0),
        ("five_m_hard_ceiling_60min_projection", stage15a_perf_v0221_values["five_m_hard_ceiling_60min"], None, None, 5312696.0),
        ("five_m_target_30min", stage15a_perf_v0221_values["five_m_target_30min"], None, None, 5312696.0),
        ("hard_ceiling_evidence_scope", "100K_LINEAR_PROJECTION_NOT_EMPIRICAL_5_31M", None, None, 5312696.0),
        ("next_gate", stage15a_perf_v0221_values["next_gate"], None, None, None),
    ]
    for (
        stage15a_perf_metric_name,
        stage15a_perf_value_text,
        stage15a_perf_value_num,
        stage15a_perf_unit,
        stage15a_perf_denominator,
    ) in stage15a_perf_current_metrics:
        conn.execute(
            """
            INSERT OR REPLACE INTO metrics(
                run_id,stage_key,metric_name,value_text,value_num,unit,
                denominator_num,source_path,metric_status,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_run_id,
                stage15a_perf_stage_key,
                stage15a_perf_metric_name,
                stage15a_perf_value_text,
                stage15a_perf_value_num,
                stage15a_perf_unit,
                stage15a_perf_denominator,
                str(stage15a_perf_v0221_qc),
                "CURRENT",
                stage15a_perf_effective_at,
            ),
        )

    add_decision(
        conn,
        key="stage15a_performance_100k_v0_2_2_1_projection_pass",
        category="performance",
        title="Stage 15A v0.2.2.1 accepted as the current 100k performance candidate",
        statement="Stage 15A v0.2.2.1 is accepted as the current isolated 100k BAM-to-final performance candidate. It preserves exact logical package parity and yields a conservative linear 5.31M projection of 58.230370558041365 minutes, passing the projected 60-minute hard-ceiling gate while missing the 30-minute target.",
        status="ACTIVE",
        confidence="HIGH",
        rationale="The 65.76363927999046-second production timer includes frozen table validation, exact-component package validation, and atomic publication. Full post-timer development audit, frozen post-publication validation, exact reference comparison, and negative-fixture failure parity also passed. Restartability and intermediate-scale scaling remain unvalidated.",
        evidence_path=str(stage15a_perf_v0221_qc),
        effective_at=stage15a_perf_effective_at,
    )

    add_interpretation(
        conn,
        key="stage15a_performance_projection_scope_v0_2_2_1",
        fact="The exact-parity Stage 15A v0.2.2.1 100k performance lane completed in 65.76363927999046 seconds and linearly projects to 58.230370558041365 minutes for 5,312,696 reads.",
        interpretation="The 100k-derived conservative projection now passes the 60-minute hard-ceiling criterion and justifies restart/resume plus deterministic 250k scaling as the next gate.",
        do_not="Do not describe this as an observed full 5.31M runtime, completion of Stage 15A, attainment of the 30-minute target, active-pipeline promotion, authorization to run full 5.31M, biological truth validation, or pathogenicity assessment.",
        confidence="HIGH",
        evidence_path=str(stage15a_perf_v0221_qc),
        evidence_metrics={
            "performance_candidate_bam_to_final_seconds": 65.76363927999046,
            "conservative_linear_5_31m_projection_minutes": 58.230370558041365,
            "package_exact_logical_parity": True,
            "active_pipeline_modified": False,
            "full_5_31m_run_started": False,
        },
        status="ACTIVE",
        effective_at=stage15a_perf_effective_at,
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            "CURRENT_RUNTIME_NOT_PRODUCTION_SCALE",
            "Stage 15A v0.2.2.1 improved the isolated 100k BAM-to-final production timer to 65.76363927999046 seconds and passes a conservative 58.230370558041365-minute linear projection for 5.31M reads. However, the 30-minute target is not met and restartability, memory behavior, and intermediate/full-scale nonlinearity have not yet been empirically validated.",
            "HIGH",
            "ACTIVE",
            "Validate restart/resume and deterministic 250k scaling before any full 5.31M execution. Continue structural optimization toward the 30-minute target after the scaling model is updated.",
            str(stage15a_perf_v0221_qc),
            stage15a_perf_effective_at,
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            "STAGE15A_FULL_SCALE_RUNTIME_NOT_EMPIRICALLY_VALIDATED",
            "The current 58.230-minute value is a linear projection from 100k reads, not an observed 5.31M BAM-to-final runtime. Startup overhead, memory pressure, storage contention, candidate density, and scaling nonlinearity remain uncertain.",
            "HIGH",
            "ACTIVE",
            "Run deterministic 250k scaling with stage-level wall time, peak RSS, temporary bytes, exact package reproducibility, and restart/resume audit before considering a full-depth run.",
            str(stage15a_perf_v0221_qc),
            stage15a_perf_effective_at,
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
            question_key,question,priority,status,blocking,next_action,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            "GENERAL_CALLER_PRODUCTION_INTEGRATION",
            "Can the exact-parity Stage 15A performance candidate remain restartable, deterministic, and within the 60-minute hard ceiling as input size increases, while continuing toward the 30-minute target?",
            "CRITICAL",
            "OPEN",
            1,
            "Run Stage 15A restart/resume validation and a deterministic 250k BAM-input scaling benchmark. Require exact package reproducibility, bounded memory, complete artifact audit, and updated scaling estimates. Do not run full 5.31M or change current_pipeline yet.",
            str(stage15a_perf_v0221_qc),
            stage15a_perf_effective_at,
        ),
    )

    add_contract(
        conn,
        key="stage15a_performance_candidate_v0221",
        name="Stage 15A performance candidate v0.2.2.1",
        state="100K_PROJECTED_60MIN_PASS_RESTART_250K_OPEN",
        statement="v0.2.2.1 is the current exact-parity isolated performance candidate. Its 65.763639-second 100k production timer linearly projects to 58.230371 minutes for 5.31M reads. This projection is not empirical full-scale validation; restart/resume and deterministic 250k scaling remain blocking.",
        implementation_id="impl_stage15a_performance_v0_2_2_1",
        evidence_path=str(stage15a_perf_v0221_qc),
    )

    stage15a_perf_failures = [
        (
            "stage15a_perf_v020_escape_anchor",
            "v0.2.0",
            "The first performance runner stopped before partitioning because a Python patch anchor encoded shell backslash-t as a literal TAB and matched zero lines.",
            "Wrapper string escaping, not performance architecture or scientific logic.",
            "Resolved in v0.2.0.1 by correcting the anchor escape and rerunning in a new isolated root.",
            stage15a_perf_v020_failure,
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.0.1",
        ),
        (
            "stage15a_perf_v022_validator_cli_wiring",
            "v0.2.2",
            "The performance computation reached final validation but the flank-uniqueness validator received --package-dir instead of its required --input argument.",
            "Parallel validator CLI wiring error; all upstream computation and generic validators had completed.",
            "Resolved in v0.2.2.1 by component-specific argument wiring and a negative-fixture failure-parity test.",
            stage15a_perf_v022_failure,
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2.1",
        ),
    ]
    for (
        stage15a_perf_failure_id,
        stage15a_perf_attempt,
        stage15a_perf_summary,
        stage15a_perf_root_cause,
        stage15a_perf_resolution,
        stage15a_perf_source,
        stage15a_perf_superseded_by,
    ) in stage15a_perf_failures:
        conn.execute(
            """
            INSERT OR REPLACE INTO failures(
                failure_id,run_id,stage_key,attempt_version,status,summary,
                root_cause,resolution,source_path,superseded_by,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_failure_id,
                stage15a_perf_run_id,
                stage15a_perf_stage_key,
                stage15a_perf_attempt,
                "RESOLVED",
                stage15a_perf_summary,
                stage15a_perf_root_cause,
                stage15a_perf_resolution,
                str(stage15a_perf_source),
                stage15a_perf_superseded_by,
                stage15a_perf_effective_at,
            ),
        )

    for stage15a_perf_source_path, stage15a_perf_source_type in [
        (stage15a_perf_v020_failure, "stage15a_performance_failure_v020"),
        (stage15a_perf_v0201_qc, "stage15a_performance_qc_v0201"),
        (stage15a_perf_v0201_timing, "stage15a_performance_timing_v0201"),
        (stage15a_perf_v0201_runner, "stage15a_performance_runner_v0201"),
        (stage15a_perf_v021_qc, "stage15a_performance_qc_v021"),
        (stage15a_perf_v021_timing, "stage15a_performance_timing_v021"),
        (stage15a_perf_v021_runner, "stage15a_performance_runner_v021"),
        (stage15a_perf_v022_failure, "stage15a_performance_failure_v022"),
        (stage15a_perf_v022_validator_log, "stage15a_performance_validator_failure_v022"),
        (stage15a_perf_v022_runner, "stage15a_performance_runner_v022"),
        (stage15a_perf_v0221_qc, "stage15a_performance_qc_v0221"),
        (stage15a_perf_v0221_timing, "stage15a_performance_timing_v0221"),
        (stage15a_perf_v0221_comparison, "stage15a_performance_comparison_v0221"),
        (stage15a_perf_v0221_post_audit, "stage15a_performance_post_audit_v0221"),
        (stage15a_perf_v0221_validators, "stage15a_performance_validators_v0221"),
        (stage15a_perf_v0221_atomic, "stage15a_performance_atomic_publication_v0221"),
        (stage15a_perf_v0221_manifest, "stage15a_performance_package_manifest_v0221"),
        (stage15a_perf_v0221_runner, "stage15a_performance_runner_v0221"),
        (stage15a_perf_v0221_parallel_validator, "stage15a_performance_parallel_validator_v0221"),
    ]:
        source_document(conn, stage15a_perf_source_path, stage15a_perf_source_type, force_hash=True)


PYFRAG

BACKUP_DIR="$SSOT_BACKUPS/pre_stage15a_performance_v0.2.2.1_v0.1.0_$STAMP"
mkdir -p "$BACKUP_DIR"
cp -a "$SSOT_CLI" "$BACKUP_DIR/rnatr_ssot.py"
cp -a "$SSOT_DB" "$BACKUP_DIR/rnatr_ssot.sqlite"
[[ ! -f "$SSOT_SUMMARY" ]] || cp -a "$SSOT_SUMMARY" "$BACKUP_DIR/CURRENT_STATE.md"
if [[ -d "$SSOT_EXPORTS" ]]; then
    PREEXISTING_EXPORTS=true
    cp -a "$SSOT_EXPORTS" "$BACKUP_DIR/exports"
fi

MUTATION_STARTED=true

"$PYTHON_BIN" - "$SSOT_CLI" "$WORK_ROOT/source_insertion.pyfrag" "$EXPECTED_BASELINE_CLI_SHA" "$WORK_ROOT/source_patch.qc.tsv" <<'PY_PATCH'
from __future__ import annotations
import csv, hashlib, py_compile, sys
from pathlib import Path

cli = Path(sys.argv[1])
insertion = Path(sys.argv[2]).read_text(encoding="utf-8")
expected_baseline_sha = sys.argv[3]
qc_path = Path(sys.argv[4])
marker = "# Stage 15A performance SSOT registration v0.2.2.1"
anchor = "    current_metrics = [\n"

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

text = cli.read_text(encoding="utf-8")
before_sha = sha256(cli)
status = "ALREADY_PRESENT"

if insertion in text:
    if text.count(marker) != 1:
        raise SystemExit(f"performance marker count mismatch: {text.count(marker)}")
else:
    if marker in text:
        raise SystemExit("performance marker exists but insertion block is not byte-identical")
    if before_sha != expected_baseline_sha:
        raise SystemExit(f"unexpected unpatched SSOT source SHA: {before_sha}")
    if text.count(anchor) != 1:
        raise SystemExit(f"current_metrics anchor count mismatch: {text.count(anchor)}")
    text = text.replace(anchor, insertion + "\n" + anchor, 1)
    temp = cli.with_name(f".{cli.name}.stage15a_perf.part")
    temp.write_text(text, encoding="utf-8")
    py_compile.compile(str(temp), doraise=True)
    temp.replace(cli)
    status = "APPLIED"

after_sha = sha256(cli)
if cli.read_text(encoding="utf-8").count(marker) != 1:
    raise SystemExit("performance marker count after patch is not one")

with qc_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["metric", "value"])
    writer.writerows([
        ("source_patch_status", status),
        ("ssot_cli_sha256_before", before_sha),
        ("ssot_cli_sha256_after", after_sha),
        ("performance_marker_count", "1"),
        ("python_compile", "PASS"),
    ])
print("SSOT_STAGE15A_PERFORMANCE_SOURCE_PATCH_PASS")
print(f"source_patch_status\t{status}")
print(f"ssot_cli_sha256_after\t{after_sha}")
PY_PATCH

"$PYTHON_BIN" "$SSOT_CLI" --project-root "$PROJECT_ROOT" rebuild \
    2>&1 | tee "$LOG_ROOT/ssot_rebuild_after_stage15a_performance.log"

"$PYTHON_BIN" "$SSOT_CLI" --project-root "$PROJECT_ROOT" validate \
    2>&1 | tee "$LOG_ROOT/ssot_validate_after.log"

"$PYTHON_BIN" - \
    "$PROJECT_ROOT" "$SSOT_CLI" "$SSOT_DB" "$WORK_ROOT/current_pipeline.after.tsv" \
    "$WORK_ROOT/postcheck.qc.tsv" "$STAGE_KEY" "$IMPL_V0201" "$IMPL_V021" "$IMPL_V0221" <<'PY_POSTCHECK'
from __future__ import annotations
import csv, sqlite3, sys
from pathlib import Path

project_root_text, cli_text, db_text, pipeline_out_text, postcheck_out_text, stage_key, impl_v0201, impl_v021, impl_v0221 = sys.argv[1:]
PROJECT_ROOT = Path(project_root_text)
DB = Path(db_text)
PIPELINE_OUT = Path(pipeline_out_text)
POSTCHECK_OUT = Path(postcheck_out_text)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
checks = []
try:
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("SQLite integrity check failed")
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        raise SystemExit("foreign-key check failed")

    pipeline_rows = conn.execute("SELECT * FROM current_pipeline ORDER BY stage_order,stage_key").fetchall()
    if len(pipeline_rows) != 11:
        raise SystemExit(f"unexpected current_pipeline count: {len(pipeline_rows)}")
    if any(str(row["stage_key"]).startswith("15A_") for row in pipeline_rows):
        raise SystemExit("Stage 15A unexpectedly entered current_pipeline")
    with PIPELINE_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(pipeline_rows[0].keys())
        for row in pipeline_rows:
            writer.writerow([row[key] for key in row.keys()])

    stage = conn.execute("SELECT * FROM stage_definitions WHERE stage_key=?", (stage_key,)).fetchone()
    if stage is None or stage["implementation_status"] != "IMPLEMENTED_WITH_GATE":
        raise SystemExit("performance stage definition missing")

    expected_lifecycle = {
        impl_v0201: "SUPERSEDED",
        impl_v021: "SUPERSEDED",
        impl_v0221: "PROVISIONAL",
    }
    for impl_id, lifecycle in expected_lifecycle.items():
        row = conn.execute("SELECT * FROM implementations WHERE implementation_id=?", (impl_id,)).fetchone()
        if row is None or row["lifecycle_status"] != lifecycle:
            raise SystemExit(f"implementation lifecycle mismatch: {impl_id}")

    expected_runs = {
        "v0.2.0.1": ("PASS", "PASS"),
        "v0.2.1": ("PASS", "PASS"),
        "v0.2.2": ("FAIL", "FAIL"),
        "v0.2.2.1": ("PASS", "PASS"),
    }
    for attempt, (status, qc_status) in expected_runs.items():
        row = conn.execute(
            "SELECT status,qc_status FROM run_stages WHERE run_id=? AND stage_key=? AND attempt_tag=?",
            ("ENCSR307SHM_pilot100k_mm2splice_v1", stage_key, attempt),
        ).fetchone()
        if row is None or row["status"] != status or row["qc_status"] != qc_status:
            raise SystemExit(f"run-stage mismatch: {attempt}")

    expected_metrics = {
        "stage15a_performance_100k_status": "PASS",
        "stage15a_overall_status": "IN_PROGRESS",
        "bam_to_final_100k_performance_validated": "true",
        "restart_resume_validated": "false",
        "deterministic_250k_scaling_validated": "false",
        "full_5_31m_empirical_runtime_validated": "false",
        "active_pipeline_switched_to_v042": "false",
        "full_5_31m_run_started": "false",
        "package_exact_logical_parity": "true",
        "performance_candidate_bam_to_final_seconds": "65.76363927999046",
        "performance_candidate_speedup": "5.078519507992296",
        "conservative_linear_5_31m_projection_minutes": "58.230370558041365",
        "five_m_hard_ceiling_60min_projection": "PASS",
        "five_m_target_30min": "TARGET_NOT_MET",
        "hard_ceiling_evidence_scope": "100K_LINEAR_PROJECTION_NOT_EMPIRICAL_5_31M",
        "next_gate": "RUN_STAGE15A_RESTART_AND_DETERMINISTIC_250K_SCALING_NOT_FULL_5_31M",
    }
    rows = conn.execute(
        "SELECT metric_name,value_text FROM metrics WHERE run_id=? AND stage_key=? AND metric_status='CURRENT'",
        ("ENCSR307SHM_pilot100k_mm2splice_v1", stage_key),
    ).fetchall()
    metrics = {row["metric_name"]: row["value_text"] for row in rows}
    for key, expected in expected_metrics.items():
        if metrics.get(key) != expected:
            raise SystemExit(f"metric mismatch {key}: {metrics.get(key)!r} != {expected!r}")

    decision = conn.execute(
        "SELECT status,confidence FROM decisions WHERE decision_key='stage15a_performance_100k_v0_2_2_1_projection_pass'"
    ).fetchone()
    if decision is None or decision["status"] != "ACTIVE" or decision["confidence"] != "HIGH":
        raise SystemExit("performance decision missing")

    interpretation = conn.execute(
        "SELECT status,confidence FROM interpretations WHERE interpretation_key='stage15a_performance_projection_scope_v0_2_2_1'"
    ).fetchone()
    if interpretation is None or interpretation["status"] != "ACTIVE" or interpretation["confidence"] != "HIGH":
        raise SystemExit("performance interpretation missing")

    limitation = conn.execute(
        "SELECT severity,status FROM limitations WHERE limitation_key='CURRENT_RUNTIME_NOT_PRODUCTION_SCALE'"
    ).fetchone()
    if limitation is None or limitation["severity"] != "HIGH" or limitation["status"] != "ACTIVE":
        raise SystemExit("runtime limitation not updated")

    question = conn.execute(
        "SELECT priority,status,blocking,next_action FROM open_questions WHERE question_key='GENERAL_CALLER_PRODUCTION_INTEGRATION'"
    ).fetchone()
    if question is None or question["priority"] != "CRITICAL" or question["status"] != "OPEN" or int(question["blocking"]) != 1:
        raise SystemExit("production integration open question mismatch")
    if "250k" not in question["next_action"]:
        raise SystemExit("next action does not contain deterministic 250k scaling")

    failure_rows = conn.execute(
        "SELECT failure_id,status FROM failures WHERE stage_key=? ORDER BY failure_id",
        (stage_key,),
    ).fetchall()
    expected_failures = {
        "stage15a_perf_v020_escape_anchor",
        "stage15a_perf_v022_validator_cli_wiring",
    }
    if {row["failure_id"] for row in failure_rows} != expected_failures:
        raise SystemExit("performance failure history mismatch")
    if any(row["status"] != "RESOLVED" for row in failure_rows):
        raise SystemExit("performance failure status mismatch")

    if conn.execute("SELECT COUNT(*) FROM scan_warnings").fetchone()[0] != 0:
        raise SystemExit("SSOT scan warnings are not zero")

    checks.extend([
        ("sqlite_integrity", "PASS"),
        ("foreign_keys", "PASS"),
        ("active_pipeline_stages", "11"),
        ("stage15a_current_pipeline_present", "false"),
        ("performance_stage_definition", "PASS"),
        ("performance_implementations", "3"),
        ("performance_run_stages", "4"),
        ("current_metrics_verified", str(len(expected_metrics))),
        ("performance_decision", "PASS"),
        ("performance_interpretation", "PASS"),
        ("runtime_limitation", "HIGH_ACTIVE"),
        ("production_question", "CRITICAL_OPEN_BLOCKING"),
        ("resolved_failures", "2"),
        ("scan_warnings", "0"),
        ("postcheck_status", "PASS"),
    ])
finally:
    conn.close()

with POSTCHECK_OUT.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["metric", "value"])
    writer.writerows(checks)
print("STAGE15A_PERFORMANCE_SSOT_POSTCHECK_PASS")
PY_POSTCHECK

cmp -s "$WORK_ROOT/current_pipeline.before.tsv" "$WORK_ROOT/current_pipeline.after.tsv" \
    || die "current_pipeline changed during performance registration"

CLI_SHA_AFTER="$(sha256_file "$SSOT_CLI")"
DB_SHA_AFTER="$(sha256_file "$SSOT_DB")"
PIPELINE_BEFORE_SHA="$(sha256_file "$WORK_ROOT/current_pipeline.before.tsv")"
PIPELINE_AFTER_SHA="$(sha256_file "$WORK_ROOT/current_pipeline.after.tsv")"
SOURCE_PATCH_STATUS="$(awk -F '\t' '$1=="source_patch_status"{print $2}' "$WORK_ROOT/source_patch.qc.tsv")"

cat > "$WORK_ROOT/stage15a_performance_ssot_update.qc.tsv" <<EOF_QC
metric	value
update_version	$UPDATE_VERSION
update_script_sha256	$SELF_SHA
run_id	$RUN_ID
stage_key	$STAGE_KEY
current_implementation_id	$IMPL_V0221
source_patch_status	$SOURCE_PATCH_STATUS
ssot_cli_sha256_before	$BASELINE_CLI_SHA
ssot_cli_sha256_after	$CLI_SHA_AFTER
ssot_db_sha256_before	$BASELINE_DB_SHA
ssot_db_sha256_after	$DB_SHA_AFTER
active_pipeline_before_sha256	$PIPELINE_BEFORE_SHA
active_pipeline_after_sha256	$PIPELINE_AFTER_SHA
active_pipeline_byte_identical	true
active_pipeline_stage_count	11
v0201_performance_seconds	99.7883502789773
v021_performance_seconds	81.39999548299238
v0221_performance_seconds	65.76363927999046
v0221_reference_speedup	5.078519507992296
v0221_linear_5_31m_projection_minutes	58.230370558041365
v0221_60min_projection_status	PASS
v0221_30min_target	TARGET_NOT_MET
v0221_exact_logical_parity	true
v0221_frozen_validators	PASS
v0221_atomic_publication	PASS
stage15a_overall_status	IN_PROGRESS
restart_resume_validated	false
deterministic_250k_scaling_validated	false
full_5_31m_empirical_runtime_validated	false
active_pipeline_modified	false
full_5_31m_run_started	false
rollback_backup	$BACKUP_DIR
audit_status	PASS
next_gate	RUN_STAGE15A_RESTART_AND_DETERMINISTIC_250K_SCALING_NOT_FULL_5_31M
EOF_QC

cat > "$WORK_ROOT/update_contract.tsv" <<EOF_CONTRACT
component	status	detail
PERFORMANCE_HISTORY	PASS	v0.2.0.1, v0.2.1, v0.2.2 failure, and v0.2.2.1 registered
V0221_CORRECTNESS	PASS	Exact logical package parity, frozen validators, failure parity, and atomic publication
V0221_60MIN_PROJECTION	PASS	58.230370558041365-minute conservative linear 5.31M projection
V0221_30MIN_TARGET	OPEN	TARGET_NOT_MET
RESTART_RESUME	OPEN	Blocking next gate
DETERMINISTIC_250K_SCALING	OPEN	Blocking next gate
FULL_5_31M	NOT_RUN	Prohibited
ACTIVE_PIPELINE	UNCHANGED	Before/after current_pipeline snapshots are byte-identical
IMPLEMENTATION_LIFECYCLE	PROVISIONAL	v0.2.2.1 is not ACTIVE
ROLLBACK	ENABLED	SSOT source, DB, summary, and exports restored on failure
EOF_CONTRACT

mkdir -p "$META_INSTALL" "$UPDATE_QC_INSTALL" "$(dirname "$SCRIPT_INSTALL")" "$(dirname "$DESIGN_INSTALL")"
cp -a "$SELF" "$SCRIPT_INSTALL"
chmod 0755 "$SCRIPT_INSTALL"
cp -a "$WORK_ROOT/RNA_TR_Scout_Stage15A_performance_SSOT_registration_v0.2.2.1.md" "$DESIGN_INSTALL"
cp -a "$WORK_ROOT/preflight.qc.tsv" "$WORK_ROOT/source_patch.qc.tsv" \
    "$WORK_ROOT/postcheck.qc.tsv" "$WORK_ROOT/update_contract.tsv" \
    "$WORK_ROOT/current_pipeline.before.tsv" "$WORK_ROOT/current_pipeline.after.tsv" \
    "$META_INSTALL/"
cp -a "$WORK_ROOT/stage15a_performance_ssot_update.qc.tsv" "$UPDATE_QC_INSTALL/"
cp -a "$LOG_ROOT" "$UPDATE_QC_INSTALL/logs"

mkdir -p \
    "$BUNDLE_ROOT/script" "$BUNDLE_ROOT/docs" "$BUNDLE_ROOT/metadata" \
    "$BUNDLE_ROOT/qc" "$BUNDLE_ROOT/ssot" "$BUNDLE_ROOT/evidence"
cp -a "$SELF" "$BUNDLE_ROOT/script/"
cp -a "$WORK_ROOT/RNA_TR_Scout_Stage15A_performance_SSOT_registration_v0.2.2.1.md" "$BUNDLE_ROOT/docs/"
cp -a "$WORK_ROOT/preflight.qc.tsv" "$WORK_ROOT/source_patch.qc.tsv" \
    "$WORK_ROOT/postcheck.qc.tsv" "$WORK_ROOT/update_contract.tsv" \
    "$WORK_ROOT/current_pipeline.before.tsv" "$WORK_ROOT/current_pipeline.after.tsv" \
    "$BUNDLE_ROOT/metadata/"
cp -a "$WORK_ROOT/stage15a_performance_ssot_update.qc.tsv" "$BUNDLE_ROOT/qc/"
cp -a "$LOG_ROOT" "$BUNDLE_ROOT/qc/logs"
cp -a "$SSOT_CLI" "$SSOT_DB" "$BUNDLE_ROOT/ssot/"
[[ ! -f "$SSOT_SUMMARY" ]] || cp -a "$SSOT_SUMMARY" "$BUNDLE_ROOT/ssot/"
[[ ! -d "$SSOT_EXPORTS" ]] || cp -a "$SSOT_EXPORTS" "$BUNDLE_ROOT/ssot/exports"
mkdir -p "$BUNDLE_ROOT/evidence/v0.2.0" "$BUNDLE_ROOT/evidence/v0.2.0.1" \
    "$BUNDLE_ROOT/evidence/v0.2.1" "$BUNDLE_ROOT/evidence/v0.2.2" \
    "$BUNDLE_ROOT/evidence/v0.2.2.1"
cp -a "$V020_FAILURE" "$BUNDLE_ROOT/evidence/v0.2.0/"
cp -a "$V0201_QC" "$V0201_TIMING" "$BUNDLE_ROOT/evidence/v0.2.0.1/"
cp -a "$V021_QC" "$V021_TIMING" "$BUNDLE_ROOT/evidence/v0.2.1/"
cp -a "$V022_FAILURE" "$V022_VALIDATOR_LOG" "$BUNDLE_ROOT/evidence/v0.2.2/"
cp -a "$V0221_QC" "$V0221_TIMING" "$V0221_COMPARISON" "$V0221_POST_AUDIT" \
    "$V0221_VALIDATORS" "$V0221_ATOMIC" "$V0221_MANIFEST" \
    "$BUNDLE_ROOT/evidence/v0.2.2.1/"

"$PYTHON_BIN" - "$BUNDLE_ROOT" <<'PY_MANIFEST'
from pathlib import Path
import csv, hashlib, sys
root = Path(sys.argv[1]).resolve()
rows = []
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    rows.append((str(path.relative_to(root)), path.stat().st_size, h.hexdigest()))
with (root / "artifact_manifest.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["relative_path", "bytes", "sha256"])
    writer.writerows(rows)
PY_MANIFEST

rm -f "$OUTPUT_BUNDLE" "$OUTPUT_BUNDLE_SHA"
tar -C "$WORK_ROOT" -czf "$OUTPUT_BUNDLE.part" "$(basename "$BUNDLE_ROOT")"
mv -f "$OUTPUT_BUNDLE.part" "$OUTPUT_BUNDLE"
printf '%s  %s\n' "$(sha256_file "$OUTPUT_BUNDLE")" "$(basename "$OUTPUT_BUNDLE")" > "$OUTPUT_BUNDLE_SHA"

SUCCESS=true
MUTATION_STARTED=false

say
say "===== STAGE 15A PERFORMANCE SSOT UPDATE COMPLETE ====="
cat "$WORK_ROOT/stage15a_performance_ssot_update.qc.tsv"
say
say "Installed script:  $SCRIPT_INSTALL"
say "Design record:     $DESIGN_INSTALL"
say "SSOT update QC:    $UPDATE_QC_INSTALL/stage15a_performance_ssot_update.qc.tsv"
say "Output bundle:     $OUTPUT_BUNDLE"
say "Bundle SHA256:     $OUTPUT_BUNDLE_SHA"
say "Next gate:         RUN_STAGE15A_RESTART_AND_DETERMINISTIC_250K_SCALING_NOT_FULL_5_31M"
say "STAGE15A_PERFORMANCE_SSOT_UPDATE_PASS"
