# RNA-TR-Scout software license owner decision v0.1.0

Date: 2026-08-17

## Status

**OWNER_SELECTION_PENDING — PUBLIC RELEASE BLOCKING**

RNA-TR-Scout does not yet have a selected top-level software license. The current `pyproject.toml` therefore continues to state that the software license has not yet been selected, and no final root `LICENSE` file is created by this checkpoint.

## Boundary

This decision concerns the RNA-TR-Scout software source code. Third-party data/catalog notices remain separately governed by their upstream terms and the attribution files already carried with the validated catalog distribution.

## Candidate choices

Two common permissive choices are suitable candidates for owner review:

- MIT License — short and permissive; requires preservation of copyright/license notice.
- Apache License 2.0 — permissive with additional explicit patent-license and notice provisions.

No license is selected merely by listing these options.

## Release requirement

Before public v0.5.0 release:

1. the repository owner must select the software license;
2. the exact license text must be committed at repository root as `LICENSE`;
3. `pyproject.toml` and `CITATION.cff` must use the same selected license identifier;
4. the final Pro cross-cut audit must verify that software-license claims and third-party catalog/data notices are not conflated.
