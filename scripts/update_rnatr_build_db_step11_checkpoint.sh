#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

TRACKER="$PROJECT_ROOT/metadata/build_tracker/rnatr_build_tracker.py"
CHECKPOINT_ROOT="$PROJECT_ROOT/metadata/build_tracker/checkpoints"
STAMP="$(date '+%Y%m%d_%H%M%S')"
CHECKPOINT_DIR="$CHECKPOINT_ROOT/${STAMP}_step11_rna_repeat_pilot"

CHECKPOINT_TSV="$CHECKPOINT_DIR/step11_checkpoint.tsv"
CHECKPOINT_MD="$CHECKPOINT_DIR/step11_checkpoint.md"
ARTIFACT_MANIFEST="$CHECKPOINT_DIR/step11_artifact_manifest.tsv"
LATEST_LINK="$CHECKPOINT_ROOT/latest_step11_checkpoint"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

mkdir -p "$CHECKPOINT_DIR"

test -s "$TRACKER" || {
    echo "ERROR: tracker not found: $TRACKER" >&2
    exit 1
}

metric() {
    local file="$1"
    local key="$2"

    if [[ ! -s "$file" ]]; then
        printf '.'
        return
    fi

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

audit_status() {
    local file="$1"

    if [[ ! -s "$file" ]]; then
        printf 'NOT_AVAILABLE'
        return
    fi

    local value
    value="$(metric "$file" audit_status)"

    if [[ "$value" == "." ]]; then
        printf 'REVIEW'
    else
        printf '%s' "$value"
    fi
}

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

add_artifact() {
    local label="$1"
    local path="$2"

    if [[ ! -s "$path" ]]; then
        return
    fi

    local rows="."

    if [[ "$path" == *.tsv.gz ]]; then
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"
    elif [[ "$path" == *.bed.gz ]]; then
        rows="$(gzip -cd "$path" | awk 'END {print NR}')"
    elif [[ "$path" == *.tsv ]]; then
        rows="$(awk 'END {print NR-1}' "$path")"
    fi

    printf '%s\t%s\t%s\t%s\t%s\n' \
        "$label" \
        "$rows" \
        "$(stat -c '%s' "$path")" \
        "$(sha256sum "$path" | awk '{print $1}')" \
        "$path" \
        >> "$ARTIFACT_MANIFEST"
}

# -------------------------------------------------------------------------
# Known QC and artifact paths
# -------------------------------------------------------------------------

MAP_QC="$PROJECT_ROOT/qc/11_mapping/$RUN_ID/${RUN_ID}.mapping_qc.tsv"
ASSIGN_QC="$PROJECT_ROOT/qc/11_assignment/$RUN_ID/target_assignment_qc.tsv"
CANDIDATE_QC="$PROJECT_ROOT/qc/11_candidates/$RUN_ID/candidate_materialization_qc.tsv"
PROJECTION_QC="$PROJECT_ROOT/qc/11_projection/$RUN_ID/v0.3.3/raw_projection_qc.v0.3.3.tsv"
MOTIF_JOB_QC="$PROJECT_ROOT/qc/11_motif_jobs/$RUN_ID/motif_job_preparation_qc.tsv"
BASELINE_QC="$PROJECT_ROOT/qc/11_periodic_baseline/$RUN_ID/high_confidence_simple_periodic_qc.tsv"
BASELINE_AUDIT_QC="$PROJECT_ROOT/qc/11_periodic_baseline_audit/$RUN_ID/periodic_baseline_target_concordance_qc.tsv"
REFINEMENT_QC="$PROJECT_ROOT/qc/11_periodic_refinement/$RUN_ID/target_constrained_periodic_qc.tsv"
FINALIZATION_QC="$PROJECT_ROOT/qc/11_periodic_finalization/$RUN_ID/simple_periodic_evidence_finalization_qc.tsv"
SPAN_QC="$PROJECT_ROOT/qc/11_span_calibration/$RUN_ID/exact_span_global_periodicity_qc.tsv"
CALIBRATION_QC="$PROJECT_ROOT/qc/11_periodic_calibrated/$RUN_ID/simple_periodic_calibration_qc.tsv"
NORMALIZATION_QC="$PROJECT_ROOT/qc/11_periodic_calibrated/$RUN_ID/v0.3.3/simple_periodic_evidence.calibrated.v0.3.3.qc.tsv"
P2_QC="$PROJECT_ROOT/qc/11_p2_periodic/$RUN_ID/p2_alternate_exact_simple_periodic_qc.tsv"

SCHEMA_JSON="$PROJECT_ROOT/config/evidence_schema/v0.3.1/schema/rnatr_v03_table_schema.json"
FINAL_CATALOG="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz"
BAM="$PROJECT_ROOT/results/11_mapping/$RUN_ID/${RUN_ID}.sorted.bam"
ALIGNMENTS="$PROJECT_ROOT/results/11_assignment/$RUN_ID/alignment_segments.tsv.gz"
READ_TARGETS="$PROJECT_ROOT/results/11_assignment/$RUN_ID/read_target_candidates.tsv.gz"
PROJECTIONS="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3/read_target_projection.v0.3.3.tsv.gz"
MOTIF_JOBS="$PROJECT_ROOT/results/11_motif_jobs/$RUN_ID/motif_scan_jobs.tsv.gz"
CALIBRATED_V033="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID/v0.3.3/simple_periodic_evidence.calibrated.v0.3.3.tsv.gz"
P2_EVIDENCE="$PROJECT_ROOT/results/11_p2_periodic/$RUN_ID/p2_alternate_exact_simple_periodic_evidence.tsv.gz"

# -------------------------------------------------------------------------
# Determine P2 state without disturbing the running process
# -------------------------------------------------------------------------

P2_STATE="NOT_STARTED"

if [[ -s "$P2_QC" ]]; then
    P2_AUDIT="$(audit_status "$P2_QC")"

    if [[ "$P2_AUDIT" == "PASS" ]]; then
        P2_STATE="COMPLETE_PASS"
    else
        P2_STATE="COMPLETE_REVIEW"
    fi
elif pgrep -f \
    '11l_run_p2_alternate_exact_simple_periodic|run_p2_alternate_exact_periodic.py' \
    >/dev/null 2>&1
then
    P2_STATE="RUNNING"
elif [[ -e "$P2_EVIDENCE" ]]; then
    P2_STATE="PARTIAL_OUTPUT"
fi

# -------------------------------------------------------------------------
# Write checkpoint database table
# -------------------------------------------------------------------------

printf 'stage\tstatus\tkey_metrics\tprimary_artifact\n' \
    > "$CHECKPOINT_TSV"

add_stage \
    "09_final_pilot_catalog" \
    "COMPLETE_PASS" \
    "loci=5599658;static_core=347234;forced_disease_loci=100;analysis_regions=349410;strchive_regions=80;mapping_targets=349490" \
    "$FINAL_CATALOG"

SCHEMA_VERSION="."
if [[ -s "$PROJECT_ROOT/config/evidence_schema/v0.3.1/SCHEMA_VERSION" ]]; then
    SCHEMA_VERSION="$(
        tr -d '\r\n' \
        < "$PROJECT_ROOT/config/evidence_schema/v0.3.1/SCHEMA_VERSION"
    )"
fi

add_stage \
    "10_evidence_schema" \
    "COMPLETE_PASS" \
    "schema_version=$SCHEMA_VERSION;added=LEFT_ONLY_INTERNAL,RIGHT_ONLY_INTERNAL;sizing=partial_internal" \
    "$SCHEMA_JSON"

add_stage \
    "11a_splice_mapping" \
    "$(audit_status "$MAP_QC")" \
    "reads=$(metric "$MAP_QC" expected_input_reads);primary_mapping_rate_percent=$(metric "$MAP_QC" primary_mapping_rate_percent);spliced_primary_reads=$(metric "$MAP_QC" spliced_primary_reads);alignment_records=$(metric "$MAP_QC" alignment_records)" \
    "$BAM"

add_stage \
    "11b_target_candidate_assignment" \
    "$(audit_status "$ASSIGN_QC")" \
    "candidate_reads=$(metric "$ASSIGN_QC" reads_with_any_candidate);exact_overlap_reads=$(metric "$ASSIGN_QC" reads_with_exact_overlap_candidate);proximal_only_reads=$(metric "$ASSIGN_QC" reads_with_only_proximal_candidate);read_target_rows=$(metric "$ASSIGN_QC" read_target_candidates)" \
    "$READ_TARGETS"

add_stage \
    "11c_candidate_fastq_materialization" \
    "$(audit_status "$CANDIDATE_QC")" \
    "candidate_reads=$(metric "$CANDIDATE_QC" candidate_reads);exact_reads=$(metric "$CANDIDATE_QC" candidate_exact_fastq_reads);missing_all=$(metric "$CANDIDATE_QC" candidate_all_missing_ids);fastq_status=$(metric "$CANDIDATE_QC" fastq_extraction_status)" \
    "$CANDIDATE_QC"

add_stage \
    "11d_raw_read_projection_v0.3.3" \
    "$(audit_status "$PROJECTION_QC")" \
    "projection_rows=$(metric "$PROJECTION_QC" projection_rows_written);reads=$(metric "$PROJECTION_QC" projection_unique_reads);orientation_mismatch=$(metric "$PROJECTION_QC" orientation_raw_sequence_mismatch);missing_alignment_ids=$(metric "$PROJECTION_QC" missing_best_alignment_ids)" \
    "$PROJECTIONS"

add_stage \
    "11e_motif_job_preparation" \
    "$(audit_status "$MOTIF_JOB_QC")" \
    "jobs=$(metric "$MOTIF_JOB_QC" observed_projection_rows);eligible=$(metric "$MOTIF_JOB_QC" eligible::true);simple_periodic=$(metric "$MOTIF_JOB_QC" strategy::SIMPLE_PERIODIC_SCAN);canonical_motifs=$(metric "$MOTIF_JOB_QC" unique_canonical_motifs)" \
    "$MOTIF_JOBS"

add_stage \
    "11f_initial_periodic_baseline" \
    "COMPLETE_SUPERSEDED" \
    "calls=$(metric "$BASELINE_QC" calls_written);pass=$(metric "$BASELINE_QC" status::PASS);low_confidence=$(metric "$BASELINE_QC" status::LOW_CONFIDENCE);reason=off_target_extension_and_low_purity" \
    "$BASELINE_QC"

add_stage \
    "11g_baseline_technical_audit" \
    "$(audit_status "$BASELINE_AUDIT_QC")" \
    "keep_for_refinement=$(metric "$BASELINE_AUDIT_QC" class::KEEP_FOR_TARGET_CONSTRAINED_REFINEMENT);off_target=$(metric "$BASELINE_AUDIT_QC" class::OFF_TARGET_TRACT);gap_or_score_review=$(metric "$BASELINE_AUDIT_QC" class::GAP_OR_SCORE_REVIEW)" \
    "$BASELINE_AUDIT_QC"

add_stage \
    "11h_target_constrained_refinement" \
    "$(audit_status "$REFINEMENT_QC")" \
    "calls=$(metric "$REFINEMENT_QC" refined_calls_written);span=$(metric "$REFINEMENT_QC" evidence_class::SPAN);censored_left=$(metric "$REFINEMENT_QC" evidence_class::LEFT_ANCHORED_CENSORED_RIGHT);censored_right=$(metric "$REFINEMENT_QC" evidence_class::RIGHT_ANCHORED_CENSORED_LEFT)" \
    "$REFINEMENT_QC"

add_stage \
    "11i_one_flank_internal_reclassification" \
    "$(audit_status "$FINALIZATION_QC")" \
    "left_only_internal=$(metric "$FINALIZATION_QC" evidence_class::LEFT_ONLY_INTERNAL);right_only_internal=$(metric "$FINALIZATION_QC" evidence_class::RIGHT_ONLY_INTERNAL);residual_unresolved=$(metric "$FINALIZATION_QC" residual_motif_positive_one_flank_unresolved)" \
    "$FINALIZATION_QC"

add_stage \
    "11j_exact_span_global_calibration" \
    "$(audit_status "$SPAN_QC")" \
    "span_rows=$(metric "$SPAN_QC" observed_span_rows);periodic_exact=$(metric "$SPAN_QC" status::PERIODIC_EXACT_SPAN_PASS);short_exact=$(metric "$SPAN_QC" status::EXACT_SPAN_TOO_SHORT);low_periodicity=$(metric "$SPAN_QC" status::EXACT_SPAN_LOW_PERIODICITY)" \
    "$SPAN_QC"

add_stage \
    "11k_calibrated_simple_periodic_evidence" \
    "$(audit_status "$CALIBRATION_QC")" \
    "rows=$(metric "$CALIBRATION_QC" calibrated_evidence_rows);exact_span=$(metric "$CALIBRATION_QC" final_sizing::exact_span);lower_bound=$(metric "$CALIBRATION_QC" final_sizing::lower_bound);partial_internal=$(metric "$CALIBRATION_QC" final_sizing::partial_internal);no_call=$(metric "$CALIBRATION_QC" final_sizing::no_call)" \
    "$CALIBRATION_QC"

add_stage \
    "11k3_span_field_normalization" \
    "$(audit_status "$NORMALIZATION_QC")" \
    "rows=$(metric "$NORMALIZATION_QC" output_rows);span_normalized=$(metric "$NORMALIZATION_QC" span_rows_normalized);unused_audit=$(metric "$NORMALIZATION_QC" unused_span_audit_rows);consistency_errors=$(metric "$NORMALIZATION_QC" consistency_errors)" \
    "$CALIBRATED_V033"

add_stage \
    "11l_p2_alternate_exact_analysis" \
    "$P2_STATE" \
    "selected_p2_jobs=$(metric "$P2_QC" selected_p2_jobs);evidence_rows=$(metric "$P2_QC" evidence_rows_written);span_rows=$(metric "$P2_QC" span_rows);audit=$(metric "$P2_QC" audit_status)" \
    "$P2_EVIDENCE"

# -------------------------------------------------------------------------
# Write artifact manifest
# -------------------------------------------------------------------------

printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n' \
    > "$ARTIFACT_MANIFEST"

add_artifact "evidence_schema_v0.3.1" "$SCHEMA_JSON"
add_artifact "mapping_target_regions" "$FINAL_CATALOG"
add_artifact "pilot_sorted_bam" "$BAM"
add_artifact "alignment_segments" "$ALIGNMENTS"
add_artifact "read_target_candidates" "$READ_TARGETS"
add_artifact "raw_read_projections_v0.3.3" "$PROJECTIONS"
add_artifact "motif_scan_jobs" "$MOTIF_JOBS"
add_artifact "calibrated_simple_periodic_v0.3.3" "$CALIBRATED_V033"
add_artifact "p2_alternate_exact_evidence" "$P2_EVIDENCE"

# -------------------------------------------------------------------------
# Human-readable checkpoint
# -------------------------------------------------------------------------

{
    echo "# RNA-TR-Scout v0.3 Step 11 checkpoint"
    echo
    echo "- Created: $(date -Is)"
    echo "- Run: \`$RUN_ID\`"
    echo "- Current Step 11 state: **in progress**"
    echo "- P2 analysis state: **$P2_STATE**"
    echo
    echo "## Current validated milestone"
    echo
    echo "- Pilot input: 100,000 ONT cDNA reads"
    echo "- Primary mapping rate: $(metric "$MAP_QC" primary_mapping_rate_percent)%"
    echo "- Candidate reads: $(metric "$ASSIGN_QC" reads_with_any_candidate)"
    echo "- Exact-overlap candidate reads: $(metric "$ASSIGN_QC" reads_with_exact_overlap_candidate)"
    echo "- Raw-read projections: $(metric "$PROJECTION_QC" projection_rows_written)"
    echo "- High-confidence calibration cohort: $(metric "$CALIBRATION_QC" calibrated_evidence_rows) rows"
    echo "- Exact SPAN: $(metric "$CALIBRATION_QC" final_sizing::exact_span)"
    echo "- Censored lower-bound evidence: $(metric "$CALIBRATION_QC" final_sizing::lower_bound)"
    echo "- One-flank internal evidence: $(metric "$CALIBRATION_QC" final_sizing::partial_internal)"
    echo "- No-call: $(metric "$CALIBRATION_QC" final_sizing::no_call)"
    echo "- Normalized SPAN consistency errors: $(metric "$NORMALIZATION_QC" consistency_errors)"
    echo
    echo "## Frozen interpretation rules"
    echo
    echo "- SPAN size is the raw-read interval between both mapped flanks."
    echo "- Censored evidence reports a lower bound only."
    echo "- LEFT_ONLY_INTERNAL and RIGHT_ONLY_INTERNAL retain one-flank sequence evidence but report neither exact size nor a lower bound."
    echo "- RNA non-observation is not evidence against a DNA repeat expansion."
    echo "- P2 rows remain alternate locus hypotheses with low assignment confidence."
    echo
    echo "## Stage table"
    echo
    echo '```text'
    column -ts $'\t' "$CHECKPOINT_TSV"
    echo '```'
    echo
    echo "## Files"
    echo
    echo "- Machine-readable checkpoint: \`$CHECKPOINT_TSV\`"
    echo "- Artifact manifest: \`$ARTIFACT_MANIFEST\`"
} > "$CHECKPOINT_MD"

# -------------------------------------------------------------------------
# Update tracker DB. Step 11 deliberately remains in_progress.
# -------------------------------------------------------------------------

python "$TRACKER" mark 10 complete \
    --note "Evidence schemaをv0.3.1へ更新。SPAN/censoredに加え、片側flankでtarget上repeatを確認するがread末端へ到達しないLEFT_ONLY_INTERNAL/RIGHT_ONLY_INTERNALとsizing_status=partial_internalを追加。validator修正・全schema検証PASS。詳細: $CHECKPOINT_DIR"

python "$TRACKER" mark 11 in_progress \
    --note "ONT cDNA pilot 100k reads。mapping、target assignment、raw FASTQ投影、motif job分類、P0/P1 simple-periodic caller校正までPASS。校正済み49,793 evidence rows、exact SPAN 23,867、censored lower bound 535、one-flank internal 10,721、no-call 14,670。SPAN全フィールドv0.3.3正規化済み・consistency error 0。現在P2 alternate exact analysis=$P2_STATE。Step 11は未完了。詳細: $CHECKPOINT_DIR"

python "$TRACKER" export

rm -f "$LATEST_LINK"
ln -s "$CHECKPOINT_DIR" "$LATEST_LINK"

echo "===== CHECKPOINT DATABASE ====="
column -ts $'\t' "$CHECKPOINT_TSV"

echo
echo "===== ARTIFACT MANIFEST ====="
column -ts $'\t' "$ARTIFACT_MANIFEST"

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
echo "$LATEST_LINK"
