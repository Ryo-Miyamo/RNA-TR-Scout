# RNA-TR-Scout v0.5.0-rc1 release notes

Date: 2026-08-17

## Status

**RELEASE CANDIDATE PACKAGING DRAFT — FINAL PRO CROSS-CUT AUDIT PENDING**

This document summarizes the candidate public v0.5.0 release state. It does not by itself create a public release or tag.

## Validated standard scope

The release candidate is validated for:

- Linux x86-64;
- Oxford Nanopore cDNA long-read RNA sequencing;
- GRCh38 / GENCODE v50;
- the standard RNA-TR-Scout compact tandem-repeat catalog;
- FASTQ-to-final analysis using the validated ONT-cDNA mapping workflow;
- compatible mapped-BAM plus source-FASTQ analysis;
- restart/resume with scientific-output preservation.

The frozen scientific Core remains rooted at:

`4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`

## Major release-engineering additions

- source-checkout installation and validation workflow;
- automatic GENCODE reference acquisition with checksum verification;
- stable public compact-catalog distribution with exact outer and runtime-member SHA-256 binding;
- public `rnatr-scout map`, `rnatr-scout run`, `rnatr-scout resources-status`, and `rnatr-scout system-info` workflows;
- CPU/RAM/tmp/free-space detection and conservative automatic Core scheduling;
- manual resource overrides with provenance and resume-plan consistency checks;
- independent second-machine fresh clone/environment/network-resource validation;
- exact Tier2 and Tier3 scientific-table parity under the release-engineering workflows;
- documented tested/recommended hardware profile with empirical minimum explicitly unresolved.

## Scientific-output contract

The five main scientific output tables remain:

1. `read_evidence.tsv`
2. `general_repeat_calls.tsv`
3. `repeat_events.tsv`
4. `repeat_segments.tsv`
5. `repeat_interruptions.tsv`

The release candidate does not redefine the frozen repeat-calling scientific semantics.

## Known scope limitations

- RNA non-observation must not be interpreted as genomic absence.
- The current automatic caller is strongest for periodic tandem-repeat structures and does not automatically solve every complex or sequence-variable repeat architecture.
- ONT direct RNA, PacBio Iso-Seq, PacBio Kinnex, and non-x86-64 systems are not yet part of the standard validated workflow.
- A formal approximately-five-million-read peak-disk benchmark is still open; no fixed full-scale minimum free-space claim is made.
- The empirical minimum CPU/RAM profile for full-scale analysis is not established. The release-scale recommended profile is intentionally more conservative than the small-run practical target.

## Remaining work before public v0.5.0

- select and bind the software license;
- generate and verify the platform-specific explicit environment lock;
- run the final Pro-level cross-cut audit;
- resolve any audit-blocking findings;
- change candidate version metadata from `0.5.0rc1` / `0.5.0-rc1` to final `0.5.0`;
- create and verify the immutable public Git tag/release/citation binding.
