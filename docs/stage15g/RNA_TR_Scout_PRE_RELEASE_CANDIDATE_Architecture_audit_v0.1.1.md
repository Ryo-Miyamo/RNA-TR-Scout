# RNA-TR-Scout PRE_RELEASE_CANDIDATE Architecture consistency audit v0.1.1

## Overall decision before remediation

**CONFLICT**

The exact-original Stage15F post-registration bundle confirms that Stage15C/Stage15E scientific evidence is intact, but current-state metadata and implementation lifecycle are not yet internally consistent. Stage15G is a metadata/governance remediation only; it must not change the active pipeline, schema, clean runtime evidence, or scientific packages.

## Evidence policy

This audit was reconstructed from the exact post-Stage15F SSOT CLI/SQLite database/exports, schema, release gates, Stage15C/Stage15E code and formal evidence, architecture contract, lifecycle inventory, packaging surface, and governance requirements. Conversation summaries and memory were not treated as authoritative evidence.

Stage15F output bundle SHA-256:
`ed49930d51f590df5050b7031cec5099c4ad750db893a51bec89bfcdcd41f11f`

## Blocking conflicts

### C01 — stale current limitations

The following 11 ACTIVE limitation rows must be preserved historically but removed from the current view:

- `CALLER_GENERALIZATION_INCOMPLETE`
- `CURRENT_RUNTIME_NOT_PRODUCTION_SCALE`
- `RNA_LPS_MISSING`
- `STAGE15A_250K_60MIN_MARGIN_TOO_SMALL`
- `STAGE15A_250K_SELECTIVE_RESUME_NOT_EXECUTED`
- `STAGE15A_FULL_SCALE_RUNTIME_NOT_EMPIRICALLY_VALIDATED`
- `STAGE15A_RESTART_SCOPE_IS_SELECTIVE_100K`
- `STAGE15A_INTERNAL_RUN_ID_COMPATIBILITY_ALIAS`
- `STAGE15C_ACTIVE_PIPELINE_NOT_PROMOTED`
- `STAGE15C_FULLSCALE_RESTART_RESUME_OPEN`
- `STAGE15C_RELEASE_SCALE_DETERMINISM_OPEN`

### C02 — stale current decisions

The following 9 ACTIVE decisions encode completed pauses/checkpoints or superseded next-gate language:

- `analysis_pause_for_ssot`
- `evidence_schema_v0_4_2_validated_candidate_v012`
- `final_ranking_gate`
- `performance_profiling_phase_started`
- `stage14l2_handover_checkpoint_v010`
- `stage15a_internal_run_id_compatibility_alias_v0_1_0`
- `stage15a_performance_100k_v0_2_2_1_projection_pass`
- `stage15c_active_promotion_deferred_v0_1_0`
- `stage15e_active_promotion_remains_deferred_v0_1_0`

### C03 — stale current interpretations

The following 9 ACTIVE interpretations retain obsolete Stage13A/Stage14L2/Stage15A next-gate statements:

- `native_v041_performance_validated_caller_only`
- `performance_stage13a_in_progress_checkpoint`
- `stage14l2_performance_boundary_v010`
- `stage14l2_validation_boundary_v010`
- `stage15a_250k_scaling_margin_interpretation`
- `stage15a_performance_projection_scope_v0_2_2_1`
- `stage15a_post250k_architecture_audit_interpretation`
- `stage15a_reference_correctness_scope`
- `stage15a_restart_resume_100k_scope`

### C04 — stale algorithm contracts

- `evidence_schema_v042` still says active BAM-to-final use is blocked by the already-passed isolated BAM-input gate.
- `architecture_consistency_audit_v0_1_0` still says PRE_RELEASE_CANDIDATE remains pending.

### C05 — lifecycle classification

The exact baseline SSOT contains 242 `DISCOVERED` rows and extended labels `REFERENCE_AUDIT`, `REFERENCE_SUPPORT`, and `VALIDATION_ONLY_FROZEN_EVIDENCE`. These must be normalized using exact implementation ID, path, and SHA guards; file existence must never imply ACTIVE.

## Correctly open items

- Stage15 active-path promotion and a generic portable production entry point.
- G25-G30 release portability/clean-install/cross-hardware gates.
- G32 Core Freeze Packet, G33 golden regression, and G34 canonical docs layout.
- PRE_BIOLOGY architecture audit and G20-G23 biology/interpretation outputs.
- Downloads cleanup after canonicalization.

## Remediation decision

Stage15G may supersede stale current-state records, classify implementation lifecycle, update G24 evidence in `release_gates_v0.3.2`, and close the PRE_RELEASE_CANDIDATE question **only if** all postchecks pass. The immediate Stage15G post-state must contain no unclassified implementation rows. Its immutable rebuild insertion remains forward-compatible by enforcing the exact plan-owned rows rather than forbidding scripts added by later versions from first appearing as `DISCOVERED`. It may not promote current_pipeline, change schema v0.4.2, rerun scientific stages, rehash the 140 GB checkpoint, rebuild the 52 GB package, or delete/move Downloads artifacts.
