# RNA-TR-Scout Single Source of Truth

- Generated: 2026-08-17T01:57:19+00:00
- Tool: rnatr_ssot_v0.1.2
- Database: `/mnt/intelssd/rnatr_project/metadata/ssot/rnatr_ssot.sqlite`
- Existing legacy build-tracker database: read-only source; not modified.

## Validation

| check | status | detail |
|---|---:|---|
| sqlite_integrity | PASS | ok |
| foreign_key_check | PASS | 0 |
| active_pipeline_mode | PASS | GENERIC_CORE |
| active_impl::CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL | PASS | 1 |
| active_impl::MAP_SPLICE | PASS | 0 |
| active_impl::11b_TARGET_ASSIGNMENT | PASS | 0 |
| active_impl::11d3_RAW_READ_PROJECTION | PASS | 0 |
| active_impl::11e_MOTIF_JOBS | PASS | 0 |
| active_impl::11f_PERIODIC_BASELINE | PASS | 0 |
| active_impl::11g_BASELINE_AUDIT | PASS | 0 |
| active_impl::11h_PERIODIC_REFINEMENT | PASS | 0 |
| active_impl::11i_INTERNAL_RECLASSIFICATION | PASS | 0 |
| active_impl::11j_EXACT_SPAN_CALIBRATION | PASS | 0 |
| active_impl::11k_CALIBRATED_EVIDENCE | PASS | 0 |
| active_impl::11k3_SPAN_NORMALIZATION | PASS | 0 |
| active_implementation_paths_present | PASS | 0 |
| active_paths_have_no_shell_variables | PASS | 0 |
| active_implementation_files_exist | PASS | 0 |
| view_rows::current_pipeline | PASS | 1 |
| view_rows::current_decisions | PASS | 47 |
| view_rows::current_interpretations | PASS | 26 |
| view_rows::current_algorithm_contract | PASS | 35 |
| view_rows::current_reference_hierarchy | PASS | 8 |
| view_rows::current_known_limitations | PASS | 22 |
| view_rows::current_open_questions | PASS | 12 |
| view_rows::current_results | PASS | 156 |
| current_target_artifacts | PASS | 4 |
| legacy_tracker_import | PASS | 63 |
| current_validator_exists | PASS | /mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py |
| current_validator_is_v0.4.2_package | PASS | /mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py |
| current_validator_sha256_recorded | PASS | 45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e |

## Current pipeline

| order | stage | name | version | script |
|---:|---|---|---|---|
| 20.0 | CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL | Generic sharded BAM+FASTQ to final Core | v0.1.0 | `/mnt/intelssd/rnatr_project/scripts/rnatr_core_production_entry_v0.1.0.py` |

## Current decisions

- **general_repeat_caller_contract_v0_1_0** — General repeat measurement will re-estimate raw-read repeat boundaries with an error-aware cyclic repeat model, treat catalog motifs as priors, preserve censored semantics, and explicitly support compound/interruption/LPS outputs.
- **general_repeat_caller_reference_v0_2_0** — Reference v0.2.0 adds conservative compound-repeat and interruption segmentation plus distinct exact-sequence and error-aware inferred LPS while preserving v0.1.0 simple-periodic regression behavior by default.
- **general_repeat_caller_reference_v0_3_0** — Reference v0.3.0 anchors motif selection to the projected locus core before soft tract extension, separates explicit censoring from projection-window context limits, and uses conditional anchored de-novo rescue through period 50.
- **general_repeat_caller_reference_v0_4_0_frozen** — Freeze rnatr_general_repeat_caller_ref_v0.4.0 as the measurement reference implementation. Preserve locus-anchored geometric expansion for recovery of repeats longer than the projected prior; do not force agreement to the legacy P0/P1 caller.
- **general_repeat_caller_v0_4_1_frozen_reference** — Promote deterministic Python general caller v0.4.1 as the frozen measurement reference; validated native implementation must remain exactly equivalent for production integration.
- **portable_core_result_manifest_v0_1_0** — Downstream layers resolve stable read_id, target_source, target_region_id, locus_id and evidence/event/call identifiers through core_result_manifest.json; machine-local paths remain in a separate local binding file.
- **stage15r_candidate_multiplicity_closure_v0_1_0** — Stage15R technical reverse traceability passed with biology weighting deferred post-Freeze.
- **stage15s_extensibility_hygiene_closure_v0_1_0** — Seven extension boundaries contain no pre-Freeze hard coupling and final hygiene passes with cleanup/Git/public-release scope retained.
- **architecture_consistency_audit_cadence_v0_1_0** — Run formal audits after 250k scaling, before biology-layer implementation, and before release candidate. Audit SSOT, active paths, schema/contracts, performance gates, restart/validation scope, biology roadmap, and script lifecycle for contradictions, obsolete remnants, implementation-state inflation, frozen-contract drift, and planned-item omissions.
- **authoritative_originals_required_for_prerc_and_freeze_v0_1_0** — PRE_RELEASE_CANDIDATE and Core Freeze conclusions must be based on reread original code, SSOT, schema, contracts, validators, runners, manifests, and formal evidence. Conversation summaries and memory are not authoritative.
- **prerc_architecture_audit_remediation_v0_1_0** — Accept the Stage15G PRE_RELEASE_CANDIDATE remediation after exact-original audit: stale current SSOT records are superseded, lifecycle rows are classified with the frozen vocabulary, G24 advances to PRE_BIOLOGY remaining open, and PRE_RELEASE_CANDIDATE audit closes. The active pipeline, schema v0.4.2, Stage15C clean benchmark, and scientific packages remain unchanged.
- **stage15_active_path_promotion_state_v0_1_0** — The active Core is the generic mapped-BAM plus read-coherent-source-FASTQ production entry v0.1.0, using sharded orchestrator v0.1.2, generic unit v0.1.1, evidence schema v0.4.2, portable result manifest v0.1.0, SHA-bound restart and post-publication final-state recovery. The legacy 11-row P0/P1 path is retained as history but is no longer current.
- **project_docs_and_downloads_canonicalization_v0_1_0** — Promote project-wide authoritative documents to a durable one-source layout, preserve stage-local history or pointers, and only then classify, move, or delete accumulated Downloads artifacts by checksum-backed inventory.
- **biology_ready_core_sidecar_separation_v0_1_0** — The v0.4.2 core 5-table package remains the repeat-measurement source of truth. Transcript/isoform, haplotype, observability, and duplicate/molecule-independence states will be added as versioned read/evidence-keyed sidecars rather than by inflating or rewriting the core tables.
- **caller_complex_strategy_gaps_deferred_from_release_engineering_v0_1_0** — VC, IUPAC-degenerate, complex disease-region, >100-bp repeat-unit, no-motif and unsupported-symbol strategies are not all automatically measured by the current production caller. Preserve these as explicit v0.5.0 scope limitations and future caller/biology work; do not change frozen caller semantics during current release engineering.
- **rna_comparison_panel_role** — The six fetal-brain PromethION datasets are used for RNA technical-bias characterization, not claimed as biological normal controls.
- **core_freeze_v0_1_0_acceptance_v0_1_0** — The validated generic Core is accepted as LOCAL_CORE_FREEZE_V0.1.0_ACCEPTED_WITH_SCOPE, permitting biology-sidecar work while public release gates remain open.
- **core_freeze_preservation_artifacts_required_v0_1_0** — Core Freeze requires a versioned checksummed Core Freeze Packet plus a machine-executable golden regression suite. SSOT alone is not sufficient to preserve the long-term scientific contract.
- **six_sample_scope_engineering_validation** — The six 100k-read fetal-brain comparison datasets close the replay/robustness gate but will not be used to estimate a precise RNA technical floor.
- **stage16t_user_facing_documentation_acceptance_v0_1_0** — Accept the Stage16T README and user guide as the current internal pre-release user-facing documentation, with internal Freeze/Stage/golden terminology kept in release records rather than ordinary-user prose.
- **large_file_storage** — New raw FASTQ and other large public datasets are downloaded directly to /media/tokushimaneuro02/T9; Intel SSD retains active indexes, catalogs, QC, manifests, scripts, and compact results.
- **stage15a_reference_correctness_pass_v0_1_3** — The isolated Stage 15A v0.1.3 path from the target 100k mapping-complete BAM and associated raw-read sequence store through schema v0.4.2 is accepted as the correctness and regression reference. It is not the active production pipeline and it has not passed the production performance gate.
- **general_locus_interpretation** — General loci are reported as population-relative longer, shorter, central, or non-comparable RNA observations; pathogenicity is not assigned.
- **purpose_specific_candidate_ranking_lanes_v0_1_0** — Candidate triage will maintain separate KNOWN_DISEASE, EXPANSION_DISCOVERY, RNA_PROCESSING, REPEAT_HETEROGENEITY, HAPLOTYPE_CONTROLLED, and TECHNICAL_CONFIDENCE lanes. Known disease repeats are retained independently of generic ranking thresholds.
- **parallel_11f_11h_active_v0_1_0** — Activate versioned 16-process multiprocessing implementations for frozen P0/P1 stages 11f and 11h; algorithms and output semantics are unchanged.
- **stage13a_performance_discovery_finalized** — Performance optimization will focus first on exact stages 11f and 11h, which together account for 80.1387% of profiled frozen-stage runtime. GPU hardware is available but GPU acceleration is not yet selected; the decision is deferred until dynamic kernel profiling.
- **mapping_baseline_separate_from_core_v0_1_0** — The current minimap2 splice configuration remains the FASTQ-to-BAM scientific baseline outside the active Core. Mapping acceleration is a post-Freeze Performance lane gated by TR-locus recall, locus assignment and final-output parity.
- **stage15a_deterministic_250k_scaling_acceptance_v0_1_2** — Stage15A v0.1.2 passes two-replicate 250k final-package and caller reproducibility and exact nested-100k parity. It does not close G06 or authorize full 5.31M because the linear 60-minute margin is only 0.141202 minutes.
- **stage15c_full_empirical_acceptance_v0_1_6** — The 5,312,696-read BAM-to-final v0.1.6 run completed in 60.041256352 minutes with correctness, memory, storage, validators, runtime-generated script/path binding, and atomic publication PASS. The result is PASS_WITH_DOCUMENTED_TOLERANCE, not strict <=60-minute PASS.
- **current_projection_implementation** — 11d3 / projection v0.3.3 is current; 11d and 11d2 are superseded.
- **current_validator** — Evidence schema v0.4.2 table and package validators are the current active final-package validators; the v0.3.1 assignment validator remains a supporting intermediate validator.
- **generic_core_input_contract_v0_1_0** — BAM alone is not the complete scientific input because raw source read sequence/quality is used by candidate extraction and hardclip-aware projection. BAM-to-final remains a timing boundary with mapping excluded.
- **stage15e_determinism_restart_acceptance_v0_1_0** — Accept exact checkpoint-based full-package reconstruction and selective caller-to-final restart/resume with corrupt-manifest rejection, atomic publication, and second-resume no-op. Preserve the explicit exclusion of upstream BAM partition/11b/11d3/11e full rerun and cross-hardware claims.
- **stage16r_fresh_public_fastq_e2e_acceptance_v0_1_0** — Accept Stage16R v0.1.0 as PASS for a fresh private-GitHub clone, fresh isolated environment, validated standard resources from exact local official/reference bundles, public `rnatr-scout run` FASTQ auto-mapping, exact five-table parity, and second-resume no-op. This is fresh-machine-equivalent validation, not final proof of full large-reference/catalog network acquisition.
- **stage16s_cross_hardware_parity_acceptance_v0_1_0** — Accept Stage16S v0.1.1 as exact five-table scientific parity for the tested Tier2 input on the tested second Linux x86-64 machine, including native kernel execution and second-resume no-op. Do not generalize this to arbitrary platforms or hardware.
- **final_ranking_gate** — Final candidate ranking remains intentionally unexecuted until versioned biology sidecars, observability and molecule-independence state, truth-bearing validation, sample-by-locus summaries, and purpose-specific ranking lanes are implemented. RNA LPS and the Core caller technical gates are no longer the blocking reason.
- **six_sample_replay_complete** — Stage 6AM v0.1.5 completed all six equalized 100k-read fetal-brain PromethION comparison datasets with the SSOT-verified frozen pipeline and validator_v0.3.1.
- **step11_status** — Step 11 is not complete despite completed P0/P1 and P3 subbranches.
- **stage15c_runtime_path_binding_resolution_v0_1_0** — The Stage15A 250k compatibility alias remains historical provenance and is not a release contract. Stage15C v0.1.6 uses runtime-bound 11b/11d3/11e sources, audits all generated shard scripts, rejects obsolete template run IDs and mapping-run IDs in analysis scripts, and binds the full analysis run identity explicitly.
- **primary_locus_catalog** — TRExplorer v2 is the primary GRCh38 locus, boundary, and motif-prior catalog.
- **primary_population_reference** — AoU PacBio HiFi validation cohort (2,102 individuals) is the primary genome-wide DNA repeat-length and LPS context.
- **tr_atlas_role** — TR-Atlas is supplementary short-read population context only; no further genome-wide live crawl is planned.
- **public_rc_single_pro_crosscut_audit_required_v0_1_0** — Before declaring the public v0.5.0 release candidate, perform one Pro-level cross-cut audit of Freeze exact state, current main, active production path, reference/catalog/mapping/CLI/install, golden and validation evidence, cross-hardware results, documentation, unresolved scope, and SSOT/Git/docs state consistency.
- **stage16_release_engineering_progress_checkpoint_v0_1_0** — Current release-engineering state now includes Stage16Q public CLI PASS, Stage16R fresh-machine-equivalent public FASTQ-to-final PASS with exact local reference/catalog resources, Stage16S scoped cross-hardware scientific parity PASS, and Stage16T owner-reviewed user documentation PASS. Full large-network resource acquisition remains a separate public-RC gate. The immutable Core Freeze root remains 4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb.
- **evidence_schema_v0_4_2_fullscale_validated_candidate_v0_1_0** — Adopt schema v0.4.2 and materializer v0.1.2 as the frozen Core evidence contract for the validated Stage15 candidate. Evidence spans isolated 100k correctness, deterministic 250k/500k scaling, empirical 5,312,696-read execution, and Stage15E scoped reconstruction/restart. This decision does not itself promote current_pipeline or close G25-G34.
- **stage15a_checkpoint_reproducibility_amendment_v0_1_0** — The original v0.1.2 QC field checkpoint_manifest_reproducibility=true was not supported by its implementation because the checker validated each replicate separately without A/B comparison. The historical QC is preserved and superseded by a 157-row role×shard logical comparison with zero differences.
- **g31_scope_split_technical_vs_biology_v0_1_0** — Preserve the original G31 v0.1.0 machine FAIL. Adopt G31-T PASS_WITH_SCOPE_AMENDMENT because row conservation, primary-ID uniqueness, cross-scale stability, low read-locus excess, and low target concentration show no scale-dependent technical runaway. Defer G31-B candidate-rate and multiplicity meaning to the biology layer as nonblocking for current technical freeze.

## Current key results

| stage | metric | value | denominator |
|---|---|---:|---:|
| 11_aou_stat_semantics_rna_length_comparison | primary_population_length_comparable_loci | 8549 | 11042.0 |
| 11_bulk_longread_reference_crosswalk_coverage | aou_validation_length_and_lps_addressable_loci | 8556 | 11042.0 |
| 11_bulk_longread_reference_crosswalk_coverage | longread_population_any_addressable_loci | 8755 | 11042.0 |
| 11_bulk_longread_reference_crosswalk_coverage | population_reference_union_with_repeatcatalogs_loci | 8756 | 11042.0 |
| 11_bulk_longread_reference_crosswalk_coverage | trexplorer_exact_strict_motif_loci | 11028 | 11042.0 |
| 11_equalized_100k_mapping | mapped_bam_count | 6 | . |
| 11_equalized_100k_read_pilot_builder | validated_total_reads | 600000 | . |
| 11_population_relative_length_interpretation | multiread_max_only_longer_molecule_loci | 534 | . |
| 11_population_relative_length_interpretation | multiread_median_shift_longer_loci | 381 | . |
| 11_population_relative_length_interpretation | multiread_median_shift_shorter_loci | 409 | . |
| 11_population_relative_length_interpretation | rna_max_or_median_tail_union_loci | 3122 | 8549.0 |
| 11_population_relative_length_interpretation | rna_max_tail_loci | 2829 | 8549.0 |
| 11_population_relative_length_interpretation | rna_median_tail_loci | 2588 | 8549.0 |
| 11_primary_fetal_brain_promethion_fastq_acquisition | primary_fastq_total_bytes | 51197490146 | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | active_pipeline_switched_to_v042 | false | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | bam_to_final_100k_performance_validated | true | 100000.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | conservative_linear_5_31m_projection_minutes | 58.230370558041365 | 5312696.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | deterministic_250k_scaling_validated | false | 250000.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | five_m_hard_ceiling_60min_projection | PASS | 5312696.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | five_m_target_30min | TARGET_NOT_MET | 5312696.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | full_5_31m_empirical_runtime_validated | false | 5312696.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | full_5_31m_run_started | false | 5312696.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | general_repeat_calls_rows | 388571 | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | hard_ceiling_evidence_scope | 100K_LINEAR_PROJECTION_NOT_EMPIRICAL_5_31M | 5312696.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | next_gate | RUN_STAGE15A_RESTART_AND_DETERMINISTIC_250K_SCALING_NOT_FULL_5_31M | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | package_exact_logical_parity | true | 388571.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | performance_candidate_bam_to_final_seconds | 65.76363927999046 | 100000.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | performance_candidate_speedup | 5.078519507992296 | 100000.0 |
| 15A_BAM_TO_FINAL_PERFORMANCE | read_evidence_rows | 388571 | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | repeat_event_rows | 160297 | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | repeat_interruption_rows | 848 | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | repeat_segment_rows | 161265 | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | restart_resume_validated | false | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | stage15a_overall_status | IN_PROGRESS | . |
| 15A_BAM_TO_FINAL_PERFORMANCE | stage15a_performance_100k_status | PASS | 100000.0 |
| 15A_BAM_TO_FINAL_REFERENCE | active_pipeline_switched_to_v042 | false | . |
| 15A_BAM_TO_FINAL_REFERENCE | bam_to_final_100k_correctness_validated | true | 100000.0 |
| 15A_BAM_TO_FINAL_REFERENCE | bam_to_final_100k_performance_validated | false | 100000.0 |
| 15A_BAM_TO_FINAL_REFERENCE | called_attempt_rows | 160315 | . |
| 15A_BAM_TO_FINAL_REFERENCE | caller_attempt_rows | 388571 | . |
| 15A_BAM_TO_FINAL_REFERENCE | full_5_31m_run_started | false | 5312696.0 |
| 15A_BAM_TO_FINAL_REFERENCE | general_repeat_calls_rows | 388571 | . |
| 15A_BAM_TO_FINAL_REFERENCE | hashseed_determinism | true | 388571.0 |
| 15A_BAM_TO_FINAL_REFERENCE | low_confidence_called_rows | 6307 | . |
| 15A_BAM_TO_FINAL_REFERENCE | naive_5_31m_projection_minutes | 295.724073 | 5312696.0 |
| 15A_BAM_TO_FINAL_REFERENCE | native_caller_reference_parity | true | 388571.0 |
| 15A_BAM_TO_FINAL_REFERENCE | next_gate | BUILD_AND_RUN_STAGE15A_PERFORMANCE_CANDIDATE | . |
| 15A_BAM_TO_FINAL_REFERENCE | package_exact_logical_parity | true | 388571.0 |
| 15A_BAM_TO_FINAL_REFERENCE | read_evidence_rows | 388571 | . |
| 15A_BAM_TO_FINAL_REFERENCE | reference_bam_to_final_composed_seconds | 333.981925 | 100000.0 |
| 15A_BAM_TO_FINAL_REFERENCE | reference_lane_30min_target | TARGET_NOT_MET | 5312696.0 |
| 15A_BAM_TO_FINAL_REFERENCE | reference_lane_60min_hard_ceiling_projection | FAIL | 5312696.0 |
| 15A_BAM_TO_FINAL_REFERENCE | repeat_event_rows | 160297 | . |
| 15A_BAM_TO_FINAL_REFERENCE | repeat_interruption_rows | 848 | . |
| 15A_BAM_TO_FINAL_REFERENCE | repeat_segment_rows | 161265 | . |
| 15A_BAM_TO_FINAL_REFERENCE | stage15a_overall_status | IN_PROGRESS | . |
| 15A_BAM_TO_FINAL_REFERENCE | stage15a_reference_correctness_status | PASS | . |
| 15A_DETERMINISTIC_500K_SCALING | bam_to_final_seconds | 335.3816997719696 | . |
| 15A_DETERMINISTIC_500K_SCALING | candidate_reads | 396549 | 500000.0 |
| 15A_DETERMINISTIC_500K_SCALING | candidate_rows | 1948859 | . |
| 15A_DETERMINISTIC_500K_SCALING | full_projection_minutes | 59.39270049505812 | . |
| 15A_DETERMINISTIC_500K_SCALING | input_reads | 500000 | . |
| 15A_DETERMINISTIC_SCALING | alignment_records | 459743 | . |
| 15A_DETERMINISTIC_SCALING | bam_to_final_conservative_seconds | 169.0068411460379 | . |
| 15A_DETERMINISTIC_SCALING | caller_attempt_rows | 972533 | . |
| 15A_DETERMINISTIC_SCALING | caller_called_rows | 401163 | . |
| 15A_DETERMINISTIC_SCALING | caller_hashseed_logical_reproducibility | 1 | . |
| 15A_DETERMINISTIC_SCALING | candidate_reads | 198188 | . |
| 15A_DETERMINISTIC_SCALING | candidate_rows | 972533 | . |
| 15A_DETERMINISTIC_SCALING | candidate_window_bases | 446573382 | . |
| 15A_DETERMINISTIC_SCALING | hard_ceiling_margin_minutes | 0.14120207138726926 | . |
| 15A_DETERMINISTIC_SCALING | input_reads | 250000 | . |
| 15A_DETERMINISTIC_SCALING | linear_5_31m_projection_minutes | 59.85879792861273 | . |
| 15A_DETERMINISTIC_SCALING | maximum_observed_stage_rss_kbytes | 13928608.0 | . |
| 15A_DETERMINISTIC_SCALING | nested_100k_package_exact_parity | 1 | . |
| 15A_DETERMINISTIC_SCALING | original_checkpoint_claim_supported | 0 | . |
| 15A_DETERMINISTIC_SCALING | package_exact_logical_reproducibility | 1 | . |
| 15A_DETERMINISTIC_SCALING | package_exact_raw_reproducibility | 1 | . |
| 15A_DETERMINISTIC_SCALING | peak_temporary_and_output_bytes | 6779981067.0 | . |
| 15A_DETERMINISTIC_SCALING | per_read_normalized_scaling_factor | 1.0279652585921333 | . |
| 15A_DETERMINISTIC_SCALING | repeat_event_rows | 401096 | . |
| 15A_DETERMINISTIC_SCALING | replacement_checkpoint_logical_reproducibility | 1 | . |
| 15A_RESTART_RESUME_VALIDATION | restart_checkpoint_rows_verified | 138 | . |
| 15A_RESTART_RESUME_VALIDATION | restart_materializer_resume_seconds | 4.647109096986242 | . |
| 15A_RESTART_RESUME_VALIDATION | restart_noop_manifest_unchanged | 1 | . |
| 15A_RESTART_RESUME_VALIDATION | restart_package_exact_raw_parity | 1 | . |
| 15A_RESTART_RESUME_VALIDATION | restart_resume_validated | 1 | . |
| 15A_RESTART_RESUME_VALIDATION | restart_validator_seconds | 13.155308639048599 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | bam_to_final_minutes | 60.041256352 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | bam_to_final_seconds | 3602.475381092 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | caller_called_rows | 8524435 | 20656258.0 |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | caller_error_rows | 0 | 20656258.0 |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | caller_no_call_rows | 12131823 | 20656258.0 |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | candidate_reads | 4212263 | 5312696.0 |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | candidate_rows | 20656258 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | checkpoint_bytes | 140029015504 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | checkpoint_rows | 1884 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | input_reads | 5312696 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | maximum_host_used_fraction | 0.272065 | 1.0 |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | minimum_project_free_bytes | 165594337280 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | peak_temporary_and_output_bytes | 146580576495 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | repeat_events_rows | 8523140 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | repeat_interruptions_rows | 43399 | . |
| 15C_FULL_EMPIRICAL_BAM_TO_FINAL | repeat_segments_rows | 8573315 | . |
| 15D_G31_ROW_EXPANSION_AUDIT | assignment_excess_over_unique_loci | 6431 | 20656258.0 |
| 15D_G31_ROW_EXPANSION_AUDIT | candidate_read_rate | 0.792867312566 | 5312696.0 |
| 15D_G31_ROW_EXPANSION_AUDIT | candidate_rows_per_candidate_read | 4.903838625461 | 4212263.0 |
| 15D_G31_ROW_EXPANSION_AUDIT | candidate_rows_per_input_read | 3.888093352226 | 5312696.0 |
| 15D_G31_ROW_EXPANSION_AUDIT | exact_overlap_candidate_reads | 3020451 | 5312696.0 |
| 15D_G31_ROW_EXPANSION_AUDIT | proximal_only_candidate_reads | 1191812 | 5312696.0 |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | baseline_hash_seed | 0 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | checkpoint_artifacts | 1884 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | checkpoint_bytes | 140029015504 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | clean_runtime_minutes | 60.041256352 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | determinism_hash_seed | 20260810 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | fresh_target_shards | 1 | 144.0 |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | frozen_reused_shards | 143 | 144.0 |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | frozen_validator_count | 6 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | fullscale_restart_resume | PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | general_repeat_calls_rows | 20656258 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | read_evidence_rows | 20656258 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | reconstruction_shards | 144 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | release_scale_determinism | PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | repeat_events_rows | 8523140 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | repeat_interruptions_rows | 43399 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | repeat_segments_rows | 8573315 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | scope | CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | second_resume_noop | PASS | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | second_resume_scientific_commands | 0 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | target_caller_called_rows | 61333 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | target_caller_input_rows | 146558 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | target_materializer_repeat_event_rows | 61323 | . |
| 15E_RELEASE_SCALE_DETERMINISM_RESTART | target_shard | shard_065 | . |
| 16R_FRESH_END_TO_END | stage16r_final_exact_plain_table_parity | PASS_5_OF_5 | . |
| 16R_FRESH_END_TO_END | stage16r_post_resume_final_parity | PASS_5_OF_5 | . |
| 16R_FRESH_END_TO_END | stage16r_public_fastq_to_final_seconds | 289.0072668030043 | . |
| 16R_FRESH_END_TO_END | stage16r_public_resume | PASS_SECOND_RESUME_NOOP | . |
| 16R_FRESH_END_TO_END | stage16r_resource_scope | LOCAL_EXACT_OFFICIAL_GENCODE_CACHE_PLUS_LOCAL_EXACT_STAGE16L_BUNDLE;FULL_LARGE_NETWORK_DEFERRED_TO_RC | . |
| 16R_FRESH_END_TO_END | stage16r_source_head | 2191352170afe284c88cccd92c192efda2465b09 | . |
| 16R_FRESH_END_TO_END | stage16r_status | PASS_FRESH_MACHINE_EQUIVALENT_PUBLIC_FASTQ_TO_FINAL | . |
| 16U_SSOT_PROGRESS_CHECKPOINT | current_main_commit | be1de2ecdcaa681e3a3424486d340280001b0bf0 | . |
| 16U_SSOT_PROGRESS_CHECKPOINT | immutable_core_freeze_root | 4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb | . |
| 16U_SSOT_PROGRESS_CHECKPOINT | stage16r_evidence_binding_status | PENDING | . |
| 16U_SSOT_PROGRESS_CHECKPOINT | stage16s_cross_hardware_status | PASS_WITH_TESTED_SCOPE | . |
| 16U_SSOT_PROGRESS_CHECKPOINT | stage16t_documentation_status | PASS_OWNER_REVIEW_ACCEPTED | . |
| ARCHITECTURE_CONSISTENCY_AUDIT | architecture_audit_status | REVIEW | . |
| ARCHITECTURE_CONSISTENCY_AUDIT | blocking_conflicts | 0 | . |
| ARCHITECTURE_CONSISTENCY_AUDIT | open_items | 2 | . |
| ARCHITECTURE_CONSISTENCY_AUDIT | replacement_checkpoint_logical_reproducibility | 1 | . |
| ARCHITECTURE_CONSISTENCY_AUDIT | review_items | 3 | . |
| P01_BACKBONE | exact_span_events | 23867 | . |
| P01_BACKBONE | exact_span_loci | 11042 | . |
| SSOT_INGEST | artifact_manifests_ingested | 1932 | . |
| SSOT_INGEST | checkpoint_files_indexed | 25 | . |
| SSOT_INGEST | manifest_artifact_rows_ingested | 18535 | . |
| SSOT_INGEST | qc_metric_rows_ingested | 12565 | . |

## Blocking and open questions

- **CRITICAL / blocking=True / PUBLIC_RC_PRO_CROSSCUT_AUDIT** — Does the complete post-Freeze release-engineering state pass a final Pro-level cross-cut audit without Freeze drift, obsolete active paths, implementation-state inflation, release-claim overreach, or SSOT/Git/docs state drift?
- **HIGH / blocking=True / CLEAN_INSTALL_INTERNAL_BETA** — Can an independent clean machine install software/references and reproduce a test run without developer-local paths?
- **HIGH / blocking=True / FULL_NETWORK_FRESH_INSTALL_RC** — Can a fresh clone on a clean supported machine acquire the intended public resources over the network and run the public FASTQ-to-final workflow successfully?
- **HIGH / blocking=True / PUBLIC_CATALOG_BUNDLE_HOSTING** — What stable public location will distribute the compact validated catalog bundle with exact SHA binding?
- **CRITICAL / blocking=False / BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT** — Can the final output support same-haplotype molecule-level repeat heterogeneity, repeat-to-isoform/splicing association, observability-aware inference, molecule-independence-aware support, purpose-specific triage, and fully traceable researcher dossiers without losing core read-level repeat information?
- **HIGH / blocking=False / CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING** — Has the local Core Freeze been converted into a clean-install, cross-hardware, full-commit/tag-bound, thesis-citable public v0.5.0 release?
- **HIGH / blocking=False / RNA_TECHNICAL_FLOOR** — What locus-, motif-, support-, and platform-specific difference should define the technical floor for longer/shorter RNA observations?
- **HIGH / blocking=False / TRANSCRIPT_OBSERVABILITY** — Which genomic TR loci are actually reached and represented in complete RNA molecules, and how does this vary across CDS, UTR, intron, isoform, and platform?
- **MODERATE / blocking=False / DOWNLOADS_ARTIFACT_CLEANUP** — Which accumulated Downloads artifacts must be preserved, moved, retained temporarily, or deleted?
- **MODERATE / blocking=False / FULLSCALE_PEAK_DISK_BENCHMARK** — What is the measured peak disk usage of a representative approximately five-million-read release workflow?
- **MODERATE / blocking=False / G31_BIOLOGICAL_CANDIDATE_ENTRY_INTERPRETATION** — What biological and algorithmic factors explain the broad candidate-entry rate and ~4.9 loci/read, and can entry be narrowed without recall loss?
- **MODERATE / blocking=False / VIENNA_RECONCILIATION** — How much additional population coverage is gained after safe Vienna ONT boundary/motif reconciliation?

## Exports

- `current_algorithm_contract.tsv`: 35 rows
- `current_artifacts.tsv`: 4 rows
- `current_decisions.tsv`: 47 rows
- `current_interpretations.tsv`: 26 rows
- `current_known_limitations.tsv`: 22 rows
- `current_open_questions.tsv`: 12 rows
- `current_pipeline.tsv`: 1 rows
- `current_reference_hierarchy.tsv`: 8 rows
- `current_results.tsv`: 156 rows
- `current_runs.tsv`: 32 rows
- `latest_stage_status.tsv`: 224 rows
- `project_dashboard.tsv`: 12 rows
