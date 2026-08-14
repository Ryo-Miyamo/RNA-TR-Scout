# RNA-TR-Scout

> **Internal laboratory snapshot — not the public v0.5.0 release.**

This repository currently contains the internal Git history beginning from the accepted
RNA-TR-Scout Local Core Freeze.

## Frozen internal baseline

- Freeze ID: `LOCAL_CORE_FREEZE_V0.1.0`
- immutable root commit: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
- internal tag: `local-core-freeze-v0.1.0-internal`
- final Core Freeze manifest SHA-256:
  `c9a54b4c01dd67d2b7df9d96ba4c86bbe26c02e2ef6f4180c8f152927129125b`

The root commit is intended to remain an exact internal snapshot of the accepted Local Core
Freeze. Subsequent commits may improve repository organization, documentation, packaging,
installation, and release engineering without rewriting that frozen point.

## Current scope

The validated current profile is ONT cDNA with the frozen RNA-TR-Scout scientific Core.

Post-Freeze release engineering has now validated both:

- source-checkout BAM + read-coherent FASTQ -> frozen Core final from a fresh private GitHub clone
  and fresh mamba environment; and
- the ONT-cDNA FASTQ -> minimap2 splice-aware BAM -> frozen Core final path on the validated
  Linux x86-64 platform.

Large sequencing inputs, reference/catalog payloads, SQLite databases, and historical evidence
archives are intentionally not stored in Git. Their identities are checksum-bound by release
resource manifests or frozen provenance.

These results do **not** make the repository the public `v0.5.0` release. Portable reference
acquisition, public CLI integration, native-wheel strategy, cross-hardware validation, release
documentation cleanup, and the final public release decision remain later work.

## Repository status

This repository is **private and intended for laboratory-internal sharing at this stage**.
Do not describe the current repository state as the public RNA-TR-Scout v0.5.0 release.
## Reference and tool compatibility

The current validated ONT-cDNA profile uses the documented GRCh38 / GENCODE v50 resources and
minimap2 2.31-r1302. Exact SHA/tool-version matches identify this validated profile; they are not
general execution-permission gates.

Other GRCh38-compatible references and mapper versions may be used through the post-Freeze
compatibility-aware mapping adapter. Such runs are recorded as custom profiles and are outside
exact golden-validation scope. Reference compatibility is checked against the frozen validated
RNA-TR-Scout mapping-target catalog. For a custom FASTA, the FASTA itself is inspected and a
run-local minimap2 index is built rather than trusting an unverified custom FAI/MMI.

Custom TRExplorer/STRchive-derived catalogs are a separate post-Freeze extension and are not
enabled merely by disabling the frozen Core catalog SHA guards.
