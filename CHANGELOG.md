# Changelog

This changelog summarizes the public RNA-TR-Scout release line. Detailed validation scope, exact evidence identities, and release-engineering records are retained under `docs/release/`, `metadata/ssot/`, and the linked Freeze/golden records.

## [0.5.0] - 2026-08-17

### Added

- Source-checkout setup and verification for the validated Linux x86-64 environment.
- Public `rnatr-scout run`, `map`, `resources-status`, and `system-info` workflows.
- Automatic checksum-verified GENCODE v50 reference bootstrap and compact GRCh38 repeat-catalog installation.
- CPU/RAM/tmp/free-space detection and conservative automatic Core resource planning.
- Restart/resume and completed-run second-resume no-op behavior.
- User, developer, and development-history navigation.
- BSD-3-Clause software license, `CITATION.cff`, third-party notices, and an explicit Linux-64 conda lock.

### Validated release scope

- Oxford Nanopore cDNA long-read RNA sequencing.
- GRCh38 / GENCODE v50.
- Linux x86-64.
- FASTQ-to-final and compatible mapped-BAM plus source-FASTQ workflows.
- Exact frozen five-table scientific parity on the validated fixtures, including independent second-host validation within the documented scope.

### Important scope limits

- RNA non-observation is not genomic absence.
- The current automatic caller does not completely measure every complex or sequence-variable repeat architecture.
- ONT direct RNA, PacBio Iso-Seq, PacBio Kinnex, and non-x86-64 systems are not yet standard validated profiles.
- Full-scale peak disk usage and a lower empirical full-scale CPU/RAM minimum remain unmeasured.
- Immutable Git tag/GitHub Release/source-checksum/citation binding is verified separately in the final release record.
