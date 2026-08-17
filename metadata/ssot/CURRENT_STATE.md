# RNA-TR-Scout Single Source of Truth

- Generated: 2026-08-17T09:32:21+00:00
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
| view_rows::current_decisions | PASS | 62 |
| view_rows::current_interpretations | PASS | 26 |
| view_rows::current_algorithm_contract | PASS | 35 |
| view_rows::current_reference_hierarchy | PASS | 8 |
| view_rows::current_known_limitations | PASS | 20 |
| view_rows::current_open_questions | PASS | 7 |
| view_rows::current_results | PASS | 225 |
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
- **stage16t_user_facing_documentation_acceptance_v0_1_0** — Accept the current README and USER_GUIDE as the ordinary-user surface, DEVELOPMENT.md as navigation to current contracts/SSOT and post-Freeze lanes, and DEVELOPMENT_HISTORY_v0.5.0.md as non-authoritative historical navigation. Stage-numbered files remain validation/reproducibility history rather than ordinary user entry points.
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
- **stage16aa_independent_machine_acceptance_v0_1_0** — Accept Stage16AA as PASS for independent second-host fresh clone, fresh environment, exact network resources, automatic Core resource selection, exact Tier2 five-table parity and second-resume no-op on Linux x86-64.
- **stage16r_fresh_public_fastq_e2e_acceptance_v0_1_0** — Accept Stage16R v0.1.0 as PASS for a fresh private-GitHub clone, fresh isolated environment, validated standard resources from exact local official/reference bundles, public `rnatr-scout run` FASTQ auto-mapping, exact five-table parity, and second-resume no-op. This is fresh-machine-equivalent validation, not final proof of full large-reference/catalog network acquisition.
- **stage16s_cross_hardware_parity_acceptance_v0_1_0** — Accept Stage16S v0.1.1 as exact five-table scientific parity for the tested Tier2 input on the tested second Linux x86-64 machine, including native kernel execution and second-resume no-op. Do not generalize this to arbitrary platforms or hardware.
- **stage16x_full_network_fresh_install_acceptance_v0_1_0** — Accept Stage16X v0.1.2 as PASS for fresh isolated source/environment/cache setup on the validated Linux x86-64 host, official GENCODE network acquisition, public catalog release-asset acquisition, public `rnatr-scout run` FASTQ auto-mapping, exact 5/5 final-table parity and second-resume no-op. This closes the intended full-network acquisition gate but is not a universal portability claim or a formal full-scale peak-disk benchmark.
- **final_ranking_gate** — Final candidate ranking remains intentionally unexecuted until versioned biology sidecars, observability and molecule-independence state, truth-bearing validation, sample-by-locus summaries, and purpose-specific ranking lanes are implemented. RNA LPS and the Core caller technical gates are no longer the blocking reason.
- **six_sample_replay_complete** — Stage 6AM v0.1.5 completed all six equalized 100k-read fetal-brain PromethION comparison datasets with the SSOT-verified frozen pipeline and validator_v0.3.1.
- **step11_status** — Step 11 is not complete despite completed P0/P1 and P3 subbranches.
- **stage15c_runtime_path_binding_resolution_v0_1_0** — The Stage15A 250k compatibility alias remains historical provenance and is not a release contract. Stage15C v0.1.6 uses runtime-bound 11b/11d3/11e sources, audits all generated shard scripts, rejects obsolete template run IDs and mapping-run IDs in analysis scripts, and binds the full analysis run identity explicitly.
- **primary_locus_catalog** — TRExplorer v2 is the primary GRCh38 locus, boundary, and motif-prior catalog.
- **primary_population_reference** — AoU PacBio HiFi validation cohort (2,102 individuals) is the primary genome-wide DNA repeat-length and LPS context.
- **tr_atlas_role** — TR-Atlas is supplementary short-read population context only; no further genome-wide live crawl is planned.
- **canonical_release_gate_table_v0_3_5** — Use validation/release_gates_v0.3.5.tsv as the current release-gate table. It preserves prior gates and records the formal G25-G30 Stage16AB adjudication; v0.3.4 remains historical/Freeze-era evidence.
- **public_rc_pro_audit_pre_remediation_v0_1_0** — The first final Pro adjudication found no scientific/runtime failure but required four metadata/governance packaging remediations before final PASS.
- **public_rc_pro_crosscut_audit_pass_v0_1_0** — The exact post-remediation RNA-TR-Scout v0.5.0 RC passes the final Pro audit for Freeze integrity, scientific/runtime identity, release packaging, standard resources, scoped portability, documentation, repository hygiene and SSOT/Git/docs consistency. Proceed only to guarded final-version and public-release binding.
- **public_rc_single_pro_crosscut_audit_required_v0_1_0** — Before declaring the public v0.5.0 release candidate, perform one Pro-level cross-cut audit of Freeze exact state, current main, active production path, reference/catalog/mapping/CLI/install, golden and validation evidence, cross-hardware results, documentation, unresolved scope, and SSOT/Git/docs state consistency.
- **public_v050_release_binding_v0_1_0** — Accept public RNA-TR-Scout v0.5.0 as bound to annotated tag object b6387580..., exact commit 9205049e..., tree feeca99e..., checksummed source/binding assets, public clone/setup evidence, BSD-3-Clause license detection, and tag-bound CITATION metadata.
- **v050_release_integrity_model_v0_1_0** — v0.5.0 uses an unsigned annotated tag plus exact tag-object, commit, tree and public asset SHA-256 binding. GitHub's immutable-release feature is not enabled; the project treats the tag as non-moving and detects drift through registered hashes.
- **software_license_bsd3_v0_1_0** — The RNA-TR-Scout software source is licensed under BSD-3-Clause with Copyright (c) 2026, Ryosuke Miyamoto. Third-party catalog/data terms remain separately attributed and are not relicensed by the software LICENSE.
- **g25_g29_release_readiness_closure_v0_1_0** — G25 reference bootstrap, G26 resource detection, G27 memory-aware Core scheduling, G28 scoped cross-hardware reproducibility and G29 clean-machine clone-to-test reproducibility are accepted for the currently tested Linux x86-64 ONT-cDNA release scope.
- **g30_hardware_profile_pass_with_scope_v0_1_0** — G30 is PASS_WITH_SCOPE: tested hardware profiles and a release-scale recommended profile are documented; a lower empirical CPU/RAM minimum is not established and is intentionally not invented. The minimum remains a nonblocking limitation while user-facing documentation preserves this distinction.
- **release_candidate_ready_for_final_pro_audit_v0_1_0** — The audited RC passed the final Pro cross-cut audit. Scientific/runtime changes are no longer authorized for this release line; the next permitted work is final 0.5.0 metadata, main/public-source verification and immutable tag/release/citation binding.
- **stage16_release_engineering_progress_checkpoint_v0_1_0** — Current release engineering now includes public catalog/network-install closure plus Stage16Z resource-aware Core scheduling and Stage16AA independent-machine fresh validation. G25-G29 are accepted. G30 has tested and recommended hardware profiles documented while the empirical minimum remains explicitly unmeasured and nonblocking. CLEAN_INSTALL_INTERNAL_BETA is closed for the current Linux x86-64 ONT-cDNA scope. The immutable Core Freeze root remains 4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb.
- **stage16ae_public_release_packaging_acceptance_v0_1_0** — Accept v0.5.0-rc1 mechanical packaging as complete with BSD-3-Clause, citation metadata, explicit Linux x86-64 conda lock, release notes and third-party notice separation. This does not create or authorize the final public v0.5.0 release before the final Pro audit.
- **stage16af_rc_preflight_acceptance_v0_1_0** — Accept candidate c7c0d985068c4d01f7669521e6fefd146fbb1718 / tree 568974b45cf06fd76a03e70e57a643184ecac528 as mechanically ready for the final Pro cross-cut audit. Public v0.5.0 remains unreleased.
- **stage16z_resource_aware_public_cli_acceptance_v0_1_0** — Accept resource detection and automatic Core scheduling for the current Linux x86-64 release scope. Tier2 and Tier3 automatic profiles retain exact scientific parity; resume reuses the recorded plan. Mapping-thread tuning and full-scale peak disk remain separate scopes.
- **stage16w_public_catalog_distribution_acceptance_v0_1_0** — Accept the public `Ryo-Miyamo/RNA-TR-Scout-resources` release `catalog-grch38-v0.1.0` as the standard catalog distribution for this validated profile. The outer archive SHA-256 is 54a24e4b60d920c8fec16b2df37b47e40407de42b949b18dc6233e97d85f2fef; unauthenticated download is exact; the five scientific runtime member bytes remain unchanged.
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
| 16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION | hostname | deeplearningboxii | . |
| 16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION | logical_cpus | 36 | . |
| 16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION | memory_total_bytes | 134726070272 | . |
| 16AB_G25_G30_RELEASE_READINESS | g25_status | PASS | . |
| 16AB_G25_G30_RELEASE_READINESS | g26_status | PASS_WITH_DEFINED_SCOPE | . |
| 16AB_G25_G30_RELEASE_READINESS | g27_status | PASS_WITH_DEFINED_SCOPE | . |
| 16AB_G25_G30_RELEASE_READINESS | g28_status | PASS_WITH_SCOPE | . |
| 16AB_G25_G30_RELEASE_READINESS | g29_status | PASS | . |
| 16AB_G25_G30_RELEASE_READINESS | g30_status | PASS_WITH_SCOPE_AMENDMENT | . |
| 16AE_PUBLIC_RELEASE_PACKAGING | candidate_package_version | 0.5.0rc1 | . |
| 16AE_PUBLIC_RELEASE_PACKAGING | explicit_lock_sha256 | 79004c8253021a6d30b35aecf91a244a1ae1460ccfcd8d77a135716b6235955c | . |
| 16AE_PUBLIC_RELEASE_PACKAGING | software_license | BSD-3-Clause | . |
| 16AF_RELEASE_CANDIDATE_PREFLIGHT | candidate_head | c7c0d985068c4d01f7669521e6fefd146fbb1718 | . |
| 16AF_RELEASE_CANDIDATE_PREFLIGHT | candidate_tree | 568974b45cf06fd76a03e70e57a643184ecac528 | . |
| 16AF_RELEASE_CANDIDATE_PREFLIGHT | git_archive_sha256 | b6b6b332560f4dca0b7450c5f27230ca6dffcc1791ce760a7714e54a975ed3ce | . |
| 16AF_RELEASE_CANDIDATE_PREFLIGHT | rc_preflight_status | PASS | . |
| 16AK_RC_PREFLIGHT_REBIND | archive_source_sha256 | f35bd177294270f48b5880bc62eef2af7cbb40f338eeb23d37212cb504920660 | . |
| 16AK_RC_PREFLIGHT_REBIND | candidate_head | fb76836852dd7e9f65a385b3ede72353b2a350c9 | . |
| 16AK_RC_PREFLIGHT_REBIND | candidate_tree | f705ed3b8594c0121ba26d69287e72c28aa0cb33 | . |
| 16AK_RC_PREFLIGHT_REBIND | rc_preflight_status | PASS | . |
| 16AL_FINAL_PRO_CROSSCUT_AUDIT | blocking_metadata_findings | 4 | . |
| 16AL_FINAL_PRO_CROSSCUT_AUDIT | pre_remediation_audit_status | REMEDIATION_REQUIRED_BEFORE_FINAL_PRO_PASS | . |
| 16AM_FINAL_PRO_METADATA_REMEDIATION | current_release_gate_table | validation/release_gates_v0.3.5.tsv | . |
| 16AM_FINAL_PRO_METADATA_REMEDIATION | g25_g30_contract_status | PASS_G25_G29_G30_WITH_SCOPE_AMENDMENT | . |
| 16AM_FINAL_PRO_METADATA_REMEDIATION | root_changelog_status | PRESENT | . |
| 16AM_FINAL_PRO_METADATA_REMEDIATION | runtime_scientific_change | false | . |
| 16AN_FINAL_PRO_CROSSCUT_AUDIT | audit_status | PASS_FINAL_PRO_CROSSCUT_AUDIT | . |
| 16AN_FINAL_PRO_CROSSCUT_AUDIT | audited_commit | 9d660e96e54c796696a28ebe686019d5636bb420 | . |
| 16AN_FINAL_PRO_CROSSCUT_AUDIT | audited_source_archive_sha256 | 93a5df2228996513d18851b8cb0c9a86b4e44547fcb5343fe14b1cb4522924b6 | . |
| 16AN_FINAL_PRO_CROSSCUT_AUDIT | audited_tree | 45833fce5a6d47b1cf706d537fb1777304f3f7b5 | . |
| 16AN_FINAL_PRO_CROSSCUT_AUDIT | blocking_findings | 0 | . |
| 16AN_FINAL_PRO_CROSSCUT_AUDIT | public_release_created | false | . |
| 16AN_FINAL_PRO_CROSSCUT_AUDIT | release_authorization | FINAL_VERSION_AND_PUBLIC_BINDING_ONLY | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | binding_asset_sha256 | 03351293b0c04d6959c21e14108d859f3980291ea4a2a47cb6dce45018e02d7f | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | citation_date_released | 2026-08-17 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | citation_version | 0.5.0 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | default_branch_release_commit | 9205049ed1fc343499416fa684dbc71f423754ef | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | freeze_root | 4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | github_license_detection | BSD-3-Clause | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | github_release_asset_count | 3 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | github_release_id | 371631603 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | github_release_immutable_flag | false | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | github_release_published_at | 2026-08-17T08:59:59Z | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | integrity_model | ANNOTATED_TAG_PLUS_EXACT_OBJECT_COMMIT_TREE_AND_SHA256_ASSETS | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | public_unauthenticated_clone_setup | PASS | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | release_binding_gate | CLOSED | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | release_status | PUBLIC_RELEASE_COMPLETE | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | release_tag | v0.5.0 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | release_tag_kind | annotated | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | release_tag_object_sha | b6387580fb99d701ec34d9fb6349b40a4e277ca9 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | release_tag_target_commit | 9205049ed1fc343499416fa684dbc71f423754ef | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | release_tree_sha | feeca99eb1f22ba350b8e6276e513116b41340e1 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | release_version | 0.5.0 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | repository_visibility | public | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | sha256sums_asset_sha256 | 66f461d7f0e04952c0c164a4fcca775121191951fe30a5117de6c800cfbaaae4 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | source_asset_sha256 | b1b3c37f358a3a6851172b4e01eb82f41e74a5281452a12b2c8c4f3bdeac87e9 | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | standard_catalog_outer_sha256 | 54a24e4b60d920c8fec16b2df37b47e40407de42b949b18dc6233e97d85f2fef | . |
| 16AR_PUBLIC_V050_RELEASE_BINDING | tag_signature | UNSIGNED_ACCEPTED | . |
| 16R_FRESH_END_TO_END | stage16r_final_exact_plain_table_parity | PASS_5_OF_5 | . |
| 16R_FRESH_END_TO_END | stage16r_post_resume_final_parity | PASS_5_OF_5 | . |
| 16R_FRESH_END_TO_END | stage16r_public_fastq_to_final_seconds | 289.0072668030043 | . |
| 16R_FRESH_END_TO_END | stage16r_public_resume | PASS_SECOND_RESUME_NOOP | . |
| 16R_FRESH_END_TO_END | stage16r_resource_scope | LOCAL_EXACT_OFFICIAL_GENCODE_CACHE_PLUS_LOCAL_EXACT_STAGE16L_BUNDLE;FULL_LARGE_NETWORK_DEFERRED_TO_RC | . |
| 16R_FRESH_END_TO_END | stage16r_source_head | 2191352170afe284c88cccd92c192efda2465b09 | . |
| 16R_FRESH_END_TO_END | stage16r_status | PASS_FRESH_MACHINE_EQUIVALENT_PUBLIC_FASTQ_TO_FINAL | . |
| 16U_SSOT_PROGRESS_CHECKPOINT | immutable_core_freeze_root | 4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb | . |
| 16U_SSOT_PROGRESS_CHECKPOINT | stage16s_cross_hardware_status | PASS_WITH_TESTED_SCOPE | . |
| 16U_SSOT_PROGRESS_CHECKPOINT | stage16t_documentation_status | PASS_OWNER_REVIEW_ACCEPTED | . |
| 16W_PUBLIC_CATALOG_DISTRIBUTION | stage16w_catalog_outer_sha256 | 54a24e4b60d920c8fec16b2df37b47e40407de42b949b18dc6233e97d85f2fef | . |
| 16W_PUBLIC_CATALOG_DISTRIBUTION | stage16w_release_tag | catalog-grch38-v0.1.0 | . |
| 16W_PUBLIC_CATALOG_DISTRIBUTION | stage16w_resource_repository | Ryo-Miyamo/RNA-TR-Scout-resources | . |
| 16W_PUBLIC_CATALOG_DISTRIBUTION | stage16w_status | PASS_PUBLIC_RELEASE_ASSET_UNAUTHENTICATED_EXACT_SHA | . |
| 16X_FULL_NETWORK_FRESH_INSTALL | stage16x_final_exact_plain_table_parity | PASS_5_OF_5 | . |
| 16X_FULL_NETWORK_FRESH_INSTALL | stage16x_network_catalog_download | PASS_PUBLIC_RELEASE_ASSET_EXACT | . |
| 16X_FULL_NETWORK_FRESH_INSTALL | stage16x_network_reference_downloads | PASS_2_OF_2_EXACT | . |
| 16X_FULL_NETWORK_FRESH_INSTALL | stage16x_public_fastq_to_final_seconds | 281 | . |
| 16X_FULL_NETWORK_FRESH_INSTALL | stage16x_public_resume | PASS_SECOND_RESUME_NOOP | . |
| 16X_FULL_NETWORK_FRESH_INSTALL | stage16x_source_commit | 24ccb15e01921f05465f8bddb59f743d1ef4cc6f | . |
| 16X_FULL_NETWORK_FRESH_INSTALL | stage16x_status | PASS_FULL_NETWORK_FRESH_INSTALL_PUBLIC_FASTQ_TO_FINAL | . |
| 16Z_RESOURCE_AWARE_PUBLIC_CLI | tier3_auto_profile | 12_SHARDS_3_UNITS_2_CALLER_WORKERS | . |
| 16Z_RESOURCE_AWARE_PUBLIC_CLI | tier3_exact_parity | PASS_5_OF_5 | . |
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

- **CRITICAL / blocking=False / BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT** — Can the final output support same-haplotype molecule-level repeat heterogeneity, repeat-to-isoform/splicing association, observability-aware inference, molecule-independence-aware support, purpose-specific triage, and fully traceable researcher dossiers without losing core read-level repeat information?
- **HIGH / blocking=False / RNA_TECHNICAL_FLOOR** — What locus-, motif-, support-, and platform-specific difference should define the technical floor for longer/shorter RNA observations?
- **HIGH / blocking=False / TRANSCRIPT_OBSERVABILITY** — Which genomic TR loci are actually reached and represented in complete RNA molecules, and how does this vary across CDS, UTR, intron, isoform, and platform?
- **MODERATE / blocking=False / DOWNLOADS_ARTIFACT_CLEANUP** — Which accumulated Downloads artifacts must be preserved, moved, retained temporarily, or deleted?
- **MODERATE / blocking=False / FULLSCALE_PEAK_DISK_BENCHMARK** — What is the measured peak disk usage of a representative approximately five-million-read release workflow?
- **MODERATE / blocking=False / G31_BIOLOGICAL_CANDIDATE_ENTRY_INTERPRETATION** — What biological and algorithmic factors explain the broad candidate-entry rate and ~4.9 loci/read, and can entry be narrowed without recall loss?
- **MODERATE / blocking=False / VIENNA_RECONCILIATION** — How much additional population coverage is gained after safe Vienna ONT boundary/motif reconciliation?

## Exports

- `current_algorithm_contract.tsv`: 35 rows
- `current_artifacts.tsv`: 4 rows
- `current_decisions.tsv`: 62 rows
- `current_interpretations.tsv`: 26 rows
- `current_known_limitations.tsv`: 20 rows
- `current_open_questions.tsv`: 7 rows
- `current_pipeline.tsv`: 1 rows
- `current_reference_hierarchy.tsv`: 8 rows
- `current_results.tsv`: 225 rows
- `current_runs.tsv`: 32 rows
- `latest_stage_status.tsv`: 242 rows
- `project_dashboard.tsv`: 12 rows
