# RNA-TR-Scout v0.5.0 release notes

Date: 2026-08-17

## Status

**FINAL v0.5.0 RELEASE — PUBLIC GIT/TAG/RELEASE BINDING COMPLETE**

RNA-TR-Scout v0.5.0 is the first public release line derived from the accepted
`LOCAL_CORE_FREEZE_V0.1.0` scientific Core. This document describes the final
source release. Repository visibility, annotated tag, GitHub Release, source
checksums, and citation binding have been verified by the Stage16AR public-release record.

## Validated standard scope

The v0.5.0 release is validated for:

- Linux x86-64;
- Oxford Nanopore cDNA long-read RNA sequencing;
- GRCh38 / GENCODE v50;
- the standard RNA-TR-Scout compact tandem-repeat catalog;
- FASTQ-to-final analysis using the validated ONT-cDNA mapping workflow;
- compatible mapped-BAM plus source-FASTQ analysis;
- restart/resume with scientific-output preservation;
- conservative automatic Core CPU/RAM-aware resource selection.

The frozen scientific Core remains rooted at:

`4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`

## Major release-engineering additions

- source-checkout installation and validation workflow;
- automatic checksum-verified GENCODE reference acquisition;
- stable public compact-catalog distribution with exact outer and runtime-member SHA-256 binding;
- public `rnatr-scout map`, `rnatr-scout run`, `rnatr-scout resources-status`, and `rnatr-scout system-info` workflows;
- CPU/RAM/tmp/free-space detection and conservative automatic Core scheduling;
- manual resource overrides with provenance and resume-plan consistency checks;
- independent second-machine fresh clone/environment/network-resource validation;
- exact Tier2 and Tier3 scientific-table parity under the release-engineering workflows;
- documented tested/recommended hardware profile with empirical minimum explicitly unresolved;
- explicit Linux x86-64 conda lock derived from the validated release environment;
- BSD 3-Clause software license with separate third-party resource/license boundary documentation;
- `CITATION.cff`, user/developer documentation, development-history navigation, and a release changelog.

## Scientific-output contract

The five main scientific output tables remain:

1. `read_evidence.tsv`
2. `general_repeat_calls.tsv`
3. `repeat_events.tsv`
4. `repeat_segments.tsv`
5. `repeat_interruptions.tsv`

v0.5.0 does not redefine the frozen repeat-calling scientific semantics.

## License

RNA-TR-Scout software source code is licensed under `BSD-3-Clause`.

Copyright (c) 2026 Ryosuke Miyamoto.

Third-party catalog/data resources and external dependencies remain governed by
their own upstream terms; the RNA-TR-Scout software license does not relicense
those materials. See `THIRD_PARTY_NOTICES.md` and
`docs/catalog_resources/third_party/`.

## Known scope limitations

- RNA non-observation must not be interpreted as genomic absence.
- The current automatic caller is strongest for periodic tandem-repeat structures and does not automatically solve every complex or sequence-variable repeat architecture.
- ONT direct RNA, PacBio Iso-Seq, PacBio Kinnex, and non-x86-64 systems are not yet part of the standard validated workflow.
- A formal approximately-five-million-read peak-disk benchmark is still open; no fixed full-scale minimum free-space claim is made.
- The empirical minimum CPU/RAM profile for full-scale analysis is not established. The release-scale recommended profile is intentionally more conservative than the small-run practical target.
- Biology-sidecar interpretation, truth-bearing biological validation, and purpose-specific candidate ranking remain post-v0.5.0 work.

## Validation summary

The final Pro cross-cut audit passed before conversion of release-candidate
metadata to `0.5.0`. The final version conversion is restricted to release
metadata and documentation plus the package/setup version guards; scientific
Core semantics and runtime implementation are otherwise unchanged.

See:

- `docs/release/STAGE16AN_FINAL_PRO_CROSSCUT_AUDIT_v0.1.0.md`
- `validation/release_gates_v0.3.5.tsv`
- `CHANGELOG.md`
- `docs/release/STAGE16AR_PUBLIC_V050_RELEASE_BINDING_v0.1.0.md`
