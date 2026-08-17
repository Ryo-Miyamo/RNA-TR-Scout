# Stage16AE public release packaging v0.1.0

Date: 2026-08-17

## Status

**MECHANICAL PACKAGING / RC PREFLIGHT / SSOT RECONCILIATION COMPLETE — FINAL PRO AUDIT PENDING**

Stage16AE prepares a coherent v0.5.0 release-candidate package without changing the frozen scientific Core.

## Immutable scientific boundary

Freeze root:

`4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`

Stage16AE may update packaging, version labels, citation metadata, environment lock records, user-facing release notes, and release checks. It must not change frozen scientific output semantics.

## Candidate release identity

- Python/PEP 440 package version: `0.5.0rc1`
- human-facing release-candidate label: `v0.5.0-rc1`
- intended final public version after audit: `v0.5.0`

The final public tag is not created at this stage.

## Packaging checklist

### Already complete before Stage16AE

- [x] immutable local Core Freeze root established;
- [x] private GitHub source history established;
- [x] public CLI workflows established;
- [x] public compact catalog hosted with exact SHA binding;
- [x] same-machine full-network fresh install validated;
- [x] independent second-machine fresh install/resource setup validated;
- [x] cross-hardware scientific parity validated for scoped fixtures;
- [x] resource-aware Core scheduling validated on Tier2/Tier3;
- [x] researcher-facing README and user guide present;
- [x] tested/recommended hardware profile documented with empirical minimum explicitly unresolved.

### Stage16AE tasks

- [x] create `CITATION.cff` release-candidate metadata;
- [x] create v0.5.0-rc1 release-notes draft;
- [x] add root `CHANGELOG.md` for the public release line;
- [x] change source package version metadata to `0.5.0rc1`;
- [x] update setup/version guards consistently;
- [x] generate an explicit Linux x86-64 conda environment lock from the validated release environment;
- [x] validate the explicit lock has no developer-local filesystem paths;
- [x] select the top-level RNA-TR-Scout software license;
- [x] add root `LICENSE` and align `pyproject.toml` / `CITATION.cff` license metadata;
- [x] record third-party software/data/catalog license boundary at repository root;
- [x] run release-candidate packaging preflight and build/source-tree smoke tests after license finalization;
- [x] reconcile SSOT current release-packaging state;
- [ ] run the final Pro-level cross-cut audit.

## Environment lock policy

`environment.yml` remains the human-readable environment specification with directly required tools pinned to tested versions. For release reproducibility, Stage16AE additionally carries `environment-linux-64.lock.txt`, an explicit conda package lock generated from the validated Linux x86-64 source-checkout environment.

The explicit lock covers the conda environment packages and builds. The RNA-TR-Scout source checkout itself remains bound by the Git commit/tag rather than by embedding a developer-local checkout path in the lock.

## License boundary

The repository owner selected the BSD 3-Clause License (`BSD-3-Clause`) for RNA-TR-Scout software source code.

- copyright year: 2026
- copyright holder: Ryosuke Miyamoto
- root license file: `LICENSE`

This software license does not relicense third-party catalog/data material, reference resources, or external dependencies. `THIRD_PARTY_NOTICES.md` and `docs/catalog_resources/third_party/` retain the corresponding boundary and upstream records.

## Acceptance

The post-license RC preflight and SSOT packaging-state reconciliation are complete. Stage16AE/AF/AG are therefore ready for the final Pro cross-cut audit. Public v0.5.0 is not declared merely by completing these mechanical steps.
