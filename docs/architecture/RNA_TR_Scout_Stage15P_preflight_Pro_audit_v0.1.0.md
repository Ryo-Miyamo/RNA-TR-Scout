# RNA-TR-Scout Stage 15P G32–G34 build-preflight — Pro audit v0.1.0

## Decision

**PASS_WITH_REQUIRED_INSTALLER_AMENDMENTS**

The Stage15P bundle is internally valid and contains sufficient exact-original evidence to
build G32, G33, and G34. No further scientific discovery or active-path redesign is
required before preparing the installer.

## Uploaded bundle

- SHA-256: `07793d1c1449a160130a85a892c3e6c6e77b20cc857f145b0a772190c1f77018`
- sidecar parity: PASS
- tar members: 73
- artifact-manifest rows: 44
- manifest coverage/path/size/SHA mismatches: 0
- unsafe paths, links, special files, or duplicate members: 0

## Exact-original evidence

- live promoted SSOT validation: PASS
- regression exact guards: 11/11 PASS
- general-caller v0.4.1 validation manifest: `0fb630f16444ad865811dd2f72ab1891017a21159a899d33e3144c8d25369e0e`
- resolved general-caller originals: 11
- formal evidence bundles: 6/6 PASS
- proposed copy bytes: 351,810,994
- free project bytes at collection: 110,451,015,680
- Downloads inventory: 367 rows
- scientific rerun/mutation/cleanup during collection: none

## Accepted G32–G34 design

### G32 — Core Freeze Packet

Freeze observable scientific/public behavior rather than current internal mechanics. The
Packet must include active code/schema/SSOT/evidence checksums, scientific semantics, stable
identities, manifest/API, restart/validation guarantees, scoped performance evidence,
known limitations, the current ONT-cDNA profile, cross-platform extension boundary, and the
biology-sidecar interface.

### G33 — executable golden suite

- Tier0: static SSOT/resource/schema/manifest/identity checks;
- Tier1: constructed-truth, legacy regression, and rejection fixtures;
- Tier2: fixed real-read `shard_088` positive execution;
- Tier3: fixed 100k sharded execution, restart, no-op, and publication recovery;
- Tier4: checksum/scope verification of Stage15C/Stage15E release-scale evidence without a
  routine 5.31M rerun.

Quick, full, and full-evidence modes are accepted.

### G34 — canonical layout

- `docs/architecture/`
- `docs/governance/`
- `docs/contracts/`
- `docs/core_freeze/v0.1.0/`
- `validation/golden/v0.1.0/`
- `metadata/core_freeze/v0.1.0/`

Stage-local documents remain history and receive pointers; they are not deleted.

## Required installer amendments

1. Canonicalize the physical Tier2 `shard_088` BAM and read-coherent FASTQ.
2. Add v0.3.1/v0.3.2 `regression_fixture.qc.tsv` originals.
3. Expand the machine-readable Freeze snapshot to resource manifest, result-manifest
   contract, schema/validators, current gates/exports, active code/resources and accepted
   result-manifest evidence.
4. Install a biology-sidecar extension contract anchored by the immutable Core result
   manifest SHA.
5. State explicitly that `read_id` is a technical-read identity, not automatically an
   independent biological molecule.
6. Install exact Tier2/Tier3 expected-output manifests.
7. Implement all ten rejection/recovery/no-op recipes as executable checks.
8. Do not close G24/G32–G34 in the installation step; install and run the full golden suite
   first, then perform a separate exact-original post-install Freeze registration audit.
9. Keep Downloads cleanup as a separate later action.

## Biology-readiness conclusion

The future biology wiring foundation is accepted:

- portable Core result manifest;
- stable read/evidence/event/call identities;
- logical source BAM/source-read resources;
- pinned locus/target catalogs;
- actual manifest-to-BAM and manifest-to-annotation smoke.

The full biology layer remains intentionally absent. Transcript annotations, molecule
identity, isoform/haplotype state, observability calibration, population references and
candidate dossiers are versioned sidecar/profile resources. They are linked through the
frozen extension contract and never rewrite the five Core source-of-truth tables.
