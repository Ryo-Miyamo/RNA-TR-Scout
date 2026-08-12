# RNA-TR-Scout Core Freeze Packet v0.1.1 — final owner-review candidate

## Status

**OWNER_REVIEW_REQUIRED / NOT_YET_REGISTERED**

Candidate final decision after owner approval, guarded installation, SSOT registration and
post-registration verification:

`LOCAL_CORE_FREEZE_V0.1.0_ACCEPTED_WITH_SCOPE`

This packet freezes the validated scientific/public Core contract so biology-sidecar work
may begin. It is not a claim that public GitHub release v0.5.0, clean-machine installation,
cross-hardware reproducibility, or biology-ready interpretation is complete.

## 1. Active Core and exact current implementation

The sole active production path is:

`CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL`

| Role | Exact current implementation | SHA-256 |
|---|---|---|
| Public entry | `scripts/rnatr_core_production_entry_v0.1.0.py` | `c6cf8298fb2dfb52b6bfbd7eda8d701356823644668d6d952abac09cc06358c4` |
| Sharded orchestrator | `scripts/rnatr_core_generic_sharded_v0.1.2.py` | `76ccd6a41f95bd0d2bbf1bf0fba1b26e4232e8f526fae6ec86d3b3f06197784b` |
| Generic unit | `scripts/rnatr_core_generic_unit_v0.1.1.py` | `cff4bfc874cb07db6a98dfb679866a4f75a0eaa10c7c16c3bf3698fd5abf79f5` |
| Native caller | `rnatr_general_repeat_caller_ref_v0.4.1.py` | `d5a2e0545afa5d97026c3a6ac0be6bc355e87f4c130bc512b0b3bf9a5bf32351` |
| Materializer | `rnatr_materialize_native_v041_to_evidence_v042_v0.1.2.py` | `18a67ef312e74257549570ae81a6cca364055240f519d29dc7664e2ea1c429ea` |
| Evidence schema | v0.4.2 `rnatr_v04_table_schema.json` | `c0509a0669344dba0b07cd1bb9e71f2aeb01e0196df47ec9178f1d2464b515f1` |
| Package validator | `rnatr_v042_validate_package.py` | `45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e` |
| Portable result-manifest contract | v0.1.0 | `533c711906e57f66998327a54db1c33cae81b484cdcf6509cc03832a11d6c737` |
| Active resource manifest | v0.1.0 | `4418837acb0aa744fef0810d6db0260b6c534789a5e7e92ef123f9f79e848a2e` |
| Golden runner | v0.1.4 | `e4be1b3cd24a2ea42fde0c6434888f725e6b65fde290f1c02e9f91ff2186203c` |

The exact current implementation remains recorded for reproducibility. The long-term Freeze
contract below is narrower than these implementation details.

## 2. Frozen scientific/public contract

The following are frozen:

- repeat-measurement semantics, including repeat length, purity, LPS, segments and
  interruptions;
- exact, lower-bound/censored, context-limited, no-call, not-attempted, not-evaluated and
  missing-state distinctions;
- the five Core tables:
  `general_repeat_calls`, `read_evidence`, `repeat_events`, `repeat_segments`,
  `repeat_interruptions`;
- schema v0.4.2 required fields, identities, cross-table references and validator acceptance;
- stable logical resources and portable result-manifest/API contract;
- deterministic scientific output under the declared comparison policy;
- SHA-bound restart/resume, corruption rejection, completed-work reuse, second-resume no-op,
  validation-before-publication and atomic publication;
- canonical golden protection of the frozen scientific output.

A biology layer must join to the immutable Core result and must not rewrite the five Core
tables.

## 3. Identity and provenance

- read identity across packages: `(core_result_manifest_sha256, read_id)`;
- locus identity: `(catalog_logical_id, catalog_sha256, target_source, target_region_id, locus_id)`;
- evidence/event/call/interruption identity across packages:
  `(core_result_manifest_sha256, Core ID)`;
- `read_id` is a technical-read identity, not automatically an independent biological
  molecule;
- `run_id` and `sample_id` remain explicit provenance fields;
- developer-machine paths belong only in local bindings or reproducibility records, not in
  the portable public contract.

## 4. Coordinates, strand and motif semantics

- genomic coordinates are 0-based, end-exclusive;
- raw-read coordinates are 0-based, end-exclusive in original FASTQ orientation;
- reverse-strand alignment coordinates are converted back to original-read orientation;
- CIGAR hard-clip offsets are retained where required;
- splice `N` creates separated genomic alignment blocks;
- secondary records without BAM sequence are reconstructed from CIGAR rather than treated
  as zero-length;
- canonical motif is the lexicographically smallest rotation across the motif and its reverse
  complement; oriented motif remains separately available.

## 5. Missingness and observation-state semantics

`.` is the schema missing value. The contract does not collapse the following into one
state or into biological absence:

- missing;
- not measured or not attempted;
- not evaluated;
- not reached/not observable;
- proximity-only assignment;
- no-call;
- censored/lower-bound;
- context-limited;
- no RNA coverage;
- covered without an outlier signal.

## 6. Current validated scientific profile

The current validated profile is **ONT cDNA**, using:

- mapping-complete BAM;
- corresponding read-coherent source FASTQ;
- the current minimap2 splice mapping baseline upstream of Core timing;
- GRCh38 and the exact SHA-bound resources in
  `config/core_runtime/v0.1.0/resource_manifest.json`;
- current TRExplorer/STRchive catalog serialization;
- plain TSV plus deterministic TSV.gz as the validated reference serialization.

These are current-profile facts, not universal physical-input or storage constraints.
Future ONT direct RNA, PacBio Iso-Seq/Kinnex, alternate assembly/catalog, storage and output
adapters remain post-Freeze work requiring the applicable parity, validator and calibration
gates.

## 7. Candidate multiplicity and reverse traceability

Full-scale technical evidence contains:

- input reads: 5,312,696;
- candidate reads: 4,212,263;
- candidate-assignment rows: 20,656,258;
- assignments per candidate read: approximately 4.90.

Stage15R reconstructed 733/733 selected assignment-to-evidence chains across 57
representative reads with zero unresolved reverse-trace failures. The preserved logical
trace is:

`read_id -> assignment -> basis/geometry -> projection/window -> motif/caller evidence`

Candidate counts are technical assignment counts, not independent biological repeat-event
counts. Secondary-alignment confidence, alias/overlap, padding/proximity, molecule
independence and biological prioritization are deferred to post-Freeze biology sidecars.

Stage15R decision: `PASS_WITH_SCOPE_BIOLOGY_DEFERRED`.

## 8. Future-extensibility audit

| Boundary | Final classification |
|---|---|
| TARGET_SELECTION_EXTENSION_BOUNDARY | `CURRENT_PROFILE_SCOPED` |
| MULTISAMPLE_NAMESPACE_EXTENSION_BOUNDARY | `BOUNDARY_OPEN` |
| PHYSICAL_STORAGE_ABSTRACTION_BOUNDARY | `POST_FREEZE_EXTENSION` |
| READ_INSPECTION_REVERSE_TRACE_BOUNDARY | `BOUNDARY_OPEN` |
| FORCED_LOCUS_ANALYSIS_EXTENSION_BOUNDARY | `POST_FREEZE_EXTENSION` |
| REFERENCE_ASSEMBLY_CATALOG_ADAPTER_BOUNDARY | `CURRENT_PROFILE_SCOPED` |
| OUTPUT_ADAPTER_BOUNDARY | `POST_FREEZE_EXTENSION` |

No boundary is `HARD_COUPLING_REQUIRES_REMEDIATION`; no ROI, force-analysis, cohort DB,
viewer, alternate storage, alternate assembly/catalog or output-adapter implementation is
required before this local Core Freeze.

## 9. Golden regression and validation evidence

The Stage15Q canonical `full-evidence` suite passed in 337.437 seconds:

- Tier0 static/current-state contract checks: PASS;
- Tier1 semantic regression and negative fixtures: PASS;
- Tier2 fixed real-read exact five-table parity: PASS;
- Tier3 fixed 100k sharded exact parity, restart/no-op and publication recovery: PASS;
- Tier4 Stage15C/Stage15E release-scale checksum/scope verification: PASS.

The golden suite protects scientific semantics and guarantees. It does not make internal
Stage names, shard count, worker count, intermediate layout or file-versus-streaming handoff
permanent.

## 10. Performance scope

Stage15C empirical 5,312,696-read BAM-to-final runtime:

`60.041256352 min — PASS_WITH_DOCUMENTED_TOLERANCE`

The strict 60-minute benchmark was exceeded by 2.475 seconds and remained within the
first-freeze tolerance of 62 minutes. Mapping is excluded. Correctness, memory, storage,
validators and atomic publication passed.

This value must not be relabeled as a direct empirical 5.31M benchmark of generic
orchestrator v0.1.2. The 30-minute objective, stage fusion, streaming, I/O reduction,
concurrency changes and mapping acceleration remain post-Freeze Performance-lane work.

## 11. Replaceable implementation details

The following are exact current records but are not permanently frozen when applicable
scientific parity and guarantee gates pass:

- internal Stage names/numbers;
- shard and worker counts;
- partition/concurrency strategy;
- internal processing order;
- intermediate files, paths and layout;
- file handoff versus streaming;
- stage fusion and I/O reduction;
- hardware-aware scheduling.

## 12. Explicitly open scopes after local Core Freeze

The following remain open and must not be claimed complete:

- G08 real truth-bearing biological validation;
- G09 large-cohort RNA background/technical distribution;
- G12 biological-versus-technical origin classifier truth validation;
- G14 RNA repeat-length clustering;
- G20–G23 transcript/isoform, haplotype, observability, molecule-level summary, ranking and
  researcher dossier implementation;
- G25–G30 reference bootstrap, resource detection, adaptive concurrency, cross-hardware,
  clean-machine install and hardware profiles;
- public GitHub repository, full 40-character commit, immutable tag and public v0.5.0
  release;
- biology interpretation of broad candidate entry and candidate narrowing.

Git binding at this Freeze point is `NOT_YET_BOUND`.

## 13. Artifact lifecycle and cleanup

Canonical architecture, governance, contracts, Freeze and golden assets are retained under
the audited project-wide layout. Stage-local documents remain history/pointers.

No Downloads deletion is authorized by this packet. The Stage15Q rollback backup remains
until final registration, post-state rehash and rollback closure. Cleanup is a separate,
explicitly approved action after authoritative destination and checksum verification.

## 14. Exact audit/evidence binding

- Stage15Q accepted output bundle:
  `6883eeb859136d8a2e1f934064dc9554a0751e65b81f2617be61d62b8bfe8dc0`;
- Stage15R R0 bundle:
  `51fdf1c10ef67731264c4e16aae50b8f0c3beaecb779985517165903e09170dc`;
- Stage15R R1 bundle:
  `c9f9270de8d0692b74d0d70d6ec75b4cfe1e477568d1674c19625d4b261f826f`;
- Stage15R R2 Pro adjudication bundle:
  `b68e4a8d078b371b72de3870fa98dc2808195f2f048aec76d8920158448c9851`;
- Stage15S exact-original preflight bundle:
  `61b5de7db51bc1e31182724bad41e20b5f69792cc096b73d10167f785901cf62`;
- Stage15S Pro extensibility/hygiene audit bundle:
  `f868d22803d29e182eccace3989d0eb481401944b657cd2630a2e7d939e76ce3`;
- Stage15S exact-SSOT supplement bundle:
  `3c09c6f1fbe6c91c6bbb34bfd1c3d4ffc58a88a12218dae110608552725eed88`;
- exact live/snapshot pre-registration SSOT SQLite:
  `58997dc429886302dcee7553f0e09bb57d8295598c05d74b907014122f5bc1d7`;
- pre-registration Core Freeze manifest:
  `b384eee38da66c95f8c66e43792830d83491e29ce37af53fcf7e8db05852e3ae`.

The final registered packet, release-gate table, SSOT database/exports and regenerated Core
Freeze manifest will receive new exact SHA bindings during the guarded Stage15T
registration. Until that completes, this document remains a candidate.

## 15. Owner decision requested

Approve only when the owner agrees that:

1. this is a local checksummed scientific Core Freeze, not a public release claim;
2. the frozen versus replaceable boundary is correct;
3. current ONT-cDNA/GRCh38/catalog/serialization scope is accurately stated;
4. candidate multiplicity biology is correctly deferred;
5. the performance claim and open-gate list are accurate.
