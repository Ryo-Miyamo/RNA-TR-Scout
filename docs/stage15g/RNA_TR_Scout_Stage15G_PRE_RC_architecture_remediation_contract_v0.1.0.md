# RNA-TR-Scout Stage15G PRE-RC architecture remediation contract v0.1.0

Stage15G is limited to current-state metadata and governance consistency.

Required invariants:

- exact post-Stage15F SSOT/source/schema/release-gate baseline;
- exact Stage15C v0.1.6 and Stage15E evidence guards;
- historical rows are superseded, not silently deleted or rewritten;
- implementation lifecycle changes use exact implementation ID, path, and SHA bindings;
- the Stage15G execute-time postcheck requires the exact immediate post-remediation lifecycle counts and zero unclassified rows;
- the immutable SSOT rebuild insertion verifies only plan-owned Stage15G lifecycle rows, so scripts introduced by later versions may be newly DISCOVERED without retroactively invalidating this historical remediation;
- current_pipeline and schema v0.4.2 remain byte-identical;
- no scientific rerun, checkpoint rehash, package reconstruction, active-path promotion, Core Freeze, or Downloads cleanup;
- G24 remains OPEN for PRE_BIOLOGY even after PRE_RELEASE_CANDIDATE closes;
- G25-G30 and G32-G34 remain OPEN.

A successful SSOT rebuild and updater postcheck are both required. Any mismatch triggers rollback.
