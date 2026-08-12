# RNA-TR-Scout Stage 15N generic active-path promotion contract v0.1.0

## Promotion decision

The active **Core** production path begins from two read-coherent scientific inputs:

1. a mapping-complete BAM; and
2. the corresponding source-read FASTQ (or a separately validated equivalent raw-sequence resource).

The active Core path is the generic sharded orchestrator `rnatr_core_generic_sharded_bam_fastq_to_final_v0.1.2`, which invokes the accepted generic unit `rnatr_core_generic_unit_bam_fastq_to_final_v0.1.1`, publishes evidence schema v0.4.2 tables plus a portable Core result manifest, validates before atomic publication, and supports SHA-bound restart/resume.

The historical eleven-row P0/P1 path is retained as provenance but removed from `current_pipeline`. The historical dataset-bound minimap2 command is retained as **REFERENCE**, not as the active Core entry point.

## Mapping boundary

FASTQ-to-BAM mapping is upstream of the active Core and remains a separately frozen scientific baseline. The current minimap2 splice settings remain the baseline; this promotion neither optimizes mapping nor claims a generic clean-install mapping CLI. Post-Freeze mapping acceleration belongs to a separate Performance lane gated by TR-locus recall, locus assignment, and final-output parity.

“BAM-to-final” remains a timing boundary meaning that mapping is excluded from that timer. It does not mean that source FASTQ is unnecessary.

## Active public execution contract

The generic sharded runner requires explicit:

- runtime configuration;
- mapped BAM;
- read-coherent source FASTQ;
- run ID and sample ID;
- work root and output root;
- shard count and bounded worker settings;
- optional expected input SHA-256 guards.

The runner code contains no Stage number, dataset accession, T9 path, or developer-machine absolute path. Machine-local component/catalog paths are carried only in the explicit local runtime configuration and result binding file.

## Frozen scientific behavior

The active path preserves:

- evidence schema v0.4.2;
- caller v0.4.1;
- materializer v0.1.2;
- target-assignment and raw-read projection semantics;
- read-coherent SHA-256 partitioning;
- deterministic table-specific global merge keys;
- validator-before-publication and atomic publication;
- portable `core_result_manifest.json` plus separate `resource_bindings.local.json`;
- stable join keys including `read_id`, `target_source`, `target_region_id`, `locus_id`, `evidence_id`, `repeat_event_id`, `repeat_call_id`, `interruption_id`, and `caller_record_id`;
- performance instrumentation;
- SHA-bound completed-shard reuse, selective resume, second-resume no-op, and recovery when publication completed but external final-state persistence was interrupted.

## Acceptance evidence

- Stage 15J: generic single-unit real-read Tier-2 output, 5/5 exact plain-table parity, validators, atomic publication, manifest smoke.
- Stage 15L: generic full-input 12-shard 100k output, 5/5 exact parity, intentional stop, selective resume, atomic publication, PRE_BIOLOGY smoke, and second-resume scientific no-op.
- Stage 15M: actual published 100k output rehash and zero-scientific-command reconstruction of missing external final state from isolated copied run/shard/partition state.
- Stage 15C/15E: frozen release-scale performance, package, deterministic reconstruction, restart, and no-op evidence for unchanged scientific components.

No new 5.31M generic-orchestrator rerun is claimed by this promotion. The generic 100k exact-parity proof is bound to the unchanged Stage15C/Stage15E release-scale scientific-component evidence.

## PRE_BIOLOGY interface

The small read-only interface smoke is accepted: downstream code can begin from the formal Core result manifest and resolve a stable read identity to BAM alignment plus a stable target/locus identity to pinned annotation without Stage-number, dataset-name, or developer-path assumptions.

This does not implement full isoform, haplotype, observability, ranking, or biological interpretation.

## Post-Freeze extensibility

The public contract does not freeze the current intermediate-file layout. Stage fusion, streaming, reduced intermediate I/O, and hardware-aware concurrency may be introduced after Freeze only behind the frozen manifest/schema/API contract and golden/release-scale parity gates.

## Gates deliberately left open

Active-path promotion does not close clean-install/reference-bootstrap/resource-autotuning/cross-hardware gates G25–G30 or G28. Core Freeze Packet G32, canonical golden suite G33, and documentation canonicalization G34 remain required before Core Freeze.
