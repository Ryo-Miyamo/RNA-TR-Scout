# RNA-TR-Scout software license owner decision v0.1.0

Date: 2026-08-17

## Status

**OWNER_SELECTED — BSD-3-CLAUSE**

The repository owner selected the BSD 3-Clause License for the RNA-TR-Scout software source code.

- SPDX identifier: `BSD-3-Clause`
- copyright year: 2026
- copyright holder: Ryosuke Miyamoto
- root license file: `LICENSE`

The repository-level software license is now bound consistently in `LICENSE`, `pyproject.toml`, and `CITATION.cff`.

## Boundary

This decision concerns the RNA-TR-Scout software source code. It does **not** relicense third-party reference data, catalog source material, external software dependencies, or other upstream resources.

The validated compact repeat catalog includes separately governed upstream material. Existing third-party records are retained under `docs/catalog_resources/third_party/`, including the STRchive attribution record and the TRExplorer license record. A root `THIRD_PARTY_NOTICES.md` points users to those boundaries.

## Owner decision

On 2026-08-17, Ryosuke Miyamoto selected `BSD-3-Clause` as the top-level RNA-TR-Scout software license and confirmed Ryosuke Miyamoto as the copyright holder.

## Release requirement

Before public v0.5.0 release, the final Pro cross-cut audit must still verify that:

1. the root `LICENSE` text is consistent with `BSD-3-Clause`;
2. `pyproject.toml` and `CITATION.cff` use the same identifier;
3. third-party catalog/data notices remain clearly separate from the software license;
4. no release metadata overstates rights over externally governed resources.
