#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/mnt/intelssd/rnatr_project"
RUN_ID_100K="ENCSR307SHM_pilot100k_mm2splice_v1"
RUN_ID_250K="ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
INPUT_VERSION="rnatr_stage15a_250k_input_v0.1.0"
SCALING_VERSION="v0.1.0_250k_scaling"
DOWNLOADS="$HOME/Downloads"
PYTHON_BIN="/home/tokushimaneuro02/miniconda3/envs/rnatr-v03/bin/python"

PREP_SRC="$PWD/scripts/rnatr_stage15a_prepare_250k_input_v0.1.0.py"
EXTRACT_SRC="$PWD/scripts/rnatr_stage15a_extract_candidate_fastq_v0.1.0.py"
RUNNER_SRC="$PWD/scripts/rnatr_stage15a_run_scaling_250k_v0.1.0.py"
DOC_SRC="$PWD/docs/RNA_TR_Scout_Stage15A_deterministic_250k_scaling_contract_v0.1.0.md"

PREP_INSTALL="$PROJECT_ROOT/scripts/rnatr_stage15a_prepare_250k_input_v0.1.0.py"
EXTRACT_INSTALL="$PROJECT_ROOT/scripts/rnatr_stage15a_extract_candidate_fastq_v0.1.0.py"
RUNNER_INSTALL="$PROJECT_ROOT/scripts/rnatr_stage15a_run_scaling_250k_v0.1.0.py"
DOC_INSTALL="$PROJECT_ROOT/docs/stage15a/RNA_TR_Scout_Stage15A_deterministic_250k_scaling_contract_v0.1.0.md"
INSTALLER_INSTALL="$PROJECT_ROOT/scripts/rnatr_stage15a_install_and_run_scaling_250k_v0.1.0.sh"
WRAPPER_INSTALL="$PROJECT_ROOT/scripts/rnatr_stage15a_scaling_250k_v010.sh"
META_ROOT="$PROJECT_ROOT/metadata/stage15a/v0.3.0_250k_scaling_v0.1.0"

INPUT_RESULT="$PROJECT_ROOT/results/15_stage15a_inputs/$RUN_ID_250K/$INPUT_VERSION"
INPUT_QC="$PROJECT_ROOT/qc/15_stage15a_inputs/$RUN_ID_250K/$INPUT_VERSION"
SCALING_RESULT="$PROJECT_ROOT/results/15_stage15a_bam_to_final/$RUN_ID_250K/$SCALING_VERSION"
SCALING_QC="$PROJECT_ROOT/qc/15_stage15a_bam_to_final/$RUN_ID_250K/$SCALING_VERSION"
COMBINED_QC="$SCALING_QC/stage15a_scaling_250k.qc.tsv"

PREP_CONSOLE="$DOWNLOADS/rnatr_stage15a_prepare_250k_input_v0.1.0.console.log"
SCALING_CONSOLE="$DOWNLOADS/rnatr_stage15a_scaling_250k_v0.1.0.console.log"
PREP_TIME="$DOWNLOADS/rnatr_stage15a_prepare_250k_input_v0.1.0.time_v.txt"
SCALING_TIME="$DOWNLOADS/rnatr_stage15a_scaling_250k_v0.1.0.time_v.txt"
SUCCESS_BUNDLE="$DOWNLOADS/rnatr_stage15a_scaling_250k_output_v0.1.0.tar.gz"
FAILURE_BUNDLE="$DOWNLOADS/rnatr_stage15a_scaling_250k_failure_v0.1.0.tar.gz"

MUTATION_STARTED=false
COMPLETED=false

fail_bundle() {
    local rc="$1"
    set +e
    rm -f "$FAILURE_BUNDLE" "$FAILURE_BUNDLE.sha256"
    local tmp
    tmp="$(mktemp -d)"
    mkdir -p "$tmp/scripts" "$tmp/docs" "$tmp/console" "$tmp/input_qc" "$tmp/scaling_qc" "$tmp/metadata"
    cp -a "$PREP_INSTALL" "$EXTRACT_INSTALL" "$RUNNER_INSTALL" "$INSTALLER_INSTALL" "$tmp/scripts/" 2>/dev/null || true
    [[ -s "$WRAPPER_INSTALL" ]] && cp -a "$WRAPPER_INSTALL" "$tmp/scripts/" 2>/dev/null || true
    cp -a "$DOC_INSTALL" "$tmp/docs/" 2>/dev/null || true
    cp -a "$PREP_CONSOLE" "$SCALING_CONSOLE" "$PREP_TIME" "$SCALING_TIME" "$tmp/console/" 2>/dev/null || true
    [[ -d "$INPUT_QC" ]] && cp -a "$INPUT_QC"/. "$tmp/input_qc/" 2>/dev/null || true
    [[ -d "$SCALING_QC" ]] && cp -a "$SCALING_QC"/. "$tmp/scaling_qc/" 2>/dev/null || true
    [[ -d "$META_ROOT" ]] && cp -a "$META_ROOT"/. "$tmp/metadata/" 2>/dev/null || true
    printf 'exit_code\t%s\nmutation_started\t%s\n' "$rc" "$MUTATION_STARTED" > "$tmp/failure_summary.tsv"
    tar -czf "$FAILURE_BUNDLE" -C "$tmp" .
    rm -rf "$tmp"
    sha256sum "$FAILURE_BUNDLE" | tee "$FAILURE_BUNDLE.sha256"
    echo
    echo "ERROR: Stage 15A deterministic 250k scaling failed (exit $rc)." >&2
    echo "Upload:" >&2
    echo "$FAILURE_BUNDLE" >&2
    echo "$FAILURE_BUNDLE.sha256" >&2
}

on_exit() {
    local rc=$?
    if [[ "$COMPLETED" != true && "$rc" -ne 0 ]]; then
        fail_bundle "$rc"
    fi
}
trap on_exit EXIT

[[ -x "$PYTHON_BIN" ]] || { echo "ERROR: missing rnatr-v03 Python: $PYTHON_BIN" >&2; exit 2; }
[[ -s "$PROJECT_ROOT/config/paths.env" ]] || { echo "ERROR: missing project paths.env" >&2; exit 2; }
[[ ! -e "$SUCCESS_BUNDLE" ]] || { echo "ERROR: success bundle already exists: $SUCCESS_BUNDLE" >&2; exit 2; }
[[ ! -e "$FAILURE_BUNDLE" ]] || { echo "ERROR: failure bundle already exists: $FAILURE_BUNDLE" >&2; exit 2; }

mkdir -p "$PROJECT_ROOT/scripts" "$PROJECT_ROOT/docs/stage15a" "$META_ROOT"
MUTATION_STARTED=true
install -m 0755 "$PREP_SRC" "$PREP_INSTALL"
install -m 0755 "$EXTRACT_SRC" "$EXTRACT_INSTALL"
install -m 0755 "$RUNNER_SRC" "$RUNNER_INSTALL"
install -m 0644 "$DOC_SRC" "$DOC_INSTALL"
install -m 0755 "$0" "$INSTALLER_INSTALL"
if [[ -n "${RNATR_STAGE15A_SELF:-}" && -s "${RNATR_STAGE15A_SELF}" ]]; then
    install -m 0755 "${RNATR_STAGE15A_SELF}" "$WRAPPER_INSTALL"
fi

"$PYTHON_BIN" -m py_compile "$PREP_INSTALL" "$EXTRACT_INSTALL" "$RUNNER_INSTALL"
bash -n "$INSTALLER_INSTALL"

{
    printf 'artifact\tbytes\tsha256\tpath\n'
    for path in "$PREP_INSTALL" "$EXTRACT_INSTALL" "$RUNNER_INSTALL" "$DOC_INSTALL" "$INSTALLER_INSTALL"; do
        printf '%s\t%s\t%s\t%s\n' \
            "$(basename "$path")" \
            "$(stat -c '%s' "$path")" \
            "$(sha256sum "$path" | awk '{print $1}')" \
            "$path"
    done
    if [[ -s "$WRAPPER_INSTALL" ]]; then
        printf '%s\t%s\t%s\t%s\n' \
            "$(basename "$WRAPPER_INSTALL")" \
            "$(stat -c '%s' "$WRAPPER_INSTALL")" \
            "$(sha256sum "$WRAPPER_INSTALL" | awk '{print $1}')" \
            "$WRAPPER_INSTALL"
    fi
} > "$META_ROOT/installation_manifest.tsv"

cat > "$META_ROOT/execution_contract.tsv" <<EOF
metric\tvalue
stage\tSTAGE15A_DETERMINISTIC_250K_BAM_INPUT_SCALING
input_reads\t250000
nested_anchor_reads\t100000
replicates\t2
hash_seed_A\t0
hash_seed_B\t20260808
shards\t12
caller_workers_per_shard\t2
mapping_time\tSEPARATE_FROM_BAM_TO_FINAL
candidate_fastq_extraction\tINCLUDED_IN_COLD_BAM_TO_FINAL_TIMER
active_pipeline_switch\tPROHIBITED
ssot_update\tPROHIBITED
full_5_31m_run\tPROHIBITED
EOF

rm -f "$PREP_CONSOLE" "$SCALING_CONSOLE" "$PREP_TIME" "$SCALING_TIME"

echo "===== STAGE 15A DETERMINISTIC 250K INPUT + SCALING ====="
echo "project_root:             $PROJECT_ROOT"
echo "250k run:                $RUN_ID_250K"
echo "mapping:                 250k only; reported separately"
echo "BAM-to-final replicates: 2"
echo "active pipeline:         unchanged"
echo "SSOT:                    unchanged"
echo "full 5.31M:              prohibited"

echo
echo "===== PREPARE DETERMINISTIC NESTED 250K INPUT ====="
set +e
"/usr/bin/time" -v -o "$PREP_TIME" \
    "$PYTHON_BIN" "$PREP_INSTALL" \
    2>&1 | tee "$PREP_CONSOLE"
prep_rc=${PIPESTATUS[0]}
set -e
[[ "$prep_rc" -eq 0 ]] || exit "$prep_rc"

echo
echo "===== RUN TWO ISOLATED 250K BAM-TO-FINAL REPLICATES ====="
set +e
"/usr/bin/time" -v -o "$SCALING_TIME" \
    "$PYTHON_BIN" "$RUNNER_INSTALL" --orchestrate \
    2>&1 | tee "$SCALING_CONSOLE"
scale_rc=${PIPESTATUS[0]}
set -e
[[ "$scale_rc" -eq 0 ]] || exit "$scale_rc"

[[ -s "$COMBINED_QC" ]] || { echo "ERROR: combined 250k QC missing" >&2; exit 2; }
awk -F $'\t' '$1=="audit_status" && $2=="PASS" {ok=1} END{exit !ok}' "$COMBINED_QC"
awk -F $'\t' '$1=="deterministic_250k_scaling" && $2=="PASS" {ok=1} END{exit !ok}' "$COMBINED_QC"
awk -F $'\t' '$1=="active_pipeline_modified" && $2=="false" {ok=1} END{exit !ok}' "$COMBINED_QC"
awk -F $'\t' '$1=="ssot_modified" && $2=="false" {ok=1} END{exit !ok}' "$COMBINED_QC"
awk -F $'\t' '$1=="full_5_31m_run_started" && $2=="false" {ok=1} END{exit !ok}' "$COMBINED_QC"

rm -f "$SUCCESS_BUNDLE" "$SUCCESS_BUNDLE.sha256"
tmp="$(mktemp -d)"
mkdir -p "$tmp/scripts" "$tmp/docs" "$tmp/console" "$tmp/input_qc" "$tmp/scaling_qc" "$tmp/metadata" "$tmp/selected_results"
cp -a "$PREP_INSTALL" "$EXTRACT_INSTALL" "$RUNNER_INSTALL" "$INSTALLER_INSTALL" "$tmp/scripts/"
[[ -s "$WRAPPER_INSTALL" ]] && cp -a "$WRAPPER_INSTALL" "$tmp/scripts/"
cp -a "$DOC_INSTALL" "$tmp/docs/"
cp -a "$PREP_CONSOLE" "$SCALING_CONSOLE" "$PREP_TIME" "$SCALING_TIME" "$tmp/console/"
cp -a "$INPUT_QC"/. "$tmp/input_qc/"
cp -a "$SCALING_QC"/. "$tmp/scaling_qc/"
cp -a "$META_ROOT"/. "$tmp/metadata/"
find "$INPUT_RESULT" -maxdepth 3 -type f \
    \( -name '*manifest*.tsv' -o -name 'run_manifest.tsv' -o -name '*.mapper_command.sh' \) \
    -exec cp -a {} "$tmp/selected_results/" \; 2>/dev/null || true
for rep in A B; do
    pkg="$SCALING_RESULT/replicate_${rep}/package_performance"
    if [[ -d "$pkg" ]]; then
        cp -a "$pkg/package_manifest.tsv" "$tmp/selected_results/package_manifest.replicate_${rep}.tsv"
        cp -a "$pkg/materialization.qc.tsv" "$tmp/selected_results/materialization.replicate_${rep}.qc.tsv"
    fi
done

tar -czf "$SUCCESS_BUNDLE" -C "$tmp" .
rm -rf "$tmp"
sha256sum "$SUCCESS_BUNDLE" | tee "$SUCCESS_BUNDLE.sha256"

COMPLETED=true
trap - EXIT

echo
echo "===== STAGE 15A DETERMINISTIC 250K SCALING COMPLETE ====="
cat "$COMBINED_QC"
echo
echo "Output bundle: $SUCCESS_BUNDLE"
echo "SHA file:      $SUCCESS_BUNDLE.sha256"
echo "STAGE15A_DETERMINISTIC_250K_SCALING_PASS"
