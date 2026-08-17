# Stage16W public catalog distribution result v0.1.0

Date: 2026-08-17

## Decision

**PASS — PUBLIC CATALOG RELEASE ASSET PUBLISHED AND EXACTLY DOWNLOADABLE**

Stage16W published the compact validated RNA-TR-Scout GRCh38 catalog bundle through a dedicated public GitHub resource repository while preserving all five validated runtime catalog members byte-for-byte.

## Public distribution identity

- public resource repository: `Ryo-Miyamo/RNA-TR-Scout-resources`
- repository visibility: PUBLIC
- resource release tag: `catalog-grch38-v0.1.0`
- asset: `rnatr-validated-catalog-grch38-local-core-freeze-v0.1.0.tar.gz`
- outer archive SHA-256: `54a24e4b60d920c8fec16b2df37b47e40407de42b949b18dc6233e97d85f2fef`

The release is neither draft nor prerelease.

## Public-download verification

The Stage16W publication result records:

- `status=PASS_PUBLIC_RELEASE_ASSET_UNAUTHENTICATED_EXACT_SHA`
- resource repository visibility: PUBLIC
- release asset upload state: uploaded
- unauthenticated download exact SHA: true

Thus ordinary resource acquisition does not require access to the private RNA-TR-Scout software repository.

## Runtime scientific identity

Before publication, the Stage16W deterministic repack process verified that all five runtime catalog artifacts remained exact. The outer archive changed only to add public redistribution metadata, third-party license/attribution notices and provenance.

The runtime scientific files and their established SHA-256 identities were not changed by Stage16W.

## Upstream notices

The public distribution archive carries:

- TRExplorer MIT license notice;
- STRchive CC BY 4.0 attribution notice; and
- RNA-TR-Scout catalog provenance metadata.

## Installer binding

The Stage16W software branch updates `config/resources/standard_v0.1.1/validated_profile.json` so that the standard installer can acquire this exact release asset automatically and verify the outer archive SHA before validating the five runtime member identities.

## Scope boundary

Stage16W changes release/distribution metadata only. It does not modify repeat coordinates, disease-region content, mapping-target content, caller semantics, evidence schema, golden outputs, or the immutable Core Freeze root.

Stage16X separately validates full network acquisition plus public FASTQ-to-final execution using this public asset.
