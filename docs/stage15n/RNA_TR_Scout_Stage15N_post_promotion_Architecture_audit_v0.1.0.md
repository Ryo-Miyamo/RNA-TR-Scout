# RNA-TR-Scout Stage 15N post-promotion Architecture consistency audit v0.1.0

## Acceptance rule

This focused audit is authoritative only when the Stage 15N promotion QC reports `audit_status=PASS` and all referenced SHA-256 values match the installed originals.

## Evidence policy

The audit is reconstructed from exact post-Stage15G SSOT CLI/SQLite/current views; exact schema, validators, generic runners, checksum-pinned runtime resource manifest, formal result-manifest contract, Stage15J/15L/15M evidence, and release-gate originals. Conversation summaries and memory are not authoritative evidence.

## Expected active state

`current_pipeline` contains exactly one active composite Core execution stage:

- stage key `CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL`;
- public entry `rnatr_core_production_entry_v0.1.0`;
- supporting orchestrator `rnatr_core_generic_sharded_bam_fastq_to_final_v0.1.2`;
- supporting generic unit `rnatr_core_generic_unit_bam_fastq_to_final_v0.1.1`;
- scientific input: mapped BAM plus corresponding source-read FASTQ;
- evidence schema v0.4.2;
- portable Core result manifest v0.1.0;
- package validation before atomic publication;
- SHA-bound shard restart/resume and publication-boundary final-state recovery.

The historical eleven-row P0/P1 pipeline remains in SSOT history but has no ACTIVE implementation. The historical dataset-bound minimap2 command remains a REFERENCE scientific mapping baseline upstream of the Core, not an active Core stage.

## Required consistency checks

- installed public entry, orchestrator, generic unit, PRE_BIOLOGY smoke, project-relative resource manifest, result-manifest contract, release gates, and promotion metadata match exact recorded hashes;
- no fixed developer-machine path, dataset accession, or Stage-specific run binding occurs in the public production entry or orchestrator;
- current pipeline has one row and one ACTIVE implementation total;
- all eleven former ACTIVE implementation IDs are no longer ACTIVE;
- old Stage15A/Stage15C candidates are REFERENCE or SUPPORT, not competing PROVISIONAL production entries;
- `ACTIVE_PATH_PROMOTION` is CLOSED;
- Architecture audit and biology-readiness questions remain OPEN for the later exact-original PRE_BIOLOGY/Core-Freeze audit;
- schema v0.4.2 is byte-identical;
- the accepted Stage15L published package and manifest interface remain valid;
- installed orchestrator v0.1.2 verifies publication-boundary recovery with zero scientific commands;
- G25–G30, G28, G32–G34 remain open as documented;
- package CLI/clean-install public release readiness is not falsely claimed;
- mapping remains a separately frozen minimap2 splice baseline and is not folded into the active Core timer or implementation.

## Scope

A PASS closes the focused active-path-promotion architecture checkpoint. It does not constitute Core Freeze, public release readiness, cross-hardware validation, truth-bearing biological validation, or implementation of isoform/haplotype biology.
