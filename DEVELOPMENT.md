# Developing RNA-TR-Scout

This file is a **navigation document**, not a new scientific specification or Single Source of Truth. When wording here and a linked current contract differ, the linked contract and current SSOT take precedence.

## Start here

Before changing the software, first identify the current contract and active implementation:

- [`docs/contracts/CURRENT_CONTRACTS_v0.1.0.tsv`](docs/contracts/CURRENT_CONTRACTS_v0.1.0.tsv) — index of current registered contracts.
- [`metadata/ssot/exports/current_pipeline.tsv`](metadata/ssot/exports/current_pipeline.tsv) — current active production path.
- [`metadata/ssot/CURRENT_STATE.md`](metadata/ssot/CURRENT_STATE.md) — generated current project state and registered decisions/limitations.
- [`docs/governance/RNA_TR_Scout_post_freeze_governance_lanes_v0.1.0.md`](docs/governance/RNA_TR_Scout_post_freeze_governance_lanes_v0.1.0.md) — how to classify post-Freeze changes and what validation is required.

The operational SSOT is maintained as a local SQLite database. Version-controlled exports under `metadata/ssot/` capture the Git-tracked SSOT state for the corresponding repository commit and should be used by repository-only readers. During active release engineering, these exports are regenerated from and reconciled with the operational SSOT before the corresponding state is committed.

The Stage15/Stage16 development scripts and stage-specific documents retained in this repository are primarily **historical development, validation, reproducibility, and release evidence**. They are not the default entry point for the current implementation.

## Biology development

Start from the published frozen Core result package rather than modifying the five Core tables in place.

Current entry points:

- [`docs/contracts/RNA_TR_Scout_Biology_sidecar_interface_contract_v0.1.0.md`](docs/contracts/RNA_TR_Scout_Biology_sidecar_interface_contract_v0.1.0.md)
- [`docs/contracts/rnatr_core_result_manifest_contract_v0.1.0.json`](docs/contracts/rnatr_core_result_manifest_contract_v0.1.0.json)
- [`docs/contracts/rnatr_biology_sidecar_manifest_contract_v0.1.0.json`](docs/contracts/rnatr_biology_sidecar_manifest_contract_v0.1.0.json)
- [`docs/contracts/RNA_TR_Scout_Biology_ready_interpretation_output_contract_v0.1.0.md`](docs/contracts/RNA_TR_Scout_Biology_ready_interpretation_output_contract_v0.1.0.md)

Biology work should be added as versioned sidecars joined through the Core result-manifest SHA and stable read/evidence/locus identities. Transcript/isoform annotation, observability, haplotype/phase evidence, molecule-independence state, sample-by-locus summaries, ranking, and researcher-facing dossiers belong in this lane unless a genuine shared Core semantic deficiency is identified.

A biology output should remain reverse-traceable through its sidecar/Core identities to the contributing Core evidence and, through the portable manifest/resource bindings, to the relevant original read/alignment resources.

## Platform extension

The currently validated standard profile is **ONT cDNA**. New ONT direct RNA, PacBio Iso-Seq, PacBio Kinnex, or other platform support should normally be implemented as a platform-specific adapter/calibration layer connected to the existing platform-independent Core boundary.

Current entry points:

- [`docs/contracts/RNA_TR_Scout_Core_Freeze_cross_platform_extension_boundary_addendum_v0.1.0.md`](docs/contracts/RNA_TR_Scout_Core_Freeze_cross_platform_extension_boundary_addendum_v0.1.0.md)
- [`docs/contracts/RNA_TR_Scout_Future_extensibility_boundary_contract_v0.1.1.md`](docs/contracts/RNA_TR_Scout_Future_extensibility_boundary_contract_v0.1.1.md)
- [`docs/governance/RNA_TR_Scout_post_freeze_governance_lanes_v0.1.0.md`](docs/governance/RNA_TR_Scout_post_freeze_governance_lanes_v0.1.0.md)

Platform-specific physical input, orientation, alignment representation, error characteristics, completeness, observability, and calibration should remain behind the adapter/profile boundary. They should connect through canonical sequence/alignment/provenance and stable identity interfaces rather than being silently mixed into platform-independent repeat semantics.

## Performance optimization

Performance work may change internal implementation while preserving the frozen scientific/public contract. Examples include sharding and concurrency, I/O reduction, intermediate layout, streaming, stage fusion, compiled kernels, CPU/GPU implementation, caching, and hardware-aware scheduling.

Start with:

- [`docs/governance/RNA_TR_Scout_post_freeze_governance_lanes_v0.1.0.md`](docs/governance/RNA_TR_Scout_post_freeze_governance_lanes_v0.1.0.md)
- [`docs/contracts/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md`](docs/contracts/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md)
- [`validation/golden/v0.1.0/`](validation/golden/v0.1.0/)
- [`metadata/ssot/exports/current_results.tsv`](metadata/ssot/exports/current_results.tsv)
- [`metadata/ssot/exports/current_known_limitations.tsv`](metadata/ssot/exports/current_known_limitations.tsv)

Before adopting an optimization, use the validation level required by the governance lane: relevant golden scientific parity, determinism, restart/resume, validators, and targeted performance/resource benchmarks. Mapping optimization additionally requires mapping/locus-assignment/final-output checks appropriate to the change.

The current SSOT records the accepted approximately 5.31-million-read BAM-to-final empirical result (about 60.04 minutes, accepted with documented tolerance) and the continuing 30-minute optimization target. Treat the SSOT and linked evidence—not this summary sentence—as authoritative.

## Development history

For the research and engineering path that led to the v0.5.0 release line, see [`docs/history/DEVELOPMENT_HISTORY_v0.5.0.md`](docs/history/DEVELOPMENT_HISTORY_v0.5.0.md). That document is historical navigation only; current contracts and SSOT remain authoritative.

## Repository history and cleanup

Do not infer that a file is obsolete merely because its name contains a Stage number or an older version. Many such files are retained as Freeze, validation, or reproducibility evidence and may be referenced by path or checksum.

For the v0.5.0 release line, prefer traceability over cosmetic relocation. Move or delete historical material only after its active/Freeze/SSOT/release references have been explicitly audited.

Ordinary users should use the supported `rnatr-scout` workflow documented in `README.md` and `docs/USER_GUIDE.md`; they should not run stage-numbered development scripts as part of normal analysis.
