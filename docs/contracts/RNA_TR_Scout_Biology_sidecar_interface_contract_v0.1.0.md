# RNA-TR-Scout biology-sidecar interface contract v0.1.0

## Purpose

Biology and interpretation layers must evolve after Core Freeze without modifying the five
frozen Core source-of-truth tables. A sidecar consumes a published Core result package and
emits new versioned artifacts plus a sidecar manifest; it never edits the Core package in
place.

## Core reference

Every sidecar manifest records:

- Core result-manifest version and SHA-256;
- Core run_id and sample_id;
- Core evidence-schema version;
- sidecar software/schema version;
- sidecar input-resource checksums;
- validation status.

The Core result-manifest SHA is the namespace anchor for all sidecar joins.

## Stable identity scope

### Read identity

Cross-result read identity is `(core_result_manifest_sha256, read_id)`.

`read_id` is a stable technical-read identity. It must not be relabeled as an independent
biological molecule without platform/library evidence.

### Molecule identity

A sidecar may define `molecule_id`, `molecule_identity_status`,
`independent_molecule_weight`, or membership tables when supported by an explicit method.
These fields do not rewrite Core `read_id`.

### Locus identity

A robust locus reference is:

`(catalog_logical_id, catalog_sha256, target_source, target_region_id, locus_id)`

A bare `locus_id` is not assumed globally invariant across arbitrary catalog versions.

### Evidence/event identities

`evidence_id`, `repeat_event_id`, `repeat_call_id`, `interruption_id`, and
`caller_record_id` are scoped by the referenced Core result-manifest SHA.

## Resource extension boundary

The Core manifest supplies logical source-alignment, source-read and repeat-catalog
resources. A sidecar may add separately checksum-bound resources such as:

- `annotation:transcriptome`
- `annotation:genes`
- `annotation:splice_junctions`
- `profile:platform`
- `profile:library`
- `calibration:observability`
- `calibration:error_model`
- `reference:population`

Machine-local paths belong only in a local binding file. Portable sidecar manifests contain
logical IDs, versions, checksums and relative artifact paths.

## Required traceability

Every sidecar row carries enough Core identity to reverse-resolve to source evidence.
Examples:

- transcript/isoform: Core manifest SHA + read_id + evidence_id + locus identity;
- haplotype: Core manifest SHA + read_id/molecule_id + locus identity + phase-evidence ref;
- observability: Core manifest SHA + read_id + transcript/profile/calibration IDs;
- sample-locus summary: Core manifest SHA + locus identity + explicit aggregation and
  missingness method;
- candidate dossier: reverse links to all contributing Core and sidecar rows.

## Immutability boundary

Sidecars must not:

- edit the five Core TSVs;
- reinterpret censored/context-limited evidence as exact;
- equate non-observation with biological absence;
- assign haplotype/allele labels without phase evidence;
- hide platform-specific calibration inside a supposedly platform-independent Core field.

A genuine shared-semantics deficiency triggers a separate strict Core-contract revision.

## PRE_BIOLOGY acceptance

Before biology implementation, the project demonstrates:

1. portable manifest -> read_id -> primary alignment;
2. portable manifest -> target/locus identity -> pinned annotation;
3. sidecar manifest -> immutable Core result-manifest SHA;
4. reverse traceability without Stage number, dataset name, or developer absolute path.

Items 1 and 2 have accepted Stage15J/L evidence. Items 3 and 4 are canonicalized and
mechanically checked by the G32/G33 installation.
