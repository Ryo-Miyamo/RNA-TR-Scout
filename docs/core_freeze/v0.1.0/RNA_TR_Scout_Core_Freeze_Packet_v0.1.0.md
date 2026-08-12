# RNA-TR-Scout Core Freeze Packet v0.1.0 — installation candidate

## Status

Installed and golden-tested by Stage15Q. Final G32/G24 closure requires a separate
post-install exact-original audit and SSOT registration.

## Active Core

- active stage: `CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL`
- public entry: `scripts/rnatr_core_production_entry_v0.1.0.py`
- generic sharded orchestrator: `scripts/rnatr_core_generic_sharded_v0.1.2.py`
- generic unit: `scripts/rnatr_core_generic_unit_v0.1.1.py`
- evidence schema: v0.4.2
- portable result manifest: `rnatr_core_result_manifest_v0.1.0`

Exact checksums are in `metadata/core_freeze/v0.1.0/core_freeze_manifest.tsv`.

## Frozen scientific/public contract

Freeze repeat-measurement semantics; censoring/context-limited/missingness distinctions;
five-table schema/output; stable identity/join contract; portable logical-resource/result
manifest; determinism, restart/resume, validation, corruption rejection and atomic
publication; and scientific output protected by the canonical golden suite.

## Stable identity scope and biology wiring

- read: `(core_result_manifest_sha256, read_id)`
- locus: `(catalog_logical_id, catalog_sha256, target_source, target_region_id, locus_id)`
- evidence/event/call/interruption: `(core_result_manifest_sha256, Core ID)`

`read_id` is a technical-read identity, not automatically an independent molecule. Biology
sidecars reference the immutable Core result-manifest SHA, add versioned transcript/gene,
platform, calibration, molecule/haplotype/population resources, retain reverse traceability,
and never rewrite the five Core tables.

## Candidate-assignment multiplicity and reverse traceability

Full-scale evidence records 5,312,696 input reads, 4,212,263 candidate reads and
20,656,258 candidate-assignment rows (approximately 4.90 assignments per candidate read).

Final Core Freeze GO remains pending a Stage15R read-only inspection and checksum-bound
reverse-traceability evidence. The long-term contract preserves the ability to explain
`read_id -> target/locus assignment -> assignment basis/geometry -> projection/window ->
motif/caller evidence`, without permanently freezing historical internal Stage filenames
or paths.

## Current validated profile and extension boundary

The ONT-cDNA baseline uses mapping-complete BAM plus read-coherent source FASTQ and the
current minimap2 splice mapping baseline upstream of Core timing. These are scoped profile
and implementation facts, not universal physical-input requirements for future ONT direct
RNA, PacBio Iso-Seq or PacBio Kinnex adapters.

## Future extensibility pending final exact-original audit

Before final Core Freeze GO, Stage15R/final audit must confirm that the active exact
originals leave open the following extension boundaries without requiring pre-Freeze
implementation:

- target selection / ROI / locus-list / known-locus force analysis;
- multi-sample and cohort-safe identity namespaces;
- physical storage/query adapters beyond TSV/TSV.gz;
- read-level reverse-trace and future inspection tooling;
- alternate reference/assembly/catalog adapters;
- alternate output adapters.

This requirement is recorded as
`PENDING_FINAL_EXACT_ORIGINAL_AUDIT_BEFORE_CORE_FREEZE_GO`. Only a demonstrated hard
coupling should trigger pre-Freeze remediation.

## Golden hierarchy

- Tier0: static contract checks.
- Tier1: exact regression/validation originals and rejection fixtures.
- Tier2: fixed real-read shard_088 exact parity.
- Tier3: fixed 100k 12-shard execution, stop/resume/no-op and publication recovery.
- Tier4: Stage15C/Stage15E release-scale checksum/scope verification without routine 5.31M rerun.

## Performance scope

The 5,312,696-read BAM-to-final result is 60.041256352 minutes,
`PASS_WITH_DOCUMENTED_TOLERANCE`, from Stage15C. It is not a direct empirical 5.31M
benchmark of generic orchestrator v0.1.2. The 30-minute objective and mapping/internal
optimization remain post-Freeze Performance-lane work.

## Replaceable implementation details

Internal Stage names, shard/worker counts, internal partition/concurrency/order,
intermediate paths/layout, and file-versus-streaming handoff are not permanently frozen when
golden scientific parity and required guarantees pass.
