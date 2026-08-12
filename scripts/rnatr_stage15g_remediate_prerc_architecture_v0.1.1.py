#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import traceback
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

VERSION = 'rnatr_stage15g_prerc_architecture_remediation_v0.1.1'
CONFIRM_TOKEN = 'REMEDIATE_PRERC_ARCHITECTURE_V011'
EFFECTIVE_AT = '2026-08-11T00:30:00+00:00'
FULL_RUN = 'ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1'
REMEDIATION_RUN = 'ENCSR307SHM_stage15g_prerc_architecture_remediation_v0_1_1'
EXPECTED_BASELINE_CLI_SHA256 = '93d9d22592fcd0aacfd6d31ad0466dfe94da6d288fbe804ba9bc8b13dd8b9943'
EXPECTED_BASELINE_DB_SHA256 = '20c5b5e7c834d2589ff31d249490abfb4ddc99d2df700de63579adbcfc0a6ef4'
EXPECTED_CURRENT_PIPELINE_SHA256 = '75965e89a6444852cb03c9d8ad0856dd04d136e07ad83316283c5615f82cafb3'
EXPECTED_CORE_SCHEMA_SHA256 = 'c0509a0669344dba0b07cd1bb9e71f2aeb01e0196df47ec9178f1d2464b515f1'
EXPECTED_GATES_V031_SHA256 = '7d6795222e05d7892118bf0b4dde392b2e33b820934be987d632290f0722fda8'
EXPECTED_STAGE15F_OUTPUT_BUNDLE_SHA256 = 'ed49930d51f590df5050b7031cec5099c4ad750db893a51bec89bfcdcd41f11f'
EXPECTED_STAGE15C_RUNNER_SHA256 = 'cca6b2d4c6e773392d3a8c24cd2fd2a1f0a41a713338b4ccdec1ba7fab5bafcc'
EXPECTED_RUNTIME_BINDING_AMENDMENT_SHA256 = 'c972777c13834ca9c16bc7d4aaecbebb20d46d3518d266a851f17a7b4751d97a'
EXPECTED_STAGE15E_QC_SHA256 = '13a827f1f00aa433476913a37bfa28b73d8415e607390f8f867c942100c9d544'
RELEASE_GATES_V032_TEXT = 'gate_id\tgate\tlevel\tblocking_for_v1\tstatus\tevidence_or_next_action\nG01\tGeneral caller deterministic across hash seeds\talgorithm\ttrue\tPASS\tStage14F2/14G, deterministic 250k/500k, and Stage15E shard_065 hash-seed logical parity\nG02\tSynthetic truth and semantic invariants\talgorithm\ttrue\tPASS\tStage14G\nG03\tPython/native 100k exact parity\timplementation\ttrue\tPASS\tStage14G all 388571 rows\nG04\tNative caller-only projected 5.31M runtime <=30 min\tperformance\tfalse\tPASS\tStage14G projected 18.90 min; BAM-to-final 30-min target remains separate and open\nG05\tPrepared-job/native-caller to validated final-evidence package\tproduction\ttrue\tPASS\tStage14K2/14L2\nG06\t5M-read BAM-input runtime <=60 min with first-freeze documented tolerance <=62 min\tperformance\ttrue\tPASS_WITH_DOCUMENTED_TOLERANCE\tEmpirical 5,312,696-read BAM-to-final v0.1.6 = 60.041256352 min; strict <=60 was exceeded by 2.475 s; mapping excluded, partition/validators/publication included\nG07\t5M-read restartability/memory/artifact audit\tproduction\ttrue\tPASS_WITH_SCOPE_AMENDMENT\tStage15E rehashed all 1,884 checkpoint artifacts/140,029,015,504 bytes before stop and resume, rejected a copied-manifest SHA corruption fixture, freshly reran caller and materializer for shard_065 under PYTHONHASHSEED=20260810, reconstructed 144 shards using 1 fresh plus 143 frozen shards with exact package parity, published atomically, and passed a zero-scientific-command second-resume no-op; scope is checkpoint-based caller-to-final, not an upstream BAM partition/11b/11d3/11e full rerun\nG08\tReal truth-bearing biological validation\tbiology\ttrue\tOPEN\tDisease/synthetic-RNA/orthogonal truth data\nG09\tLarge-cohort RNA technical/background distribution\tpopulation\tfalse\tOPEN\tDefer until production core is frozen\nG10\tFASTQ-to-final mapping-inclusive performance\tconvenience\tfalse\tOPEN\tReport minimap2 separately; current full mapping = 75.433333 min\nG11\tMismatch/indel/interruption/purity/LPS preserved separately\tschema_contract\ttrue\tPASS\tSchema v0.4.2 retains separate fields and explicit missingness\nG12\tBiological-vs-technical origin classifier truth validation\tschema_contract\tfalse\tOPEN\tCurrent package uses NOT_ASSESSED\nG13\tRead-level RNA repeat-length distribution retained\tschema_contract\ttrue\tPASS\trepeat_events remains source of truth\nG14\tRNA repeat-length clustering algorithm validated\tschema_contract\tfalse\tOPEN\tImplement after core freeze and sufficient same-locus support\nG15\tAllele/haplotype labels prohibited without phase evidence\tschema_contract\ttrue\tPASS\tValidator/contract rejects unsupported labels\nG16\tCensored/context-limited reads not naively mixed as exact observations\tschema_contract\ttrue\tPASS\tExact-only or explicit censor-aware handling required\nG17\tMapping-complete BAM to validated schema v0.4.2 package\tproduction\ttrue\tPASS\t100k/250k/500k, full 5.31M empirical package, and Stage15E exact full-package reconstruction PASS\nG18\tCalled non-locus-anchored attempts retained but not eventized\tmaterialization\ttrue\tPASS\tLossless materialization contract\nG19\tfailure_code/qc_flags/materialization_status semantics are distinct\tschema_contract\ttrue\tPASS\tStage14L2 contract\nG20\tRead-keyed biology joinability for transcript, haplotype, observability, and molecule independence\tbiology_output\ttrue\tOPEN\tFreeze and validate sidecar schemas after core technical completion\nG21\tMolecule-level distribution retained through sample-by-locus summarization\tinterpretation_output\ttrue\tOPEN\tImplement molecule_repeat_state and censor-aware sample_locus_summary\nG22\tPurpose-specific ranking lanes with unconditional known-disease retention\tinterpretation_output\ttrue\tOPEN\tImplement biology/triage lanes after core freeze\nG23\tResearcher-facing candidate dossier fully traceable to core and sidecars\tinterpretation_output\ttrue\tOPEN\tImplement dossier and reverse-traceability validator\nG24\tMajor-checkpoint Architecture consistency audit and closure\tarchitecture_contract\ttrue\tOPEN\tPOST_250K and PRE_RELEASE_CANDIDATE audits are completed. PRE-RC v0.1.1 identified and Stage15G remediates stale SSOT current-state metadata plus lifecycle classification without changing the active pipeline, frozen schema, or scientific outputs. PRE_BIOLOGY remains mandatory and must reconstruct state from exact original code, SSOT, schema, contracts, validators, runners, and formal artifacts.\nG25\tAutomatic version-pinned reference bootstrap with resumable download and checksum verification\trelease_readiness\ttrue\tOPEN_PLANNED\tImplement reference manifest/downloader/cache; large references excluded from GitHub\nG26\tCPU/RAM/output/tmp resource detection before execution\trelease_readiness\ttrue\tOPEN_PLANNED\tExpose resource report and override provenance\nG27\tMemory-aware automatic shard/concurrency selection with manual overrides\trelease_readiness\ttrue\tOPEN_PLANNED\tUse empirical resource model; support --threads --memory-gb --tmp-dir\nG28\tScientific logical output reproducibility across supported hardware/concurrency profiles\trelease_readiness\ttrue\tOPEN_PLANNED\tStage15E is same-machine checkpoint-based evidence and does not close cross-profile or cross-machine reproducibility\nG29\tClean-machine clone-to-setup-to-test reproducibility\trelease_readiness\ttrue\tOPEN_PLANNED\tValidate independent clean environment without hidden developer paths\nG30\tEmpirical minimum/recommended/tested hardware profiles in README\trelease_readiness\ttrue\tOPEN_PLANNED\tDerive from release-scale measurements\nG31-T\tTechnical multiplicity integrity and absence of scale-dependent row runaway\ttechnical_audit\ttrue\tPASS_WITH_SCOPE_AMENDMENT\t11b-through-materialization row conservation, primary ID uniqueness, 0.0311% read-locus excess, stable 100k/500k/full multiplicity, and low target concentration; original v0.1.0 machine FAIL preserved\nG31-B\tBiological interpretation of 79.29% candidate entry and ~4.9 loci/read\tbiology_interpretation\tfalse\tOPEN_DEFERRED_TO_BIOLOGY_LAYER\tInterpret catalog overlap, +/-500bp padding, transcript concentration, motif equivalence, and recall-preserving candidate narrowing after technical core freeze\nG32\tAuthoritative Core Freeze Packet preserving the frozen Core contract\tcore_freeze_governance\ttrue\tOPEN_PLANNED\tAfter PRE-RC audit and active-path decision, create a versioned, checksummed Core Freeze Packet from reread originals covering active production path, frozen schema/API/join keys, scientific semantics, performance/restart/validator contracts, known limitations, and biology-layer interface.\nG33\tGolden regression suite for frozen scientific-output semantics\tregression_contract\ttrue\tOPEN_PLANNED\tFreeze representative test inputs, expected outputs, exact/logical parity rules, validators, versions, manifests, and SHA-256 bindings so biology additions and performance optimization cannot silently change the Core scientific contract.\nG34\tProject-wide canonical documentation and artifact-retention structure\tarchitecture_governance\ttrue\tOPEN_PLANNED\tPromote project-wide architecture/governance/contracts/freeze/regression documents to one unambiguous canonical layout; retain stage-local copies as history or pointers; classify Downloads artifacts before any move or deletion.\n'
STALE_LIMITATIONS = ['CALLER_GENERALIZATION_INCOMPLETE', 'CURRENT_RUNTIME_NOT_PRODUCTION_SCALE', 'RNA_LPS_MISSING', 'STAGE15A_250K_60MIN_MARGIN_TOO_SMALL', 'STAGE15A_250K_SELECTIVE_RESUME_NOT_EXECUTED', 'STAGE15A_FULL_SCALE_RUNTIME_NOT_EMPIRICALLY_VALIDATED', 'STAGE15A_RESTART_SCOPE_IS_SELECTIVE_100K', 'STAGE15A_INTERNAL_RUN_ID_COMPATIBILITY_ALIAS', 'STAGE15C_ACTIVE_PIPELINE_NOT_PROMOTED', 'STAGE15C_FULLSCALE_RESTART_RESUME_OPEN', 'STAGE15C_RELEASE_SCALE_DETERMINISM_OPEN']
STALE_DECISIONS = ['analysis_pause_for_ssot', 'evidence_schema_v0_4_2_validated_candidate_v012', 'final_ranking_gate', 'performance_profiling_phase_started', 'stage14l2_handover_checkpoint_v010', 'stage15a_internal_run_id_compatibility_alias_v0_1_0', 'stage15a_performance_100k_v0_2_2_1_projection_pass', 'stage15c_active_promotion_deferred_v0_1_0', 'stage15e_active_promotion_remains_deferred_v0_1_0']
STALE_INTERPRETATIONS = ['native_v041_performance_validated_caller_only', 'performance_stage13a_in_progress_checkpoint', 'stage14l2_performance_boundary_v010', 'stage14l2_validation_boundary_v010', 'stage15a_250k_scaling_margin_interpretation', 'stage15a_performance_projection_scope_v0_2_2_1', 'stage15a_post250k_architecture_audit_interpretation', 'stage15a_reference_correctness_scope', 'stage15a_restart_resume_100k_scope']
STALE_CONTRACTS = ['architecture_consistency_audit_v0_1_0', 'evidence_schema_v042']
REPLACEMENT_DECISIONS = [{'decision_key': 'evidence_schema_v0_4_2_fullscale_validated_candidate_v0_1_0', 'category': 'schema_design', 'title': 'Schema v0.4.2 and materializer v0.1.2 validated through the full-scale Stage15 candidate', 'statement': 'Adopt schema v0.4.2 and materializer v0.1.2 as the frozen Core evidence contract for the validated Stage15 candidate. Evidence spans isolated 100k correctness, deterministic 250k/500k scaling, empirical 5,312,696-read execution, and Stage15E scoped reconstruction/restart. This decision does not itself promote current_pipeline or close G25-G34.', 'confidence': 'HIGH', 'rationale': 'The prior ACTIVE decision was limited to prepared-job-to-package validation and incorrectly retained the already-passed isolated BAM-input gate as the blocker.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv', 'supersedes_key': 'evidence_schema_v0_4_2_validated_candidate_v012'}, {'decision_key': 'final_ranking_gate', 'category': 'project_state', 'title': 'Final ranking remains deferred to the biology and interpretation layer', 'statement': 'Final candidate ranking remains intentionally unexecuted until versioned biology sidecars, observability and molecule-independence state, truth-bearing validation, sample-by-locus summaries, and purpose-specific ranking lanes are implemented. RNA LPS and the Core caller technical gates are no longer the blocking reason.', 'confidence': 'HIGH', 'rationale': 'The Core now measures dual LPS and has passed caller/materializer/full-scale technical gates, while G08 and G20-G23 remain open.', 'evidence_path': '/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.2.tsv', 'supersedes_key': 'final_ranking_gate'}, {'decision_key': 'stage15_active_path_promotion_state_v0_1_0', 'category': 'architecture_governance', 'title': 'Keep Stage15 candidate provisional after PRE-RC remediation and design a generic production entry point', 'statement': 'PRE_RELEASE_CANDIDATE current-state consistency is remediated, but the Stage15 candidate remains PROVISIONAL. Before promotion, construct and audit a generic portable production entry point with exact component bindings, rollback, and golden-regression guards; do not expose the dataset- and machine-bound benchmark runner unchanged as the public production CLI. G25-G30 and G32-G34 remain open.', 'confidence': 'HIGH', 'rationale': 'Full-scale correctness, documented-tolerance performance, and scoped determinism/restart are accepted; release packaging, portability, explicit promotion, freeze preservation, and clean-install gates are separate.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md', 'supersedes_key': 'stage15e_active_promotion_remains_deferred_v0_1_0'}, {'decision_key': 'stage15c_runtime_path_binding_resolution_v0_1_0', 'category': 'provenance', 'title': 'Treat the Stage15A 250k internal run-ID alias as historical only', 'statement': 'The Stage15A 250k compatibility alias remains historical provenance and is not a release contract. Stage15C v0.1.6 uses runtime-bound 11b/11d3/11e sources, audits all generated shard scripts, rejects obsolete template run IDs and mapping-run IDs in analysis scripts, and binds the full analysis run identity explicitly.', 'confidence': 'HIGH', 'rationale': 'Exact Stage15C v0.1.6 source and runtime-path binding amendment close the PRE-RC provenance concern for the validated candidate without rewriting the historical 250k artifact.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/stage15c/runtime_path_binding_amendment_v0.1.6/rnatr_stage15c_runtime_path_binding_amendment_v0.1.6.json', 'supersedes_key': 'stage15a_internal_run_id_compatibility_alias_v0_1_0'}, {'decision_key': 'prerc_architecture_audit_remediation_v0_1_0', 'category': 'architecture_governance', 'title': 'Accept PRE-RC architecture current-state remediation without scientific or active-path mutation', 'statement': 'Accept the Stage15G PRE_RELEASE_CANDIDATE remediation after exact-original audit: stale current SSOT records are superseded, lifecycle rows are classified with the frozen vocabulary, G24 advances to PRE_BIOLOGY remaining open, and PRE_RELEASE_CANDIDATE audit closes. The active pipeline, schema v0.4.2, Stage15C clean benchmark, and scientific packages remain unchanged.', 'confidence': 'HIGH', 'rationale': 'The blocking conflicts were current-state metadata and lifecycle inconsistencies, not scientific-output failures.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md', 'supersedes_key': None}]
REPLACEMENT_INTERPRETATIONS = [{'interpretation_key': 'native_v041_performance_validated_caller_only', 'fact_statement': 'Native deterministic v0.4.1 retains an approximately 18.9-minute linear 5.31M caller-only projection, while the exact empirical Stage15C BAM-to-final runtime is 60.041256352 minutes with mapping excluded and validators/publication included.', 'interpretation': 'The measurement engine meets the caller-only 30-minute target without GPU. The complete BAM-to-final candidate passes the predeclared first-freeze tolerance but does not meet the 30-minute whole-pipeline target; caller-only and whole-pipeline performance must remain separate.', 'do_not_interpret_as': 'Do not report 18.9 minutes as complete-pipeline runtime or 60.041256352 minutes as strict <=60-minute PASS.', 'confidence': 'HIGH', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv', 'evidence_metrics': {'caller_only_projected_minutes': 18.901733196639434, 'bam_to_final_empirical_minutes': 60.041256352, 'runtime_status': 'PASS_WITH_DOCUMENTED_TOLERANCE'}, 'supersedes_key': 'native_v041_performance_validated_caller_only'}, {'interpretation_key': 'stage15a_reference_correctness_scope', 'fact_statement': 'Stage15A v0.1.3 remains the isolated 100k correctness/regression reference; Stage15C v0.1.6 supplies empirical full-scale evidence and Stage15E supplies scoped checkpoint-based determinism/restart evidence.', 'interpretation': 'Use the 100k reference for focused correctness regression and the Stage15C/Stage15E artifacts for registered release-scale performance/restart evidence. None of these alone constitutes active-path promotion or the final golden regression suite.', 'do_not_interpret_as': 'Do not treat the historical v0.1.3 performance result as the current full-scale result, and do not treat Stage15E as an upstream full rerun or cross-machine proof.', 'confidence': 'HIGH', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md', 'evidence_metrics': {'stage15a_100k_reference': 'PASS', 'stage15c_fullscale': 'PASS_WITH_DOCUMENTED_TOLERANCE', 'stage15e_scope': 'CHECKPOINT_BASED'}, 'supersedes_key': 'stage15a_reference_correctness_scope'}, {'interpretation_key': 'prerc_architecture_audit_scope_v0_1_0', 'fact_statement': 'The exact-original PRE-RC audit found stale current-state SSOT rows and unclassified lifecycle records; Stage15G remediation changes metadata/governance state only and verifies byte-identical current_pipeline and frozen schema.', 'interpretation': 'PRE-RC consistency can pass after remediation without rerunning or modifying scientific outputs. Active-path promotion, clean-install release readiness, Core Freeze Packet, golden regression, docs canonicalization, and PRE_BIOLOGY audit remain separate open gates.', 'do_not_interpret_as': 'Do not interpret PRE-RC metadata remediation as active promotion, Core Freeze, biological validation, clean-install readiness, or cross-hardware determinism.', 'confidence': 'HIGH', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md', 'evidence_metrics': {'scientific_rerun': False, 'active_pipeline_modified': False, 'core_schema_modified': False}, 'supersedes_key': None}]
REPLACEMENT_CONTRACTS = [{'component_key': 'evidence_schema_v042', 'component_name': 'Evidence schema v0.4.2', 'implementation_state': 'FULLSCALE_VALIDATED_FROZEN_CORE_CANDIDATE_NOT_ACTIVE_PIPELINE', 'contract_statement': 'Schema v0.4.2 plus materializer v0.1.2 is the frozen Core evidence contract for the validated Stage15 candidate. It passed isolated 100k correctness, deterministic 250k/500k scaling, empirical 5,312,696-read execution, frozen validators, and Stage15E scoped package reconstruction/restart. This contract does not itself promote current_pipeline, provide biology sidecars, or close G25-G34.', 'active_implementation_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv', 'supersedes_component_key': 'evidence_schema_v042'}, {'component_key': 'architecture_consistency_audit_v0_1_0', 'component_name': 'Architecture consistency audit contract v0.1.0', 'implementation_state': 'POST250K_AND_PRERC_PASS_PREBIOLOGY_OPEN', 'contract_statement': 'Major-checkpoint audits cross-check exact-original SSOT, active paths, schema/contracts, performance, validation/restart scope, biology roadmap, release gates, and lifecycle. POST_250K and PRE_RELEASE_CANDIDATE are complete; PRE_BIOLOGY remains mandatory, and focused audits are required around active-path promotion or other major architecture changes. Conversation summaries and memory are not authoritative evidence.', 'active_implementation_id': 'impl_stage15g_prerc_architecture_remediation_v0_1_1', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md', 'supersedes_component_key': 'architecture_consistency_audit_v0_1_0'}]
NEW_LIMITATIONS = [{'limitation_key': 'STAGE15_ACTIVE_PATH_AND_PORTABLE_ENTRYPOINT_NOT_PROMOTED', 'statement': 'The empirically validated Stage15 candidate remains PROVISIONAL; current_pipeline still points to the legacy P0/P1 path, and the validated full-scale runner is dataset- and machine-bound rather than a generic public production entry point.', 'severity': 'HIGH', 'mitigation': 'Design and audit a generic portable production entry point with exact component/resource bindings, versioned active-path promotion, rollback, and golden-regression guards. Keep G25-G30 and G32-G34 open until separately satisfied.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md'}]
QUESTION_UPDATES = [{'question_key': 'PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT', 'status': 'CLOSED', 'blocking': 0, 'next_action': 'Closed by exact-original PRE-RC audit v0.1.1 plus Stage15G remediation. Reopen only on evidence drift or a later major architecture change.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md'}, {'question_key': 'ARCHITECTURE_CONSISTENCY_AUDIT_CLOSURE', 'status': 'OPEN', 'blocking': 1, 'next_action': 'POST_250K and PRE_RELEASE_CANDIDATE checkpoints are complete. Perform the exact-original PRE_BIOLOGY audit before biology-layer implementation; add focused audits around active-path promotion or major contract changes.', 'evidence_path': '/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.2.tsv'}, {'question_key': 'ACTIVE_PATH_PROMOTION', 'status': 'OPEN', 'blocking': 1, 'next_action': 'Design a generic portable production entry point from the exact validated components, define promotion/rollback and golden-regression guards, and run a separate versioned promotion preflight. Do not promote the dataset-bound Stage15C benchmark runner unchanged.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md'}, {'question_key': 'BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT', 'status': 'OPEN', 'blocking': 1, 'next_action': 'After active-path promotion and Core Freeze preservation artifacts are complete, run PRE_BIOLOGY Architecture audit, then freeze sidecar schemas/validators and implement G20-G23 without rewriting the core 5-table source of truth.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md'}, {'question_key': 'CORE_FREEZE_PACKET', 'status': 'OPEN', 'blocking': 1, 'next_action': 'After the active-path decision, reconstruct the G32 packet from exact originals and bind it to the accepted golden regression, canonical docs layout, versions, and checksums.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md'}]
AUDIT_MD = '# RNA-TR-Scout PRE_RELEASE_CANDIDATE Architecture consistency audit v0.1.1\n\n## Overall decision before remediation\n\n**CONFLICT**\n\nThe exact-original Stage15F post-registration bundle confirms that Stage15C/Stage15E scientific evidence is intact, but current-state metadata and implementation lifecycle are not yet internally consistent. Stage15G is a metadata/governance remediation only; it must not change the active pipeline, schema, clean runtime evidence, or scientific packages.\n\n## Evidence policy\n\nThis audit was reconstructed from the exact post-Stage15F SSOT CLI/SQLite database/exports, schema, release gates, Stage15C/Stage15E code and formal evidence, architecture contract, lifecycle inventory, packaging surface, and governance requirements. Conversation summaries and memory were not treated as authoritative evidence.\n\nStage15F output bundle SHA-256:\n`ed49930d51f590df5050b7031cec5099c4ad750db893a51bec89bfcdcd41f11f`\n\n## Blocking conflicts\n\n### C01 — stale current limitations\n\nThe following 11 ACTIVE limitation rows must be preserved historically but removed from the current view:\n\n- `CALLER_GENERALIZATION_INCOMPLETE`\n- `CURRENT_RUNTIME_NOT_PRODUCTION_SCALE`\n- `RNA_LPS_MISSING`\n- `STAGE15A_250K_60MIN_MARGIN_TOO_SMALL`\n- `STAGE15A_250K_SELECTIVE_RESUME_NOT_EXECUTED`\n- `STAGE15A_FULL_SCALE_RUNTIME_NOT_EMPIRICALLY_VALIDATED`\n- `STAGE15A_RESTART_SCOPE_IS_SELECTIVE_100K`\n- `STAGE15A_INTERNAL_RUN_ID_COMPATIBILITY_ALIAS`\n- `STAGE15C_ACTIVE_PIPELINE_NOT_PROMOTED`\n- `STAGE15C_FULLSCALE_RESTART_RESUME_OPEN`\n- `STAGE15C_RELEASE_SCALE_DETERMINISM_OPEN`\n\n### C02 — stale current decisions\n\nThe following 9 ACTIVE decisions encode completed pauses/checkpoints or superseded next-gate language:\n\n- `analysis_pause_for_ssot`\n- `evidence_schema_v0_4_2_validated_candidate_v012`\n- `final_ranking_gate`\n- `performance_profiling_phase_started`\n- `stage14l2_handover_checkpoint_v010`\n- `stage15a_internal_run_id_compatibility_alias_v0_1_0`\n- `stage15a_performance_100k_v0_2_2_1_projection_pass`\n- `stage15c_active_promotion_deferred_v0_1_0`\n- `stage15e_active_promotion_remains_deferred_v0_1_0`\n\n### C03 — stale current interpretations\n\nThe following 9 ACTIVE interpretations retain obsolete Stage13A/Stage14L2/Stage15A next-gate statements:\n\n- `native_v041_performance_validated_caller_only`\n- `performance_stage13a_in_progress_checkpoint`\n- `stage14l2_performance_boundary_v010`\n- `stage14l2_validation_boundary_v010`\n- `stage15a_250k_scaling_margin_interpretation`\n- `stage15a_performance_projection_scope_v0_2_2_1`\n- `stage15a_post250k_architecture_audit_interpretation`\n- `stage15a_reference_correctness_scope`\n- `stage15a_restart_resume_100k_scope`\n\n### C04 — stale algorithm contracts\n\n- `evidence_schema_v042` still says active BAM-to-final use is blocked by the already-passed isolated BAM-input gate.\n- `architecture_consistency_audit_v0_1_0` still says PRE_RELEASE_CANDIDATE remains pending.\n\n### C05 — lifecycle classification\n\nThe exact baseline SSOT contains 242 `DISCOVERED` rows and extended labels `REFERENCE_AUDIT`, `REFERENCE_SUPPORT`, and `VALIDATION_ONLY_FROZEN_EVIDENCE`. These must be normalized using exact implementation ID, path, and SHA guards; file existence must never imply ACTIVE.\n\n## Correctly open items\n\n- Stage15 active-path promotion and a generic portable production entry point.\n- G25-G30 release portability/clean-install/cross-hardware gates.\n- G32 Core Freeze Packet, G33 golden regression, and G34 canonical docs layout.\n- PRE_BIOLOGY architecture audit and G20-G23 biology/interpretation outputs.\n- Downloads cleanup after canonicalization.\n\n## Remediation decision\n\nStage15G may supersede stale current-state records, classify implementation lifecycle, update G24 evidence in `release_gates_v0.3.2`, and close the PRE_RELEASE_CANDIDATE question **only if** all postchecks pass. The immediate Stage15G post-state must contain no unclassified implementation rows. Its immutable rebuild insertion remains forward-compatible by enforcing the exact plan-owned rows rather than forbidding scripts added by later versions from first appearing as `DISCOVERED`. It may not promote current_pipeline, change schema v0.4.2, rerun scientific stages, rehash the 140 GB checkpoint, rebuild the 52 GB package, or delete/move Downloads artifacts.\n'
GOVERNANCE_MD = '# RNA-TR-Scout Stage15G PRE-RC architecture remediation contract v0.1.0\n\nStage15G is limited to current-state metadata and governance consistency.\n\nRequired invariants:\n\n- exact post-Stage15F SSOT/source/schema/release-gate baseline;\n- exact Stage15C v0.1.6 and Stage15E evidence guards;\n- historical rows are superseded, not silently deleted or rewritten;\n- implementation lifecycle changes use exact implementation ID, path, and SHA bindings;\n- the Stage15G execute-time postcheck requires the exact immediate post-remediation lifecycle counts and zero unclassified rows;\n- the immutable SSOT rebuild insertion verifies only plan-owned Stage15G lifecycle rows, so scripts introduced by later versions may be newly DISCOVERED without retroactively invalidating this historical remediation;\n- current_pipeline and schema v0.4.2 remain byte-identical;\n- no scientific rerun, checkpoint rehash, package reconstruction, active-path promotion, Core Freeze, or Downloads cleanup;\n- G24 remains OPEN for PRE_BIOLOGY even after PRE_RELEASE_CANDIDATE closes;\n- G25-G30 and G32-G34 remain OPEN.\n\nA successful SSOT rebuild and updater postcheck are both required. Any mismatch triggers rollback.\n'
AUDIT_TSV = 'finding_id\tseverity\tdomain\tstatus\tfinding\trequired_action\nC01\tBLOCKING_CONFLICT\tSSOT current limitations\tCONFLICT\t11 ACTIVE limitations are stale or superseded by exact Stage15C/Stage15E evidence, including caller/LPS, projected/full-scale runtime, restart/determinism, compatibility-alias, and pre-PRE-RC promotion wording.\tSupersede historical rows without deleting them and retain only current scoped limitations.\nC02\tBLOCKING_CONFLICT\tSSOT current decisions\tCONFLICT\t9 ACTIVE decisions encode completed pauses/checkpoints or superseded next-gate language.\tSupersede exact decision IDs; add current schema, ranking, provenance, promotion, and PRE-RC remediation decisions.\nC03\tBLOCKING_CONFLICT\tSSOT current interpretations\tCONFLICT\t9 ACTIVE interpretations still describe Stage13A/Stage14L2/Stage15A next gates as pending.\tSupersede exact interpretation IDs; add current caller/full-pipeline performance and regression-scope interpretations.\nC04\tBLOCKING_CONFLICT\tSSOT algorithm contracts\tCONFLICT\tThe ACTIVE evidence_schema_v042 and architecture-consistency contracts predate passed full-scale/PRE-RC evidence.\tSupersede and replace both contracts while keeping PRE_BIOLOGY open.\nC05\tRELEASE_BLOCKING_REVIEW\tImplementation lifecycle\tREVIEW\t242 DISCOVERED rows plus five rows carrying three extended lifecycle labels violate the frozen lifecycle vocabulary; 32 DISCOVERED rows duplicate explicitly classified paths.\tApply exact-ID/path/SHA classification: duplicate discovery rows to SUPERSEDED, discovery-only to REFERENCE, and normalize extended labels.\nR01\tEXPECTED_OPEN_GATE\tActive production path\tOPEN\tcurrent_pipeline remains the 11-stage legacy path while the validated Stage15C candidate is PROVISIONAL.\tDo not promote in Stage15G; design a generic production entry point and separate promotion gate.\nR02\tEXPECTED_OPEN_GATE\tRelease portability\tOPEN\tG25-G30 remain open; packaging and benchmark runners include developer-local assumptions.\tKeep clean-install and portability work separate and explicit.\nO01\tPLANNED_BLOCKING\tCore Freeze governance\tOPEN\tG32-G34 remain required and incomplete.\tBuild Core Freeze Packet, golden regression, and canonical docs from exact originals before Core Freeze.\nO02\tNONBLOCKING_PLANNED\tDownloads cleanup\tOPEN\tDownloads cleanup remains deferred until canonical destinations/checksums are established.\tDo not move or delete current evidence during Stage15G.\n'


PATCH_MARKER = "# Stage 15G PRE_RELEASE_CANDIDATE architecture remediation v0.1.1"
PATCH_ANCHOR = "\n\n    current_metrics = ["
ALLOWED_LIFECYCLE = {
    "ACTIVE", "PROVISIONAL", "REFERENCE", "SUPPORT",
    "SUPERSEDED", "OBSOLETE_FAILED_HISTORICAL",
}

FAILED_V010_RESIDUE_RELATIVE_PATHS = (
    "scripts/rnatr_stage15g_remediate_prerc_architecture_v0.1.0.py",
    "metadata/stage15g/prerc_architecture_remediation_v0.1.0",
    "qc/15_stage15g_prerc_architecture_remediation/" + FULL_RUN + "/v0.1.0",
)

class UpdateError(RuntimeError):
    pass

@dataclass(frozen=True)
class Paths:
    project_root: Path
    downloads: Path

    @property
    def ssot_root(self) -> Path: return self.project_root / "metadata/ssot"
    @property
    def ssot_cli(self) -> Path: return self.ssot_root / "rnatr_ssot.py"
    @property
    def ssot_db(self) -> Path: return self.ssot_root / "rnatr_ssot.sqlite"
    @property
    def ssot_summary(self) -> Path: return self.ssot_root / "CURRENT_STATE.md"
    @property
    def ssot_exports(self) -> Path: return self.ssot_root / "exports"
    @property
    def ssot_backups(self) -> Path: return self.ssot_root / "backups"
    @property
    def lock_path(self) -> Path: return self.ssot_root / ".stage15g_prerc_architecture_remediation.lock"
    @property
    def core_schema(self) -> Path: return self.project_root / "config/evidence_schema/v0.4.2/schema/rnatr_v04_table_schema.json"
    @property
    def gates_v031(self) -> Path: return self.project_root / "validation/release_gates_v0.3.1.tsv"
    @property
    def gates_v032(self) -> Path: return self.project_root / "validation/release_gates_v0.3.2.tsv"
    @property
    def stage15f_output_bundle(self) -> Path: return self.downloads / "rnatr_stage15f_stage15e_registration_prerc_input_v0.1.1_output.tar.gz"
    @property
    def stage15f_output_sidecar(self) -> Path: return Path(str(self.stage15f_output_bundle) + ".sha256")
    @property
    def stage15c_runner(self) -> Path: return self.project_root / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py"
    @property
    def runtime_binding_amendment(self) -> Path: return self.project_root / "metadata/stage15c/runtime_path_binding_amendment_v0.1.6/rnatr_stage15c_runtime_path_binding_amendment_v0.1.6.json"
    @property
    def stage15e_qc(self) -> Path: return self.project_root / "qc/15_stage15e_determinism_restart" / FULL_RUN / "v0.1.0/stage15e_combined_determinism_restart.qc.tsv"
    @property
    def updater_install(self) -> Path: return self.project_root / "scripts/rnatr_stage15g_remediate_prerc_architecture_v0.1.1.py"
    @property
    def audit_doc_install(self) -> Path: return self.project_root / "docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md"
    @property
    def governance_doc_install(self) -> Path: return self.project_root / "docs/stage15g/RNA_TR_Scout_Stage15G_PRE_RC_architecture_remediation_contract_v0.1.0.md"
    @property
    def findings_install(self) -> Path: return self.project_root / "docs/stage15g/rnatr_prerc_architecture_audit_v0.1.1.tsv"
    @property
    def lifecycle_plan_install(self) -> Path: return self.project_root / "metadata/stage15g/prerc_architecture_remediation_v0.1.1/lifecycle_plan.tsv"
    @property
    def state_plan_install(self) -> Path: return self.project_root / "metadata/stage15g/prerc_architecture_remediation_v0.1.1/state_remediation_plan.tsv"
    @property
    def contract_install(self) -> Path: return self.project_root / "metadata/stage15g/prerc_architecture_remediation_v0.1.1/remediation_contract.json"
    @property
    def update_qc_root(self) -> Path: return self.project_root / "qc/15_stage15g_prerc_architecture_remediation" / FULL_RUN / "v0.1.1"
    @property
    def update_meta_root(self) -> Path: return self.project_root / "metadata/stage15g/prerc_architecture_remediation_v0.1.1"
    @property
    def preflight_qc(self) -> Path: return self.downloads / "rnatr_stage15g_prerc_architecture_remediation_preflight_v0.1.1.qc.tsv"
    @property
    def preflight_bundle(self) -> Path: return self.downloads / "rnatr_stage15g_prerc_architecture_remediation_preflight_v0.1.1.tar.gz"
    @property
    def success_bundle(self) -> Path: return self.downloads / "rnatr_stage15g_prerc_architecture_remediation_v0.1.1_output.tar.gz"
    @property
    def failure_bundle(self) -> Path: return self.downloads / "rnatr_stage15g_prerc_architecture_remediation_v0.1.1_failure.tar.gz"


def default_paths() -> Paths:
    return Paths(Path("/mnt/intelssd/rnatr_project"), Path.home() / "Downloads")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise UpdateError(f"missing or empty required file: {path}")


def require_sha(path: Path, expected: str) -> None:
    require_file(path)
    observed = sha256_file(path)
    if observed != expected:
        raise UpdateError(f"SHA-256 mismatch: {path}: {observed} != {expected}")


def atomic_write(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name("." + path.name + f".part.{os.getpid()}")
    if temp.exists(): temp.unlink()
    with temp.open("xb") as handle:
        handle.write(payload)
        handle.flush(); os.fsync(handle.fileno())
    temp.chmod(mode); os.replace(temp, path)


def write_metrics(path: Path, rows: Iterable[tuple[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key, value in rows: writer.writerow([key, value])


def read_metrics(path: Path) -> dict[str, str]:
    require_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        if next(reader, None) != ["metric", "value"]:
            raise UpdateError(f"invalid metric TSV header: {path}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


def write_rows(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def make_bundle(root: Path, output: Path) -> str:
    manifest = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name == "artifact_manifest.tsv": continue
        manifest.append({"relative_path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    write_rows(root / "artifact_manifest.tsv", manifest, ["relative_path", "bytes", "sha256"])
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_name("." + output.name + ".part")
    if part.exists(): part.unlink()
    with tarfile.open(part, "w:gz", format=tarfile.PAX_FORMAT) as tf:
        tf.add(root, arcname=root.name, recursive=True)
    os.replace(part, output)
    digest = sha256_file(output)
    atomic_write(Path(str(output) + ".sha256"), f"{digest}  {output.name}\n".encode())
    return digest


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def read_table_rows(con: sqlite3.Connection, table: str, key_col: str, keys: Sequence[str]) -> list[dict[str, Any]]:
    con.row_factory = sqlite3.Row
    rows = []
    for key in keys:
        matches = con.execute(f"SELECT * FROM {table} WHERE {key_col}=? AND status='ACTIVE'", (key,)).fetchall()
        if len(matches) != 1:
            raise UpdateError(f"expected exactly one ACTIVE baseline row: {table}.{key}: observed={len(matches)}")
        rows.append(dict(matches[0]))
    return rows


def implementation_id_for(stage_key: str, path: str, sha: str | None) -> str:
    token = f"{stage_key}\0{path}\0{sha or '.'}"
    return "impl_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]


def decision_id_for(key: str, effective_at: str) -> str:
    return "decision_" + hashlib.sha256(f"{key}\0{effective_at}".encode()).hexdigest()[:24]


def interpretation_id_for(key: str, effective_at: str) -> str:
    return "interp_" + hashlib.sha256(f"{key}\0{effective_at}".encode()).hexdigest()[:24]


def contract_id_for(key: str, effective_at: str) -> str:
    return "contract_" + hashlib.sha256(f"{key}\0{effective_at}".encode()).hexdigest()[:24]


def scan_script_inventory(project_root: Path) -> list[dict[str, Any]]:
    rows = []
    for root in [project_root / "scripts", project_root / "config/evidence_schema", project_root / "metadata/build_tracker"]:
        if not root.exists(): continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".py", ".sh"}:
                rows.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return rows


def inventory_digest(rows: Sequence[dict[str, Any]]) -> str:
    payload = "".join(f"{r['path']}\t{r['bytes']}\t{r['sha256']}\n" for r in rows).encode()
    return sha256_bytes(payload)


def build_lifecycle_plan(con: sqlite3.Connection, paths: Paths, updater_sha: str) -> list[dict[str, Any]]:
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM implementations ORDER BY implementation_id")]
    explicit_paths = {r["script_path"] for r in rows if r["lifecycle_status"] != "DISCOVERED" and r["script_path"]}
    plan = []
    for r in rows:
        old = r["lifecycle_status"]; new = old; rationale = "."
        if old == "DISCOVERED":
            if r["script_path"] in explicit_paths:
                new = "SUPERSEDED"; rationale = "Auto-discovery duplicate of an explicitly classified exact path."
            else:
                new = "REFERENCE"; rationale = "Exact file is present but file existence does not imply ACTIVE; conservatively classify as REFERENCE."
        elif old == "REFERENCE_AUDIT":
            new = "REFERENCE"; rationale = "Normalize audit-reference label to the frozen lifecycle vocabulary."
        elif old == "REFERENCE_SUPPORT":
            new = "SUPPORT"; rationale = "Normalize support-reference label to the frozen lifecycle vocabulary."
        elif old == "VALIDATION_ONLY_FROZEN_EVIDENCE":
            new = "REFERENCE"; rationale = "Normalize frozen validation-evidence implementation to REFERENCE; scientific acceptance remains in evidence/contracts."
        if new != old:
            plan.append({
                "implementation_id": r["implementation_id"], "stage_key": r["stage_key"], "script_path": r["script_path"] or ".",
                "script_sha256": r["script_sha256"] or ".", "current_lifecycle_status": old,
                "proposed_lifecycle_status": new, "rationale": rationale,
            })
    install_path = paths.updater_install
    stage_key = "SCRIPT_" + install_path.stem
    auto_id = implementation_id_for(stage_key, str(install_path), updater_sha)
    plan.append({
        "implementation_id": auto_id, "stage_key": stage_key, "script_path": str(install_path),
        "script_sha256": updater_sha, "current_lifecycle_status": "DISCOVERED",
        "proposed_lifecycle_status": "SUPERSEDED",
        "rationale": "Auto-discovery duplicate of the explicit Stage15G SUPPORT implementation registered by the remediation contract.",
    })
    plan.sort(key=lambda r: r["implementation_id"])
    return plan


def build_state_plan(con: sqlite3.Connection) -> list[dict[str, Any]]:
    plan = []
    for table, key_col, keys in [
        ("limitations","limitation_key",STALE_LIMITATIONS),
        ("decisions","decision_key",STALE_DECISIONS),
        ("interpretations","interpretation_key",STALE_INTERPRETATIONS),
        ("algorithm_contracts","component_key",STALE_CONTRACTS),
    ]:
        for row in read_table_rows(con, table, key_col, keys):
            plan.append({
                "object_type": table, "object_key": row[key_col],
                "object_id": row.get({"decisions":"decision_id","interpretations":"interpretation_id","algorithm_contracts":"contract_id"}.get(table, key_col), row[key_col]),
                "current_status": row["status"], "proposed_status": "SUPERSEDED",
                "expected_row_json": json.dumps(row, sort_keys=True, ensure_ascii=False),
            })
    plan.sort(key=lambda r: (r["object_type"], r["object_key"]))
    return plan


def build_contract(paths: Paths, updater_sha: str, lifecycle_plan: list[dict[str, Any]], state_plan: list[dict[str, Any]], script_inventory_sha: str) -> dict[str, Any]:
    replacements_decisions = []
    superseded_decision_ids = {r["object_key"]:r["object_id"] for r in state_plan if r["object_type"]=="decisions"}
    for r in REPLACEMENT_DECISIONS:
        item = dict(r); item["decision_id"] = decision_id_for(item["decision_key"], EFFECTIVE_AT)
        item["supersedes_decision_id"] = superseded_decision_ids.get(item.pop("supersedes_key"))
        replacements_decisions.append(item)
    replacements_interpretations = []
    superseded_interp_ids = {r["object_key"]:r["object_id"] for r in state_plan if r["object_type"]=="interpretations"}
    for r in REPLACEMENT_INTERPRETATIONS:
        item = dict(r); item["interpretation_id"] = interpretation_id_for(item["interpretation_key"], EFFECTIVE_AT)
        item["supersedes_interpretation_id"] = superseded_interp_ids.get(item.pop("supersedes_key"))
        replacements_interpretations.append(item)
    replacements_contracts = []
    superseded_contract_ids = {r["object_key"]:r["object_id"] for r in state_plan if r["object_type"]=="algorithm_contracts"}
    for r in REPLACEMENT_CONTRACTS:
        item = dict(r); item["contract_id"] = contract_id_for(item["component_key"], EFFECTIVE_AT)
        item["supersedes_contract_id"] = superseded_contract_ids.get(item.pop("supersedes_component_key"))
        replacements_contracts.append(item)
    return {
        "schema":"rnatr.stage15g.prerc_architecture_remediation.v1",
        "version":VERSION,"effective_at":EFFECTIVE_AT,"full_run":FULL_RUN,"remediation_run":REMEDIATION_RUN,
        "updater_path":str(paths.updater_install),"updater_sha256":updater_sha,
        "baseline":{"ssot_cli_sha256":EXPECTED_BASELINE_CLI_SHA256,"ssot_db_sha256":EXPECTED_BASELINE_DB_SHA256,
                    "current_pipeline_sha256":EXPECTED_CURRENT_PIPELINE_SHA256,"core_schema_sha256":EXPECTED_CORE_SCHEMA_SHA256,
                    "release_gates_v031_sha256":EXPECTED_GATES_V031_SHA256,"script_inventory_sha256":script_inventory_sha},
        "state_plan":state_plan,"lifecycle_plan":lifecycle_plan,
        "replacement_decisions":replacements_decisions,"replacement_interpretations":replacements_interpretations,
        "replacement_contracts":replacements_contracts,"new_limitations":NEW_LIMITATIONS,"question_updates":QUESTION_UPDATES,
        "release_gates_v032_sha256":sha256_bytes(RELEASE_GATES_V032_TEXT.encode()),
        "invariants":{"scientific_rerun":False,"checkpoint_rehash":False,"package_reconstruction":False,
                      "active_pipeline_modified":False,"core_schema_modified":False,"downloads_cleanup":False,
                      "core_freeze":False,"g24_remains_open":True,"g25_g30_remain_open":True,"g32_g34_remain_open":True},
    }


def generated_payloads(paths: Paths, updater_sha: str, con: sqlite3.Connection, script_inventory_sha: str) -> dict[str, bytes]:
    lifecycle = build_lifecycle_plan(con, paths, updater_sha)
    state = build_state_plan(con)
    from io import StringIO
    b=StringIO(); w=csv.DictWriter(b,fieldnames=["implementation_id","stage_key","script_path","script_sha256","current_lifecycle_status","proposed_lifecycle_status","rationale"],delimiter="\t",lineterminator="\n");w.writeheader();w.writerows(lifecycle)
    life_bytes=b.getvalue().encode()
    b=StringIO(); w=csv.DictWriter(b,fieldnames=["object_type","object_key","object_id","current_status","proposed_status","expected_row_json"],delimiter="\t",lineterminator="\n");w.writeheader();w.writerows(state)
    state_bytes=b.getvalue().encode()
    contract=build_contract(paths,updater_sha,lifecycle,state,script_inventory_sha)
    return {
        "audit_md":AUDIT_MD.encode(),"governance_md":GOVERNANCE_MD.encode(),"audit_tsv":AUDIT_TSV.encode(),
        "lifecycle_plan":life_bytes,"state_plan":state_bytes,"contract":canonical_json(contract),
        "release_gates":RELEASE_GATES_V032_TEXT.encode(),
    }


def expected_install_hashes(paths: Paths, updater_sha: str, payloads: dict[str, bytes]) -> dict[str, str]:
    return {
        str(paths.updater_install):updater_sha,
        str(paths.audit_doc_install):sha256_bytes(payloads["audit_md"]),
        str(paths.governance_doc_install):sha256_bytes(payloads["governance_md"]),
        str(paths.findings_install):sha256_bytes(payloads["audit_tsv"]),
        str(paths.lifecycle_plan_install):sha256_bytes(payloads["lifecycle_plan"]),
        str(paths.state_plan_install):sha256_bytes(payloads["state_plan"]),
        str(paths.contract_install):sha256_bytes(payloads["contract"]),
        str(paths.gates_v032):sha256_bytes(payloads["release_gates"]),
        str(paths.stage15c_runner):EXPECTED_STAGE15C_RUNNER_SHA256,
        str(paths.runtime_binding_amendment):EXPECTED_RUNTIME_BINDING_AMENDMENT_SHA256,
        str(paths.stage15e_qc):EXPECTED_STAGE15E_QC_SHA256,
    }


def build_source_insertion(paths: Paths, updater_sha: str, payloads: dict[str, bytes]) -> str:
    guards = expected_install_hashes(paths, updater_sha, payloads)
    body = f'''{PATCH_MARKER}
stage15g_contract_path = {str(paths.contract_install)!r}
stage15g_contract_sha256 = {sha256_bytes(payloads["contract"])!r}
stage15g_lifecycle_plan_path = {str(paths.lifecycle_plan_install)!r}
stage15g_lifecycle_plan_sha256 = {sha256_bytes(payloads["lifecycle_plan"])!r}
stage15g_source_guards = {repr(guards)}

def _s15g_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _s15g_guard(path_text, expected):
    path = Path(path_text)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("Stage15G evidence missing: %s" % path)
    observed = _s15g_sha256(path)
    if observed != expected:
        raise RuntimeError("Stage15G evidence drift: %s: %s != %s" % (path, observed, expected))
    return path

for _s15g_path, _s15g_expected in stage15g_source_guards.items():
    _s15g_guard(_s15g_path, _s15g_expected)
_s15g_contract = json.loads(_s15g_guard(stage15g_contract_path, stage15g_contract_sha256).read_text(encoding="utf-8"))
if _s15g_contract.get("schema") != "rnatr.stage15g.prerc_architecture_remediation.v1":
    raise RuntimeError("Stage15G contract schema mismatch")
if _s15g_contract.get("version") != {VERSION!r}:
    raise RuntimeError("Stage15G contract version mismatch")
_s15g_effective_at = _s15g_contract["effective_at"]

_s15g_parent = conn.execute("SELECT dataset_id FROM runs WHERE run_id=?", ({FULL_RUN!r},)).fetchone()
if _s15g_parent is None:
    raise RuntimeError("Stage15G requires registered Stage15C full run")
_s15g_dataset_id = _s15g_parent[0]
conn.execute("""INSERT INTO stage_definitions(stage_key,stage_order,name,purpose,category,implementation_status,notes)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(stage_key) DO UPDATE SET stage_order=excluded.stage_order,name=excluded.name,
                purpose=excluded.purpose,category=excluded.category,implementation_status=excluded.implementation_status,notes=excluded.notes""",
             ("15G_PRERC_ARCHITECTURE_REMEDIATION",153.0,"Stage15G PRE-RC architecture remediation",
              "Supersede stale current-state SSOT metadata, normalize implementation lifecycle, and close PRE-RC consistency without scientific or active-path mutation.",
              "architecture_governance","IMPLEMENTED_SUPPORT_ONLY","G24 remains OPEN for PRE_BIOLOGY; no active pipeline promotion."))
conn.execute("""INSERT INTO runs(run_id,dataset_id,parent_run_id,run_role,pipeline_version,status,started_at,ended_at,root_path,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET dataset_id=excluded.dataset_id,
                parent_run_id=excluded.parent_run_id,run_role=excluded.run_role,pipeline_version=excluded.pipeline_version,
                status=excluded.status,root_path=excluded.root_path,notes=excluded.notes""",
             ({REMEDIATION_RUN!r},_s15g_dataset_id,{FULL_RUN!r},"architecture_governance",{VERSION!r},"PASS",None,None,
              {str(paths.update_qc_root)!r},"Metadata/lifecycle remediation only; active pipeline, schema, and scientific outputs unchanged."))
conn.execute("""INSERT OR REPLACE INTO implementations(implementation_id,stage_key,version,script_path,script_sha256,
                validator_path,validator_sha256,package_version,parameters_json,lifecycle_status,supersedes_implementation_id,
                rationale,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             ("impl_stage15g_prerc_architecture_remediation_v0_1_1","15G_PRERC_ARCHITECTURE_REMEDIATION","v0.1.1",
              {str(paths.updater_install)!r},{updater_sha!r},None,None,None,None,"SUPPORT",None,
              "Versioned SSOT/governance updater; not a scientific production entry point.",{str(paths.audit_doc_install)!r},_s15g_effective_at))
conn.execute("""INSERT OR REPLACE INTO run_stages(run_id,stage_key,implementation_id,attempt_tag,status,command_text,qc_path,qc_status,started_at,ended_at,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
             ({REMEDIATION_RUN!r},"15G_PRERC_ARCHITECTURE_REMEDIATION","impl_stage15g_prerc_architecture_remediation_v0_1_1",
              "v0.1.1","PASS",None,{str(paths.update_qc_root / 'stage15g_prerc_architecture_remediation.qc.tsv')!r},"PASS",None,None,
              "Successful SSOT rebuild is conditional on all exact remediation guards."))

# Supersede exact historical/current rows. Source baseline and the immutable contract are SHA-bound.
for _entry in _s15g_contract["state_plan"]:
    _table = _entry["object_type"]
    _expected = json.loads(_entry["expected_row_json"])
    if _table == "limitations":
        _keycol = "limitation_key"; _id = _entry["object_key"]
    elif _table == "decisions":
        _keycol = "decision_id"; _id = _entry["object_id"]
    elif _table == "interpretations":
        _keycol = "interpretation_id"; _id = _entry["object_id"]
    elif _table == "algorithm_contracts":
        _keycol = "contract_id"; _id = _entry["object_id"]
    else:
        raise RuntimeError("unknown Stage15G state-plan table: %s" % _table)
    _cursor = conn.execute("SELECT * FROM %s WHERE %s=?" % (_table,_keycol), (_id,))
    _row = _cursor.fetchone()
    if _row is None:
        raise RuntimeError("Stage15G expected row missing: %s:%s" % (_table,_id))
    _observed = {{d[0]: _row[i] for i,d in enumerate(_cursor.description)}}
    if _observed != _expected:
        raise RuntimeError("Stage15G expected row drift: %s:%s" % (_table,_id))
    conn.execute("UPDATE %s SET status='SUPERSEDED' WHERE %s=? AND status='ACTIVE'" % (_table,_keycol), (_id,))
    if conn.execute("SELECT changes()").fetchone()[0] != 1:
        raise RuntimeError("Stage15G supersede count mismatch: %s:%s" % (_table,_id))

for _r in _s15g_contract["replacement_decisions"]:
    conn.execute("""INSERT OR REPLACE INTO decisions(decision_id,decision_key,category,title,statement,status,confidence,effective_at,
                    supersedes_decision_id,rationale,evidence_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                 (_r["decision_id"],_r["decision_key"],_r["category"],_r["title"],_r["statement"],"ACTIVE",_r["confidence"],
                  _s15g_effective_at,_r.get("supersedes_decision_id"),_r["rationale"],_r["evidence_path"]))
for _r in _s15g_contract["replacement_interpretations"]:
    conn.execute("""INSERT OR REPLACE INTO interpretations(interpretation_id,interpretation_key,fact_statement,interpretation,
                    do_not_interpret_as,status,confidence,effective_at,supersedes_interpretation_id,evidence_path,evidence_metrics_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                 (_r["interpretation_id"],_r["interpretation_key"],_r["fact_statement"],_r["interpretation"],_r["do_not_interpret_as"],
                  "ACTIVE",_r["confidence"],_s15g_effective_at,_r.get("supersedes_interpretation_id"),_r["evidence_path"],
                  json.dumps(_r["evidence_metrics"],sort_keys=True)))
for _r in _s15g_contract["replacement_contracts"]:
    conn.execute("""INSERT OR REPLACE INTO algorithm_contracts(contract_id,component_key,component_name,implementation_state,
                    contract_statement,active_implementation_id,evidence_path,effective_at,status) VALUES(?,?,?,?,?,?,?,?,?)""",
                 (_r["contract_id"],_r["component_key"],_r["component_name"],_r["implementation_state"],_r["contract_statement"],
                  _r.get("active_implementation_id"),_r["evidence_path"],_s15g_effective_at,"ACTIVE"))
for _r in _s15g_contract["new_limitations"]:
    conn.execute("""INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at)
                    VALUES(?,?,?,?,?,?,?)""",
                 (_r["limitation_key"],_r["statement"],_r["severity"],"ACTIVE",_r["mitigation"],_r["evidence_path"],_s15g_effective_at))
for _r in _s15g_contract["question_updates"]:
    _existing = conn.execute("SELECT question,priority FROM open_questions WHERE question_key=?",(_r["question_key"],)).fetchone()
    if _existing is None:
        raise RuntimeError("Stage15G question missing: %s" % _r["question_key"])
    conn.execute("""UPDATE open_questions SET status=?,blocking=?,next_action=?,evidence_path=?,effective_at=? WHERE question_key=?""",
                 (_r["status"],int(_r["blocking"]),_r["next_action"],_r["evidence_path"],_s15g_effective_at,_r["question_key"]))
    if conn.execute("SELECT changes()").fetchone()[0] != 1:
        raise RuntimeError("Stage15G question update count mismatch: %s" % _r["question_key"])

# Exact implementation-ID/path/SHA lifecycle normalization.
with _s15g_guard(stage15g_lifecycle_plan_path,stage15g_lifecycle_plan_sha256).open("r",encoding="utf-8",newline="") as _handle:
    _lifecycle_rows = list(csv.DictReader(_handle,delimiter="\t"))
if len(_lifecycle_rows) != len(_s15g_contract["lifecycle_plan"]):
    raise RuntimeError("Stage15G lifecycle plan row-count mismatch")
for _r in _lifecycle_rows:
    _row = conn.execute("SELECT stage_key,script_path,script_sha256,lifecycle_status FROM implementations WHERE implementation_id=?",(_r["implementation_id"],)).fetchone()
    if _row is None:
        raise RuntimeError("Stage15G implementation missing: %s" % _r["implementation_id"])
    _expected = (_r["stage_key"],None if _r["script_path"]=="." else _r["script_path"],None if _r["script_sha256"]=="." else _r["script_sha256"],_r["current_lifecycle_status"])
    if tuple(_row) != _expected:
        raise RuntimeError("Stage15G implementation drift: %s" % _r["implementation_id"])
    conn.execute("UPDATE implementations SET lifecycle_status=?,rationale=? WHERE implementation_id=?",
                 (_r["proposed_lifecycle_status"],_r["rationale"],_r["implementation_id"]))
    if conn.execute("SELECT changes()").fetchone()[0] != 1:
        raise RuntimeError("Stage15G lifecycle update count mismatch: %s" % _r["implementation_id"])

# Register immutable Stage15G source documents.
for _path_text,_expected in stage15g_source_guards.items():
    _path = _s15g_guard(_path_text,_expected)
    _mtime = __import__("datetime").datetime.fromtimestamp(_path.stat().st_mtime,__import__("datetime").timezone.utc).replace(microsecond=0).isoformat()
    conn.execute("""INSERT INTO source_documents(source_type,path,sha256,bytes,mtime_utc,content_status,ingested_at)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET source_type=excluded.source_type,sha256=excluded.sha256,
                    bytes=excluded.bytes,mtime_utc=excluded.mtime_utc,content_status=excluded.content_status,ingested_at=excluded.ingested_at""",
                 ("stage15g_prerc_architecture_remediation_evidence",str(_path),_expected,_path.stat().st_size,_mtime,"PRESENT",_s15g_effective_at))

# Hard postconditions inside the atomic SSOT rebuild.
# Verify only the exact implementation rows owned by this immutable remediation plan.
# Future SSOT rebuilds may legitimately discover scripts introduced after Stage15G; those
# future rows must not make this historical insertion fail merely because they are DISCOVERED.
for _r in _lifecycle_rows:
    _row = conn.execute("SELECT stage_key,script_path,script_sha256,lifecycle_status FROM implementations WHERE implementation_id=?",(_r["implementation_id"],)).fetchone()
    _expected = (_r["stage_key"],None if _r["script_path"]=="." else _r["script_path"],None if _r["script_sha256"]=="." else _r["script_sha256"],_r["proposed_lifecycle_status"])
    if _row is None or tuple(_row) != _expected:
        raise RuntimeError("Stage15G lifecycle postcondition mismatch: %s" % _r["implementation_id"])
    if _r["proposed_lifecycle_status"] not in {repr(sorted(ALLOWED_LIFECYCLE))}:
        raise RuntimeError("Stage15G plan contains noncanonical lifecycle: %s" % _r["implementation_id"])
_stage15g_support = conn.execute("SELECT stage_key,script_path,script_sha256,lifecycle_status FROM implementations WHERE implementation_id='impl_stage15g_prerc_architecture_remediation_v0_1_1'").fetchone()
if _stage15g_support is None or tuple(_stage15g_support) != ("15G_PRERC_ARCHITECTURE_REMEDIATION",{str(paths.updater_install)!r},{updater_sha!r},"SUPPORT"):
    raise RuntimeError("Stage15G explicit SUPPORT implementation postcondition mismatch")
for _key in {repr(STALE_LIMITATIONS)}:
    if conn.execute("SELECT COUNT(*) FROM limitations WHERE limitation_key=? AND status='ACTIVE'",(_key,)).fetchone()[0] != 0:
        raise RuntimeError("Stage15G stale limitation remains ACTIVE: %s" % _key)
for _key in {repr(STALE_DECISIONS)}:
    if conn.execute("SELECT COUNT(*) FROM decisions WHERE decision_key=? AND status='ACTIVE'",(_key,)).fetchone()[0] != 0 and _key != "final_ranking_gate":
        raise RuntimeError("Stage15G stale decision remains ACTIVE: %s" % _key)
for _key in {repr(STALE_INTERPRETATIONS)}:
    _expected_count = 1 if _key in ("native_v041_performance_validated_caller_only","stage15a_reference_correctness_scope") else 0
    if conn.execute("SELECT COUNT(*) FROM interpretations WHERE interpretation_key=? AND status='ACTIVE'",(_key,)).fetchone()[0] != _expected_count:
        raise RuntimeError("Stage15G stale interpretation active-count mismatch: %s" % _key)
for _key in {repr(STALE_CONTRACTS)}:
    if conn.execute("SELECT COUNT(*) FROM algorithm_contracts WHERE component_key=? AND status='ACTIVE'",(_key,)).fetchone()[0] != 1:
        raise RuntimeError("Stage15G replacement contract count mismatch: %s" % _key)
if conn.execute("SELECT status FROM open_questions WHERE question_key='PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT'").fetchone()[0] != "CLOSED":
    raise RuntimeError("Stage15G PRE-RC question not closed")
'''
    return textwrap.indent(textwrap.dedent(body).rstrip() + "\n", "    ")


def verify_stage15f_bundle(paths: Paths) -> None:
    require_sha(paths.stage15f_output_bundle, EXPECTED_STAGE15F_OUTPUT_BUNDLE_SHA256)
    require_file(paths.stage15f_output_sidecar)
    if paths.stage15f_output_sidecar.read_text(encoding="utf-8").strip().split()[0] != EXPECTED_STAGE15F_OUTPUT_BUNDLE_SHA256:
        raise UpdateError("Stage15F output sidecar mismatch")
    with tarfile.open(paths.stage15f_output_bundle,"r:gz") as tf:
        for m in tf.getmembers():
            p=Path(m.name)
            if p.is_absolute() or ".." in p.parts or m.issym() or m.islnk() or m.isdev() or m.isfifo():
                raise UpdateError(f"unsafe Stage15F output member: {m.name}")


def verify_baseline(paths: Paths, *, require_absent: bool = True) -> dict[str, Any]:
    if paths.project_root != Path("/mnt/intelssd/rnatr_project"):
        raise UpdateError("unexpected project root")
    require_sha(paths.ssot_cli,EXPECTED_BASELINE_CLI_SHA256)
    require_sha(paths.ssot_db,EXPECTED_BASELINE_DB_SHA256)
    require_sha(paths.ssot_exports/"current_pipeline.tsv",EXPECTED_CURRENT_PIPELINE_SHA256)
    require_sha(paths.core_schema,EXPECTED_CORE_SCHEMA_SHA256)
    require_sha(paths.gates_v031,EXPECTED_GATES_V031_SHA256)
    require_sha(paths.stage15c_runner,EXPECTED_STAGE15C_RUNNER_SHA256)
    require_sha(paths.runtime_binding_amendment,EXPECTED_RUNTIME_BINDING_AMENDMENT_SHA256)
    require_sha(paths.stage15e_qc,EXPECTED_STAGE15E_QC_SHA256)
    verify_stage15f_bundle(paths)
    source=paths.ssot_cli.read_text(encoding="utf-8")
    if require_absent and PATCH_MARKER in source: raise UpdateError("Stage15G marker already present")
    if source.count(PATCH_ANCHOR)!=1: raise UpdateError("SSOT patch anchor count mismatch")
    destinations=[paths.gates_v032,paths.updater_install,paths.audit_doc_install,paths.governance_doc_install,paths.findings_install,
                  paths.lifecycle_plan_install,paths.state_plan_install,paths.contract_install]
    if require_absent:
        for p in destinations:
            if p.exists(): raise UpdateError(f"Stage15G destination already exists: {p}")
        if paths.update_qc_root.exists(): raise UpdateError("Stage15G QC root already exists")
        # v0.1.0 failed during SSOT rebuild and must have been fully rolled back before v0.1.1.
        for relative in FAILED_V010_RESIDUE_RELATIVE_PATHS:
            residue = paths.project_root / relative
            if residue.exists():
                raise UpdateError(f"failed Stage15G v0.1.0 residue remains after rollback: {residue}")
    con=sqlite3.connect(paths.ssot_db)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or list(con.execute("PRAGMA foreign_key_check")):
            raise UpdateError("baseline SSOT integrity failure")
        if con.execute("SELECT COUNT(*) FROM runs WHERE run_id=?",(FULL_RUN,)).fetchone()[0]!=1:
            raise UpdateError("Stage15C full run missing")
        counts=dict(con.execute("SELECT lifecycle_status,COUNT(*) FROM implementations GROUP BY lifecycle_status"))
        expected={"ACTIVE":11,"DISCOVERED":242,"PROVISIONAL":9,"REFERENCE":1,"REFERENCE_AUDIT":3,"REFERENCE_SUPPORT":1,"SUPERSEDED":8,"VALIDATION_ONLY_FROZEN_EVIDENCE":1}
        if counts!=expected: raise UpdateError(f"baseline lifecycle counts drift: {counts} != {expected}")
        # Exact current-state rows must exist.
        build_state_plan(con)
    finally: con.close()
    inventory=scan_script_inventory(paths.project_root)
    return {"ssot_cli_sha256":sha256_file(paths.ssot_cli),"ssot_db_sha256":sha256_file(paths.ssot_db),
            "current_pipeline_sha256":sha256_file(paths.ssot_exports/"current_pipeline.tsv"),"core_schema_sha256":sha256_file(paths.core_schema),
            "release_gates_v031_sha256":sha256_file(paths.gates_v031),"script_inventory_rows":len(inventory),
            "script_inventory_sha256":inventory_digest(inventory)}


def apply_contract_to_db(con: sqlite3.Connection, contract: dict[str, Any], *, updater_path: str, updater_sha: str) -> None:
    """Independent preflight simulation of the intended SQL state transition."""
    con.row_factory=sqlite3.Row
    # Add scan-derived and explicit Stage15G implementations to the DB copy.
    stage_key="SCRIPT_"+Path(updater_path).stem
    auto_id=implementation_id_for(stage_key,updater_path,updater_sha)
    con.execute("INSERT OR IGNORE INTO stage_definitions(stage_key,name,implementation_status) VALUES(?,?,?)",(stage_key,stage_key,"discovered"))
    con.execute("INSERT INTO implementations(implementation_id,stage_key,script_path,script_sha256,lifecycle_status,rationale,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?,?)",
                (auto_id,stage_key,updater_path,updater_sha,"DISCOVERED","fixture",updater_path,EFFECTIVE_AT))
    con.execute("INSERT OR REPLACE INTO stage_definitions(stage_key,stage_order,name,purpose,category,implementation_status,notes) VALUES(?,?,?,?,?,?,?)",
                ("15G_PRERC_ARCHITECTURE_REMEDIATION",153.0,"Stage15G PRE-RC architecture remediation","metadata remediation","architecture_governance","IMPLEMENTED_SUPPORT_ONLY","fixture"))
    con.execute("INSERT OR REPLACE INTO implementations(implementation_id,stage_key,version,script_path,script_sha256,lifecycle_status,rationale,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?,?,?)",
                ("impl_stage15g_prerc_architecture_remediation_v0_1_1","15G_PRERC_ARCHITECTURE_REMEDIATION","v0.1.1",updater_path,updater_sha,"SUPPORT","support",contract["replacement_decisions"][-1]["evidence_path"],EFFECTIVE_AT))
    for entry in contract["state_plan"]:
        table=entry["object_type"]
        keycol={"limitations":"limitation_key","decisions":"decision_id","interpretations":"interpretation_id","algorithm_contracts":"contract_id"}[table]
        obj=entry["object_key"] if table=="limitations" else entry["object_id"]
        row=con.execute(f"SELECT * FROM {table} WHERE {keycol}=?",(obj,)).fetchone()
        if row is None or dict(row)!=json.loads(entry["expected_row_json"]): raise UpdateError(f"simulation expected row mismatch: {table}:{obj}")
        con.execute(f"UPDATE {table} SET status='SUPERSEDED' WHERE {keycol}=?",(obj,))
    for r in contract["replacement_decisions"]:
        con.execute("INSERT OR REPLACE INTO decisions(decision_id,decision_key,category,title,statement,status,confidence,effective_at,supersedes_decision_id,rationale,evidence_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (r["decision_id"],r["decision_key"],r["category"],r["title"],r["statement"],"ACTIVE",r["confidence"],EFFECTIVE_AT,r.get("supersedes_decision_id"),r["rationale"],r["evidence_path"]))
    for r in contract["replacement_interpretations"]:
        con.execute("INSERT OR REPLACE INTO interpretations(interpretation_id,interpretation_key,fact_statement,interpretation,do_not_interpret_as,status,confidence,effective_at,supersedes_interpretation_id,evidence_path,evidence_metrics_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (r["interpretation_id"],r["interpretation_key"],r["fact_statement"],r["interpretation"],r["do_not_interpret_as"],"ACTIVE",r["confidence"],EFFECTIVE_AT,r.get("supersedes_interpretation_id"),r["evidence_path"],json.dumps(r["evidence_metrics"],sort_keys=True)))
    for r in contract["replacement_contracts"]:
        con.execute("INSERT OR REPLACE INTO algorithm_contracts(contract_id,component_key,component_name,implementation_state,contract_statement,active_implementation_id,evidence_path,effective_at,status) VALUES(?,?,?,?,?,?,?,?,?)",
                    (r["contract_id"],r["component_key"],r["component_name"],r["implementation_state"],r["contract_statement"],r.get("active_implementation_id"),r["evidence_path"],EFFECTIVE_AT,"ACTIVE"))
    for r in contract["new_limitations"]:
        con.execute("INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)",
                    (r["limitation_key"],r["statement"],r["severity"],"ACTIVE",r["mitigation"],r["evidence_path"],EFFECTIVE_AT))
    for r in contract["question_updates"]:
        con.execute("UPDATE open_questions SET status=?,blocking=?,next_action=?,evidence_path=?,effective_at=? WHERE question_key=?",
                    (r["status"],int(r["blocking"]),r["next_action"],r["evidence_path"],EFFECTIVE_AT,r["question_key"]))
        if con.execute("SELECT changes()").fetchone()[0] != 1:
            raise UpdateError(f"simulation question update count mismatch: {r['question_key']}")
    for r in contract["lifecycle_plan"]:
        row=con.execute("SELECT stage_key,script_path,script_sha256,lifecycle_status FROM implementations WHERE implementation_id=?",(r["implementation_id"],)).fetchone()
        expected=(r["stage_key"],None if r["script_path"]=="." else r["script_path"],None if r["script_sha256"]=="." else r["script_sha256"],r["current_lifecycle_status"])
        if row is None or tuple(row)!=expected: raise UpdateError(f"simulation implementation mismatch: {r['implementation_id']}")
        con.execute("UPDATE implementations SET lifecycle_status=?,rationale=? WHERE implementation_id=?",(r["proposed_lifecycle_status"],r["rationale"],r["implementation_id"]))
        if con.execute("SELECT changes()").fetchone()[0] != 1:
            raise UpdateError(f"simulation lifecycle update count mismatch: {r['implementation_id']}")
        observed=con.execute("SELECT stage_key,script_path,script_sha256,lifecycle_status FROM implementations WHERE implementation_id=?",(r["implementation_id"],)).fetchone()
        post_expected=(r["stage_key"],None if r["script_path"]=="." else r["script_path"],None if r["script_sha256"]=="." else r["script_sha256"],r["proposed_lifecycle_status"])
        if observed is None or tuple(observed)!=post_expected:
            raise UpdateError(f"simulation lifecycle postcondition mismatch: {r['implementation_id']}")
    con.commit()


def validate_remediated_db(con: sqlite3.Connection) -> dict[str, Any]:
    con.row_factory=sqlite3.Row
    if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or list(con.execute("PRAGMA foreign_key_check")):
        raise UpdateError("remediated DB integrity failure")
    statuses=dict(con.execute("SELECT lifecycle_status,COUNT(*) FROM implementations GROUP BY lifecycle_status"))
    expected={"ACTIVE":11,"PROVISIONAL":9,"REFERENCE":215,"SUPPORT":2,"SUPERSEDED":41}
    if statuses!=expected: raise UpdateError(f"remediated lifecycle counts mismatch: {statuses} != {expected}")
    if set(statuses)-ALLOWED_LIFECYCLE: raise UpdateError("noncanonical lifecycle remains")
    for key in STALE_LIMITATIONS:
        if con.execute("SELECT COUNT(*) FROM limitations WHERE limitation_key=? AND status='ACTIVE'",(key,)).fetchone()[0]: raise UpdateError(f"stale limitation active: {key}")
    for key in STALE_DECISIONS:
        count=con.execute("SELECT COUNT(*) FROM decisions WHERE decision_key=? AND status='ACTIVE'",(key,)).fetchone()[0]
        if count!=(1 if key=="final_ranking_gate" else 0): raise UpdateError(f"stale decision active count: {key}:{count}")
    for key in STALE_INTERPRETATIONS:
        count=con.execute("SELECT COUNT(*) FROM interpretations WHERE interpretation_key=? AND status='ACTIVE'",(key,)).fetchone()[0]
        if count!=(1 if key in {"native_v041_performance_validated_caller_only","stage15a_reference_correctness_scope"} else 0): raise UpdateError(f"stale interpretation active count: {key}:{count}")
    for key in STALE_CONTRACTS:
        if con.execute("SELECT COUNT(*) FROM algorithm_contracts WHERE component_key=? AND status='ACTIVE'",(key,)).fetchone()[0]!=1: raise UpdateError(f"replacement contract count: {key}")
    if con.execute("SELECT status FROM open_questions WHERE question_key='PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT'").fetchone()[0]!="CLOSED": raise UpdateError("PRE-RC question not closed")
    return {"lifecycle_counts":statuses,"active_decisions":con.execute("SELECT COUNT(*) FROM current_decisions").fetchone()[0],
            "active_interpretations":con.execute("SELECT COUNT(*) FROM current_interpretations").fetchone()[0],
            "active_contracts":con.execute("SELECT COUNT(*) FROM current_algorithm_contract").fetchone()[0],
            "active_limitations":con.execute("SELECT COUNT(*) FROM current_known_limitations").fetchone()[0],
            "open_questions":con.execute("SELECT COUNT(*) FROM current_open_questions").fetchone()[0]}


def preflight_payload(paths: Paths) -> tuple[dict[str, Any],dict[str,bytes],str]:
    baseline=verify_baseline(paths)
    updater_sha=sha256_file(Path(__file__).resolve())
    con=sqlite3.connect(paths.ssot_db)
    try: payloads=generated_payloads(paths,updater_sha,con,baseline["script_inventory_sha256"])
    finally: con.close()
    insertion=build_source_insertion(paths,updater_sha,payloads)
    source=paths.ssot_cli.read_text(encoding="utf-8")
    patched=source.replace(PATCH_ANCHOR,"\n\n"+insertion+PATCH_ANCHOR,1)
    compile(patched,str(paths.ssot_cli),"exec")
    # Independent exact-DB simulation.
    with tempfile.TemporaryDirectory(prefix="rnatr_stage15g_sim_") as td:
        copy=Path(td)/"ssot.sqlite"; shutil.copy2(paths.ssot_db,copy)
        sim=sqlite3.connect(copy)
        try:
            contract=json.loads(payloads["contract"])
            apply_contract_to_db(sim,contract,updater_path=str(paths.updater_install),updater_sha=updater_sha)
            simulation=validate_remediated_db(sim)
        finally: sim.close()
    metrics={**baseline,"updater_sha256":updater_sha,"source_insertion_sha256":sha256_bytes(insertion.encode()),
             "release_gates_v032_sha256":sha256_bytes(payloads["release_gates"]),
             "audit_doc_sha256":sha256_bytes(payloads["audit_md"]),"governance_doc_sha256":sha256_bytes(payloads["governance_md"]),
             "findings_sha256":sha256_bytes(payloads["audit_tsv"]),"lifecycle_plan_sha256":sha256_bytes(payloads["lifecycle_plan"]),
             "state_plan_sha256":sha256_bytes(payloads["state_plan"]),"remediation_contract_sha256":sha256_bytes(payloads["contract"]),
             "state_plan_rows":len(json.loads(payloads["contract"])["state_plan"]),
             "lifecycle_plan_rows":len(json.loads(payloads["contract"])["lifecycle_plan"]),
             "simulation_lifecycle_counts":json.dumps(simulation["lifecycle_counts"],sort_keys=True),
             "patched_source_compile":"PASS","exact_db_simulation":"PASS","prior_v010_failure_rollback_guard":"PASS","ssot_mutation_started":"false",
             "active_pipeline_modified":"false","core_schema_modified":"false","scientific_rerun_started":"false",
             "downloads_cleanup":"false","preflight_status":"PASS_READY_FOR_PRO_REVIEW"}
    return metrics,payloads,insertion


def run_preflight(paths: Paths) -> int:
    metrics,payloads,insertion=preflight_payload(paths)
    write_metrics(paths.preflight_qc,metrics.items())
    parent=Path(tempfile.mkdtemp(prefix="rnatr_stage15g_preflight_")); root=parent/"rnatr_stage15g_prerc_architecture_remediation_preflight_v0.1.1"
    for d in ["proposed","current","simulation"]: (root/d).mkdir(parents=True,exist_ok=True)
    shutil.copy2(paths.preflight_qc,root/paths.preflight_qc.name); shutil.copy2(Path(__file__).resolve(),root/Path(__file__).name)
    mapping={"audit_md":"RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md",
             "governance_md":"RNA_TR_Scout_Stage15G_PRE_RC_architecture_remediation_contract_v0.1.0.md",
             "audit_tsv":"rnatr_prerc_architecture_audit_v0.1.1.tsv","lifecycle_plan":"lifecycle_plan.tsv",
             "state_plan":"state_remediation_plan.tsv","contract":"remediation_contract.json","release_gates":"release_gates_v0.3.2.tsv"}
    for key,name in mapping.items(): (root/"proposed"/name).write_bytes(payloads[key])
    (root/"proposed/source_insertion.py.txt").write_text(insertion,encoding="utf-8",newline="\n")
    for p in [paths.ssot_exports/"current_decisions.tsv",paths.ssot_exports/"current_interpretations.tsv",paths.ssot_exports/"current_algorithm_contract.tsv",
              paths.ssot_exports/"current_known_limitations.tsv",paths.ssot_exports/"current_open_questions.tsv",paths.ssot_exports/"current_pipeline.tsv",paths.gates_v031]:
        shutil.copy2(p,root/"current"/p.name)
    (root/"simulation/exact_db_simulation.tsv").write_text("metric\tvalue\nstatus\tPASS\n"+f"lifecycle_counts\t{metrics['simulation_lifecycle_counts']}\n",encoding="utf-8")
    digest=make_bundle(root,paths.preflight_bundle); shutil.rmtree(parent,ignore_errors=True)
    print("===== RNA-TR-Scout Stage15G PRE-RC architecture remediation preflight =====")
    for key in ["preflight_status","ssot_cli_sha256","ssot_db_sha256","current_pipeline_sha256","core_schema_sha256","script_inventory_rows","script_inventory_sha256",
                "updater_sha256","source_insertion_sha256","release_gates_v032_sha256","state_plan_rows","lifecycle_plan_rows","exact_db_simulation",
                "prior_v010_failure_rollback_guard","ssot_mutation_started","active_pipeline_modified","core_schema_modified","scientific_rerun_started","downloads_cleanup"]:
        print(f"{key}\t{metrics[key]}")
    print(f"PREFLIGHT_QC\t{paths.preflight_qc}");print(f"OUTPUT_BUNDLE\t{paths.preflight_bundle}");print(f"OUTPUT_BUNDLE_SHA256\t{digest}")
    print("NEXT_GATE\tPRO_REVIEW_THEN_EXPLICIT_EXECUTE")
    return 0


def run_checked(command: list[str], log: Path) -> None:
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open("w",encoding="utf-8") as handle:
        proc=subprocess.run(command,stdout=handle,stderr=subprocess.STDOUT,text=True)
    if proc.returncode!=0:
        tail=log.read_text(encoding="utf-8",errors="replace")[-8000:]
        raise UpdateError(f"command failed rc={proc.returncode}: {' '.join(command)}\n{tail}")


def backup_state(paths: Paths, backup: Path) -> dict[str,bool]:
    backup.mkdir(parents=True,exist_ok=False)
    targets=[paths.gates_v032,paths.updater_install,paths.audit_doc_install,paths.governance_doc_install,paths.findings_install,
             paths.lifecycle_plan_install,paths.state_plan_install,paths.contract_install]
    pre={str(p):p.exists() for p in targets};pre["qc_root"]=paths.update_qc_root.exists();pre["meta_root"]=paths.update_meta_root.exists()
    for p in [paths.ssot_cli,paths.ssot_db,paths.ssot_summary]:
        if p.exists(): shutil.copy2(p,backup/p.name)
    if paths.ssot_exports.exists(): shutil.copytree(paths.ssot_exports,backup/"exports")
    for i,p in enumerate(targets):
        if p.exists(): shutil.copy2(p,backup/f"target_{i}_{p.name}")
    (backup/"preexisting.json").write_text(json.dumps(pre,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return pre


def restore_state(paths: Paths, backup: Path, pre: dict[str,bool]) -> None:
    for name,target in [(paths.ssot_cli.name,paths.ssot_cli),(paths.ssot_db.name,paths.ssot_db),(paths.ssot_summary.name,paths.ssot_summary)]:
        src=backup/name
        if src.exists(): target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    if paths.ssot_exports.exists(): shutil.rmtree(paths.ssot_exports)
    if (backup/"exports").exists(): shutil.copytree(backup/"exports",paths.ssot_exports)
    targets=[paths.gates_v032,paths.updater_install,paths.audit_doc_install,paths.governance_doc_install,paths.findings_install,
             paths.lifecycle_plan_install,paths.state_plan_install,paths.contract_install]
    for i,p in enumerate(targets):
        saved=backup/f"target_{i}_{p.name}"
        if pre.get(str(p)) and saved.exists(): p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(saved,p)
        elif p.exists(): p.unlink()
    if not pre.get("qc_root") and paths.update_qc_root.exists(): shutil.rmtree(paths.update_qc_root)
    # update_meta_root may be a parent of versioned targets; only remove if it did not preexist.
    if not pre.get("meta_root") and paths.update_meta_root.exists(): shutil.rmtree(paths.update_meta_root)


def verify_preflight_binding(paths: Paths) -> tuple[dict[str,str],dict[str,bytes],str]:
    qc=read_metrics(paths.preflight_qc)
    required={"preflight_status":"PASS_READY_FOR_PRO_REVIEW","updater_sha256":sha256_file(Path(__file__).resolve()),
              "ssot_cli_sha256":EXPECTED_BASELINE_CLI_SHA256,"ssot_db_sha256":EXPECTED_BASELINE_DB_SHA256,
              "current_pipeline_sha256":EXPECTED_CURRENT_PIPELINE_SHA256,"core_schema_sha256":EXPECTED_CORE_SCHEMA_SHA256,
              "release_gates_v031_sha256":EXPECTED_GATES_V031_SHA256,"ssot_mutation_started":"false"}
    for k,v in required.items():
        if qc.get(k)!=v: raise UpdateError(f"preflight binding mismatch {k}: {qc.get(k)} != {v}")
    baseline=verify_baseline(paths)
    if qc.get("script_inventory_sha256")!=baseline["script_inventory_sha256"]: raise UpdateError("script inventory drift since preflight")
    con=sqlite3.connect(paths.ssot_db)
    try: payloads=generated_payloads(paths,required["updater_sha256"],con,baseline["script_inventory_sha256"])
    finally: con.close()
    insertion=build_source_insertion(paths,required["updater_sha256"],payloads)
    checks={"source_insertion_sha256":sha256_bytes(insertion.encode()),"release_gates_v032_sha256":sha256_bytes(payloads["release_gates"]),
            "lifecycle_plan_sha256":sha256_bytes(payloads["lifecycle_plan"]),"state_plan_sha256":sha256_bytes(payloads["state_plan"]),
            "remediation_contract_sha256":sha256_bytes(payloads["contract"])}
    for k,v in checks.items():
        if qc.get(k)!=v: raise UpdateError(f"preflight generated-payload drift {k}")
    return qc,payloads,insertion


def postcheck(paths: Paths, before_pipeline_sha: str, before_schema_sha: str) -> dict[str,Any]:
    require_sha(paths.ssot_exports/"current_pipeline.tsv",before_pipeline_sha)
    require_sha(paths.core_schema,before_schema_sha)
    require_sha(paths.gates_v031,EXPECTED_GATES_V031_SHA256)
    require_sha(paths.gates_v032,sha256_bytes(RELEASE_GATES_V032_TEXT.encode()))
    require_sha(paths.stage15c_runner,EXPECTED_STAGE15C_RUNNER_SHA256);require_sha(paths.runtime_binding_amendment,EXPECTED_RUNTIME_BINDING_AMENDMENT_SHA256);require_sha(paths.stage15e_qc,EXPECTED_STAGE15E_QC_SHA256)
    con=sqlite3.connect(paths.ssot_db)
    try:
        result=validate_remediated_db(con)
        if con.execute("SELECT COUNT(*) FROM current_pipeline").fetchone()[0]!=11: raise UpdateError("current_pipeline row count changed")
        if con.execute("SELECT COUNT(*) FROM current_pipeline WHERE stage_key LIKE '15%'").fetchone()[0]!=0: raise UpdateError("Stage15 unexpectedly promoted")
    finally: con.close()
    # Gate contract checks.
    rows=list(csv.DictReader(paths.gates_v032.open(encoding="utf-8"),delimiter="\t"));by={r["gate_id"]:r for r in rows}
    if by["G24"]["status"]!="OPEN" or "PRE_BIOLOGY" not in by["G24"]["evidence_or_next_action"]: raise UpdateError("G24 postcondition failure")
    for g in ["G25","G26","G27","G28","G29","G30","G32","G33","G34"]:
        if by[g]["status"] not in {"OPEN","OPEN_PLANNED"}: raise UpdateError(f"gate unexpectedly closed: {g}")
    return {**result,"current_pipeline_sha256":sha256_file(paths.ssot_exports/"current_pipeline.tsv"),"core_schema_sha256":sha256_file(paths.core_schema),
            "ssot_cli_sha256":sha256_file(paths.ssot_cli),"ssot_db_sha256":sha256_file(paths.ssot_db),"release_gates_v032_sha256":sha256_file(paths.gates_v032)}


def run_execute(paths: Paths, confirm: str) -> int:
    if confirm!=CONFIRM_TOKEN: raise UpdateError(f"--confirm-update must exactly equal {CONFIRM_TOKEN}")
    preflight,payloads,insertion=verify_preflight_binding(paths)
    lock=paths.lock_path.open("a+");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup=paths.ssot_backups/f"stage15g_prerc_architecture_remediation_v0.1.1_{stamp}"
    pre={};mutation=False
    try:
        pre=backup_state(paths,backup);mutation=True
        # Install immutable versioned sources before rebuilding the SSOT.
        installs=[(paths.updater_install,Path(__file__).resolve().read_bytes()),(paths.audit_doc_install,payloads["audit_md"]),
                  (paths.governance_doc_install,payloads["governance_md"]),(paths.findings_install,payloads["audit_tsv"]),
                  (paths.lifecycle_plan_install,payloads["lifecycle_plan"]),(paths.state_plan_install,payloads["state_plan"]),
                  (paths.contract_install,payloads["contract"]),(paths.gates_v032,payloads["release_gates"])]
        for path,data in installs: atomic_write(path,data,0o755 if path==paths.updater_install else 0o644)
        # Patch exact SSOT source atomically.
        source=paths.ssot_cli.read_text(encoding="utf-8")
        if PATCH_MARKER in source or source.count(PATCH_ANCHOR)!=1: raise UpdateError("SSOT source marker/anchor precondition failure")
        patched=source.replace(PATCH_ANCHOR,"\n\n"+insertion+PATCH_ANCHOR,1);compile(patched,str(paths.ssot_cli),"exec")
        atomic_write(paths.ssot_cli,patched.encode(),0o755)
        paths.update_qc_root.mkdir(parents=True,exist_ok=False)
        shutil.copy2(paths.preflight_qc,paths.update_qc_root/paths.preflight_qc.name)
        write_metrics(paths.update_qc_root/"stage15g_execute_intent.tsv",[
            ("version",VERSION),("confirm_token",CONFIRM_TOKEN),("mutation_started","true"),("scientific_rerun_started","false"),
            ("active_pipeline_promotion","false"),("core_freeze","false"),("downloads_cleanup","false"),("backup",backup)])
        run_checked([sys.executable,str(paths.ssot_cli),"rebuild"],paths.update_qc_root/"ssot_rebuild.log")
        run_checked([sys.executable,str(paths.ssot_cli),"validate"],paths.update_qc_root/"ssot_validate.log")
        result=postcheck(paths,EXPECTED_CURRENT_PIPELINE_SHA256,EXPECTED_CORE_SCHEMA_SHA256)
        qc_rows=[
            ("version",VERSION),("prerc_architecture_audit","PASS_AFTER_REMEDIATION"),("state_rows_superseded",len(json.loads(payloads["contract"])["state_plan"])),
            ("lifecycle_rows_classified",len(json.loads(payloads["contract"])["lifecycle_plan"])),("lifecycle_counts",json.dumps(result["lifecycle_counts"],sort_keys=True)),
            ("pre_release_candidate_question","CLOSED"),("G24","OPEN_PREBIOLOGY_REMAINS"),("active_path_promotion","OPEN"),
            ("core_freeze_packet","OPEN_REQUIRED"),("golden_regression_suite","OPEN_REQUIRED"),("project_wide_docs_canonicalization","OPEN_REQUIRED"),
            ("clean_install_g25_g30","OPEN"),("current_pipeline_modified","false"),("core_schema_modified","false"),
            ("scientific_rerun_started","false"),("checkpoint_rehash","false"),("package_reconstruction","false"),("downloads_cleanup","false"),
            ("audit_status","PASS"),("next_gate","DESIGN_GENERIC_ACTIVE_PATH_PROMOTION_WITH_GOLDEN_REGRESSION_GUARDS"),
        ]
        write_metrics(paths.update_qc_root/"stage15g_prerc_architecture_remediation.qc.tsv",qc_rows)
        # Post-state snapshots.
        snap=paths.update_qc_root/"post_state";snap.mkdir()
        for p in [paths.ssot_exports/"current_decisions.tsv",paths.ssot_exports/"current_interpretations.tsv",paths.ssot_exports/"current_algorithm_contract.tsv",
                  paths.ssot_exports/"current_known_limitations.tsv",paths.ssot_exports/"current_open_questions.tsv",paths.ssot_exports/"current_pipeline.tsv"]:
            shutil.copy2(p,snap/p.name)
        # Success bundle.
        parent=Path(tempfile.mkdtemp(prefix="rnatr_stage15g_output_"));root=parent/"rnatr_stage15g_prerc_architecture_remediation_v0.1.1"
        for d in ["qc","metadata","docs","validation","script","ssot"]:(root/d).mkdir(parents=True,exist_ok=True)
        shutil.copytree(paths.update_qc_root,root/"qc",dirs_exist_ok=True)
        for p in [paths.lifecycle_plan_install,paths.state_plan_install,paths.contract_install]: shutil.copy2(p,root/"metadata"/p.name)
        for p in [paths.audit_doc_install,paths.governance_doc_install,paths.findings_install]: shutil.copy2(p,root/"docs"/p.name)
        shutil.copy2(paths.gates_v032,root/"validation"/paths.gates_v032.name);shutil.copy2(paths.updater_install,root/"script"/paths.updater_install.name)
        for p in [paths.ssot_cli,paths.ssot_db,paths.ssot_summary]: shutil.copy2(p,root/"ssot"/p.name)
        for p in sorted(paths.ssot_exports.glob("current_*.tsv")): shutil.copy2(p,root/"ssot"/p.name)
        digest=make_bundle(root,paths.success_bundle);shutil.rmtree(parent,ignore_errors=True)
        print("===== RNA-TR-Scout Stage15G PRE-RC architecture remediation final =====")
        for k,v in qc_rows: print(f"{k}\t{v}")
        print(f"SSOT_CLI\t{paths.ssot_cli}");print(f"SSOT_DB\t{paths.ssot_db}");print(f"BACKUP\t{backup}")
        print(f"OUTPUT_BUNDLE\t{paths.success_bundle}");print(f"OUTPUT_BUNDLE_SHA256\t{digest}")
        return 0
    except Exception as original_exc:
        if mutation:
            try:
                restore_state(paths,backup,pre)
                # A failed mutating execution is not considered safely rolled back until the
                # exact Stage15F baseline guards pass again.
                verify_baseline(paths)
            except Exception as rollback_exc:
                raise UpdateError(
                    f"Stage15G execution failed and exact rollback verification also failed: "
                    f"original={type(original_exc).__name__}: {original_exc}; "
                    f"rollback={type(rollback_exc).__name__}: {rollback_exc}"
                ) from original_exc
        raise
    finally:
        try: fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
        except Exception: pass


def self_test() -> int:
    compile(Path(__file__).read_text(encoding="utf-8"),str(Path(__file__)),"exec")
    rows=list(csv.DictReader(RELEASE_GATES_V032_TEXT.splitlines(),delimiter="\t"))
    if len(rows)!=35 or {r["gate_id"]:r for r in rows}["G24"]["status"]!="OPEN": raise UpdateError("release gates self-test failed")
    # Minimal lifecycle fixture tests exact-ID logic and vocabulary.
    con=sqlite3.connect(":memory:")
    con.executescript("""
    CREATE TABLE stage_definitions(stage_key TEXT PRIMARY KEY,stage_order REAL,name TEXT NOT NULL,purpose TEXT,category TEXT,implementation_status TEXT,notes TEXT);
    CREATE TABLE implementations(implementation_id TEXT PRIMARY KEY,stage_key TEXT NOT NULL,version TEXT,script_path TEXT,script_sha256 TEXT,validator_path TEXT,validator_sha256 TEXT,package_version TEXT,parameters_json TEXT,lifecycle_status TEXT NOT NULL,supersedes_implementation_id TEXT,rationale TEXT,evidence_path TEXT,effective_at TEXT NOT NULL);
    INSERT INTO stage_definitions(stage_key,name) VALUES('A','A'),('B','B');
    INSERT INTO implementations(implementation_id,stage_key,script_path,script_sha256,lifecycle_status,effective_at) VALUES
      ('explicit','A','/x/a.py','aaa','REFERENCE_AUDIT','x'),('auto_dup','B','/x/a.py','aaa','DISCOVERED','x'),('auto_only','B','/x/b.py','bbb','DISCOVERED','x');
    """)
    # Directly verify expected classification algorithm.
    rows=[dict(zip([d[0] for d in con.execute('select * from implementations limit 0').description],r)) for r in con.execute('select * from implementations')]
    explicit={r['script_path'] for r in rows if r['lifecycle_status']!='DISCOVERED'}
    changes={}
    for r in rows:
        if r['lifecycle_status']=='DISCOVERED': changes[r['implementation_id']]='SUPERSEDED' if r['script_path'] in explicit else 'REFERENCE'
        elif r['lifecycle_status']=='REFERENCE_AUDIT': changes[r['implementation_id']]='REFERENCE'
    if changes!={'explicit':'REFERENCE','auto_dup':'SUPERSEDED','auto_only':'REFERENCE'}: raise UpdateError(f"lifecycle self-test failed: {changes}")
    con.close()
    # Source-insertion syntax with synthetic paths and payloads.
    p=Paths(Path('/synthetic/project'),Path('/synthetic/downloads'))
    con=sqlite3.connect(':memory:')
    con.executescript("""
    CREATE TABLE implementations(implementation_id TEXT PRIMARY KEY,stage_key TEXT,version TEXT,script_path TEXT,script_sha256 TEXT,validator_path TEXT,validator_sha256 TEXT,package_version TEXT,parameters_json TEXT,lifecycle_status TEXT,supersedes_implementation_id TEXT,rationale TEXT,evidence_path TEXT,effective_at TEXT);
    CREATE TABLE limitations(limitation_key TEXT PRIMARY KEY,statement TEXT,severity TEXT,status TEXT,mitigation TEXT,evidence_path TEXT,effective_at TEXT);
    CREATE TABLE decisions(decision_id TEXT PRIMARY KEY,decision_key TEXT,category TEXT,title TEXT,statement TEXT,status TEXT,confidence TEXT,effective_at TEXT,supersedes_decision_id TEXT,rationale TEXT,evidence_path TEXT);
    CREATE TABLE interpretations(interpretation_id TEXT PRIMARY KEY,interpretation_key TEXT,fact_statement TEXT,interpretation TEXT,do_not_interpret_as TEXT,status TEXT,confidence TEXT,effective_at TEXT,supersedes_interpretation_id TEXT,evidence_path TEXT,evidence_metrics_json TEXT);
    CREATE TABLE algorithm_contracts(contract_id TEXT PRIMARY KEY,component_key TEXT,component_name TEXT,implementation_state TEXT,contract_statement TEXT,active_implementation_id TEXT,evidence_path TEXT,effective_at TEXT,status TEXT);
    CREATE TABLE open_questions(question_key TEXT PRIMARY KEY,question TEXT,priority TEXT,status TEXT,blocking INTEGER,next_action TEXT,evidence_path TEXT,effective_at TEXT);
    """)
    con.close()
    synthetic_payloads={key:b"fixture\n" for key in ("audit_md","governance_md","audit_tsv","lifecycle_plan","state_plan","contract","release_gates")}
    insertion=build_source_insertion(p,"a"*64,synthetic_payloads)
    compile("def _fixture(conn):\n"+insertion,"<stage15g-source-insertion-self-test>","exec")
    if "SELECT COUNT(*) FROM implementations WHERE lifecycle_status='DISCOVERED'" in insertion:
        raise UpdateError("source insertion is not forward-compatible with future discovered scripts")
    if "Stage15G lifecycle postcondition mismatch" not in insertion:
        raise UpdateError("source insertion lacks exact plan-owned lifecycle postconditions")
    # Regression for v0.1.0 failure: sqlite3.Row is not equal to an equivalent tuple.
    # The immutable source insertion must normalize the fetched SUPPORT row with tuple(...).
    if "_stage15g_support != (" in insertion:
        raise UpdateError("source insertion contains unsafe sqlite3.Row-vs-tuple comparison")
    if "tuple(_stage15g_support) != (" not in insertion:
        raise UpdateError("source insertion lacks sqlite3.Row normalization for SUPPORT postcondition")
    row_con = sqlite3.connect(":memory:")
    row_con.row_factory = sqlite3.Row
    row_con.execute("CREATE TABLE t(a TEXT,b TEXT,c TEXT,d TEXT)")
    expected_row = ("15G_PRERC_ARCHITECTURE_REMEDIATION","/x/updater.py","abc","SUPPORT")
    row_con.execute("INSERT INTO t VALUES(?,?,?,?)", expected_row)
    fetched_row = row_con.execute("SELECT a,b,c,d FROM t").fetchone()
    if fetched_row is None:
        raise UpdateError("sqlite3.Row regression fixture returned no row")
    if fetched_row == expected_row:
        raise UpdateError("sqlite3.Row regression fixture no longer exposes Row-vs-tuple inequality")
    if tuple(fetched_row) != expected_row:
        raise UpdateError("sqlite3.Row normalization regression fixture failed")
    row_con.close()
    print("SELF_TEST\tPASS");print(f"version\t{VERSION}");print(f"release_gates_v032_sha256\t{sha256_bytes(RELEASE_GATES_V032_TEXT.encode())}")
    return 0


def failure_bundle(paths: Paths, exc: BaseException) -> None:
    try:
        parent=Path(tempfile.mkdtemp(prefix="rnatr_stage15g_failure_"));root=parent/"rnatr_stage15g_prerc_architecture_remediation_v0.1.1_failure";root.mkdir()
        (root/"failure.txt").write_text(f"version\t{VERSION}\nexception_type\t{type(exc).__name__}\nexception\t{exc}\n\n{traceback.format_exc()}",encoding="utf-8")
        if Path(__file__).is_file(): shutil.copy2(Path(__file__).resolve(),root/Path(__file__).name)
        for p in [paths.preflight_qc,paths.ssot_exports/"current_pipeline.tsv"]:
            if p.is_file(): shutil.copy2(p,root/p.name)
        # Record the exact post-failure/rollback state without mutating it.
        guard_rows = []
        for label, path, expected in [
            ("ssot_cli", paths.ssot_cli, EXPECTED_BASELINE_CLI_SHA256),
            ("ssot_db", paths.ssot_db, EXPECTED_BASELINE_DB_SHA256),
            ("current_pipeline", paths.ssot_exports/"current_pipeline.tsv", EXPECTED_CURRENT_PIPELINE_SHA256),
            ("core_schema", paths.core_schema, EXPECTED_CORE_SCHEMA_SHA256),
            ("release_gates_v031", paths.gates_v031, EXPECTED_GATES_V031_SHA256),
        ]:
            observed = sha256_file(path) if path.is_file() else "MISSING"
            guard_rows.append({"artifact":label,"path":str(path),"expected_sha256":expected,
                               "observed_sha256":observed,"status":"PASS" if observed==expected else "FAIL"})
        write_rows(root/"post_failure_baseline_guard.tsv",guard_rows,
                   ["artifact","path","expected_sha256","observed_sha256","status"])
        digest=make_bundle(root,paths.failure_bundle);shutil.rmtree(parent,ignore_errors=True)
        print(f"FAILURE_BUNDLE\t{paths.failure_bundle}",file=sys.stderr);print(f"FAILURE_BUNDLE_SHA256\t{digest}",file=sys.stderr)
    except Exception as bundle_exc: print(f"WARNING: could not create failure bundle: {bundle_exc}",file=sys.stderr)


def main() -> int:
    parser=argparse.ArgumentParser(description="Remediate PRE_RELEASE_CANDIDATE architecture current-state and lifecycle conflicts without scientific or active-path mutation")
    modes=parser.add_mutually_exclusive_group(required=True);modes.add_argument("--self-test",action="store_true");modes.add_argument("--preflight",action="store_true");modes.add_argument("--execute",action="store_true")
    parser.add_argument("--confirm-update",default="");args=parser.parse_args();paths=default_paths()
    if args.self_test:return self_test()
    if args.preflight:return run_preflight(paths)
    return run_execute(paths,args.confirm_update)

if __name__=="__main__":
    try: raise SystemExit(main())
    except SystemExit: raise
    except Exception as exc:
        failure_bundle(default_paths(),exc);print(f"ERROR: {type(exc).__name__}: {exc}",file=sys.stderr);raise
