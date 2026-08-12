# RNA-TR-Scout Architecture Consistency Audit — post-250k v0.1.1

Date: 2026-08-09  
Audit status: **REVIEW**  
Mutation policy: SSOT, active pipeline, core schema, and prior result artifacts were not modified.

## 1. 250k scaling result

- Deterministic 250k scaling: `PASS`
- Replicate A/B final package raw equality: `true`
- Replicate A/B final package logical equality: `true`
- Caller hash-seed logical reproducibility: `true`
- Nested original-100k package exact parity: `true`
- Conservative 250k BAM-to-final time: `169.0068411460379` seconds
- Linear 5.31M projection: `59.858798` minutes
- Margin to 60-minute ceiling: `0.141202` minutes
- Per-read normalized 100k→250k scaling factor: `1.027965`
- Maximum observed stage RSS: `13.283` GiB
- Peak temporary+output footprint: `6.780` GB

The linear projection technically passes 60 minutes, but the margin is too small to close G06. Deterministic 500k remains mandatory.

## 2. Architecture findings

| ID | Domain | Status | Finding | Required action |
|---|---|---|---|---|
| AC001 | SSOT_ACTIVE_PIPELINE | PASS | The live current_pipeline remains the 11-stage legacy active path; no Stage15A candidate is active. | Keep active switch prohibited until later promotion gate. |
| AC002 | SCHEMA_FREEZE | PASS | Frozen component guards pass; replicate A/B final packages are raw and logically identical, and the nested 100k package is exact. | Retain evidence schema v0.4.2 as immutable core source of truth. |
| AC003 | DETERMINISM | PASS | Two 250k hash-seed replicates have exact final-package and caller logical reproducibility. | Carry the same determinism checks into 500k. |
| AC004 | CHECKPOINT_REPRODUCIBILITY | PASS | A replacement role×shard logical checkpoint comparison passes. | Supersede the unsupported v0.1.2 checkpoint_manifest_reproducibility=true claim with this amendment; do not alter original QC. |
| AC005 | PROVENANCE_RUN_ID | REVIEW | The external run is 250k, but internal component paths and IDs still use the 100k compatibility alias. | Document the compatibility shim now; remove or encapsulate it before release candidate. |
| AC006 | PERFORMANCE_GATE | REVIEW | The 250k linear projection is 59.858798 min with only 0.141202 min margin to the 60-min ceiling. | Keep G06 OPEN and run deterministic 500k; full 5.31M remains prohibited. |
| AC007 | RESTART_MEMORY_ARTIFACT | OPEN | 100k selective resume is validated, but 250k selective resume, arbitrary upstream recovery, concurrent-memory semantics, and full-scale restart remain unvalidated. | Keep G07 OPEN; add a larger-scale resume/memory audit before full run. |
| AC008 | BIOLOGY_ROADMAP | PASS | Biology-ready sidecars and interpretation hierarchy are registered as DESIGNED_NOT_IMPLEMENTED; G20-G23 remain OPEN. | Do not start biology implementation until performance architecture stabilizes and the pre-biology audit runs. |
| AC009 | SCRIPT_LIFECYCLE | REVIEW | 3 Stage15A scripts are not classified by active pipeline, SSOT lifecycle, or known support/obsolete patterns. | Retain historical scripts for provenance, but maintain an explicit lifecycle ledger and never infer activity from file presence. |
| AC010 | PLANNED_ITEMS | OPEN | 500k scaling, empirical full-scale runtime, broader restart/memory validation, 30-min optimization, active promotion, and G20-G23 biology outputs remain planned and not implemented. | Register this audit and 250k evidence, then proceed only to deterministic 500k. |

## 3. Checkpoint amendment

The original v0.1.2 function named `compare_checkpoint_manifests()` did **not** compare replicate A against replicate B. It validated each replicate independently and returned `True`. Therefore the original field:

```text
checkpoint_manifest_reproducibility=true
```

was not supported by the implementation and must be superseded, not silently rewritten.

Replacement audit result:

```text
checkpoint_logical_reproducibility=true
original_checker_sufficient=false
```

Compressed TSV checkpoint artifacts are compared by decompressed bytes; runtime materialization QC is compared after excluding timing and stage-version fields; other deterministic artifacts are compared by raw bytes.

## 4. Stage scaling profile

| Stage | Conservative 250k seconds | 100k→250k ratio |
|---|---:|---:|
| 15AS0_partition_inputs | 15.487 | 2.6237467975442783 |
| 15AS1C_extract_candidate_fastq | 0.558 | . |
| 15AS1_11b | 8.814 | 2.24037029274407 |
| 15AS2_11d3 | 14.601 | 2.316291378351041 |
| 15AS3_fast_shared_catalog_motif_jobs | 5.299 | 1.600880971402605 |
| 15AS4_5_caller_materializer_pipeline | 82.247 | 2.6902091925819964 |
| 15AS6_parallel_global_gzip | 1.451 | 2.45174711459296 |
| 15AS6_parallel_global_merge | 3.711 | 2.626926075693769 |
| 15AS7_concurrent_frozen_validators | 37.209 | 2.713183251747486 |
| 15AS8_atomic_publication | 0.003 | 0.729957788983227 |

## 5. Cross-domain consistency

- Active pipeline rows: `11`
- Active pipeline canonical SHA-256: `b044fa71b7a0541eab3c5fcf41a2448ecc59298a4bcf313ee0cbc154277345eb`
- Stage15A in current_pipeline: `false`
- Core schema/frozen component drift: `false`
- Historical runner SSOT guards: `excluded from frozen-component drift; current SSOT source/DB are independently SHA-pinned and validated`
- Biology sidecars implemented: `false`
- Interpretation layer implemented: `false`
- G06: `OPEN`
- G07: `OPEN`
- G20-G23: `OPEN`
- Unclassified Stage15A scripts: `3`
- Explicit obsolete historical scripts: `3`

## 6. Gate decision

Do **not** run the full 5.31M sample.

Next sequence:

```text
post-250k architecture audit
→ register 250k result + checkpoint amendment + audit in SSOT
→ deterministic 500k BAM-input scaling with corrected checkpoint checker
→ reassess G06/G07
```

Biology-layer implementation remains paused until the designated pre-biology Architecture consistency audit.
