# Stage16AO final v0.5.0 source metadata v0.1.0

## Status

**FINAL VERSION SOURCE CANDIDATE — MAIN / PUBLIC / TAG / RELEASE BINDING PENDING**

## Preconditions

- final Pro cross-cut audit: PASS and registered;
- `PUBLIC_RC_PRO_CROSSCUT_AUDIT`: CLOSED;
- immutable Core Freeze root: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`;
- pre-Stage16AO release branch head: `3c59966216af67614af8bd5faa5a270fd461df70`.

## Changes permitted in this stage

- package version `0.5.0rc1` -> `0.5.0`;
- `CITATION.cff` version -> `0.5.0` and release date -> `2026-08-17`;
- source-checkout version guard -> `0.5.0`;
- README / USER_GUIDE / CHANGELOG final-release wording;
- addition of final `docs/release/RELEASE_NOTES_v0.5.0.md`;
- this Stage16AO release record.

No scientific/runtime semantics, resource profile, native kernel, schema,
golden fixture, or release-gate decision may change.

## Required validation

The exact prospective Git tree must pass:

- Python compile;
- unit tests;
- resource-planner tests;
- `rnatr-scout version == 0.5.0`;
- public CLI help surface;
- setup help;
- native shared-library load;
- Markdown local-link validation;
- high-confidence secret scan;
- package/license/resource identity guards.

## Remaining publication steps

After this source tree is validated and committed:

1. fast-forward the exact release line into `main`;
2. make the repository public;
3. verify unauthenticated public clone/source setup;
4. create and verify the immutable `v0.5.0` tag and GitHub Release;
5. verify source checksums, license display, and `CITATION.cff` binding;
6. register the final public release and close the remaining release-binding gate.
