# Stage16W public catalog distribution contract v0.1.0

Date: 2026-08-17

## Status

**DESIGN_ACCEPTED — IMPLEMENTATION/NETWORK VALIDATION PENDING**

Stage16W prepares a stable public distribution path for the compact validated RNA-TR-Scout catalog bundle without modifying the frozen scientific Core or the five validated runtime catalog artifacts.

## Distribution decision

Use a dedicated public GitHub resource repository separate from the still-private RNA-TR-Scout software repository.

Planned repository:

`Ryo-Miyamo/RNA-TR-Scout-resources`

The validated catalog bundle will be distributed as a GitHub Release asset rather than committed into the software repository Git history.

Rationale:

- the software repository can remain private until the public v0.5.0 release process is ready;
- binary catalog payloads do not need to become ordinary Git objects;
- the installer can use one stable release-asset URL plus the exact bundle SHA-256;
- the resource release can carry provenance, attribution, checksums and release notes independently of software source history;
- future catalog profiles can be published as new immutable resource releases without rewriting earlier validated profiles.

## Runtime scientific identity must remain unchanged

The current validated runtime catalog consists of exactly five scientific/runtime artifacts:

- `TRExplorer_v2.rnatr_pilot_analysis_regions.final.tsv.gz`
- `STRchive_disease_regions.final.tsv.gz`
- `RNA-TR-Scout_v0.3.mapping_target_regions.tsv.gz`
- `RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz`
- `RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz.tbi`

Their existing SHA-256 identities remain the scientific compatibility contract.

Stage16W may change only the outer distribution bundle bytes by adding non-runtime metadata such as third-party notices and provenance. Any repacked bundle must be revalidated to prove that all five runtime member bytes remain exact.

## Third-party provenance and attribution

The compact catalog is derived from:

### TRExplorer catalog

- upstream repository: `https://github.com/broadinstitute/trexplorer-catalog`
- validated upstream release basis: TRExplorer catalog v2.0
- upstream repository license: MIT
- copyright notice recorded by the upstream repository: Broad Institute, 2024

The public RNA-TR-Scout resource bundle must retain an MIT license notice for the TRExplorer-derived material.

### STRchive

- upstream repository: `https://github.com/dashnowlab/STRchive`
- RNA-TR-Scout frozen source commit: `88502a64bd47ae464b908757122cc7e4bbeed8c8`
- repository version metadata at the frozen source commit: 2.24.2
- STRchive data/resource license: Creative Commons Attribution 4.0 International (CC BY 4.0)
- citation: Hiatt L, Weisburd B, Dolzhenko E, et al. STRchive: a dynamic resource detailing population-level and locus-specific insights at tandem repeat disease loci. Genome Medicine. 2025. doi:10.1186/s13073-025-01454-4

The public RNA-TR-Scout resource bundle must include explicit STRchive attribution and identify that RNA-TR-Scout distributes a transformed/selected derivative rather than the complete upstream STRchive resource.

## Bundle metadata policy

The existing standard-resource installer already permits metadata files in the validated catalog bundle while requiring the five runtime members and their exact SHA identities.

Stage16W therefore uses the following policy:

1. Start only from the exact currently validated Stage16L bundle.
2. Verify its exact expected bundle SHA before repacking.
3. Extract and verify all five runtime member SHA-256 values.
4. Add only non-runtime metadata under the bundle root, including third-party notices and RNA-TR-Scout provenance.
5. Repack deterministically.
6. Re-open the new archive and verify that every runtime member is byte-identical to the current validated runtime member.
7. Record the new outer bundle SHA-256.
8. Update `validated_profile.json` only after the new archive passes this check.
9. Publish exactly that archive as the public release asset.
10. Test unauthenticated network download and installer SHA enforcement before closing the public catalog hosting gate.

## Planned resource release identity

Provisional resource release tag:

`catalog-grch38-v0.1.0`

Provisional asset name:

`rnatr-validated-catalog-grch38-local-core-freeze-v0.1.0.tar.gz`

The release notes must state that the `local-core-freeze-v0.1.0` token identifies the validated scientific catalog profile from which the public distribution asset was prepared; it does not mean that ordinary users need access to the historical development tree.

## Installer contract

After public hosting is validated, the standard profile may set `catalog_bundle.public_url` to the immutable release-asset URL and update the bundle SHA to the repacked public-distribution archive SHA.

The installer must continue to:

- download automatically when no explicit local `--catalog-bundle` is supplied;
- verify the exact outer bundle SHA before extraction;
- reject mismatched downloads;
- validate the five exact runtime artifact SHA values after installation;
- retain explicit local-bundle installation as an advanced/offline option.

## Scope boundary

Stage16W does not alter:

- repeat-locus coordinates;
- motif semantics;
- disease-region content;
- mapping-target content;
- caller semantics;
- evidence schema;
- golden scientific outputs;
- the immutable Core Freeze root.

The following remain later gates even after the catalog asset is published:

- full-network fresh install from the final public acquisition paths;
- public-RC claim audit;
- final Pro cross-cut audit.
