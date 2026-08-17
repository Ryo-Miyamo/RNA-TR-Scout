# Stage16AE public release packaging v0.1.0

Date: 2026-08-17

## Status

**IN_PROGRESS — HIGH-MODE RELEASE PACKAGING BEFORE FINAL PRO AUDIT**

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
- [x] change source package version metadata to `0.5.0rc1`;
- [ ] update setup/version guards consistently and rerun source-checkout validation;
- [ ] generate an explicit Linux x86-64 conda environment lock from the validated release environment;
- [ ] validate the explicit lock has no developer-local filesystem paths;
- [ ] select the top-level RNA-TR-Scout software license;
- [ ] add root `LICENSE` and align `pyproject.toml` / `CITATION.cff` license metadata;
- [ ] run release-candidate packaging preflight and build/source-tree smoke tests;
- [ ] reconcile SSOT current release-packaging state;
- [ ] run the final Pro-level cross-cut audit.

## Environment lock policy

`environment.yml` remains the human-readable environment specification with directly required tools pinned to tested versions. For release reproducibility, Stage16AE will additionally commit a platform-specific explicit conda package lock generated from a validated Linux x86-64 source-checkout environment.

The explicit lock covers the conda environment packages and builds. The RNA-TR-Scout editable/source checkout itself remains bound by the Git commit/tag rather than by embedding a developer-local checkout path in the lock.

## License boundary

The software license is an owner decision and remains release-blocking until explicitly selected. Third-party catalog/data attribution and redistribution terms remain separate from the software license.

## Acceptance

Stage16AE is ready for the final Pro audit only when all mechanical packaging items are complete and the only remaining decisions are either explicitly nonblocking or owner-approved. Public v0.5.0 is not declared merely by completing this stage.
