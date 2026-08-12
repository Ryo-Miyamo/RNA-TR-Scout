#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
TRACKER="$PROJECT_ROOT/metadata/build_tracker/rnatr_build_tracker.py"
CHECKPOINT_ROOT="$PROJECT_ROOT/metadata/build_tracker/checkpoints"
STAMP="$(date '+%Y%m%d_%H%M%S')"
CHECKPOINT_DIR="$CHECKPOINT_ROOT/${STAMP}_step11_p3_end_to_end_v032"
LATEST_LINK="$CHECKPOINT_ROOT/latest_step11_checkpoint"

CHECKPOINT_TSV="$CHECKPOINT_DIR/step11_p3_end_to_end_checkpoint.tsv"
CHECKPOINT_MD="$CHECKPOINT_DIR/step11_p3_end_to_end_checkpoint.md"
ARTIFACT_MANIFEST="$CHECKPOINT_DIR/step11_p3_end_to_end_artifacts.tsv"
MODULE_INVENTORY="$CHECKPOINT_DIR/production_module_inventory.tsv"

SCHEMA_QC="$PROJECT_ROOT/qc/11_schema_regression_v032_postcheck/$RUN_ID/schema_regression_v0.3.2.postcheck.qc.tsv"
PACKAGE_QC="$PROJECT_ROOT/qc/11_production_package/$RUN_ID/production_package_skeleton.qc.tsv"
GEOMETRY_QC="$PROJECT_ROOT/qc/11_production_p3_geometry/$RUN_ID/p3_geometry_core.qc.tsv"
PAIR_QC="$PROJECT_ROOT/qc/11_production_p3_pair_projection_fix/$RUN_ID/p3_pair_alignment_projection_contract_fix.qc.tsv"
REPEAT_QC="$PROJECT_ROOT/qc/11_production_p3_repeat/$RUN_ID/p3_repeat_measurement_core.qc.tsv"
FINAL_QC="$PROJECT_ROOT/qc/11_production_p3_end_to_end_finalize/$RUN_ID/p3_end_to_end_finalization.qc.tsv"

SELECTED_META="$PROJECT_ROOT/results/11_production_p3_end_to_end_finalize/$RUN_ID/p3_bridge_pair_metadata.selected23.tsv.gz"
E2E_REPLAY="$PROJECT_ROOT/results/11_production_p3_end_to_end/$RUN_ID/p3_end_to_end_replay.tsv"
E2E_COMPARE="$PROJECT_ROOT/results/11_production_p3_end_to_end/$RUN_ID/p3_end_to_end_field_comparison.tsv"

SCHEMA_PATCH="$PROJECT_ROOT/config/evidence_schema/v0.3.2/SCHEMA_PATCH_0.3.2.md"
REGRESSION_CASES="$PROJECT_ROOT/tests/regression/v0.3.2/regression_cases.tsv"
DECISION_RULES="$PROJECT_ROOT/tests/regression/v0.3.2/decision_rules.tsv"
PYPROJECT="$PROJECT_ROOT/pyproject.toml"

mkdir -p "$CHECKPOINT_DIR"

for path in \
  "$TRACKER" \
  "$SCHEMA_QC" \
  "$PACKAGE_QC" \
  "$GEOMETRY_QC" \
  "$PAIR_QC" \
  "$REPEAT_QC" \
  "$FINAL_QC" \
  "$SELECTED_META" \
  "$E2E_REPLAY" \
  "$E2E_COMPARE" \
  "$SCHEMA_PATCH" \
  "$REGRESSION_CASES" \
  "$DECISION_RULES" \
  "$PYPROJECT"
do
    test -s "$path" || {
        echo "ERROR: missing required checkpoint artifact: $path" >&2
        exit 1
    }
done

metric() {
    local file="$1"
    local key="$2"

    awk -F '\t' -v key="$key" '
        $1 == key {
            print $2
            found = 1
            exit
        }
        END {
            if (!found) {
                print "."
            }
        }
    ' "$file"
}

require_metric() {
    local file="$1"
    local key="$2"
    local expected="$3"
    local observed

    observed="$(metric "$file" "$key")"

    if [[ "$observed" != "$expected" ]]; then
        echo "ERROR: $file :: $key expected $expected, observed $observed" >&2
        exit 1
    fi
}

require_metric \
  "$SCHEMA_QC" \
  "postcheck_status" \
  "PASS"

require_metric \
  "$PACKAGE_QC" \
  "package_status" \
  "PASS"

require_metric \
  "$GEOMETRY_QC" \
  "geometry_core_status" \
  "PASS"

require_metric \
  "$PAIR_QC" \
  "pair_projection_contract_fix_status" \
  "PASS"

require_metric \
  "$REPEAT_QC" \
  "p3_repeat_measurement_core_status" \
  "PASS"

require_metric \
  "$FINAL_QC" \
  "p3_end_to_end_finalization_status" \
  "PASS"

require_metric \
  "$FINAL_QC" \
  "comparison_mismatches" \
  "0"

require_metric \
  "$FINAL_QC" \
  "standard_evidence_emitted" \
  "0"

require_metric \
  "$FINAL_QC" \
  "bad_allele_status_rows" \
  "0"

require_metric \
  "$FINAL_QC" \
  "bad_expansion_status_rows" \
  "0"

add_stage() {
    local stage="$1"
    local status="$2"
    local summary="$3"
    local artifact="$4"

    printf '%s\t%s\t%s\t%s\n' \
      "$stage" \
      "$status" \
      "$summary" \
      "$artifact" \
      >> "$CHECKPOINT_TSV"
}

row_count() {
    local path="$1"

    if [[ "$path" == *.tsv.gz ]]; then
        gzip -cd "$path" \
          | awk 'END {print NR-1}'
    elif [[ "$path" == *.tsv ]]; then
        awk 'END {print NR-1}' "$path"
    else
        printf '.'
    fi
}

add_artifact() {
    local label="$1"
    local path="$2"

    test -s "$path" || return 0

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$label" \
      "$(row_count "$path")" \
      "$(stat -c '%s' "$path")" \
      "$(sha256sum "$path" | awk '{print $1}')" \
      "$path" \
      >> "$ARTIFACT_MANIFEST"
}

printf 'stage\tstatus\tsummary\tprimary_artifact\n' \
  > "$CHECKPOINT_TSV"

add_stage \
  "schema_v0.3.2" \
  "PASS" \
  "P3 failure codes 3; JSON/TSV enums, dictionaries, templates, and 29-entry manifest validated." \
  "$SCHEMA_QC"

add_stage \
  "regression_fixture_v0.3.2" \
  "PASS" \
  "20 cases, 16 rules, 19 unique reads; RC019/RC020 and R014-R016 added." \
  "$REGRESSION_CASES"

add_stage \
  "production_package_v0.3.2" \
  "PASS" \
  "Editable rnatr-scout package installed; modular P3 production code and CLI available." \
  "$PACKAGE_QC"

add_stage \
  "p3_orientation_geometry" \
  "PASS" \
  "23 orientation rows replayed; transform mismatches 0." \
  "$GEOMETRY_QC"

add_stage \
  "p3_pair_projection" \
  "PASS" \
  "23 pairs; valid plus bridge 1; reverse-only 22; projection status and query-offset mismatches 0." \
  "$PAIR_QC"

add_stage \
  "p3_repeat_measurement" \
  "PASS" \
  "23 rows x 20 fields = 460 comparisons; mismatches 0; no_call 22; partial_internal 1." \
  "$REPEAT_QC"

add_stage \
  "p3_end_to_end_regression" \
  "PASS" \
  "23 candidates; 713 comparisons; mismatches 0; orientation rejects 22; homopolymer review 1; standard evidence 0; guardrail failures 0." \
  "$FINAL_QC"

add_stage \
  "p3_metadata_checkpoint" \
  "PASS" \
  "Full calibration metadata 1007 unique IDs; selected regression metadata 23; unused 984; exact selected ID set frozen." \
  "$SELECTED_META"

add_stage \
  "next_p3_batch_architecture" \
  "IN_PROGRESS" \
  "Design resumable, parallel, audited batch execution for 38,424 P3_SOFTCLIP_SIMPLE_PERIODIC_READY candidates; benchmark 100 then 1,000 before full run." \
  "$PROJECT_ROOT/results/11_p3_inventory/$RUN_ID/p3_proximal_inventory_summary.tsv"

printf 'label\tdata_rows\tbytes\tsha256\tpath\n' \
  > "$ARTIFACT_MANIFEST"

add_artifact "schema_postcheck_qc" "$SCHEMA_QC"
add_artifact "package_qc" "$PACKAGE_QC"
add_artifact "geometry_qc" "$GEOMETRY_QC"
add_artifact "pair_projection_qc" "$PAIR_QC"
add_artifact "repeat_measurement_qc" "$REPEAT_QC"
add_artifact "end_to_end_final_qc" "$FINAL_QC"
add_artifact "selected23_metadata" "$SELECTED_META"
add_artifact "end_to_end_replay" "$E2E_REPLAY"
add_artifact "end_to_end_713_comparison" "$E2E_COMPARE"
add_artifact "schema_patch" "$SCHEMA_PATCH"
add_artifact "regression_cases" "$REGRESSION_CASES"
add_artifact "decision_rules" "$DECISION_RULES"
add_artifact "pyproject" "$PYPROJECT"

printf 'module\tbytes\tsha256\tpath\n' \
  > "$MODULE_INVENTORY"

for path in \
  "$PROJECT_ROOT/src/rnatr_scout/sequence.py" \
  "$PROJECT_ROOT/src/rnatr_scout/cigar.py" \
  "$PROJECT_ROOT/src/rnatr_scout/fasta.py" \
  "$PROJECT_ROOT/src/rnatr_scout/paf.py" \
  "$PROJECT_ROOT/src/rnatr_scout/p3_geometry.py" \
  "$PROJECT_ROOT/src/rnatr_scout/p3_bridge.py" \
  "$PROJECT_ROOT/src/rnatr_scout/p3_pair.py" \
  "$PROJECT_ROOT/src/rnatr_scout/p3_repeat.py" \
  "$PROJECT_ROOT/src/rnatr_scout/p3.py" \
  "$PROJECT_ROOT/src/rnatr_scout/p3_pipeline.py" \
  "$PROJECT_ROOT/src/rnatr_scout/batch.py" \
  "$PROJECT_ROOT/src/rnatr_scout/contract.py" \
  "$PROJECT_ROOT/src/rnatr_scout/cli.py"
do
    test -s "$path" || {
        echo "ERROR: missing production module: $path" >&2
        exit 1
    }

    printf '%s\t%s\t%s\t%s\n' \
      "$(basename "$path")" \
      "$(stat -c '%s' "$path")" \
      "$(sha256sum "$path" | awk '{print $1}')" \
      "$path" \
      >> "$MODULE_INVENTORY"
done

{
    echo "# RNA-TR-Scout Step 11 checkpoint — P3 end-to-end production regression"
    echo
    echo "- Created: $(date -Is)"
    echo "- Run ID: \`$RUN_ID\`"
    echo "- Package: \`rnatr-scout 0.3.2\`"
    echo "- Tracker Step 11 remains: **in_progress**"
    echo
    echo "## Validated milestone"
    echo
    echo "- Schema v0.3.2 postcheck: $(metric "$SCHEMA_QC" postcheck_status)"
    echo "- Package skeleton: $(metric "$PACKAGE_QC" package_status)"
    echo "- Orientation geometry: $(metric "$GEOMETRY_QC" geometry_core_status)"
    echo "- Pair projection: $(metric "$PAIR_QC" pair_projection_contract_fix_status)"
    echo "- Repeat measurement: $(metric "$REPEAT_QC" p3_repeat_measurement_core_status)"
    echo "- End-to-end finalization: $(metric "$FINAL_QC" p3_end_to_end_finalization_status)"
    echo
    echo "## P3 final regression"
    echo
    echo "- Full pair metadata rows: $(metric "$FINAL_QC" full_metadata_rows)"
    echo "- Selected metadata rows: $(metric "$FINAL_QC" selected_metadata_rows)"
    echo "- Unused metadata IDs: $(metric "$FINAL_QC" unused_full_metadata_ids)"
    echo "- Pipeline rows: $(metric "$FINAL_QC" pipeline_rows)"
    echo "- Total comparisons: $(metric "$FINAL_QC" comparison_rows)"
    echo "- Comparison mismatches: $(metric "$FINAL_QC" comparison_mismatches)"
    echo "- Orientation reject: $(metric "$FINAL_QC" primary_orientation_reject)"
    echo "- Homopolymer review: $(metric "$FINAL_QC" primary_homopolymer_review)"
    echo "- Standard P3 evidence emitted: $(metric "$FINAL_QC" standard_evidence_emitted)"
    echo "- Exact repeat estimates emitted: $(metric "$FINAL_QC" repeat_estimate_rows)"
    echo "- Lower bounds emitted: $(metric "$FINAL_QC" repeat_lower_bound_rows)"
    echo "- Bad allele status rows: $(metric "$FINAL_QC" bad_allele_status_rows)"
    echo "- Bad expansion status rows: $(metric "$FINAL_QC" bad_expansion_status_rows)"
    echo
    echo "## Frozen interpretation"
    echo
    echo "- Query and candidate reference are normalized from mapped-block boundary toward target."
    echo "- A valid P3 bridge requires plus-orientation alignment after normalization."
    echo "- Target entry must be projected through CIGAR before repeat sizing."
    echo "- One-flank evidence never emits exact allele length."
    echo "- P3 alone never emits expansion or pathogenicity."
    echo "- Motif length 1 is routed to homopolymer/poly(A)/poly(T) review."
    echo
    echo "## Next task"
    echo
    echo "Design production batch execution for 38,424 P3_SOFTCLIP_SIMPLE_PERIODIC_READY candidates."
    echo
    echo "Do not start with all 38,424. Build and benchmark:"
    echo
    echo "1. 100-candidate stratified subset"
    echo "2. 1,000-candidate subset"
    echo "3. chunk manifest, atomic output, retry, resume, and aggregation"
    echo "4. compare per-pair minimap2 subprocess, worker-pool, and in-process alternatives"
    echo "5. only then run the full set"
    echo
    echo "This architecture step is Pro-level design work. High is sufficient for running a frozen script or reading QC."
    echo
    echo "## Stage table"
    echo
    echo '```text'
    column -ts $'\t' "$CHECKPOINT_TSV"
    echo '```'
    echo
    echo "## Files"
    echo
    echo "- Machine checkpoint: \`$CHECKPOINT_TSV\`"
    echo "- Artifact manifest: \`$ARTIFACT_MANIFEST\`"
    echo "- Module inventory: \`$MODULE_INVENTORY\`"
    echo "- Selected 23 metadata: \`$SELECTED_META\`"
    echo "- Final QC: \`$FINAL_QC\`"
} > "$CHECKPOINT_MD"

python "$TRACKER" mark 10 complete \
  --note "Evidence schema/package checkpoint更新。schema v0.3.2はP3 failure codes ORIENTATION_INCONSISTENT_BRIDGE, TARGET_ENTRY_NOT_PROJECTED, HOMOPOLYMER_REVIEWを追加しpostcheck PASS。regression fixture v0.3.2は20 cases, 16 rules, 19 reads。rnatr-scout 0.3.2 production package・unit tests・contract check PASS。詳細: $CHECKPOINT_DIR"

python "$TRACKER" mark 11 in_progress \
  --note "ONT cDNA 100k pilotのP3 production pathをend-to-endで凍結。raw clip orientation→isolated minimap2→PAF/bridge→CIGAR target-entry projection→repeat measurement→final decision。selected 23 candidatesで713 comparisons, mismatch 0, orientation reject 22, homopolymer review 1, standard P3 evidence 0, exact/lower-bound/expansion誤出力0。full metadata 1007からselected23を固定。次はP3 simple-periodic ready 38,424件向けの再開可能・並列batch architectureを100→1000件でbenchmarkする。Step 11は未完了。詳細: $CHECKPOINT_DIR"

python "$TRACKER" export

ln -sfn "$CHECKPOINT_DIR" "$LATEST_LINK"

echo "===== CHECKPOINT ====="
column -ts $'\t' "$CHECKPOINT_TSV"

echo
echo "===== ARTIFACT MANIFEST ====="
column -ts $'\t' "$ARTIFACT_MANIFEST"

echo
echo "===== MODULE INVENTORY ====="
column -ts $'\t' "$MODULE_INVENTORY"

echo
echo "===== TRACKER STEP 10 ====="
python "$TRACKER" show 10

echo
echo "===== TRACKER STEP 11 ====="
python "$TRACKER" show 11

echo
echo "===== TRACKER STATUS ====="
python "$TRACKER" status

echo
echo "===== COMPLETE ====="
echo "$CHECKPOINT_TSV"
echo "$CHECKPOINT_MD"
echo "$ARTIFACT_MANIFEST"
echo "$MODULE_INVENTORY"
echo "$LATEST_LINK"
