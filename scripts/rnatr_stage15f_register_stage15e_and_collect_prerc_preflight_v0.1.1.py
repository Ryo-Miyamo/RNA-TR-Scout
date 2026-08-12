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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

VERSION = "rnatr_stage15f_register_stage15e_and_collect_prerc_preflight_v0.1.1"
CONFIRM_TOKEN = "REGISTER_STAGE15E_AND_START_PRERC_V011"
FULL_RUN = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
MAPPING_RUN = "ENCSR307SHM_full5312696_mm2splice_v1"
STAGE15E_RUN = "ENCSR307SHM_stage15e_determinism_restart_hashseed20260810_v1"
TARGET_SHARD = "shard_065"
EFFECTIVE_AT = "2026-08-10T12:30:00+00:00"
PATCH_MARKER = "# Stage 15E determinism/restart acceptance and Stage 15F registration v0.1.1"
PATCH_ANCHOR = "\n\n    current_metrics = ["

EXPECTED_BASELINE_CLI_SHA256 = "001d91048297e34f4d0663f86075e3c5f8894be751675bf767df6ea940aa2904"
EXPECTED_BASELINE_DB_SHA256 = "cf50c3a06c81471d38eb244c2ba7c93bd324f6339cfb76771926099558d264ad"
EXPECTED_CURRENT_PIPELINE_SHA256 = "75965e89a6444852cb03c9d8ad0856dd04d136e07ad83316283c5615f82cafb3"
EXPECTED_CORE_SCHEMA_SHA256 = "c0509a0669344dba0b07cd1bb9e71f2aeb01e0196df47ec9178f1d2464b515f1"
EXPECTED_GATES_V030_SHA256 = "4d5d0572a11ac111c3ac12e1121fd6101ec3a59d7c69e53aa46855f351356715"
EXPECTED_STAGE15E_OUTPUT_BUNDLE_SHA256 = "4e4ffb3ae62b7baa14bc42df0831bd0ecf6f1a9c3606feab9c6a9aa437cd997c"
EXPECTED_HARNESS_SHA256 = "70998ac5c04d01d95955a3fecddbe7aa685f9d9fa396993f0fe616058558730d"
EXPECTED_PRO_AUDIT_SHA256 = "a1c2e37d6e5202c9242e18586fc2ecfcfb2976f24ba19e3efed3d303899047c6"

RELEASE_GATES_V031_TEXT = 'gate_id\tgate\tlevel\tblocking_for_v1\tstatus\tevidence_or_next_action\nG01\tGeneral caller deterministic across hash seeds\talgorithm\ttrue\tPASS\tStage14F2/14G, deterministic 250k/500k, and Stage15E shard_065 hash-seed logical parity\nG02\tSynthetic truth and semantic invariants\talgorithm\ttrue\tPASS\tStage14G\nG03\tPython/native 100k exact parity\timplementation\ttrue\tPASS\tStage14G all 388571 rows\nG04\tNative caller-only projected 5.31M runtime <=30 min\tperformance\tfalse\tPASS\tStage14G projected 18.90 min; BAM-to-final 30-min target remains separate and open\nG05\tPrepared-job/native-caller to validated final-evidence package\tproduction\ttrue\tPASS\tStage14K2/14L2\nG06\t5M-read BAM-input runtime <=60 min with first-freeze documented tolerance <=62 min\tperformance\ttrue\tPASS_WITH_DOCUMENTED_TOLERANCE\tEmpirical 5,312,696-read BAM-to-final v0.1.6 = 60.041256352 min; strict <=60 was exceeded by 2.475 s; mapping excluded, partition/validators/publication included\nG07\t5M-read restartability/memory/artifact audit\tproduction\ttrue\tPASS_WITH_SCOPE_AMENDMENT\tStage15E rehashed all 1,884 checkpoint artifacts/140,029,015,504 bytes before stop and resume, rejected a copied-manifest SHA corruption fixture, freshly reran caller and materializer for shard_065 under PYTHONHASHSEED=20260810, reconstructed 144 shards using 1 fresh plus 143 frozen shards with exact package parity, published atomically, and passed a zero-scientific-command second-resume no-op; scope is checkpoint-based caller-to-final, not an upstream BAM partition/11b/11d3/11e full rerun\nG08\tReal truth-bearing biological validation\tbiology\ttrue\tOPEN\tDisease/synthetic-RNA/orthogonal truth data\nG09\tLarge-cohort RNA technical/background distribution\tpopulation\tfalse\tOPEN\tDefer until production core is frozen\nG10\tFASTQ-to-final mapping-inclusive performance\tconvenience\tfalse\tOPEN\tReport minimap2 separately; current full mapping = 75.433333 min\nG11\tMismatch/indel/interruption/purity/LPS preserved separately\tschema_contract\ttrue\tPASS\tSchema v0.4.2 retains separate fields and explicit missingness\nG12\tBiological-vs-technical origin classifier truth validation\tschema_contract\tfalse\tOPEN\tCurrent package uses NOT_ASSESSED\nG13\tRead-level RNA repeat-length distribution retained\tschema_contract\ttrue\tPASS\trepeat_events remains source of truth\nG14\tRNA repeat-length clustering algorithm validated\tschema_contract\tfalse\tOPEN\tImplement after core freeze and sufficient same-locus support\nG15\tAllele/haplotype labels prohibited without phase evidence\tschema_contract\ttrue\tPASS\tValidator/contract rejects unsupported labels\nG16\tCensored/context-limited reads not naively mixed as exact observations\tschema_contract\ttrue\tPASS\tExact-only or explicit censor-aware handling required\nG17\tMapping-complete BAM to validated schema v0.4.2 package\tproduction\ttrue\tPASS\t100k/250k/500k, full 5.31M empirical package, and Stage15E exact full-package reconstruction PASS\nG18\tCalled non-locus-anchored attempts retained but not eventized\tmaterialization\ttrue\tPASS\tLossless materialization contract\nG19\tfailure_code/qc_flags/materialization_status semantics are distinct\tschema_contract\ttrue\tPASS\tStage14L2 contract\nG20\tRead-keyed biology joinability for transcript, haplotype, observability, and molecule independence\tbiology_output\ttrue\tOPEN\tFreeze and validate sidecar schemas after core technical completion\nG21\tMolecule-level distribution retained through sample-by-locus summarization\tinterpretation_output\ttrue\tOPEN\tImplement molecule_repeat_state and censor-aware sample_locus_summary\nG22\tPurpose-specific ranking lanes with unconditional known-disease retention\tinterpretation_output\ttrue\tOPEN\tImplement biology/triage lanes after core freeze\nG23\tResearcher-facing candidate dossier fully traceable to core and sidecars\tinterpretation_output\ttrue\tOPEN\tImplement dossier and reverse-traceability validator\nG24\tMajor-checkpoint Architecture consistency audit and closure\tarchitecture_contract\ttrue\tOPEN\tPost-250k audit completed. Run PRE_RELEASE_CANDIDATE audit now and PRE_BIOLOGY audit later; both must reconstruct active state from exact original code, SSOT, schema, contracts, validators, runners, and formal artifacts rather than conversation summaries or memory.\nG25\tAutomatic version-pinned reference bootstrap with resumable download and checksum verification\trelease_readiness\ttrue\tOPEN_PLANNED\tImplement reference manifest/downloader/cache; large references excluded from GitHub\nG26\tCPU/RAM/output/tmp resource detection before execution\trelease_readiness\ttrue\tOPEN_PLANNED\tExpose resource report and override provenance\nG27\tMemory-aware automatic shard/concurrency selection with manual overrides\trelease_readiness\ttrue\tOPEN_PLANNED\tUse empirical resource model; support --threads --memory-gb --tmp-dir\nG28\tScientific logical output reproducibility across supported hardware/concurrency profiles\trelease_readiness\ttrue\tOPEN_PLANNED\tStage15E is same-machine checkpoint-based evidence and does not close cross-profile or cross-machine reproducibility\nG29\tClean-machine clone-to-setup-to-test reproducibility\trelease_readiness\ttrue\tOPEN_PLANNED\tValidate independent clean environment without hidden developer paths\nG30\tEmpirical minimum/recommended/tested hardware profiles in README\trelease_readiness\ttrue\tOPEN_PLANNED\tDerive from release-scale measurements\nG31-T\tTechnical multiplicity integrity and absence of scale-dependent row runaway\ttechnical_audit\ttrue\tPASS_WITH_SCOPE_AMENDMENT\t11b-through-materialization row conservation, primary ID uniqueness, 0.0311% read-locus excess, stable 100k/500k/full multiplicity, and low target concentration; original v0.1.0 machine FAIL preserved\nG31-B\tBiological interpretation of 79.29% candidate entry and ~4.9 loci/read\tbiology_interpretation\tfalse\tOPEN_DEFERRED_TO_BIOLOGY_LAYER\tInterpret catalog overlap, +/-500bp padding, transcript concentration, motif equivalence, and recall-preserving candidate narrowing after technical core freeze\nG32\tAuthoritative Core Freeze Packet preserving the frozen Core contract\tcore_freeze_governance\ttrue\tOPEN_PLANNED\tAfter PRE-RC audit and active-path decision, create a versioned, checksummed Core Freeze Packet from reread originals covering active production path, frozen schema/API/join keys, scientific semantics, performance/restart/validator contracts, known limitations, and biology-layer interface.\nG33\tGolden regression suite for frozen scientific-output semantics\tregression_contract\ttrue\tOPEN_PLANNED\tFreeze representative test inputs, expected outputs, exact/logical parity rules, validators, versions, manifests, and SHA-256 bindings so biology additions and performance optimization cannot silently change the Core scientific contract.\nG34\tProject-wide canonical documentation and artifact-retention structure\tarchitecture_governance\ttrue\tOPEN_PLANNED\tPromote project-wide architecture/governance/contracts/freeze/regression documents to one unambiguous canonical layout; retain stage-local copies as history or pointers; classify Downloads artifacts before any move or deletion.'
REGISTRATION_DOC_TEXT = '# RNA-TR-Scout Stage 15E determinism/restart acceptance and Stage 15F registration v0.1.1\n\nStage 15E completed the frozen release-scale determinism and restart/resume gate for the current Stage15 candidate.\n\nAccepted evidence:\n\n- full checkpoint rehash before intentional stop and first resume: 1,884 artifacts, 140,029,015,504 bytes, PASS;\n- copied-manifest SHA corruption fixture rejected without modifying the source checkpoint;\n- `shard_065` caller rerun under `PYTHONHASHSEED=20260810` with exact logical parity to the baseline hash-seed-0 output;\n- selective first resume reused the fresh caller result, executed the target materializer once, reused 143 frozen shards, and reconstructed all 144 shards;\n- five plain core tables and ten plain/gzip package-manifest entries matched the clean Stage15C package exactly at the required scientific comparison level;\n- all frozen and memory-bounded validators passed before atomic publication;\n- the second resume executed zero scientific commands and preserved size, mtime, inode, device, and SHA-256 for 20 scientific artifacts;\n- the clean empirical runtime record remained 60.041256352 minutes with `PASS_WITH_DOCUMENTED_TOLERANCE` and was not overwritten.\n\nFormal scope:\n\n`CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN`\n\nThe accepted evidence closes the current checkpoint-based release-scale reconstruction and selective caller-to-final restart/resume requirement. It does not establish an independent upstream BAM partition/11b/11d3/11e full rerun, arbitrary upstream recovery, or cross-hardware/cross-machine reproducibility. G28 therefore remains open.\n\nThis registration does not promote the Stage15 candidate into `current_pipeline`, does not change caller v0.4.1, materializer v0.1.2, or schema v0.4.2, and does not overwrite the clean 60.041256352-minute benchmark. The immediate next gate is the PRE_RELEASE_CANDIDATE Architecture consistency audit, followed by explicit active-path promotion and G25-G30 release-readiness work.\n\nCore Freeze governance prerequisites added before execution:\n\n- an authoritative Core Freeze Packet is required and must be reconstructed from exact original artifacts;\n- a versioned golden regression suite with fixed inputs, expected outputs, exact/logical parity rules, validators, manifests, and checksums is required;\n- project-wide canonical documentation placement is required, with stage-local copies retained only as history or pointers;\n- PRE_RELEASE_CANDIDATE and Core Freeze decisions may not be inferred from conversation summaries or memory; missing or size-capped originals must be requested and reread;\n- Downloads cleanup is deferred until authoritative artifacts have been classified and moved to their canonical locations.\n\nThese requirements are registered as open blocking Core Freeze gates G32-G34. Stage15E registration does not itself close them or authorize Core Freeze.'
FREEZE_GOVERNANCE_DOC_TEXT = '# RNA-TR-Scout Core Freeze governance requirements v0.1.0\n\nStatus: **REQUIRED BEFORE CORE FREEZE**\n\n## 1. Role separation\n\n- **Architecture consistency audit** checks cross-domain consistency at defined checkpoints.\n- **SSOT** records the current project state.\n- **Core Freeze Packet** preserves the concise, authoritative essence of the frozen Core.\n- **Golden regression suite** mechanically proves that future changes preserve the frozen scientific-output contract.\n\n## 2. Authoritative-original rule\n\nThe PRE_RELEASE_CANDIDATE Architecture audit and Core Freeze must reconstruct active state from the exact original artifacts that govern it: code, SSOT database and exports, schema, contracts, validators, runners, manifests, checksums, and prior formal evidence. Conversation summaries and remembered historical state are not authoritative evidence.\n\nWhen an original is missing, ambiguous, too large for the collection bundle, or represented only by an inventory/hash, the audit must mark it as unresolved and request the original before finalizing the affected conclusion. No Freeze Packet, golden regression contract, active-path decision, or canonical-docs decision may be finalized by inference from memory.\n\n## 3. Core Freeze Packet\n\nCreate a versioned and checksummed formal artifact containing at least:\n\n- active production entry points and path bindings;\n- frozen schemas, table/API contracts, join keys such as `read_id`, identifiers, and missingness semantics;\n- scientific semantics and exact-versus-logical comparison rules;\n- performance, restart/resume, checkpoint, validator, and atomic-publication contracts;\n- known limitations and explicitly unproven scopes;\n- the supported interface through which biology/interpretation layers may connect without mutating Core semantics;\n- source-artifact manifest, versions, SHA-256 bindings, and a reverse-traceability map.\n\nThe packet is a compressed freeze-time contract, not a copy of the complete development history.\n\n## 4. Golden regression suite\n\nCreate a versioned suite with fixed representative inputs and expected outputs. It must include:\n\n- input manifests and checksums;\n- expected raw and/or logical outputs according to an explicit comparison policy;\n- schema and validator expectations, including accepted negative fixtures;\n- stable IDs and join-key checks;\n- commands, environment/version bindings, expected exit states, and machine-readable PASS/FAIL output;\n- coverage of lossless read-level repeat evidence, interruptions/purity/LPS/censoring semantics, materialization, restart/no-op behavior, and package publication where applicable.\n\nFuture biology additions and 30-minute performance optimization must run this suite before the Core contract is considered preserved.\n\n## 5. Canonical documentation layout\n\nAt Core Freeze, promote project-wide authoritative documents to durable canonical locations such as `docs/architecture/`, `docs/governance/`, `docs/contracts/`, `docs/core_freeze/`, and `tests/golden/` or an audited equivalent chosen after inspecting the actual repository. Stage-local copies, including the original `docs/stage15a/` architecture documents, remain as historical records or pointers to the canonical source. There must be one unambiguous authoritative location per contract.\n\nThe final layout must be chosen only after the PRE-RC audit has reread the actual repository and formal artifacts.\n\n## 6. Downloads cleanup\n\nDo not delete or relocate active-gate evidence from `~/Downloads` until authoritative artifacts and checksums are classified. After canonicalization, produce a machine-readable inventory separating:\n\n1. authoritative artifacts to preserve or move;\n2. active-gate inputs that must remain temporarily;\n3. superseded or duplicate files safe to delete;\n4. unresolved files requiring review.\n\nDeletion must be explicit and occur only after the preserved destinations and checksums are verified.'
PRO_AUDIT_TSV_TEXT = "check\tstatus\tdetail\tevidence\noverall_pro_audit\tPASS\tchecks=67 failures=0\trnatr_stage15e_combined_determinism_restart_v0.1.0_output.tar.gz\narchive_sha256_sidecar\tPASS\t4e4ffb3ae62b7baa14bc42df0831bd0ecf6f1a9c3606feab9c6a9aa437cd997c\trnatr_stage15e_combined_determinism_restart_v0.1.0_output.tar.gz.sha256\ntar_member_count\tPASS\t386\trnatr_stage15e_combined_determinism_restart_v0.1.0_output.tar.gz\ntar_path_and_type_safety\tPASS\tunsafe=0\trnatr_stage15e_combined_determinism_restart_v0.1.0_output.tar.gz\nartifact_manifest_rows\tPASS\t210\tartifact_manifest.tsv\nartifact_manifest_size_sha_verification\tPASS\terrors=0\tartifact_manifest.tsv\nunmanifested_files\tPASS\t0\tartifact_manifest.tsv\nfinal_qc::scope\tPASS\tobserved=CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN expected=CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::hash_seed_different\tPASS\tobserved=true expected=true\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::full_checkpoint_rehash_before_stop\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::full_checkpoint_rehash_before_resume\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::corrupt_checkpoint_rejection\tPASS\tobserved=PASS_COPIED_MANIFEST_SHA_NEGATIVE_FIXTURE expected=PASS_COPIED_MANIFEST_SHA_NEGATIVE_FIXTURE\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::source_checkpoint_artifact_corrupted\tPASS\tobserved=false expected=false\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::intentional_stop_after_fresh_caller\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::final_package_visible_at_stop\tPASS\tobserved=false expected=false\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::selective_resume_caller_reused\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::selective_resume_materializer_executed\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::target_caller_logical_parity\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::target_materializer_raw_parity\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::full_reconstruction_shards\tPASS\tobserved=144 expected=144\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::fresh_target_shards\tPASS\tobserved=1 expected=1\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::full_package_plain_raw_parity\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::full_package_gzip_logical_parity\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::package_manifest_logical_parity\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::frozen_validators\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::memory_bounded_validator\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::atomic_publication\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::second_resume_noop\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::second_resume_scientific_commands\tPASS\tobserved=0 expected=0\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::release_scale_determinism\tPASS\tobserved=PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE expected=PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::fullscale_restart_resume\tPASS\tobserved=PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE expected=PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::clean_full_runtime_status\tPASS\tobserved=PASS_WITH_DOCUMENTED_TOLERANCE expected=PASS_WITH_DOCUMENTED_TOLERANCE\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::clean_runtime_benchmark_overwritten\tPASS\tobserved=false expected=false\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::baseline_result_modified\tPASS\tobserved=false expected=false\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::baseline_qc_modified\tPASS\tobserved=false expected=false\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::active_pipeline_modified\tPASS\tobserved=false expected=false\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::ssot_modified\tPASS\tobserved=false expected=false\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::core_schema_modified\tPASS\tobserved=false expected=false\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::stage_status\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nfinal_qc::audit_status\tPASS\tobserved=PASS expected=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nclean_full_runtime_minutes\tPASS\t60.041256352\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv\nstate_sidecar\tPASS\td81316286a47fd5647768c7f39109a33e7f3fa6bb90b8cf1633df92d24cf3454\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json\nstate::phase\tPASS\tobserved='COMPLETE' expected='COMPLETE'\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json\nstate::second_resume_noop\tPASS\tobserved='PASS' expected='PASS'\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json\nstate::second_resume_scientific_command_count\tPASS\tobserved=0 expected=0\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json\nstate::package_final_visible\tPASS\tobserved=True expected=True\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json\nstate::package_part_visible\tPASS\tobserved=False expected=False\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json\nstate::active_pipeline_modified\tPASS\tobserved=False expected=False\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json\nstate::ssot_modified\tPASS\tobserved=False expected=False\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json\nstate::core_schema_modified\tPASS\tobserved=False expected=False\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json\ndeterminism/full_package_table_parity.tsv::rows\tPASS\t5 expected=5\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/full_package_table_parity.tsv\ndeterminism/full_package_table_parity.tsv::all_pass\tPASS\tpass=5/5\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/full_package_table_parity.tsv\ndeterminism/package_manifest_logical_parity.tsv::rows\tPASS\t10 expected=10\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/package_manifest_logical_parity.tsv\ndeterminism/package_manifest_logical_parity.tsv::all_pass\tPASS\tpass=10/10\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/package_manifest_logical_parity.tsv\ndeterminism/target_caller_parity.tsv::rows\tPASS\t1 expected=1\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_caller_parity.tsv\ndeterminism/target_caller_parity.tsv::all_pass\tPASS\tpass=1/1\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_caller_parity.tsv\ndeterminism/target_materializer_table_parity.tsv::rows\tPASS\t5 expected=5\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_materializer_table_parity.tsv\ndeterminism/target_materializer_table_parity.tsv::all_pass\tPASS\tpass=5/5\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_materializer_table_parity.tsv\nnoop/second_resume_artifact_immutability.tsv::rows\tPASS\t20 expected=20\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/noop/second_resume_artifact_immutability.tsv\nnoop/second_resume_artifact_immutability.tsv::all_pass\tPASS\tpass=20/20\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/noop/second_resume_artifact_immutability.tsv\nstage15c_fullscale_validators.tsv::rows\tPASS\t6 expected=6\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15c_fullscale_validators.tsv\nstage15c_fullscale_validators.tsv::all_pass\tPASS\tpass=6/6\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15c_fullscale_validators.tsv\ncheckpoint/intentional_stop.checkpoint_rehash.qc.tsv\tPASS\trows=1884 bytes=140029015504 status=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/checkpoint/intentional_stop.checkpoint_rehash.qc.tsv\ncheckpoint/first_resume.checkpoint_rehash.qc.tsv\tPASS\trows=1884 bytes=140029015504 status=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/checkpoint/first_resume.checkpoint_rehash.qc.tsv\ncorrupt_checkpoint_negative_fixture\tPASS\tstatus=PASS\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/negative_fixture/corrupt_checkpoint_rejection.qc.tsv\nscientific_command_ledger\tPASS\trows=2 labels=['target_caller_hashseed20260810', 'target_materializer_hashseed20260810']\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/command_ledger.tsv\nsource_and_state_guards\tPASS\tpass=29/29\tproject/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/guards/second_resume_noop.source_and_state_guards.tsv\nharness_raw_sha256\tPASS\t70998ac5c04d01d95955a3fecddbe7aa685f9d9fa396993f0fe616058558730d\trnatr_stage15e_run_combined_determinism_restart_v010.py\n"

STAGE15E_REL = Path("qc/15_stage15e_determinism_restart") / FULL_RUN / "v0.1.0"
STAGE15E_RESULT_REL = Path("results/15_stage15e_determinism_restart") / FULL_RUN / "v0.1.0"
STAGE15C_REL = Path("qc/15_stage15c_fullscale_bam_to_final") / FULL_RUN / "v0.1.6"
STAGE15C_RESULT_REL = Path("results/15_stage15c_fullscale_bam_to_final") / FULL_RUN / "v0.1.6"

EVIDENCE_RELATIVE_GUARDS: dict[str, str] = {
    str(STAGE15E_REL / "stage15e_combined_determinism_restart.qc.tsv"): "13a827f1f00aa433476913a37bfa28b73d8415e607390f8f867c942100c9d544",
    str(STAGE15E_REL / "stage15e_first_resume.qc.tsv"): "87f274eb3e0b07dad8c518bb029e749f36ff0c1001dd44d606d25da0e3a30ef6",
    str(STAGE15E_REL / "stage15e_intentional_stop.qc.tsv"): "77dcc41f058ccc2f86c006a7394fa0cacc85766b9b25b656e0d7a257160e3ebb",
    str(STAGE15E_REL / "state/stage15e_state.json"): "d81316286a47fd5647768c7f39109a33e7f3fa6bb90b8cf1633df92d24cf3454",
    str(STAGE15E_REL / "guards/second_resume_noop.source_and_state_guards.tsv"): "6cec8a72a4bc6828cf55799935d2cd1e5db80f795a6c9a8f95af15cc87c691ba",
    str(STAGE15E_REL / "checkpoint/intentional_stop.checkpoint_rehash.qc.tsv"): "4f11cddf740a113c52697e89851fedf8f6f60bfd71a4fd6ee8fa8f35d866f579",
    str(STAGE15E_REL / "checkpoint/first_resume.checkpoint_rehash.qc.tsv"): "bd34f9f63143f3c1a17fee44ea71726e5e97e25d84b495aec5da9eff6317b8b1",
    str(STAGE15E_REL / "negative_fixture/corrupt_checkpoint_rejection.qc.tsv"): "aa1284c8ed5d9e14663d79bd6afe40b5479c61e8ed2ec4722fdd688477087199",
    str(STAGE15E_REL / "determinism/target_caller_parity.tsv"): "7aaa721c28231b68e2d47497ac20c07124ac32eed9fe6fdd6e5c4965ee6d69eb",
    str(STAGE15E_REL / "determinism/target_caller_qc_stable_parity.tsv"): "d1d6ca434d9aff7e8b4f5d3f02dc291cabd36ce4c007ec9fed30d5f832e3e02a",
    str(STAGE15E_REL / "determinism/target_materializer_qc_stable_parity.tsv"): "1c8b044aefcabe5eeb5e1de01abc02daa27c467cdc608693377195745dfa98a5",
    str(STAGE15E_REL / "determinism/target_materializer_table_parity.tsv"): "363261726f1945a4c9ff40bd9681bce8dc4718f05f31e45ffdb983b3b57dc639",
    str(STAGE15E_REL / "determinism/full_package_table_parity.tsv"): "aa1c7b14f5d756f63318f57c3b37639481850296c65f73edef62b33e6be9569c",
    str(STAGE15E_REL / "determinism/package_manifest_logical_parity.tsv"): "22002643de110544781dec1e51472a88ed2ebf41837524923eebc20fe58a234f",
    str(STAGE15E_REL / "reconstruction/stage15e_reconstruction.qc.tsv"): "d9d64701680c71b904e1df1e195c0018b61742cc5f14eec22e998c55c4071671",
    str(STAGE15E_REL / "stage15c_fullscale_validators.tsv"): "45a8b5dd7be3f91ae054ffda3ae4c3dd5512e024041752d28b5695c84465a185",
    str(STAGE15E_REL / "stage15a_performance_atomic_publication.tsv"): "6cff188fd1a7da50b5256cb45ed72e9ddb16c35452696d1d1b69af17a65a0944",
    str(STAGE15E_REL / "noop/scientific_artifact_snapshot.tsv"): "294f54661e2faadf86619e340633569773e788e1238848e95c9e6f9dea5f25bf",
    str(STAGE15E_REL / "noop/second_resume_artifact_immutability.tsv"): "85f7a23420c4f75d54085a316b271eecf0657ef6dfe28f5ff5c87a48318cd312",
    str(STAGE15E_REL / "noop/second_resume_noop.qc.tsv"): "2c3087affb375f656e4b13d0167f77cecf85644817cdcd585678e4b9f7e057ac",
    str(STAGE15E_REL / "command_ledger.tsv"): "b003fb5c0ee344f0460cfb0fe70b28f7d2a2cb243948db13f129917e7dfe44dc",
    str(STAGE15E_RESULT_REL / "package_full/package_manifest.tsv"): "dd64ad79ef1301ed44255112e9b9a95ec42398a03c7fb6898ccb5417371ec06f",
    str(STAGE15E_RESULT_REL / "package_full/materialization.qc.tsv"): "f0090a2b82d8b4302aeb83b68448b1a18d51d454b8da510757d9fc17f26a54d6",
    str(STAGE15C_REL / "stage15c_full_empirical_run.qc.tsv"): "3b95addc1e7aa50ddf22d90dab3373025b9c7b41569fcb2aaea7d2910b35fd07",
    str(STAGE15C_REL / "stage15c_fullscale_checkpoint_manifest.tsv"): "f00d67e28413d66730b8c2ffab0f52b9ce9e1553e5cc9a3f9d768e4a7a0083b4",
    str(STAGE15C_RESULT_REL / "package_full/package_manifest.tsv"): "335058228a3f3c4205161f3d24b208009175aed5e50f995a74e04100b4f3a738",
}

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
    def lock_path(self) -> Path: return self.ssot_root / ".stage15f_stage15e_registration.lock"
    @property
    def core_schema(self) -> Path: return self.project_root / "config/evidence_schema/v0.4.2/schema/rnatr_v04_table_schema.json"
    @property
    def gates_v030(self) -> Path: return self.project_root / "validation/release_gates_v0.3.0.tsv"
    @property
    def gates_v031(self) -> Path: return self.project_root / "validation/release_gates_v0.3.1.tsv"
    @property
    def output_bundle(self) -> Path: return self.downloads / "rnatr_stage15e_combined_determinism_restart_v0.1.0_output.tar.gz"
    @property
    def output_sidecar(self) -> Path: return self.downloads / "rnatr_stage15e_combined_determinism_restart_v0.1.0_output.tar.gz.sha256"
    @property
    def preflight_qc(self) -> Path: return self.downloads / "rnatr_stage15f_stage15e_registration_prerc_preflight_v0.1.1.qc.tsv"
    @property
    def preflight_bundle(self) -> Path: return self.downloads / "rnatr_stage15f_stage15e_registration_prerc_preflight_v0.1.1.tar.gz"
    @property
    def success_bundle(self) -> Path: return self.downloads / "rnatr_stage15f_stage15e_registration_prerc_input_v0.1.1_output.tar.gz"
    @property
    def failure_bundle(self) -> Path: return self.downloads / "rnatr_stage15f_stage15e_registration_prerc_input_v0.1.1_failure.tar.gz"
    @property
    def harness_install(self) -> Path: return self.project_root / "scripts/rnatr_stage15e_run_combined_determinism_restart_v0.1.0.py"
    @property
    def updater_install(self) -> Path: return self.project_root / "scripts/rnatr_stage15f_register_stage15e_and_collect_prerc_preflight_v0.1.1.py"
    @property
    def doc_install(self) -> Path: return self.project_root / "docs/stage15e/RNA_TR_Scout_Stage15E_determinism_restart_acceptance_v0.1.1.md"
    @property
    def audit_install(self) -> Path: return self.project_root / "docs/stage15e/RNA_TR_Scout_Stage15E_combined_final_Pro_audit_v0.1.0.tsv"
    @property
    def governance_install(self) -> Path: return self.project_root / "docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md"
    @property
    def binding_install(self) -> Path: return self.project_root / "metadata/stage15e/determinism_restart_v0.1.0/final_bundle_binding.json"
    @property
    def update_qc_root(self) -> Path: return self.project_root / "qc/15_stage15f_stage15e_registration" / FULL_RUN / "v0.1.1"
    @property
    def update_meta_root(self) -> Path: return self.project_root / "metadata/stage15f/ssot_updates/stage15e_registration_v0.1.1"
    @property
    def prerc_root(self) -> Path: return self.update_qc_root / "pre_release_candidate_architecture_input_v0.1.1"


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


def read_metrics(path: Path) -> dict[str, str]:
    require_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if header != ["metric", "value"]:
            raise UpdateError(f"invalid metric TSV header: {path}: {header}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


def read_dict_rows(path: Path) -> list[dict[str, str]]:
    require_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_metrics(path: Path, rows: Iterable[tuple[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key, value in rows:
            writer.writerow([key, value])


def write_rows(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def atomic_write(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name("." + path.name + f".part.{os.getpid()}")
    if temp.exists(): temp.unlink()
    with temp.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temp.chmod(mode)
    os.replace(temp, path)


def make_bundle(root: Path, output: Path) -> str:
    manifest_rows: list[dict[str, Any]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name == "artifact_manifest.tsv": continue
        manifest_rows.append({"relative_path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    write_rows(root / "artifact_manifest.tsv", manifest_rows, ["relative_path", "bytes", "sha256"])
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_name("." + output.name + ".part")
    if part.exists(): part.unlink()
    with tarfile.open(part, "w:gz", format=tarfile.PAX_FORMAT) as tf:
        tf.add(root, arcname=root.name, recursive=True)
    os.replace(part, output)
    digest = sha256_file(output)
    atomic_write(Path(str(output) + ".sha256"), f"{digest}  {output.name}\n".encode())
    return digest


def output_bundle_member_bytes(paths: Paths, suffix: str) -> bytes:
    require_sha(paths.output_bundle, EXPECTED_STAGE15E_OUTPUT_BUNDLE_SHA256)
    with tarfile.open(paths.output_bundle, "r:gz") as tf:
        matches = [m for m in tf.getmembers() if m.isfile() and m.name.endswith(suffix)]
        if len(matches) != 1:
            raise UpdateError(f"output bundle member match count for {suffix}: {len(matches)}")
        handle = tf.extractfile(matches[0])
        if handle is None: raise UpdateError(f"cannot read bundle member: {matches[0].name}")
        return handle.read()


def verify_output_bundle(paths: Paths) -> dict[str, Any]:
    require_sha(paths.output_bundle, EXPECTED_STAGE15E_OUTPUT_BUNDLE_SHA256)
    require_file(paths.output_sidecar)
    side = paths.output_sidecar.read_text(encoding="utf-8").strip().split()[0]
    if side != EXPECTED_STAGE15E_OUTPUT_BUNDLE_SHA256:
        raise UpdateError("Stage15E output sidecar mismatch")
    with tarfile.open(paths.output_bundle, "r:gz") as tf:
        members = tf.getmembers()
        for member in members:
            p = Path(member.name)
            if p.is_absolute() or ".." in p.parts or member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise UpdateError(f"unsafe Stage15E output bundle member: {member.name}")
        manifest_members = [m for m in members if m.isfile() and m.name.endswith("/artifact_manifest.tsv")]
        if len(manifest_members) != 1: raise UpdateError("Stage15E output artifact manifest missing or ambiguous")
        manifest_data = tf.extractfile(manifest_members[0]).read().decode("utf-8")
        rows = list(csv.DictReader(manifest_data.splitlines(), delimiter="\t"))
        by_name = {m.name: m for m in members if m.isfile()}
        prefix = manifest_members[0].name.rsplit("/", 1)[0] + "/"
        for row in rows:
            name = prefix + row["relative_path"]
            member = by_name.get(name)
            if member is None: raise UpdateError(f"manifest member missing: {name}")
            payload = tf.extractfile(member).read()
            if len(payload) != int(row["bytes"]) or sha256_bytes(payload) != row["sha256"]:
                raise UpdateError(f"manifest member mismatch: {name}")
    harness = output_bundle_member_bytes(paths, "/rnatr_stage15e_run_combined_determinism_restart_v010.py")
    if sha256_bytes(harness) != EXPECTED_HARNESS_SHA256:
        raise UpdateError("Stage15E harness hash mismatch inside final bundle")
    return {"bundle_members": len(members), "bundle_manifest_rows": len(rows), "harness_sha256": sha256_bytes(harness)}


def evidence_paths(paths: Paths) -> dict[Path, str]:
    return {paths.project_root / rel: digest for rel, digest in EVIDENCE_RELATIVE_GUARDS.items()}


def verify_evidence_hashes(paths: Paths) -> None:
    for path, expected in evidence_paths(paths).items(): require_sha(path, expected)


def verify_stage15e_semantics(paths: Paths) -> dict[str, Any]:
    base = paths.project_root / STAGE15E_REL
    qc = read_metrics(base / "stage15e_combined_determinism_restart.qc.tsv")
    expected = {
        "scope": "CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN",
        "hash_seed_different": "true", "full_checkpoint_rehash_before_stop": "PASS", "full_checkpoint_rehash_before_resume": "PASS",
        "corrupt_checkpoint_rejection": "PASS_COPIED_MANIFEST_SHA_NEGATIVE_FIXTURE", "source_checkpoint_artifact_corrupted": "false",
        "intentional_stop_after_fresh_caller": "PASS", "final_package_visible_at_stop": "false",
        "selective_resume_caller_reused": "PASS", "selective_resume_materializer_executed": "PASS",
        "target_caller_logical_parity": "PASS", "target_materializer_raw_parity": "PASS",
        "full_reconstruction_shards": "144", "fresh_target_shards": "1",
        "full_package_plain_raw_parity": "PASS", "full_package_gzip_logical_parity": "PASS",
        "package_manifest_logical_parity": "PASS", "frozen_validators": "PASS", "memory_bounded_validator": "PASS",
        "atomic_publication": "PASS", "second_resume_noop": "PASS", "second_resume_scientific_commands": "0",
        "release_scale_determinism": "PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE",
        "fullscale_restart_resume": "PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE",
        "clean_full_runtime_minutes": "60.041256352", "clean_full_runtime_status": "PASS_WITH_DOCUMENTED_TOLERANCE",
        "clean_runtime_benchmark_overwritten": "false", "baseline_result_modified": "false", "baseline_qc_modified": "false",
        "active_pipeline_modified": "false", "ssot_modified": "false", "core_schema_modified": "false",
        "stage_status": "PASS", "audit_status": "PASS",
    }
    for key, value in expected.items():
        if qc.get(key) != value: raise UpdateError(f"Stage15E final QC mismatch {key}: {qc.get(key)} != {value}")
    for rel in ("checkpoint/intentional_stop.checkpoint_rehash.qc.tsv", "checkpoint/first_resume.checkpoint_rehash.qc.tsv"):
        data = read_metrics(base / rel)
        for key, value in {"checkpoint_rows":"1884", "checkpoint_bytes":"140029015504", "full_checkpoint_rehash":"PASS", "baseline_modified_during_rehash":"false", "audit_status":"PASS"}.items():
            if data.get(key) != value: raise UpdateError(f"checkpoint QC mismatch {rel} {key}")
    state = json.loads((base / "state/stage15e_state.json").read_text(encoding="utf-8"))
    for key, value in {"phase":"COMPLETE", "second_resume_noop":"PASS", "second_resume_scientific_command_count":0, "package_final_visible":True, "package_part_visible":False, "active_pipeline_modified":False, "ssot_modified":False, "core_schema_modified":False}.items():
        if state.get(key) != value: raise UpdateError(f"Stage15E state mismatch {key}: {state.get(key)!r}")
    guards = read_dict_rows(base / "guards/second_resume_noop.source_and_state_guards.tsv")
    if len(guards) != 29 or any(row.get("status") != "PASS" or row.get("expected_sha256") != row.get("observed_sha256") for row in guards):
        raise UpdateError("Stage15E source/state guard mismatch")
    checks = [
        ("determinism/full_package_table_parity.tsv", 5), ("determinism/package_manifest_logical_parity.tsv", 10),
        ("determinism/target_caller_parity.tsv", 1), ("determinism/target_materializer_table_parity.tsv", 5),
        ("noop/second_resume_artifact_immutability.tsv", 20), ("stage15c_fullscale_validators.tsv", 6),
    ]
    for rel, count in checks:
        rows = read_dict_rows(base / rel)
        if len(rows) != count or any(row.get("status") != "PASS" for row in rows):
            raise UpdateError(f"Stage15E table audit mismatch: {rel}")
    ledger = read_dict_rows(base / "command_ledger.tsv")
    if [row.get("label") for row in ledger] != ["target_caller_hashseed20260810", "target_materializer_hashseed20260810"] or any(row.get("status") != "PASS" for row in ledger):
        raise UpdateError("Stage15E command ledger mismatch")
    return {"checkpoint_rows":1884, "checkpoint_bytes":140029015504, "scientific_commands":len(ledger), "source_state_guards":len(guards)}


def parse_release_gates(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(text.splitlines(), delimiter="\t"))
    if len(rows) != 35: raise UpdateError(f"release gate row count mismatch: {len(rows)}")
    by = {row["gate_id"]: row for row in rows}
    expected = {"G06":"PASS_WITH_DOCUMENTED_TOLERANCE", "G07":"PASS_WITH_SCOPE_AMENDMENT", "G24":"OPEN", "G25":"OPEN_PLANNED", "G28":"OPEN_PLANNED", "G30":"OPEN_PLANNED", "G31-T":"PASS_WITH_SCOPE_AMENDMENT", "G31-B":"OPEN_DEFERRED_TO_BIOLOGY_LAYER", "G32":"OPEN_PLANNED", "G33":"OPEN_PLANNED", "G34":"OPEN_PLANNED"}
    for gate, status in expected.items():
        if by.get(gate, {}).get("status") != status: raise UpdateError(f"release gate mismatch {gate}")
    return rows


def build_binding_json(updater_sha256: str) -> bytes:
    payload = {
        "version": VERSION, "stage15e_output_bundle": "rnatr_stage15e_combined_determinism_restart_v0.1.0_output.tar.gz",
        "stage15e_output_bundle_sha256": EXPECTED_STAGE15E_OUTPUT_BUNDLE_SHA256,
        "harness_sha256": EXPECTED_HARNESS_SHA256, "updater_sha256": updater_sha256,
        "pro_audit_sha256": EXPECTED_PRO_AUDIT_SHA256,
        "scope": "CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN",
        "release_scale_determinism": "PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE",
        "fullscale_restart_resume": "PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE",
        "second_resume_noop": "PASS", "clean_runtime_minutes": 60.041256352,
        "clean_runtime_status": "PASS_WITH_DOCUMENTED_TOLERANCE",
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def source_guard_hashes(paths: Paths, updater_sha: str) -> dict[Path, str]:
    return {
        paths.harness_install: EXPECTED_HARNESS_SHA256,
        paths.updater_install: updater_sha,
        paths.doc_install: sha256_bytes(REGISTRATION_DOC_TEXT.encode("utf-8")),
        paths.audit_install: EXPECTED_PRO_AUDIT_SHA256,
        paths.governance_install: sha256_bytes(FREEZE_GOVERNANCE_DOC_TEXT.encode("utf-8")),
        paths.binding_install: sha256_bytes(build_binding_json(updater_sha)),
        paths.gates_v031: sha256_bytes(RELEASE_GATES_V031_TEXT.encode("utf-8")),
    }


def build_source_insertion(paths: Paths, updater_sha: str, *, evidence: dict[Path,str] | None = None, sources: dict[Path,str] | None = None) -> str:
    ev = evidence_paths(paths) if evidence is None else evidence
    src = source_guard_hashes(paths, updater_sha) if sources is None else sources
    body = f'''{PATCH_MARKER}
stage15e_effective_at = {EFFECTIVE_AT!r}
stage15e_base_run = {FULL_RUN!r}
stage15e_validation_run = {STAGE15E_RUN!r}
stage15e_evidence_guards = {repr({str(k):v for k,v in ev.items()})}
stage15e_source_guards = {repr({str(k):v for k,v in src.items()})}

def _s15f_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _s15f_guard(path_text, expected):
    path = Path(path_text)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("Stage15E registration evidence missing: %s" % path)
    observed = _s15f_sha256(path)
    if observed != expected:
        raise RuntimeError("Stage15E registration evidence drift: %s: %s != %s" % (path, observed, expected))
    return path

for _s15f_path, _s15f_expected in {{**stage15e_evidence_guards, **stage15e_source_guards}}.items():
    _s15f_guard(_s15f_path, _s15f_expected)

_s15f_parent = conn.execute("SELECT dataset_id FROM runs WHERE run_id=?", (stage15e_base_run,)).fetchone()
if _s15f_parent is None:
    raise RuntimeError("Stage15E registration requires registered Stage15C full run")
_s15f_dataset_id = _s15f_parent[0]

def _s15f_stage(key, order, name, purpose, category, implementation_status, notes):
    conn.execute("""INSERT INTO stage_definitions(stage_key,stage_order,name,purpose,category,implementation_status,notes)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(stage_key) DO UPDATE SET stage_order=excluded.stage_order,
                    name=excluded.name,purpose=excluded.purpose,category=excluded.category,
                    implementation_status=excluded.implementation_status,notes=excluded.notes""",
                 (key,order,name,purpose,category,implementation_status,notes))

def _s15f_run(run_id,parent_run_id,role,pipeline_version,status,root_path,notes):
    conn.execute("""INSERT INTO runs(run_id,dataset_id,parent_run_id,run_role,pipeline_version,status,started_at,ended_at,root_path,notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET dataset_id=excluded.dataset_id,
                    parent_run_id=excluded.parent_run_id,run_role=excluded.run_role,pipeline_version=excluded.pipeline_version,
                    status=excluded.status,root_path=excluded.root_path,notes=excluded.notes""",
                 (run_id,_s15f_dataset_id,parent_run_id,role,pipeline_version,status,None,None,root_path,notes))

def _s15f_impl(impl_id,stage_key,version,script_path,script_sha,lifecycle,rationale,evidence_path):
    conn.execute("""INSERT OR REPLACE INTO implementations(implementation_id,stage_key,version,script_path,script_sha256,
                    validator_path,validator_sha256,package_version,parameters_json,lifecycle_status,
                    supersedes_implementation_id,rationale,evidence_path,effective_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (impl_id,stage_key,version,script_path,script_sha,None,None,"v0.4.2",None,lifecycle,None,rationale,evidence_path,stage15e_effective_at))

def _s15f_run_stage(run_id,stage_key,impl_id,attempt,status,qc_path,qc_status,notes):
    conn.execute("""INSERT OR REPLACE INTO run_stages(run_id,stage_key,implementation_id,attempt_tag,status,command_text,
                    qc_path,qc_status,started_at,ended_at,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                 (run_id,stage_key,impl_id,attempt,status,None,qc_path,qc_status,None,None,notes))

def _s15f_metric(name,value_text,value_num,unit,denominator,source_path,status="CURRENT"):
    conn.execute("""INSERT OR REPLACE INTO metrics(run_id,stage_key,metric_name,value_text,value_num,unit,
                    denominator_num,source_path,metric_status,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                 (stage15e_validation_run,"15E_RELEASE_SCALE_DETERMINISM_RESTART",name,str(value_text),value_num,unit,
                  denominator,str(source_path),status,stage15e_effective_at))

def _s15f_decision(key,category,title,statement,confidence,rationale,evidence_path):
    decision_id = "decision_" + hashlib.sha256(key.encode()).hexdigest()[:20]
    conn.execute("""INSERT OR REPLACE INTO decisions(decision_id,decision_key,category,title,statement,status,confidence,
                    effective_at,supersedes_decision_id,rationale,evidence_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                 (decision_id,key,category,title,statement,"ACTIVE",confidence,stage15e_effective_at,None,rationale,str(evidence_path)))

def _s15f_interpretation(key,fact,interpretation,do_not,confidence,evidence_path,metrics):
    interpretation_id = "interpretation_" + hashlib.sha256(key.encode()).hexdigest()[:20]
    conn.execute("""INSERT OR REPLACE INTO interpretations(interpretation_id,interpretation_key,fact_statement,interpretation,
                    do_not_interpret_as,status,confidence,effective_at,supersedes_interpretation_id,evidence_path,evidence_metrics_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                 (interpretation_id,key,fact,interpretation,do_not,"ACTIVE",confidence,stage15e_effective_at,None,
                  str(evidence_path),json.dumps(metrics,sort_keys=True)))

def _s15f_contract(key,name,state,statement,impl_id,evidence_path,status="ACTIVE"):
    contract_id = "contract_" + hashlib.sha256(key.encode()).hexdigest()[:20]
    conn.execute("""INSERT OR REPLACE INTO algorithm_contracts(contract_id,component_key,component_name,implementation_state,
                    contract_statement,active_implementation_id,evidence_path,effective_at,status) VALUES(?,?,?,?,?,?,?,?,?)""",
                 (contract_id,key,name,state,statement,impl_id,str(evidence_path),stage15e_effective_at,status))

def _s15f_source(path_text,source_type,expected):
    path = _s15f_guard(path_text,expected)
    mtime = __import__("datetime").datetime.fromtimestamp(path.stat().st_mtime,__import__("datetime").timezone.utc).replace(microsecond=0).isoformat()
    conn.execute("""INSERT INTO source_documents(source_type,path,sha256,bytes,mtime_utc,content_status,ingested_at)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET source_type=excluded.source_type,
                    sha256=excluded.sha256,bytes=excluded.bytes,mtime_utc=excluded.mtime_utc,
                    content_status=excluded.content_status,ingested_at=excluded.ingested_at""",
                 (source_type,str(path),expected,path.stat().st_size,mtime,"PRESENT",stage15e_effective_at))

_s15f_stage("15E_RELEASE_SCALE_DETERMINISM_RESTART",152.0,"Stage 15E release-scale determinism and restart/resume",
            "Validate checkpoint integrity, different-hash-seed scientific parity, intentional stop, selective caller-to-final resume, full package reconstruction, atomic publication, and second-resume idempotence at full scale.",
            "production_validation","IMPLEMENTED_WITH_SCOPE_AMENDMENT",
            "PASS for checkpoint-based reconstruction with one fresh target shard and 143 frozen reused shards; not an upstream BAM partition/11b/11d3/11e full rerun or cross-hardware test.")
_s15f_stage("15C_FULL_EMPIRICAL_BAM_TO_FINAL",151.8,"Stage 15C full 5.31M empirical BAM-to-final",
            "Run mapping-complete full BAM through target assignment, projection, caller, materialization, validation, and atomic publication.",
            "production_validation","IMPLEMENTED_WITH_GATE",
            "Correctness/memory/storage/publication PASS and runtime PASS_WITH_DOCUMENTED_TOLERANCE; Stage15E subsequently closed checkpoint-based release-scale determinism and selective caller-to-final restart/resume.")
conn.execute("UPDATE stage_definitions SET notes=? WHERE stage_key='15A_BAM_TO_FINAL_PERFORMANCE'",
             ("Historical isolated candidate. Deterministic 500k, full empirical execution, and Stage15E scoped determinism/restart subsequently passed; 30-minute optimization remains nonblocking for first freeze.",))
conn.execute("UPDATE stage_definitions SET notes=? WHERE stage_key='15A_RESTART_RESUME_VALIDATION'",
             ("Historical 100k selective-resume validation. Stage15E subsequently passed full-scale checkpoint-based caller-to-final selective restart/resume and no-op verification.",))
conn.execute("UPDATE stage_definitions SET notes=? WHERE stage_key='15A_DETERMINISTIC_SCALING'",
             ("Historical 250k scaling gate. Deterministic 500k and full empirical execution subsequently passed.",))

_s15f_run(stage15e_validation_run,stage15e_base_run,"RELEASE_SCALE_DETERMINISM_RESTART_VALIDATION",
           "rnatr_stage15e_combined_determinism_restart_v0.1.0","PASS_WITH_SCOPE_AMENDMENT",
           {str(paths.project_root / STAGE15E_RESULT_REL)!r},
           "Different-hash-seed target caller/materializer parity, 144-shard exact package reconstruction, checkpoint rejection, intentional stop/selective resume, atomic publication, and second-resume no-op PASS within the frozen checkpoint-based scope.")
conn.execute("UPDATE runs SET notes=? WHERE run_id=?",
             ("Full 5.31M BAM-to-final correctness PASS at 60.041256352 min with documented tolerance. Stage15E subsequently closed checkpoint-based release-scale reconstruction and selective caller-to-final restart/resume; active pipeline remains unpromoted.",stage15e_base_run))
_s15f_impl("impl_stage15e_combined_determinism_restart_v0_1_0","15E_RELEASE_SCALE_DETERMINISM_RESTART","v0.1.0",
           {str(paths.harness_install)!r},{EXPECTED_HARNESS_SHA256!r},"VALIDATION_ONLY_FROZEN_EVIDENCE",
           "Governance/validation harness; not an active scientific production entry point.",{str(paths.project_root / STAGE15E_REL / 'stage15e_combined_determinism_restart.qc.tsv')!r})
_s15f_run_stage(stage15e_validation_run,"15E_RELEASE_SCALE_DETERMINISM_RESTART","impl_stage15e_combined_determinism_restart_v0_1_0",
                 "hashseed20260810_intentional_stop_resume_noop","PASS",
                 {str(paths.project_root / STAGE15E_REL / 'stage15e_combined_determinism_restart.qc.tsv')!r},"PASS",
                 "Checkpoint-based scope explicitly excludes upstream BAM partition/11b/11d3/11e full rerun and cross-hardware validation.")

_s15f_qc = Path({str(paths.project_root / STAGE15E_REL / 'stage15e_combined_determinism_restart.qc.tsv')!r})
_s15f_caller = Path({str(paths.project_root / STAGE15E_REL / 'determinism/target_caller_qc_stable_parity.tsv')!r})
_s15f_materializer = Path({str(paths.project_root / STAGE15E_REL / 'determinism/target_materializer_qc_stable_parity.tsv')!r})
_s15f_package = Path({str(paths.project_root / STAGE15E_REL / 'determinism/full_package_table_parity.tsv')!r})
_s15f_rehash = Path({str(paths.project_root / STAGE15E_REL / 'checkpoint/first_resume.checkpoint_rehash.qc.tsv')!r})
_s15f_noop = Path({str(paths.project_root / STAGE15E_REL / 'noop/second_resume_noop.qc.tsv')!r})
for _name,_text,_num,_unit,_den,_source in [
    ("scope","CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN",None,None,None,_s15f_qc),
    ("baseline_hash_seed","0",0,None,None,_s15f_qc),("determinism_hash_seed","20260810",20260810,None,None,_s15f_qc),
    ("checkpoint_artifacts","1884",1884,"artifacts",None,_s15f_rehash),("checkpoint_bytes","140029015504",140029015504,"bytes",None,_s15f_rehash),
    ("target_shard","shard_065",65,"shard_index",None,_s15f_qc),("target_caller_input_rows","146558",146558,"rows",None,_s15f_caller),
    ("target_caller_called_rows","61333",61333,"rows",None,_s15f_caller),("target_materializer_repeat_event_rows","61323",61323,"rows",None,_s15f_materializer),
    ("reconstruction_shards","144",144,"shards",None,_s15f_qc),("fresh_target_shards","1",1,"shards",144,_s15f_qc),("frozen_reused_shards","143",143,"shards",144,_s15f_qc),
    ("read_evidence_rows","20656258",20656258,"rows",None,_s15f_package),("general_repeat_calls_rows","20656258",20656258,"rows",None,_s15f_package),
    ("repeat_events_rows","8523140",8523140,"rows",None,_s15f_package),("repeat_segments_rows","8573315",8573315,"rows",None,_s15f_package),
    ("repeat_interruptions_rows","43399",43399,"rows",None,_s15f_package),("frozen_validator_count","6",6,"validators",None,_s15f_qc),
    ("second_resume_scientific_commands","0",0,"commands",None,_s15f_noop),("clean_runtime_minutes","60.041256352",60.041256352,"minutes",None,_s15f_qc),
    ("release_scale_determinism","PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE",None,None,None,_s15f_qc),
    ("fullscale_restart_resume","PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE",None,None,None,_s15f_qc),
    ("second_resume_noop","PASS",None,None,None,_s15f_noop),
]: _s15f_metric(_name,_text,_num,_unit,_den,_source)

conn.execute("UPDATE decisions SET status='SUPERSEDED' WHERE decision_key='stage15a_restart_resume_scope_v0_1_0' AND status='ACTIVE'")
_s15f_decision("stage15e_determinism_restart_acceptance_v0_1_0","production_validation","Accept Stage15E scoped release-scale determinism and restart/resume",
               "Accept exact checkpoint-based full-package reconstruction and selective caller-to-final restart/resume with corrupt-manifest rejection, atomic publication, and second-resume no-op. Preserve the explicit exclusion of upstream BAM partition/11b/11d3/11e full rerun and cross-hardware claims.",
               "HIGH","All frozen Stage15E validators and parity checks passed and the clean Stage15C benchmark remained unchanged.",_s15f_qc)
_s15f_decision("stage15e_cross_hardware_not_closed_v0_1_0","release_readiness","Do not close cross-hardware determinism from Stage15E",
               "Stage15E is same-machine checkpoint-based evidence. G28 remains OPEN_PLANNED until supported hardware/concurrency profiles and an independent machine are compared.",
               "HIGH","The validated scope is narrower than G28.",_s15f_qc)
_s15f_decision("stage15e_active_promotion_remains_deferred_v0_1_0","architecture","Keep Stage15 candidate provisional after Stage15E",
               "Do not modify current_pipeline during Stage15E registration. Run PRE_RELEASE_CANDIDATE Architecture consistency audit, then perform an explicit versioned active-path promotion only after all Core Freeze governance gates are explicitly accounted for.",
               "HIGH","Stage15E closes determinism/restart but not architecture audit, promotion, Core Freeze Packet, golden regression, documentation canonicalization, or clean-install gates.",{str(paths.gates_v031)!r})
_s15f_decision("core_freeze_preservation_artifacts_required_v0_1_0","core_freeze_governance","Require Core Freeze Packet and golden regression suite",
               "Core Freeze requires a versioned checksummed Core Freeze Packet plus a machine-executable golden regression suite. SSOT alone is not sufficient to preserve the long-term scientific contract.",
               "HIGH","The packet preserves the concise human-readable contract and the regression suite enforces it mechanically.",{str(paths.governance_install)!r})
_s15f_decision("authoritative_originals_required_for_prerc_and_freeze_v0_1_0","architecture_governance","Require exact originals for PRE-RC and Core Freeze reconstruction",
               "PRE_RELEASE_CANDIDATE and Core Freeze conclusions must be based on reread original code, SSOT, schema, contracts, validators, runners, manifests, and formal evidence. Conversation summaries and memory are not authoritative.",
               "HIGH","Missing, ambiguous, or size-capped originals must remain unresolved until supplied and reread.",{str(paths.governance_install)!r})
_s15f_decision("project_docs_and_downloads_canonicalization_v0_1_0","artifact_governance","Canonicalize project docs before Downloads cleanup",
               "Promote project-wide authoritative documents to a durable one-source layout, preserve stage-local history or pointers, and only then classify, move, or delete accumulated Downloads artifacts by checksum-backed inventory.",
               "HIGH","This prevents deletion of active evidence and avoids competing authoritative copies.",{str(paths.governance_install)!r})

_s15f_interpretation("stage15e_full_package_parity_v0_1_0","The reconstructed five-table package matched the clean Stage15C package at all required plain/raw and gzip/logical comparison points.",
                     "Within the checkpoint-based scope, scientific output is reproducible under a different hash seed and selective target-shard recomputation.",
                     "An independent upstream full rerun, arbitrary upstream recovery, or cross-machine reproducibility.","HIGH",_s15f_package,
                     {{"reconstruction_shards":144,"fresh_target_shards":1,"frozen_reused_shards":143}})
_s15f_interpretation("stage15e_second_resume_idempotence_v0_1_0","The second resume executed zero scientific commands and preserved 20 scientific artifacts by size, mtime, inode, device, and SHA-256.",
                     "The completed Stage15E resume state is idempotent and does not silently rewrite the scientific package.",
                     "A guarantee for future changed code, references, parameters, or arbitrary upstream checkpoints.","HIGH",_s15f_noop,{{"scientific_commands":0,"artifacts":20}})
_s15f_interpretation("stage15e_corruption_fixture_scope_v0_1_0","The negative fixture changed the expected SHA in a copied manifest and the same checkpoint validator rejected the mismatch without modifying source artifacts.",
                     "The SHA-binding rejection path is validated.",
                     "A physical bit-flip of the source checkpoint artifact or every possible corruption mode.","HIGH",
                     {str(paths.project_root / STAGE15E_REL / 'negative_fixture/corrupt_checkpoint_rejection.qc.tsv')!r},{{"source_artifact_corrupted":False}})

conn.execute("UPDATE algorithm_contracts SET status='SUPERSEDED' WHERE component_key IN ('stage15a_bam_to_final_gate_v010','stage15a_deterministic_scaling_v0_1_2','stage15a_performance_candidate_v0221','stage15a_restart_resume_v0_1_0') AND status='ACTIVE'")
_s15f_contract("stage15e_release_scale_determinism_restart_v0_1_0","Stage15E release-scale determinism and restart/resume",
               "PASS_CHECKPOINT_BASED_RECONSTRUCTION_AND_SELECTIVE_CALLER_TO_FINAL_RESUME",
               "Rehash the frozen 1,884-artifact checkpoint before reuse; reject SHA drift; fresh-run the target caller under a different hash seed; stop before materialization; selectively resume materializer and 144-shard reconstruction; require clean-package parity and all frozen validators before atomic publication; require second resume to be a no-op. Scope excludes upstream BAM partition/11b/11d3/11e full rerun and cross-hardware claims.",
               "impl_stage15e_combined_determinism_restart_v0_1_0",_s15f_qc)
_s15f_contract("stage15c_fullscale_execution_v0_1_6","Stage15C full-scale execution contract",
               "EMPIRICAL_FULLSCALE_PASS_WITH_TOLERANCE_STAGE15E_DETERMINISM_RESTART_PASS_SCOPED",
               "Use 144 read-coherent shards, concurrency 12, caller workers 2/shard, validator workers 3, 512M external sort, PYTHONHASHSEED=0 for the clean benchmark, prepartition runtime-script/path audit, bounded validation, and atomic publication. Stage15E adds checkpoint-based different-hash-seed reconstruction and selective caller-to-final resume evidence; active promotion and G25-G30 remain open.",
               "impl_stage15c_full_runner_v0_1_6",_s15f_qc)
_s15f_contract("release_readiness_g25_g30_v0_1_0","Internal-beta release readiness G25-G30","DESIGNED_NOT_IMPLEMENTED",
               "Portable reference bootstrap, resource detection, adaptive concurrency, cross-hardware determinism, clean-machine install, and empirical hardware profiles remain required before internal beta/release candidate. Stage15E does not close these gates.",
               None,{str(paths.gates_v031)!r})
_s15f_contract("core_freeze_preservation_governance_v0_1_0","Core Freeze preservation and governance contract","DESIGNED_REQUIRED_BEFORE_CORE_FREEZE",
               "Before Core Freeze, reread exact originals; create a checksummed Core Freeze Packet and golden regression suite; establish one canonical project-wide documentation layout with stage-local history/pointers; and defer Downloads deletion until an authoritative retention inventory is verified.",
               None,{str(paths.governance_install)!r})

for _key,_question,_priority,_status,_blocking,_next,_evidence in [
    ("RELEASE_SCALE_DETERMINISM","Does an independent release-scale execution reproduce the full scientific package exactly at the logical level?","RESOLVED","CLOSED",0,
     "Closed for checkpoint-based reconstruction by Stage15E. Preserve the explicit exclusion of upstream full rerun and cross-hardware evidence; G28 remains open.",str(_s15f_qc)),
    ("FULLSCALE_RESTART_RESUME","Can the full run reject corrupt checkpoints, selectively resume, match the clean package, and become a second-resume no-op?","RESOLVED","CLOSED",0,
     "Closed for copied-manifest SHA rejection and selective caller-to-final resume by Stage15E; arbitrary upstream recovery is outside the accepted scope.",str(_s15f_qc)),
    ("GENERAL_CALLER_PRODUCTION_INTEGRATION","Can the exact-parity Stage 15A candidate remain deterministic, restartable, artifact-complete, and within the 60-minute hard ceiling as BAM input increases, while continuing toward the 30-minute target?","RESOLVED","CLOSED",0,
     "Core integration is validated at full scale with documented 60-62 minute tolerance and Stage15E scoped determinism/restart. Continue 30-minute optimization as a separate nonblocking engineering target.",str(_s15f_qc)),
    ("PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT","Are SSOT, active paths, frozen schema/contracts, runtime-generated artifacts, restart, biology roadmap, and release gates globally consistent?","CRITICAL","OPEN",1,
     "Run the PRE_RELEASE_CANDIDATE Architecture consistency audit immediately using the Stage15F post-registration input bundle.",str(_s15f_qc)),
    ("ARCHITECTURE_CONSISTENCY_AUDIT_CLOSURE","Are SSOT, active code/path, schema/contracts, performance gates, validation/restart scope, biology roadmap, and implementation lifecycle mutually consistent at each major checkpoint?","CRITICAL","OPEN",1,
     "Post-250k audit is complete. Perform PRE_RELEASE_CANDIDATE audit now and preserve PRE_BIOLOGY audit as a later mandatory checkpoint.",str(_s15f_qc)),
    ("ACTIVE_PATH_PROMOTION","When and how should the validated Stage15 candidate replace the legacy active P0/P1 pipeline?","CRITICAL","OPEN",1,
     "After PRE_RELEASE_CANDIDATE audit closure and an explicit plan for G32-G34, perform a versioned promotion with rollback and golden-regression guards.",str(_s15f_qc)),
    ("CLEAN_INSTALL_INTERNAL_BETA","Can an independent clean machine install software/references and reproduce a test run without developer-local paths?","HIGH","OPEN",1,
     "Implement and validate G25-G30 before v0.5.0-rc1/internal beta.",str({str(paths.gates_v031)!r})),
    ("CORE_FREEZE_PACKET","Has a versioned checksummed Core Freeze Packet been reconstructed from exact originals and accepted as the concise human-readable Core contract?","CRITICAL","OPEN",1,
     "After PRE-RC architecture reconstruction and active-path decision, create and audit the packet specified by G32.",{str(paths.governance_install)!r}),
    ("GOLDEN_REGRESSION_SUITE","Does a fixed-input expected-output suite mechanically enforce the frozen Core scientific contract, including exact/logical parity rules and negative fixtures?","CRITICAL","OPEN",1,
     "Build, run, and freeze the G33 suite before Core Freeze; future biology and performance changes must run it.",{str(paths.governance_install)!r}),
    ("PROJECT_WIDE_DOCS_CANONICALIZATION","Is there one unambiguous project-wide authoritative location for architecture, governance, contracts, Core Freeze, and regression documents?","CRITICAL","OPEN",1,
     "Choose the canonical layout only after rereading the actual repository; retain stage-local copies as history or pointers and close G34 before Core Freeze.",{str(paths.governance_install)!r}),
    ("DOWNLOADS_ARTIFACT_CLEANUP","Which accumulated Downloads artifacts must be preserved, moved, retained temporarily, or deleted?","MODERATE","OPEN",0,
     "After authoritative destinations and checksums are established, produce an explicit retention/deletion plan and execute cleanup separately.",{str(paths.governance_install)!r}),
]:
    conn.execute("""INSERT OR REPLACE INTO open_questions(question_key,question,priority,status,blocking,next_action,evidence_path,effective_at)
                    VALUES(?,?,?,?,?,?,?,?)""",(_key,_question,_priority,_status,_blocking,_next,_evidence,stage15e_effective_at))

for _key,_statement,_severity,_mitigation,_evidence in [
    ("STAGE15E_CHECKPOINT_BASED_SCOPE_NOT_UPSTREAM_FULL_RERUN","Stage15E proves checkpoint-based reconstruction with one fresh target shard and selective caller-to-final resume; it is not an independent upstream BAM partition/11b/11d3/11e full rerun.","HIGH","Do not generalize the evidence beyond the registered scope; retain G28 and clean-install gates.",str(_s15f_qc)),
    ("STAGE15E_SAME_MACHINE_NOT_CROSS_HARDWARE","Stage15E was executed on the same machine and does not establish scientific reproducibility across supported hardware/concurrency profiles.","HIGH","Close G28 with explicit cross-profile and cross-machine comparisons.",str(_s15f_qc)),
    ("STAGE15E_CORRUPTION_FIXTURE_IS_COPIED_MANIFEST_SHA_MISMATCH","The corruption negative fixture altered an expected SHA in a copied manifest, not the source checkpoint bytes.","MODERATE","Interpret as validation of SHA-bound rejection logic, not exhaustive physical-corruption coverage.",{str(paths.project_root / STAGE15E_REL / 'negative_fixture/corrupt_checkpoint_rejection.qc.tsv')!r}),
    ("STAGE15C_ACTIVE_PIPELINE_NOT_PROMOTED","The empirically validated Stage15 candidate remains provisional and is not the current active pipeline.","HIGH","Run PRE_RELEASE_CANDIDATE audit, then explicit active-path promotion with rollback and golden regression.",str(_s15f_qc)),
    ("CORE_FREEZE_GOVERNANCE_ARTIFACTS_NOT_YET_CREATED","Core Freeze Packet, golden regression suite, and project-wide documentation canonicalization are required but not yet complete.","HIGH","Keep G32-G34 and the corresponding SSOT questions open until exact-original reconstruction and formal artifact audits pass.",{str(paths.governance_install)!r}),
]:
    conn.execute("""INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at)
                    VALUES(?,?,?,?,?,?,?)""",(_key,_statement,_severity,"ACTIVE",_mitigation,_evidence,stage15e_effective_at))

for _path_text,_expected in {{**stage15e_evidence_guards, **stage15e_source_guards}}.items():
    _s15f_source(_path_text,"stage15e_determinism_restart_registration_evidence",_expected)
'''
    return textwrap.indent(textwrap.dedent(body).rstrip() + "\n", "    ")


def verify_baseline(paths: Paths, *, require_absent: bool = True) -> dict[str, str]:
    if paths.project_root != Path("/mnt/intelssd/rnatr_project"):
        raise UpdateError("unexpected project root")
    require_sha(paths.ssot_cli, EXPECTED_BASELINE_CLI_SHA256)
    require_sha(paths.ssot_db, EXPECTED_BASELINE_DB_SHA256)
    require_sha(paths.ssot_exports / "current_pipeline.tsv", EXPECTED_CURRENT_PIPELINE_SHA256)
    require_sha(paths.core_schema, EXPECTED_CORE_SCHEMA_SHA256)
    require_sha(paths.gates_v030, EXPECTED_GATES_V030_SHA256)
    source = paths.ssot_cli.read_text(encoding="utf-8")
    if require_absent and PATCH_MARKER in source: raise UpdateError("Stage15E registration marker already present")
    if source.count(PATCH_ANCHOR) != 1: raise UpdateError(f"SSOT patch anchor count mismatch: {source.count(PATCH_ANCHOR)}")
    if require_absent:
        for path in (paths.gates_v031, paths.harness_install, paths.updater_install, paths.doc_install, paths.audit_install, paths.governance_install, paths.binding_install):
            if path.exists(): raise UpdateError(f"versioned Stage15F destination already exists: {path}")
        if paths.update_qc_root.exists() or paths.update_meta_root.exists(): raise UpdateError("Stage15F versioned output root already exists")
    con = sqlite3.connect(paths.ssot_db)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or list(con.execute("PRAGMA foreign_key_check")):
            raise UpdateError("baseline SSOT database integrity failure")
        if con.execute("SELECT count(*) FROM runs WHERE run_id=?", (FULL_RUN,)).fetchone()[0] != 1:
            raise UpdateError("Stage15C full run missing from SSOT")
    finally: con.close()
    return {"ssot_cli_sha256":sha256_file(paths.ssot_cli), "ssot_db_sha256":sha256_file(paths.ssot_db),
            "current_pipeline_sha256":sha256_file(paths.ssot_exports / "current_pipeline.tsv"), "core_schema_sha256":sha256_file(paths.core_schema)}


def preflight_payload(paths: Paths) -> dict[str, Any]:
    baseline = verify_baseline(paths)
    bundle = verify_output_bundle(paths)
    verify_evidence_hashes(paths)
    semantics = verify_stage15e_semantics(paths)
    parse_release_gates(RELEASE_GATES_V031_TEXT)
    updater_sha = sha256_file(Path(__file__).resolve())
    if sha256_bytes(PRO_AUDIT_TSV_TEXT.encode("utf-8")) != EXPECTED_PRO_AUDIT_SHA256:
        raise UpdateError("embedded Pro audit hash mismatch")
    insertion = build_source_insertion(paths, updater_sha)
    source = paths.ssot_cli.read_text(encoding="utf-8")
    patched = source.replace(PATCH_ANCHOR, "\n\n" + insertion + PATCH_ANCHOR, 1)
    compile(patched, str(paths.ssot_cli), "exec")
    return {**baseline, **bundle, **semantics, "updater_sha256":updater_sha,
            "release_gates_v031_sha256":sha256_bytes(RELEASE_GATES_V031_TEXT.encode()),
            "registration_doc_sha256":sha256_bytes(REGISTRATION_DOC_TEXT.encode()),
            "pro_audit_sha256":EXPECTED_PRO_AUDIT_SHA256,
            "source_insertion_sha256":sha256_bytes(insertion.encode()),
            "patched_source_compile":"PASS", "ssot_mutation_started":"false",
            "active_pipeline_modified":"false", "core_schema_modified":"false",
            "prerc_post_registration_collection_planned":"true", "preflight_status":"PASS_READY_FOR_PRO_REVIEW"}


def run_preflight(paths: Paths) -> int:
    payload = preflight_payload(paths)
    write_metrics(paths.preflight_qc, payload.items())
    parent = Path(tempfile.mkdtemp(prefix="rnatr_stage15f_preflight_"))
    root = parent / "rnatr_stage15f_stage15e_registration_prerc_preflight_v0.1.1"
    (root / "proposed").mkdir(parents=True)
    (root / "current_ssot").mkdir(parents=True)
    shutil.copy2(paths.preflight_qc, root / paths.preflight_qc.name)
    shutil.copy2(Path(__file__).resolve(), root / Path(__file__).name)
    (root / "proposed/release_gates_v0.3.1.tsv").write_text(RELEASE_GATES_V031_TEXT, encoding="utf-8", newline="\n")
    (root / "proposed/registration_plan.md").write_text(REGISTRATION_DOC_TEXT, encoding="utf-8", newline="\n")
    (root / "proposed/stage15e_final_pro_audit.tsv").write_text(PRO_AUDIT_TSV_TEXT, encoding="utf-8", newline="\n")
    (root / "proposed/core_freeze_governance_requirements_v0.1.0.md").write_text(FREEZE_GOVERNANCE_DOC_TEXT, encoding="utf-8", newline="\n")
    (root / "proposed/source_insertion.py.txt").write_text(build_source_insertion(paths, payload["updater_sha256"]), encoding="utf-8", newline="\n")
    harness = output_bundle_member_bytes(paths, "/rnatr_stage15e_run_combined_determinism_restart_v010.py")
    (root / "proposed/rnatr_stage15e_run_combined_determinism_restart_v0.1.0.py").write_bytes(harness)
    for path in (paths.ssot_cli, paths.ssot_exports / "current_pipeline.tsv", paths.ssot_exports / "current_open_questions.tsv", paths.ssot_exports / "current_algorithm_contract.tsv", paths.gates_v030):
        shutil.copy2(path, root / "current_ssot" / path.name)
    shutil.copy2(paths.output_bundle, root / paths.output_bundle.name)
    shutil.copy2(paths.output_sidecar, root / paths.output_sidecar.name)
    digest = make_bundle(root, paths.preflight_bundle)
    shutil.rmtree(parent, ignore_errors=True)
    print("===== RNA-TR-Scout Stage15F registration + PRE-RC collection preflight =====")
    for key in ("preflight_status","checkpoint_rows","checkpoint_bytes","source_state_guards","bundle_manifest_rows",
                "ssot_cli_sha256","ssot_db_sha256","current_pipeline_sha256","updater_sha256","release_gates_v031_sha256",
                "source_insertion_sha256","ssot_mutation_started","active_pipeline_modified","core_schema_modified",
                "prerc_post_registration_collection_planned"):
        print(f"{key}\t{payload[key]}")
    print(f"PREFLIGHT_QC\t{paths.preflight_qc}")
    print(f"OUTPUT_BUNDLE\t{paths.preflight_bundle}")
    print(f"OUTPUT_BUNDLE_SHA256\t{digest}")
    print("NEXT_GATE\tPRO_REVIEW_THEN_EXPLICIT_EXECUTE")
    return 0


def run_checked(command: list[str], log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-6000:]
        raise UpdateError(f"command failed rc={proc.returncode}: {' '.join(command)}\n{tail}")


def backup_state(paths: Paths, backup: Path) -> dict[str, bool]:
    backup.mkdir(parents=True, exist_ok=False)
    targets = [paths.gates_v031, paths.harness_install, paths.updater_install, paths.doc_install, paths.audit_install, paths.governance_install, paths.binding_install]
    preexisting = {str(path):path.exists() for path in targets}
    preexisting["update_qc_root"] = paths.update_qc_root.exists(); preexisting["update_meta_root"] = paths.update_meta_root.exists()
    for path in (paths.ssot_cli, paths.ssot_db, paths.ssot_summary):
        if path.exists(): shutil.copy2(path, backup / path.name)
    if paths.ssot_exports.exists(): shutil.copytree(paths.ssot_exports, backup / "exports")
    for idx,path in enumerate(targets):
        if path.exists(): shutil.copy2(path, backup / f"target_{idx}_{path.name}")
    (backup / "preexisting.json").write_text(json.dumps(preexisting,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return preexisting


def restore_state(paths: Paths, backup: Path, preexisting: dict[str,bool]) -> None:
    for name,target in ((paths.ssot_cli.name,paths.ssot_cli),(paths.ssot_db.name,paths.ssot_db),(paths.ssot_summary.name,paths.ssot_summary)):
        src=backup/name
        if src.exists(): target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,target)
    if paths.ssot_exports.exists(): shutil.rmtree(paths.ssot_exports)
    if (backup/"exports").exists(): shutil.copytree(backup/"exports",paths.ssot_exports)
    targets=[paths.gates_v031,paths.harness_install,paths.updater_install,paths.doc_install,paths.audit_install,paths.governance_install,paths.binding_install]
    for idx,path in enumerate(targets):
        saved=backup/f"target_{idx}_{path.name}"
        if preexisting.get(str(path)) and saved.exists(): path.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(saved,path)
        elif path.exists(): path.unlink()
    if not preexisting.get("update_qc_root") and paths.update_qc_root.exists(): shutil.rmtree(paths.update_qc_root)
    if not preexisting.get("update_meta_root") and paths.update_meta_root.exists(): shutil.rmtree(paths.update_meta_root)


def verify_preflight_binding(paths: Paths) -> dict[str,str]:
    qc=read_metrics(paths.preflight_qc)
    required={"preflight_status":"PASS_READY_FOR_PRO_REVIEW","ssot_mutation_started":"false","active_pipeline_modified":"false",
              "core_schema_modified":"false","updater_sha256":sha256_file(Path(__file__).resolve()),
              "ssot_cli_sha256":EXPECTED_BASELINE_CLI_SHA256,"ssot_db_sha256":EXPECTED_BASELINE_DB_SHA256,
              "current_pipeline_sha256":EXPECTED_CURRENT_PIPELINE_SHA256,
              "release_gates_v031_sha256":sha256_bytes(RELEASE_GATES_V031_TEXT.encode())}
    for key,value in required.items():
        if qc.get(key)!=value: raise UpdateError(f"preflight binding mismatch {key}: {qc.get(key)} != {value}")
    return qc


def safe_copy(source: Path, root: Path, project_root: Path, category: str, rows: list[dict[str,Any]], *, max_bytes: int = 10_000_000) -> None:
    if not source.is_file():
        rows.append({"category":category,"source_path":str(source),"bytes":".","sha256":".","copied":"false","reason":"MISSING"}); return
    size=source.stat().st_size; digest=sha256_file(source)
    if size>max_bytes:
        rows.append({"category":category,"source_path":str(source),"bytes":size,"sha256":digest,"copied":"false","reason":"SIZE_CAP"}); return
    try: rel=source.relative_to(project_root)
    except ValueError: rel=Path("external")/source.name
    dest=root/"files"/rel
    dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,dest)
    rows.append({"category":category,"source_path":str(source),"bytes":size,"sha256":digest,"copied":"true","reason":"PASS"})


def collect_prerc_inputs(paths: Paths) -> dict[str,Any]:
    root=paths.prerc_root
    if root.exists(): raise UpdateError(f"PRE-RC input root already exists: {root}")
    root.mkdir(parents=True)
    inventory: list[dict[str,Any]]=[]
    # Exact post-registration SSOT/release state.
    for path in [paths.ssot_cli,paths.ssot_db,paths.ssot_summary,paths.gates_v030,paths.gates_v031,
                 *sorted(paths.ssot_exports.glob("current_*.tsv"))]:
        safe_copy(path,root,paths.project_root,"SSOT_AND_RELEASE_STATE",inventory,max_bytes=30_000_000)
    # Active pipeline source and validator bindings.
    active_rows=read_dict_rows(paths.ssot_exports/"current_pipeline.tsv")
    active_inventory=[]
    for row in active_rows:
        for field,hash_field,kind in (("script_path","script_sha256","ACTIVE_SCRIPT"),("validator_path","validator_sha256","ACTIVE_VALIDATOR")):
            value=row.get(field,".")
            if not value or value==".": continue
            path=Path(value); expected=row.get(hash_field,"."); observed=sha256_file(path) if path.is_file() else "."
            status="PASS" if path.is_file() and (not expected or expected=="." or expected==observed) else "FAIL"
            active_inventory.append({"stage_key":row.get("stage_key"),"kind":kind,"path":str(path),"expected_sha256":expected,"observed_sha256":observed,"status":status})
            safe_copy(path,root,paths.project_root,kind,inventory,max_bytes=5_000_000)
    write_rows(root/"active_pipeline_inventory.tsv",active_inventory,["stage_key","kind","path","expected_sha256","observed_sha256","status"])
    if any(row["status"]!="PASS" for row in active_inventory): raise UpdateError("active pipeline source binding failure during PRE-RC collection")
    # Stage15E guard inventory, copying source/config/small evidence but not large data.
    guard_rows=read_dict_rows(paths.project_root/STAGE15E_REL/"guards/second_resume_noop.source_and_state_guards.tsv")
    write_rows(root/"stage15e_source_state_guard_snapshot.tsv",guard_rows,list(guard_rows[0].keys()))
    for row in guard_rows:
        p=Path(row["path"]); category="STAGE15E_"+row["guard_class"]
        cap=5_000_000 if row["guard_class"]=="SOURCE_STATE" else 2_000_000
        safe_copy(p,root,paths.project_root,category,inventory,max_bytes=cap)
    # Runtime-generated frozen scripts: exact 144 x 6 contract.
    shards_root=paths.project_root/STAGE15C_RESULT_REL/"shards"
    expected_names=["11b.stage15c_fullscale.sh","11b.stage15c_fullscale.sh.stage15a_v021.diff",
                    "11d3.stage15c_fullscale.sh","11d3.stage15c_fullscale.sh.stage15a_v021.diff",
                    "11e.stage15c_fullscale.sh","11e.stage15c_fullscale.sh.stage15a_v021.diff"]
    runtime_rows=[]
    for index in range(144):
        shard=f"shard_{index:03d}"; d=shards_root/shard/"frozen_scripts"
        names=sorted(p.name for p in d.iterdir() if p.is_file()) if d.is_dir() else []
        if names!=expected_names: raise UpdateError(f"runtime frozen-script contract mismatch: {shard}: {names}")
        for name in names:
            p=d/name; runtime_rows.append({"shard":shard,"filename":name,"bytes":p.stat().st_size,"sha256":sha256_file(p),"status":"PASS"})
            safe_copy(p,root,paths.project_root,"RUNTIME_FROZEN_SCRIPT",inventory,max_bytes=2_000_000)
    write_rows(root/"runtime_frozen_script_inventory.tsv",runtime_rows,["shard","filename","bytes","sha256","status"])
    # Candidate and historical lifecycle surface.
    lifecycle=[]
    patterns=("rnatr_stage14*","rnatr_stage15*","rnatr_materialize_native_v041*","rnatr_general_repeat*")
    candidates=set()
    for pattern in patterns: candidates.update(paths.project_root.joinpath("scripts").glob(pattern))
    candidates.update(paths.project_root.joinpath("src/rnatr_scout").rglob("*.py"))
    for p in sorted(x for x in candidates if x.is_file()):
        if p.stat().st_size>5_000_000: continue
        text=p.read_text(encoding="utf-8",errors="replace")
        version="."
        m=re.search(r"(?m)^VERSION\s*=\s*[\"']([^\"']+)",text)
        if m: version=m.group(1)
        lifecycle.append({"path":str(p),"bytes":p.stat().st_size,"sha256":sha256_file(p),"version_literal":version,"contains_main":str("if __name__" in text).lower()})
        safe_copy(p,root,paths.project_root,"STAGE14_15_LIFECYCLE",inventory,max_bytes=5_000_000)
    write_rows(root/"stage14_15_script_lifecycle_inventory.tsv",lifecycle,["path","bytes","sha256","version_literal","contains_main"])
    # Project-wide architecture, biology, handover, validation, schema, and release-readiness originals.
    doc_roots=[paths.project_root/"docs",paths.project_root/"validation",paths.project_root/"metadata/general_caller",
               paths.project_root/"config/evidence_schema/v0.4.2"]
    allowed={".md",".tsv",".json",".txt",".yaml",".yml",".toml",".py",".sh"}
    seen_doc_paths=set()
    for d in doc_roots:
        if not d.exists(): continue
        for p in sorted(x for x in d.rglob("*") if x.is_file() and x.suffix.lower() in allowed):
            if p in seen_doc_paths: continue
            seen_doc_paths.add(p)
            safe_copy(p,root,paths.project_root,"PROJECT_WIDE_CONTRACT_DOC_SCHEMA_OR_VALIDATION",inventory,max_bytes=5_000_000)
    # Previous architecture audit evidence.
    prev=paths.project_root/"qc/15_architecture_consistency_audit"
    if prev.exists():
        for p in sorted(x for x in prev.rglob("*") if x.is_file()): safe_copy(p,root,paths.project_root,"PREVIOUS_ARCHITECTURE_AUDIT",inventory,max_bytes=5_000_000)
    # Project packaging/setup surface and git state.
    root_patterns=["README*","pyproject.toml","setup.py","setup.cfg","requirements*.txt","environment*.yml","environment*.yaml","Dockerfile*","Makefile","CITATION.cff","LICENSE*"]
    for pattern in root_patterns:
        for p in paths.project_root.glob(pattern): safe_copy(p,root,paths.project_root,"RELEASE_PACKAGING",inventory,max_bytes=5_000_000)
    for pattern in ("*bootstrap*","*setup*","*install*","*reference*","*download*","*resource*","*hardware*","*concurrency*"):
        for p in paths.project_root.joinpath("scripts").glob(pattern):
            if p.is_file(): safe_copy(p,root,paths.project_root,"RELEASE_READINESS_CANDIDATE",inventory,max_bytes=5_000_000)
    git_rows=[]
    if (paths.project_root/".git").exists():
        for label,cmd in (("head",["git","-C",str(paths.project_root),"rev-parse","HEAD"]),("status",["git","-C",str(paths.project_root),"status","--porcelain=v1"]),("tracked",["git","-C",str(paths.project_root),"ls-files"])):
            proc=subprocess.run(cmd,capture_output=True,text=True)
            (root/f"git_{label}.txt").write_text(proc.stdout+proc.stderr,encoding="utf-8")
            git_rows.append({"command":label,"returncode":proc.returncode,"output_lines":len((proc.stdout+proc.stderr).splitlines())})
    write_rows(root/"git_state_summary.tsv",git_rows,["command","returncode","output_lines"])
    # Text scan for developer-specific absolute paths and unresolved shell variables.
    path_scan=[]
    tokens=("/home/tokushimaneuro02","/mnt/intelssd/rnatr_project","/media/tokushimaneuro02/T9","${PROJECT_ROOT}","$PROJECT_ROOT","${HOME}")
    for p in sorted((root/"files").rglob("*")):
        if not p.is_file() or p.stat().st_size>5_000_000: continue
        try: text=p.read_text(encoding="utf-8")
        except UnicodeDecodeError: continue
        for lineno,line in enumerate(text.splitlines(),1):
            for token in tokens:
                if token in line: path_scan.append({"file":p.relative_to(root).as_posix(),"line":lineno,"token":token,"text":line[:500]})
    write_rows(root/"developer_path_and_variable_scan.tsv",path_scan,["file","line","token","text"])
    # Read-only Downloads inventory for later checksum-backed cleanup; no move or deletion occurs here.
    downloads_rows=[]
    for p in sorted(x for x in paths.downloads.iterdir() if x.is_file() and (x.name.lower().startswith("rnatr") or x.name.startswith("RNA_TR_Scout") or x.name.startswith("RNA-TR-Scout"))):
        size=p.stat().st_size
        digest=sha256_file(p) if size<=100_000_000 else "."
        mtime=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).replace(microsecond=0).isoformat()
        downloads_rows.append({"path":str(p),"bytes":size,"sha256":digest,"mtime_utc":mtime,"classification":"UNCLASSIFIED_DO_NOT_DELETE"})
    write_rows(root/"downloads_rnatr_inventory.tsv",downloads_rows,["path","bytes","sha256","mtime_utc","classification"])

    # Gate/open-question snapshots and audit scope.
    gates=read_dict_rows(paths.gates_v031)
    write_rows(root/"blocking_release_gates_snapshot.tsv",[r for r in gates if r.get("blocking_for_v1")=="true"],list(gates[0].keys()))
    scope_rows=[
        {"domain":"SSOT","required":"true"},{"domain":"active code/path","required":"true"},{"domain":"schema/frozen contracts","required":"true"},
        {"domain":"performance gates","required":"true"},{"domain":"validation/restart/artifact contracts","required":"true"},
        {"domain":"biology roadmap","required":"true"},{"domain":"release-readiness roadmap","required":"true"},{"domain":"script lifecycle","required":"true"},
        {"domain":"runtime-generated artifacts","required":"true"},{"domain":"installer/setup","required":"true"},
        {"domain":"authoritative original artifacts reread","required":"true"},{"domain":"Core Freeze Packet specification","required":"true"},
        {"domain":"golden regression specification","required":"true"},{"domain":"project-wide canonical docs layout","required":"true"},
        {"domain":"Downloads retention and cleanup plan","required":"true"},
    ]
    write_rows(root/"architecture_audit_required_domains.tsv",scope_rows,["domain","required"])
    write_rows(root/"authoritative_original_policy.tsv",[
        {"policy":"conversation_or_memory_is_not_authoritative","required":"true","action":"Use exact originals or leave conclusion unresolved"},
        {"policy":"missing_or_size_capped_original","required":"true","action":"Request upload or direct collection before final decision"},
        {"policy":"freeze_packet_and_regression_from_reread_originals","required":"true","action":"Bind versions, paths, manifests, and SHA-256"},
    ],["policy","required","action"])
    write_rows(root/"collection_inventory.tsv",inventory,["category","source_path","bytes","sha256","copied","reason"])
    copied=sum(r["copied"]=="true" for r in inventory); skipped=len(inventory)-copied
    return {"active_pipeline_rows":len(active_rows),"runtime_frozen_scripts":len(runtime_rows),"lifecycle_files":len(lifecycle),
            "collection_inventory_rows":len(inventory),"collection_copied":copied,"collection_skipped":skipped,"path_scan_hits":len(path_scan),
            "downloads_inventory_rows":len(downloads_rows),"downloads_cleanup":"DEFERRED_UNTIL_CANONICALIZATION"}


def postcheck(paths: Paths, before_pipeline_sha: str, before_schema_sha: str) -> dict[str,Any]:
    run_checked([sys.executable,str(paths.ssot_cli),"--project-root",str(paths.project_root),"rebuild"],paths.update_qc_root/"logs/ssot_rebuild.log")
    run_checked([sys.executable,str(paths.ssot_cli),"--project-root",str(paths.project_root),"validate"],paths.update_qc_root/"logs/ssot_validate_after.log")
    if sha256_file(paths.core_schema)!=before_schema_sha: raise UpdateError("core schema changed")
    after_pipeline=sha256_file(paths.ssot_exports/"current_pipeline.tsv")
    if after_pipeline!=before_pipeline_sha: raise UpdateError("current_pipeline changed during Stage15E registration")
    require_sha(paths.gates_v030,EXPECTED_GATES_V030_SHA256)
    con=sqlite3.connect(paths.ssot_db)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or list(con.execute("PRAGMA foreign_key_check")): raise UpdateError("post-update SSOT integrity failure")
        checks={
            "stage15e_run":con.execute("SELECT count(*) FROM runs WHERE run_id=? AND status='PASS_WITH_SCOPE_AMENDMENT'",(STAGE15E_RUN,)).fetchone()[0],
            "stage15e_stage":con.execute("SELECT count(*) FROM stage_definitions WHERE stage_key='15E_RELEASE_SCALE_DETERMINISM_RESTART' AND implementation_status='IMPLEMENTED_WITH_SCOPE_AMENDMENT'").fetchone()[0],
            "stage15e_impl":con.execute("SELECT count(*) FROM implementations WHERE implementation_id='impl_stage15e_combined_determinism_restart_v0_1_0' AND lifecycle_status='VALIDATION_ONLY_FROZEN_EVIDENCE'").fetchone()[0],
            "stage15e_contract":con.execute("SELECT count(*) FROM algorithm_contracts WHERE component_key='stage15e_release_scale_determinism_restart_v0_1_0' AND status='ACTIVE'").fetchone()[0],
            "determinism_closed":con.execute("SELECT count(*) FROM open_questions WHERE question_key='RELEASE_SCALE_DETERMINISM' AND status='CLOSED' AND blocking=0").fetchone()[0],
            "restart_closed":con.execute("SELECT count(*) FROM open_questions WHERE question_key='FULLSCALE_RESTART_RESUME' AND status='CLOSED' AND blocking=0").fetchone()[0],
            "integration_closed":con.execute("SELECT count(*) FROM open_questions WHERE question_key='GENERAL_CALLER_PRODUCTION_INTEGRATION' AND status='CLOSED' AND blocking=0").fetchone()[0],
            "prerc_open":con.execute("SELECT count(*) FROM open_questions WHERE question_key='PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT' AND status='OPEN' AND blocking=1").fetchone()[0],
            "promotion_open":con.execute("SELECT count(*) FROM open_questions WHERE question_key='ACTIVE_PATH_PROMOTION' AND status='OPEN' AND blocking=1").fetchone()[0],
            "clean_install_open":con.execute("SELECT count(*) FROM open_questions WHERE question_key='CLEAN_INSTALL_INTERNAL_BETA' AND status='OPEN' AND blocking=1").fetchone()[0],
            "freeze_packet_open":con.execute("SELECT count(*) FROM open_questions WHERE question_key='CORE_FREEZE_PACKET' AND status='OPEN' AND blocking=1").fetchone()[0],
            "golden_regression_open":con.execute("SELECT count(*) FROM open_questions WHERE question_key='GOLDEN_REGRESSION_SUITE' AND status='OPEN' AND blocking=1").fetchone()[0],
            "docs_canonicalization_open":con.execute("SELECT count(*) FROM open_questions WHERE question_key='PROJECT_WIDE_DOCS_CANONICALIZATION' AND status='OPEN' AND blocking=1").fetchone()[0],
            "downloads_cleanup_open":con.execute("SELECT count(*) FROM open_questions WHERE question_key='DOWNLOADS_ARTIFACT_CLEANUP' AND status='OPEN' AND blocking=0").fetchone()[0],
            "freeze_governance_contract":con.execute("SELECT count(*) FROM algorithm_contracts WHERE component_key='core_freeze_preservation_governance_v0_1_0' AND status='ACTIVE'").fetchone()[0],
            "pipeline_stage15_active":con.execute("SELECT count(*) FROM current_pipeline WHERE stage_key LIKE '15%'").fetchone()[0],
        }
    finally: con.close()
    for key in ("stage15e_run","stage15e_stage","stage15e_impl","stage15e_contract","determinism_closed","restart_closed","integration_closed","prerc_open","promotion_open","clean_install_open","freeze_packet_open","golden_regression_open","docs_canonicalization_open","downloads_cleanup_open","freeze_governance_contract"):
        if checks[key]!=1: raise UpdateError(f"postcheck failed {key}: {checks[key]}")
    if checks["pipeline_stage15_active"]!=0: raise UpdateError("Stage15 unexpectedly promoted into current_pipeline")
    gates=parse_release_gates(paths.gates_v031.read_text(encoding="utf-8")); by={r["gate_id"]:r for r in gates}
    if by["G07"]["status"]!="PASS_WITH_SCOPE_AMENDMENT" or by["G28"]["status"]!="OPEN_PLANNED" or any(by[g]["status"]!="OPEN_PLANNED" for g in ("G32","G33","G34")): raise UpdateError("release gate postcheck failed")
    return {"ssot_cli_sha256_after":sha256_file(paths.ssot_cli),"ssot_db_sha256_after":sha256_file(paths.ssot_db),
            "current_pipeline_sha256_after":after_pipeline,"active_pipeline_byte_identical":str(after_pipeline==before_pipeline_sha).lower(),
            "core_schema_byte_identical":str(sha256_file(paths.core_schema)==before_schema_sha).lower(),**checks}


def run_execute(paths: Paths, confirm: str) -> int:
    if confirm!=CONFIRM_TOKEN: raise UpdateError(f"--confirm-update must exactly equal {CONFIRM_TOKEN}")
    preflight=verify_preflight_binding(paths)
    verify_baseline(paths); verify_output_bundle(paths); verify_evidence_hashes(paths); verify_stage15e_semantics(paths)
    updater_sha=sha256_file(Path(__file__).resolve()); before_pipeline=sha256_file(paths.ssot_exports/"current_pipeline.tsv"); before_schema=sha256_file(paths.core_schema)
    paths.ssot_backups.mkdir(parents=True,exist_ok=True)
    backup=paths.ssot_backups/("stage15f_stage15e_registration_v0.1.1_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    paths.lock_path.parent.mkdir(parents=True,exist_ok=True); lock=paths.lock_path.open("a+"); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    preexisting=backup_state(paths,backup); mutation=True
    try:
        harness=output_bundle_member_bytes(paths,"/rnatr_stage15e_run_combined_determinism_restart_v010.py")
        atomic_write(paths.harness_install,harness); atomic_write(paths.updater_install,Path(__file__).read_bytes())
        atomic_write(paths.doc_install,REGISTRATION_DOC_TEXT.encode()); atomic_write(paths.audit_install,PRO_AUDIT_TSV_TEXT.encode())
        atomic_write(paths.governance_install,FREEZE_GOVERNANCE_DOC_TEXT.encode())
        atomic_write(paths.binding_install,build_binding_json(updater_sha)); atomic_write(paths.gates_v031,RELEASE_GATES_V031_TEXT.encode())
        source=paths.ssot_cli.read_text(encoding="utf-8")
        if PATCH_MARKER in source: raise UpdateError("Stage15E registration marker already present during execute")
        insertion=build_source_insertion(paths,updater_sha); patched=source.replace(PATCH_ANCHOR,"\n\n"+insertion+PATCH_ANCHOR,1)
        compile(patched,str(paths.ssot_cli),"exec"); atomic_write(paths.ssot_cli,patched.encode(),mode=0o755)
        paths.update_qc_root.mkdir(parents=True,exist_ok=False); paths.update_meta_root.mkdir(parents=True,exist_ok=False)
        result=postcheck(paths,before_pipeline,before_schema)
        prerc=collect_prerc_inputs(paths)
        qc_rows=[
            ("version",VERSION),("stage15e_output_bundle_sha256",EXPECTED_STAGE15E_OUTPUT_BUNDLE_SHA256),
            ("stage15e_registration","PASS"),("release_scale_determinism","PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE"),
            ("fullscale_restart_resume","PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE"),("second_resume_noop","PASS"),
            ("release_gate_G07","PASS_WITH_SCOPE_AMENDMENT"),("release_gate_G28","OPEN_PLANNED"),
            ("current_pipeline_modified","false"),("core_schema_modified","false"),("clean_runtime_benchmark_overwritten","false"),
            ("core_freeze_packet","OPEN_REQUIRED"),("golden_regression_suite","OPEN_REQUIRED"),("project_wide_docs_canonicalization","OPEN_REQUIRED"),
            ("authoritative_originals_policy","REQUIRED"),("pre_release_candidate_input_collection","PASS"),*[(k,v) for k,v in prerc.items()],
            ("audit_status","PASS"),("next_gate","PRO_REVIEW_PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT"),
        ]
        write_metrics(paths.update_qc_root/"stage15f_stage15e_registration.qc.tsv",qc_rows)
        (paths.update_meta_root/"registration_contract.json").write_text(json.dumps({"version":VERSION,"confirm_token":CONFIRM_TOKEN,"backup":str(backup),"preflight":preflight,"postcheck":result,"prerc":prerc},indent=2,sort_keys=True)+"\n",encoding="utf-8")
        parent=Path(tempfile.mkdtemp(prefix="rnatr_stage15f_output_")); root=parent/"rnatr_stage15f_stage15e_registration_prerc_input_v0.1.1"
        for d in ("qc","metadata","docs","validation","script","ssot","prerc_input"): (root/d).mkdir(parents=True,exist_ok=True)
        shutil.copytree(paths.update_qc_root,root/"qc",dirs_exist_ok=True); shutil.copytree(paths.update_meta_root,root/"metadata",dirs_exist_ok=True)
        shutil.copy2(paths.doc_install,root/"docs"/paths.doc_install.name); shutil.copy2(paths.audit_install,root/"docs"/paths.audit_install.name)
        shutil.copy2(paths.governance_install,root/"docs"/paths.governance_install.name)
        shutil.copy2(paths.gates_v031,root/"validation"/paths.gates_v031.name); shutil.copy2(paths.updater_install,root/"script"/paths.updater_install.name); shutil.copy2(paths.harness_install,root/"script"/paths.harness_install.name)
        for p in (paths.ssot_cli,paths.ssot_db,paths.ssot_summary):
            if p.exists(): shutil.copy2(p,root/"ssot"/p.name)
        for p in sorted(paths.ssot_exports.glob("current_*.tsv")): shutil.copy2(p,root/"ssot"/p.name)
        shutil.copytree(paths.prerc_root,root/"prerc_input",dirs_exist_ok=True)
        digest=make_bundle(root,paths.success_bundle); shutil.rmtree(parent,ignore_errors=True)
        print("===== RNA-TR-Scout Stage15F Stage15E registration final =====")
        for key,value in qc_rows: print(f"{key}\t{value}")
        print(f"SSOT_CLI\t{paths.ssot_cli}"); print(f"SSOT_DB\t{paths.ssot_db}"); print(f"BACKUP\t{backup}")
        print(f"OUTPUT_BUNDLE\t{paths.success_bundle}"); print(f"OUTPUT_BUNDLE_SHA256\t{digest}")
        return 0
    except Exception:
        if mutation: restore_state(paths,backup,preexisting)
        raise
    finally:
        try: fcntl.flock(lock,fcntl.LOCK_UN); lock.close()
        except Exception: pass


def self_test() -> int:
    compile(Path(__file__).read_text(encoding="utf-8"),str(Path(__file__)),"exec")
    parse_release_gates(RELEASE_GATES_V031_TEXT)
    if sha256_bytes(PRO_AUDIT_TSV_TEXT.encode())!=EXPECTED_PRO_AUDIT_SHA256: raise UpdateError("Pro audit self-test hash mismatch")
    test_paths=Paths(Path("/synthetic/project"),Path("/synthetic/downloads"))
    insertion=build_source_insertion(test_paths,"a"*64,evidence={},sources={})
    compile("def _populate(conn):\n"+insertion,"<stage15f-insertion>","exec")
    con=sqlite3.connect(":memory:")
    con.executescript("""
    CREATE TABLE source_documents(source_id INTEGER PRIMARY KEY AUTOINCREMENT,source_type TEXT NOT NULL,path TEXT NOT NULL UNIQUE,sha256 TEXT,bytes INTEGER,mtime_utc TEXT,content_status TEXT NOT NULL,ingested_at TEXT NOT NULL);
    CREATE TABLE datasets(dataset_id TEXT PRIMARY KEY);
    CREATE TABLE runs(run_id TEXT PRIMARY KEY,dataset_id TEXT,parent_run_id TEXT,run_role TEXT,pipeline_version TEXT,status TEXT NOT NULL,started_at TEXT,ended_at TEXT,root_path TEXT,notes TEXT);
    CREATE TABLE stage_definitions(stage_key TEXT PRIMARY KEY,stage_order REAL,name TEXT NOT NULL,purpose TEXT,category TEXT,implementation_status TEXT,notes TEXT);
    CREATE TABLE implementations(implementation_id TEXT PRIMARY KEY,stage_key TEXT NOT NULL,version TEXT,script_path TEXT,script_sha256 TEXT,validator_path TEXT,validator_sha256 TEXT,package_version TEXT,parameters_json TEXT,lifecycle_status TEXT NOT NULL,supersedes_implementation_id TEXT,rationale TEXT,evidence_path TEXT,effective_at TEXT NOT NULL);
    CREATE TABLE run_stages(run_stage_id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,stage_key TEXT NOT NULL,implementation_id TEXT,attempt_tag TEXT NOT NULL,status TEXT NOT NULL,command_text TEXT,qc_path TEXT,qc_status TEXT,started_at TEXT,ended_at TEXT,notes TEXT,UNIQUE(run_id,stage_key,attempt_tag));
    CREATE TABLE metrics(metric_id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,stage_key TEXT,metric_name TEXT NOT NULL,value_text TEXT NOT NULL,value_num REAL,unit TEXT,denominator_num REAL,source_path TEXT NOT NULL,metric_status TEXT NOT NULL,recorded_at TEXT NOT NULL,UNIQUE(run_id,stage_key,metric_name,source_path));
    CREATE TABLE decisions(decision_id TEXT PRIMARY KEY,decision_key TEXT NOT NULL,category TEXT,title TEXT NOT NULL,statement TEXT NOT NULL,status TEXT NOT NULL,confidence TEXT,effective_at TEXT NOT NULL,supersedes_decision_id TEXT,rationale TEXT,evidence_path TEXT);
    CREATE UNIQUE INDEX one_active_decision_per_key ON decisions(decision_key) WHERE status='ACTIVE';
    CREATE TABLE interpretations(interpretation_id TEXT PRIMARY KEY,interpretation_key TEXT NOT NULL,fact_statement TEXT NOT NULL,interpretation TEXT NOT NULL,do_not_interpret_as TEXT,status TEXT NOT NULL,confidence TEXT,effective_at TEXT NOT NULL,supersedes_interpretation_id TEXT,evidence_path TEXT,evidence_metrics_json TEXT);
    CREATE UNIQUE INDEX one_active_interpretation_per_key ON interpretations(interpretation_key) WHERE status='ACTIVE';
    CREATE TABLE algorithm_contracts(contract_id TEXT PRIMARY KEY,component_key TEXT NOT NULL,component_name TEXT NOT NULL,implementation_state TEXT NOT NULL,contract_statement TEXT NOT NULL,active_implementation_id TEXT,evidence_path TEXT,effective_at TEXT NOT NULL,status TEXT NOT NULL);
    CREATE UNIQUE INDEX one_active_contract_per_component ON algorithm_contracts(component_key) WHERE status='ACTIVE';
    CREATE TABLE limitations(limitation_key TEXT PRIMARY KEY,statement TEXT NOT NULL,severity TEXT,status TEXT NOT NULL,mitigation TEXT,evidence_path TEXT,effective_at TEXT NOT NULL);
    CREATE TABLE open_questions(question_key TEXT PRIMARY KEY,question TEXT NOT NULL,priority TEXT,status TEXT NOT NULL,blocking INTEGER NOT NULL,next_action TEXT,evidence_path TEXT,effective_at TEXT NOT NULL);
    INSERT INTO datasets(dataset_id) VALUES('dataset_test');
    INSERT INTO runs(run_id,dataset_id,status,notes) VALUES('ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1','dataset_test','PASS_WITH_DOCUMENTED_TOLERANCE','baseline');
    INSERT INTO stage_definitions(stage_key,name) VALUES('15C_FULL_EMPIRICAL_BAM_TO_FINAL','full'),('15A_BAM_TO_FINAL_PERFORMANCE','perf'),('15A_RESTART_RESUME_VALIDATION','restart'),('15A_DETERMINISTIC_SCALING','scale');
    INSERT INTO implementations(implementation_id,stage_key,lifecycle_status,effective_at) VALUES('impl_stage15c_full_runner_v0_1_6','15C_FULL_EMPIRICAL_BAM_TO_FINAL','PROVISIONAL','2026-08-10');
    INSERT INTO open_questions(question_key,question,status,blocking,effective_at) VALUES('RELEASE_SCALE_DETERMINISM','x','OPEN',1,'x'),('FULLSCALE_RESTART_RESUME','x','OPEN',1,'x'),('GENERAL_CALLER_PRODUCTION_INTEGRATION','x','OPEN',1,'x');
    """)
    ns={"hashlib":hashlib,"json":json,"Path":Path}
    exec("def _populate(conn):\n"+insertion,ns); ns["_populate"](con)
    checks=(con.execute("SELECT count(*) FROM runs WHERE run_id=?",(STAGE15E_RUN,)).fetchone()[0],
            con.execute("SELECT status FROM open_questions WHERE question_key='RELEASE_SCALE_DETERMINISM'").fetchone()[0],
            con.execute("SELECT count(*) FROM algorithm_contracts WHERE component_key='stage15e_release_scale_determinism_restart_v0_1_0'").fetchone()[0],
            con.execute("SELECT count(*) FROM open_questions WHERE question_key='CORE_FREEZE_PACKET' AND status='OPEN' AND blocking=1").fetchone()[0],
            con.execute("SELECT count(*) FROM open_questions WHERE question_key='GOLDEN_REGRESSION_SUITE' AND status='OPEN' AND blocking=1").fetchone()[0],
            con.execute("SELECT count(*) FROM open_questions WHERE question_key='PROJECT_WIDE_DOCS_CANONICALIZATION' AND status='OPEN' AND blocking=1").fetchone()[0],
            con.execute("SELECT count(*) FROM algorithm_contracts WHERE component_key='core_freeze_preservation_governance_v0_1_0'").fetchone()[0])
    con.close()
    if checks!=(1,"CLOSED",1,1,1,1,1): raise UpdateError(f"synthetic insertion self-test failed: {checks}")
    print("SELF_TEST\tPASS"); print(f"version\t{VERSION}"); print(f"release_gates_v031_sha256\t{sha256_bytes(RELEASE_GATES_V031_TEXT.encode())}")
    return 0


def failure_bundle(paths: Paths, exc: BaseException) -> None:
    try:
        parent=Path(tempfile.mkdtemp(prefix="rnatr_stage15f_failure_")); root=parent/"rnatr_stage15f_stage15e_registration_prerc_input_v0.1.1_failure"; root.mkdir()
        (root/"failure.txt").write_text(f"version\t{VERSION}\nexception_type\t{type(exc).__name__}\nexception\t{exc}\n\n{traceback.format_exc()}",encoding="utf-8")
        if Path(__file__).is_file(): shutil.copy2(Path(__file__).resolve(),root/Path(__file__).name)
        digest=make_bundle(root,paths.failure_bundle); shutil.rmtree(parent,ignore_errors=True)
        print(f"FAILURE_BUNDLE\t{paths.failure_bundle}",file=sys.stderr); print(f"FAILURE_BUNDLE_SHA256\t{digest}",file=sys.stderr)
    except Exception as bundle_exc: print(f"WARNING: could not create failure bundle: {bundle_exc}",file=sys.stderr)


def main() -> int:
    parser=argparse.ArgumentParser(description="Register Stage15E determinism/restart evidence in SSOT and collect exact PRE_RELEASE_CANDIDATE architecture inputs")
    modes=parser.add_mutually_exclusive_group(required=True); modes.add_argument("--self-test",action="store_true"); modes.add_argument("--preflight",action="store_true"); modes.add_argument("--execute",action="store_true")
    parser.add_argument("--confirm-update",default=""); args=parser.parse_args(); paths=default_paths()
    if args.self_test: return self_test()
    if args.preflight: return run_preflight(paths)
    return run_execute(paths,args.confirm_update)

if __name__=="__main__":
    try: raise SystemExit(main())
    except SystemExit: raise
    except Exception as exc:
        failure_bundle(default_paths(),exc); print(f"ERROR: {type(exc).__name__}: {exc}",file=sys.stderr); raise
