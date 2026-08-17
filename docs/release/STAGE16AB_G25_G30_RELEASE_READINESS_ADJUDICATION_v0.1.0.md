# Stage16AB G25-G30 release-readiness adjudication v0.1.0

Date: 2026-08-17

## Status

**PASS_WITH_SCOPE — G25-G29 CLOSED; G30 TESTED/RECOMMENDED COMPLETE, EMPIRICAL MINIMUM UNRESOLVED NONBLOCKING**

This record reconciles the original G25-G30 release-readiness requirements with the post-Freeze implementation and validation evidence.

## G25 — automatic reference bootstrap

**PASS**

The standard installer uses version-pinned GENCODE source URLs and the public compact-catalog release asset, verifies expected SHA-256 identities, supports resumable network download behavior, builds/validates derived reference resources, and records installation provenance.

Evidence includes successful fresh network installation on both the primary release-engineering path and the independent second Linux x86-64 host.

## G26 — CPU/RAM/output/tmp resource detection

**PASS_WITH_DEFINED_SCOPE**

The public CLI detects and records logical CPU count, total and available RAM, selected temporary directory, temporary-directory free space, and relevant working-filesystem free space.

`rnatr-scout system-info` exposes the detected state. `rnatr-scout run` records the selected resource plan.

The original phrase "output resource detection" is satisfied as working-filesystem free-space detection/provenance; it is not interpreted as a claimed full-scale peak-disk minimum because that benchmark remains open.

## G27 — memory-aware automatic shard/concurrency selection

**PASS_WITH_DEFINED_SCOPE**

`rnatr_resource_policy_v0.1.0` automatically selects Core shard/concurrency settings from input scale, logical CPU budget, and available/selected RAM budget. Manual overrides are accepted with provenance and conservative guards.

Validated actual execution:

- Tier2 on `deeplearningboxii`: automatic `1 / 1 / 2` profile, exact 5/5 scientific parity;
- Tier3 100k on the primary host: automatic `12 / 3 / 2` profile, exact 5/5 scientific parity;
- synthetic lower-RAM policy tests reduce concurrency.

Mapping-thread tuning remains separately versioned and outside this Core-scheduling closure.

## G28 — reproducibility across supported hardware/concurrency profiles

**PASS_WITH_SCOPE**

Exact scientific parity has been reproduced on the second Linux x86-64 host, including native-kernel execution in prior cross-hardware validation and independent fresh-install Tier2 execution under automatic resource selection.

This is a supported-scope Linux x86-64 claim, not arbitrary hardware portability.

## G29 — clean-machine clone-to-setup-to-test reproducibility

**PASS**

`deeplearningboxii` completed:

1. fresh authenticated private-GitHub clone;
2. fresh isolated conda environment;
3. fresh network reference installation;
4. public compact-catalog network installation;
5. resource detection and automatic Core scheduling;
6. exact Tier2 scientific-output validation; and
7. `SECOND_RESUME_NOOP`.

The fresh clone remained Git-clean after validation.

## G30 — empirical minimum / recommended / tested hardware profile

**PASS_WITH_SCOPE_AMENDMENT**

The requirement is decomposed explicitly:

- tested hardware profile: **established**;
- recommended release-scale hardware profile: **established**;
- empirical minimum hardware profile: **not established**.

Tested Linux x86-64 hosts have 24 and 36 logical CPUs with approximately 128 GB RAM. The current recommended approximately-five-million-read profile is about 24 or more logical CPU threads, approximately 128 GB RAM, and fast local SSD/NVMe storage.

For mapping and smaller runs, 32 GB RAM remains a practical target, but it is **not** claimed as sufficient for the current five-million-read workflow.

No lower empirical CPU/RAM minimum is invented from untested configurations. The resource-aware planner reduces Core concurrency when resources are lower and records the actual plan.

The unresolved empirical minimum is accepted as **nonblocking for the current v0.5.0 release-readiness path**, provided user-facing documentation continues to distinguish tested/recommended values from unmeasured minima.

Full-scale peak disk remains a separate open benchmark and is not silently converted into a minimum-disk claim.

## CLEAN_INSTALL_INTERNAL_BETA adjudication

With G25-G29 PASS and G30 documented accurately with the scoped minimum amendment, the independent clean-machine/internal-beta reproducibility question is **CLOSED** for the currently tested Linux x86-64 ONT-cDNA scope.

This closure does not close:

- `FULLSCALE_PEAK_DISK_BENCHMARK`;
- `PUBLIC_RC_PRO_CROSSCUT_AUDIT`;
- immutable public v0.5.0 release/tag/citation binding.

## Evidence identities

- Stage16Z static/policy preflight SHA-256: `b85bd0ca8addd88f2d5fd68f8ee49a5765bfe1a4d1eb6c6adbce410f85bf85cb`
- Stage16Z Tier3 automatic-parity result SHA-256: `b1c166f60ed5ae9266d5cccc5dac573e09865d67ea50b0b0c52af411981ce02a`
- Stage16AA independent-machine result SHA-256: `38ba94527d42bb08e13e600ea7c41ef4768c1571a70b6d1c7e50ab9f82a544f1`
- immutable Core Freeze root: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
