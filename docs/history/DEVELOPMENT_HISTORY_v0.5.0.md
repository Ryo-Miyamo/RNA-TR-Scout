# RNA-TR-Scout development history to v0.5.0

## Status and purpose

This document is a **historical narrative and navigation aid**. It is not the Single Source of Truth, it does not redefine the scientific contract, and it is not a substitute for current release/validation records.

Use the repository in three different ways:

- **What is current now:** [`metadata/ssot/CURRENT_STATE.md`](../../metadata/ssot/CURRENT_STATE.md), the version-controlled SSOT exports under [`metadata/ssot/`](../../metadata/ssot/), and the current-contract index [`docs/contracts/CURRENT_CONTRACTS_v0.1.0.tsv`](../contracts/CURRENT_CONTRACTS_v0.1.0.tsv).
- **How to continue development:** [`DEVELOPMENT.md`](../../DEVELOPMENT.md).
- **How the project reached the v0.5.0 release line:** this document, with links back to the primary contracts, audits, validation records, and historical evidence.

The version-controlled repository history begins from the Local Core Freeze snapshot rather than reproducing every earlier development step as Git commits. The pre-Freeze record is therefore preserved mainly through checksummed documents, SSOT records, historical scripts, QC/evidence references, and Freeze artifacts.

## 1. Research problem and early design direction

RNA-TR-Scout began as a research-software effort to detect and characterize tandem-repeat sequence **as observed in long-read RNA molecules**, rather than treating RNA as a proxy for a personal DNA genotype.

Several design consequences followed early:

- genomic locus assignment and repeat measurement had to remain separate;
- splice-aware genomic alignment could assign a read to a locus, while repeat length and motif architecture had to be re-estimated from the original read sequence;
- catalog motifs were useful priors, but not immutable truth for the observed RNA molecule;
- incomplete RNA molecules required explicit lower-bound/censoring semantics rather than forced exact sizes;
- non-observation in RNA could not be equated with genomic absence;
- repeat architecture needed to remain read-level information so later transcript, haplotype, observability, and molecule-level biology could be joined without discarding the underlying evidence.

The early caller contract captures these principles and the decision to keep locus-assignment confidence separate from repeat-measurement confidence:

- [`RNA_TR_Scout_general_repeat_caller_contract_v0.1.0.md`](../design/RNA_TR_Scout_general_repeat_caller_contract_v0.1.0.md)
- [`RNA-TR-Scout_population_reference_hierarchy_20260805.md`](../design/RNA-TR-Scout_population_reference_hierarchy_20260805.md)

## 2. Separating catalogs, population context, and RNA measurement

A major architecture decision was to stop asking one reference resource to answer three different questions.

The project separated:

1. **locus/catalog definition** — coordinates, locus identity, reference/canonical motif and catalog annotations;
2. **DNA population context** — long-read allele-length/LPS distributions;
3. **RNA molecule measurement** — observed tract length, motif composition, interruptions and censoring on individual RNA reads.

TRExplorer v2 became the main GRCh38 locus/motif-prior catalog. STRchive supplied disease-focused locus information and thresholds/context where appropriate. Population context was organized around long-read DNA resources, with the All of Us PacBio HiFi validation cohort designated as the primary genome-wide distribution layer in the adopted hierarchy. Cohorts, platforms and callers were intentionally kept separate rather than silently pooled.

The governing design record is:

- [`RNA-TR-Scout_population_reference_hierarchy_20260805.md`](../design/RNA-TR-Scout_population_reference_hierarchy_20260805.md)

The compact release catalog later distributed to ordinary users is a release-engineering product of this resource work, not a replacement for the underlying provenance.

## 3. From mapped RNA reads to repeat evidence

The working pipeline evolved into a sequence of conceptually distinct responsibilities:

**mapping -> candidate assignment -> raw-read projection -> motif hypotheses -> repeat caller -> evidence materialization**

The important boundary was that a genomic candidate could be successfully assigned and projected even when the final repeat caller could not produce a complete repeat measurement. This prevented “not measured” from being silently converted into “repeat absent.”

By the Freeze line, the scientific/public Core was represented through a generic mapped-BAM plus read-coherent source-FASTQ production entry, with the portable result manifest providing stable logical access to resources and outputs. Current readers should use the active-path export rather than choose a historical Stage script by filename:

- [`metadata/ssot/exports/current_pipeline.tsv`](../../metadata/ssot/exports/current_pipeline.tsv)
- [`docs/contracts/CURRENT_CONTRACTS_v0.1.0.tsv`](../contracts/CURRENT_CONTRACTS_v0.1.0.tsv)

Historical Stage15/Stage16 scripts remain in the repository chiefly because they are part of validation and reverse-traceability evidence.

## 4. Repeat-caller semantics matured before optimization

The repeat caller was deliberately developed as a scientific reference before being treated as a performance problem.

The caller-design sequence introduced, in stages:

- error-aware cyclic repeat alignment;
- motif normalization across rotation/reverse complement and primitive/harmonic equivalents;
- raw-read boundary re-estimation rather than hard use of catalog boundaries;
- compound-repeat and interruption representation;
- distinct exact-sequence and error-aware inferred LPS concepts;
- anchored motif selection and stronger de-novo rescue;
- explicit treatment of censoring and context limits;
- deterministic tie-breaking and regression preservation.

The design/reference series documents that evolution:

- [`RNA_TR_Scout_general_repeat_caller_contract_v0.1.0.md`](../design/RNA_TR_Scout_general_repeat_caller_contract_v0.1.0.md)
- [`RNA_TR_Scout_general_repeat_caller_reference_v0.2.0.md`](../design/RNA_TR_Scout_general_repeat_caller_reference_v0.2.0.md)
- [`RNA_TR_Scout_general_repeat_caller_reference_v0.3.0.md`](../design/RNA_TR_Scout_general_repeat_caller_reference_v0.3.0.md)
- [`RNA_TR_Scout_general_repeat_caller_reference_v0.4.0.md`](../design/RNA_TR_Scout_general_repeat_caller_reference_v0.4.0.md)

The final frozen measurement reference became deterministic general caller v0.4.1, with materialization into evidence schema v0.4.2.

## 5. The five-table evidence model

The Core output was intentionally kept read/evidence centered rather than collapsed immediately to one row per locus.

The frozen scientific package consists of five linked tables:

- `read_evidence.tsv`
- `general_repeat_calls.tsv`
- `repeat_events.tsv`
- `repeat_segments.tsv`
- `repeat_interruptions.tsv`

The model preserves distinctions that became important during development:

- exact length versus lower bound/interval/context-limited observation;
- projection success versus successful repeat measurement;
- canonical/oriented motif;
- compound segments and interruptions;
- LPS concepts;
- explicit missingness rather than inferred values;
- assignment context and competing technical candidates;
- stable read/evidence/event/locus identities.

The Core Freeze contract records the identity/join/missingness/censoring semantics that were frozen:

- [`RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md`](../contracts/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md)
- [`RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md`](../core_freeze/v0.1.1/RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md)

## 6. Scaling from pilot analysis to release-scale execution

Development moved from small correctness/regression fixtures into larger equalized and nested runs, then to release-scale data. The central scaling sequence was:

**pilot/small fixtures -> 100k -> 250k -> 500k -> full 5,312,696 reads**

The scaling work was not only about runtime. Each step was used to test whether scientific output identity, validation, memory behavior and architecture remained controlled as the dataset grew.

At 500k, deterministic replicate execution supported a conservative full-scale projection near the one-hour engineering target. The subsequent full ENCODE ONT-cDNA run (`ENCSR307SHM`) processed 5,312,696 reads through the BAM-to-final timing boundary in **60.041256352 minutes**. This was registered as `PASS_WITH_DOCUMENTED_TOLERANCE`, not as a strict <=60.000-minute pass. Mapping remained a separate timing boundary.

A memory-bounded validation path was also introduced because a naïve global validation strategy did not scale safely to the full package.

The most useful historical consolidation of this phase is:

- [`RNA_TR_Scout_handover_Stage15C_full_empirical_to_determinism_restart_20260810.md`](../handover/RNA_TR_Scout_handover_Stage15C_full_empirical_to_determinism_restart_20260810.md)

The architecture was also audited during scaling rather than assumed to remain coherent:

- [`RNA_TR_Scout_Architecture_consistency_audit_post250k_v0.1.1.md`](../stage15a/RNA_TR_Scout_Architecture_consistency_audit_post250k_v0.1.1.md)

For current registered measurements and limitations, use:

- [`metadata/ssot/exports/current_results.tsv`](../../metadata/ssot/exports/current_results.tsv)
- [`metadata/ssot/exports/current_known_limitations.tsv`](../../metadata/ssot/exports/current_known_limitations.tsv)

## 7. Determinism, restart/resume, validators and golden protection

Release-scale reliability was treated as part of the scientific contract rather than merely an operational convenience.

The project added and validated:

- deterministic scientific-table output;
- SHA-bound checkpoint/restart state;
- selective restart/resume and completed-run no-op behavior;
- corruption rejection;
- validate-then-atomic-publication behavior;
- memory-bounded validation;
- fixed golden regression suites spanning multiple fixture scales;
- architecture consistency audits at major checkpoints.

The Local Core Freeze ultimately accepted release-scale determinism/restart with explicitly documented scope amendments rather than overstating what had been tested.

Current Freeze scope and the canonical golden/restart obligations are summarized by:

- [`RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md`](../contracts/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md)
- [`validation/golden/v0.1.0/`](../../validation/golden/v0.1.0/)

## 8. Candidate multiplicity and issues deliberately deferred to biology

One important development finding was that a single RNA read can generate multiple technical candidate assignments. Overlapping target definitions, secondary/alternative alignments, aliases, proximity/padding and related assignment geometry can all contribute.

The project therefore rejected the interpretation:

> candidate rows = independent biological repeat events

Candidate multiplicity became a **technical assignment count**, while biological weighting/ranking was intentionally deferred until a biology layer could incorporate transcript context, observability, haplotype/phase evidence, molecule independence and purpose-specific analysis.

Similarly, the production caller did not pretend to solve every complex repeat architecture. Candidate/projection evidence is preserved even when specialized sequence-variable/IUPAC/complex disease-region or otherwise unsupported strategies do not yield a complete automatic measurement.

The post-Freeze biology boundary is documented in:

- [`RNA_TR_Scout_Biology_sidecar_interface_contract_v0.1.0.md`](../contracts/RNA_TR_Scout_Biology_sidecar_interface_contract_v0.1.0.md)
- [`RNA_TR_Scout_Biology_ready_interpretation_output_contract_v0.1.0.md`](../contracts/RNA_TR_Scout_Biology_ready_interpretation_output_contract_v0.1.0.md)

## 9. Local Core Freeze: what became immutable, and what did not

The Local Core Freeze was deliberately separated from the later public/thesis-citable software release.

The Freeze fixed:

- deterministic repeat-measurement semantics;
- materializer semantics;
- evidence schema v0.4.2 five-table contract;
- stable identity/join and missingness/censoring/context-limit semantics;
- portable result-manifest/resource interfaces;
- validators and restart/resume/corruption/publication guarantees;
- canonical golden-protected scientific output;
- the validated ONT-cDNA profile and exact resource bindings.

It intentionally **did not** permanently freeze:

- internal Stage names;
- shard/worker counts;
- internal execution order;
- intermediate paths;
- file handoff versus streaming;
- other implementation details that may change under applicable scientific-parity and guarantee gates.

This distinction is the foundation for later biology, platform and performance work.

Authoritative Freeze material:

- [`RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md`](../contracts/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md)
- [`RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md`](../core_freeze/v0.1.1/RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md)
- [`docs/contracts/CURRENT_CONTRACTS_v0.1.0.tsv`](../contracts/CURRENT_CONTRACTS_v0.1.0.tsv)

## 10. Stage16: turning a frozen scientific Core into releaseable software

After Local Core Freeze, development shifted from scientific-core stabilization to public release engineering.

The release-engineering work added or validated:

- a source-checkout installation workflow;
- automatic acquisition and exact verification of the standard GENCODE resources;
- public distribution of the compact validated GRCh38 catalog;
- public `rnatr-scout map`, `run`, `resources-status` and `system-info` workflows;
- full-network fresh-install FASTQ-to-final validation;
- exact scientific-table parity on a second Linux x86-64 machine;
- CPU/RAM/tmp/free-space detection and conservative automatic Core scheduling;
- Tier2/Tier3 automatic-resource parity;
- explicit tested/recommended hardware wording without inventing an empirical minimum;
- BSD-3-Clause software licensing with separate third-party attribution;
- release-candidate version/citation/environment-lock packaging;
- repository hygiene/navigation work while preserving Freeze/release traceability.

Representative release records:

- [`STAGE16W_PUBLIC_CATALOG_DISTRIBUTION_RESULT_v0.1.0.md`](../release/STAGE16W_PUBLIC_CATALOG_DISTRIBUTION_RESULT_v0.1.0.md)
- [`STAGE16X_FULL_NETWORK_FRESH_INSTALL_v0.1.2.md`](../release/STAGE16X_FULL_NETWORK_FRESH_INSTALL_v0.1.2.md)
- [`STAGE16Z_RESOURCE_AWARE_PUBLIC_CLI_v0.1.0.md`](../release/STAGE16Z_RESOURCE_AWARE_PUBLIC_CLI_v0.1.0.md)
- [`STAGE16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION_v0.1.0.md`](../release/STAGE16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION_v0.1.0.md)
- [`STAGE16AB_G25_G30_RELEASE_READINESS_ADJUDICATION_v0.1.0.md`](../release/STAGE16AB_G25_G30_RELEASE_READINESS_ADJUDICATION_v0.1.0.md)
- [`RELEASE_NOTES_v0.5.0-rc1.md`](../release/RELEASE_NOTES_v0.5.0-rc1.md)

The public release line remains governed by the final release audit and immutable Git/tag/release binding rather than by this narrative.

## 11. Why historical Stage files remain in the repository

The project accumulated many stage-numbered scripts and documents before and during Freeze/release engineering. They are visually noisy, but many are reverse-traceability evidence, exact validation sources, historical contracts, or records of why a current decision was made.

Before the v0.5.0 release line, repository hygiene was audited with the explicit rule that a Stage number or older filename is **not enough evidence that a file is obsolete**. Cosmetic movement/deletion was therefore avoided when it could break exact path/SHA references or obscure development provenance.

Ordinary users should not select these Stage scripts as the supported workflow. Current users start from `README.md` / `docs/USER_GUIDE.md`; current developers start from `DEVELOPMENT.md` and the current contracts/SSOT.

## 12. Where development continues after v0.5.0

Post-Freeze development is intentionally split into lanes.

### Biology sidecars

Add transcript/isoform, observability, haplotype/phase, molecule-independence, sample-by-locus summaries, ranking and researcher-facing dossiers as versioned sidecars. Preserve reverse traceability to the immutable Core result manifest and read/evidence/locus identities. Do not rewrite the Core five tables in place.

### Platform adapters/calibration

The validated profile is ONT cDNA. ONT direct RNA, PacBio Iso-Seq, PacBio Kinnex and other profiles should normally enter through platform-specific input/orientation/error/observability/calibration adapters connected to the canonical sequence/alignment/stable-identity interface.

### Performance optimization

Optimize internal sharding/concurrency, I/O, streaming, intermediate representation, stage fusion, compiled kernels and similar implementation details while preserving scientific output semantics and guarantees. The accepted full-scale BAM-to-final observation remains about 60.04 minutes with documented tolerance, while the **30-minute target** remains a post-Freeze optimization goal.

The developer entry points and required validation levels are collected in:

- [`DEVELOPMENT.md`](../../DEVELOPMENT.md)
- [`RNA_TR_Scout_post_freeze_governance_lanes_v0.1.0.md`](../governance/RNA_TR_Scout_post_freeze_governance_lanes_v0.1.0.md)
- [`RNA_TR_Scout_Core_Freeze_cross_platform_extension_boundary_addendum_v0.1.0.md`](../contracts/RNA_TR_Scout_Core_Freeze_cross_platform_extension_boundary_addendum_v0.1.0.md)
- [`RNA_TR_Scout_Future_extensibility_boundary_contract_v0.1.1.md`](../contracts/RNA_TR_Scout_Future_extensibility_boundary_contract_v0.1.1.md)

## 13. Reading the repository without the original development conversation

A repository-only reader should be able to answer three different questions without reconstructing the original development discussion:

- **How do I use RNA-TR-Scout?** Start with [`README.md`](../../README.md) and [`docs/USER_GUIDE.md`](../USER_GUIDE.md).
- **How do I modify or extend it?** Start with [`DEVELOPMENT.md`](../../DEVELOPMENT.md), [`CURRENT_CONTRACTS_v0.1.0.tsv`](../contracts/CURRENT_CONTRACTS_v0.1.0.tsv), and the Git-tracked SSOT exports.
- **Why is the architecture like this?** Use this history narrative, then follow its links to the primary source documents and evidence.

For current truth, current contracts and SSOT always supersede this historical summary.
