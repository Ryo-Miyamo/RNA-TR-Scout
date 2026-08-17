# Stage16X full-network fresh-install validation v0.1.2

Date: 2026-08-17

## Decision

**PASS_WITH_SCOPE — FULL_NETWORK_FRESH_INSTALL_PUBLIC_FASTQ_TO_FINAL**

Stage16X validates the intended public network acquisition paths and public FASTQ-to-final workflow from a fresh isolated release-engineering state on the validated Linux x86-64 host.

## Source identity

- source branch: `stage16w-public-catalog-distribution`
- source commit: `24ccb15e01921f05465f8bddb59f743d1ef4cc6f`
- immutable Core Freeze root: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`

The source commit descends from the immutable Freeze root. The scientific Core was not modified by Stage16X.

## Authoritative result

Authoritative result file:

- `rnatr_stage16x_full_network_fresh_install_result_v0.1.2_20260817T022512Z.json`
- SHA-256: `75f9cc560c22adb236902324d2d4771f7a1a6fee439cedf747a9cfb163fffd09`

The result records `status=PASS_FULL_NETWORK_FRESH_INSTALL_PUBLIC_FASTQ_TO_FINAL`.

## Network resource validation

Stage16X used fresh dedicated environment/cache paths. The v0.1.1 wrapper completed resource setup successfully and then stopped only because the wrapper incorrectly interpreted acquisition-status fields in the installation manifest as filesystem paths. v0.1.2 continued the same fresh run after revalidating the downloaded cache files by exact SHA-256.

Validated network acquisitions:

- official GENCODE reference FASTA source: exact download PASS
- official GENCODE GTF source: exact download PASS
- public RNA-TR-Scout catalog GitHub Release asset: exact download PASS
- standard resource profile after install: `PASS_STANDARD_RESOURCES_READY`
- validated reference profile: PASS
- validated catalog profile: PASS

Public catalog outer archive SHA-256:

`54a24e4b60d920c8fec16b2df37b47e40407de42b949b18dc6233e97d85f2fef`

The five runtime catalog members retained their previously validated exact SHA-256 identities.

## Public FASTQ-to-final validation

The scientific fixture remained an exact-SHA external golden fixture outside the Git checkout, consistent with the existing golden-fixture policy.

- Tier3 FASTQ SHA-256: `559dd0f3cb7d7de3c108a68a0d36efb895aae8f63e1a78aa4acd1d91b2c27173`
- public command: `rnatr-scout run`
- input mode: `FASTQ_AUTO_MAPPING`
- mapping: PASS
- exact final-table parity: `PASS_5_OF_5`
- resume: `PASS_SECOND_RESUME_NOOP`
- mapping rerun on resume: false
- mapping artifacts unchanged on resume: true
- post-resume final parity: `PASS_5_OF_5`
- fresh clone Git-clean after validation: true

Exact final scientific table identities matched the accepted Tier3 golden output for all five tables.

## Scope boundary

This validation closes the release-engineering gates for:

1. stable public catalog bundle hosting with exact SHA binding; and
2. full-network acquisition of the intended standard reference/catalog resources followed by public FASTQ-to-final execution in a fresh isolated state.

It does **not** claim that every Linux installation, every network, every hardware configuration, or every future upstream resource version has been tested. Stage16S remains the scoped second-machine hardware-parity evidence.

This validation is also not a formal approximately-five-million-read peak-disk benchmark. The existing full-scale peak-disk question remains open until separately measured or explicitly dispositioned before public release.

## Remaining RC work

Remaining work includes the final release-engineering cleanup needed for public v0.5.0, any still-required operational benchmark/document update, and the single Pro-level cross-cut audit immediately before declaring the public release candidate.
