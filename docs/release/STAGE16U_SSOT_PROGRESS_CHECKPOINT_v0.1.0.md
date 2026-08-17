# Stage16U SSOT release-progress checkpoint v0.1.0

Date: 2026-08-17

## Decision

**PASS_WITH_STAGE16R_EVIDENCE_BINDING_PENDING**

Stage16U reconciles the post-Freeze release-engineering state across the canonical SSOT database, Git main, and formal Stage16 validation/documentation records. It does not alter the frozen scientific Core.

## Authoritative state registered

- Git main at checkpoint start: `be1de2ecdcaa681e3a3424486d340280001b0bf0`
- immutable Local Core Freeze root: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
- Stage16Q public CLI integration: PASS from Git ancestry
- Stage16S cross-hardware scientific parity: PASS with tested Linux x86-64 scope
- Stage16T user-facing documentation: PASS, owner review accepted
- Stage16R fresh end-to-end: **EVIDENCE_BINDING_PENDING**, not asserted PASS by this checkpoint

The exact Stage16U result JSON reported by the canonical project SSOT update has SHA-256:

`7c4565c6ca751c6c20af7ac6a4566464cb80c65cef46e20291ce97478d66b1df`

Canonical SSOT SQLite SHA-256 changed from:

`15af9a7fa1bfb8a892dd55d07e2aac1245ff65f38b3f3d9ab21dc70ba287a7f9`

to:

`f2a19e219d8aae94df167db2157fe03f7870c300c458397942b302dfdb3162db`

before the durable-evidence path finalization step.

## SSOT validation after update

The regenerated SSOT reported PASS for:

- SQLite integrity
- foreign-key check
- active pipeline mode = `GENERIC_CORE`
- one active generic Core implementation and zero active legacy P0/P1 implementations
- active implementation paths present and existing
- current views populated
- current final-package validator = evidence schema v0.4.2 package validator

The post-update current views contained 46 active decisions, 22 active limitations, 13 open questions, and 149 current metrics at the initial Stage16U checkpoint.

## State-drift remediation

The pre-Stage16U Git-exported SSOT snapshot was generated on 2026-08-12 and predated the Stage16 release-engineering work.

Stage16U therefore superseded current-state records that incorrectly continued to describe cross-hardware/clean-install work as wholly uncompleted after Stage16S and replaced them with scoped current statements.

The following stale limitations were confirmed absent from the regenerated `current_known_limitations` view:

- `GENERIC_ACTIVE_PATH_NOT_CLEAN_INSTALL_OR_CROSS_HARDWARE`
- `STAGE15E_SAME_MACHINE_NOT_CROSS_HARDWARE`
- `LOCAL_CORE_FREEZE_NOT_PUBLIC_GIT_RELEASE`

## Current release-engineering limitations registered

Stage16U explicitly keeps the following open rather than inflating release readiness:

- public v0.5.0 RC/final release is not complete;
- compact validated catalog-bundle public URL is not finalized;
- final full-network fresh-install RC validation remains pending;
- full-scale peak disk usage has not been formally benchmarked;
- complex caller strategy coverage remains incomplete for specialized strategies.

The caller-scope record reflects the current production adapter: automatic caller execution is limited to `SIMPLE_PERIODIC_SCAN`, `MULTI_MOTIF_PERIODIC_SCAN`, and `LONG_UNIT_21_TO_100_PERIODIC_SCAN`. VC, IUPAC-degenerate, complex disease-region, >100-bp repeat-unit, no-motif and unsupported-symbol strategies are retained as explicit unsupported/specialized scope rather than silently treated as negative repeat calls.

## Public-RC governance registered

Before declaring public v0.5.0 RC, one Pro-level cross-cut audit is required after the remaining High-mode release-engineering tasks stabilize. The audit will cover:

- Freeze exact state and contract consistency;
- current Git state and active production path;
- reference/catalog/mapping/CLI/install paths;
- golden and validation evidence;
- cross-hardware scope;
- researcher-facing documentation and release claims;
- obsolete-path contamination and implementation-state inflation; and
- SSOT/Git/docs state drift.

Normal implementation, installation, benchmarking, SHA comparison and validator-driven release engineering may continue in High mode until that checkpoint unless a Freeze-contract change, new caller semantics, unexplained scientific mismatch, or golden-output discrepancy requires escalation.

## Stage16R handling

Stage16R is deliberately not promoted to PASS in this checkpoint because the authoritative formal fresh end-to-end result artifact has not yet been bound into the SSOT/Git release record.

The required next action is to locate the original Stage16R result, verify its identity and scope, and register it only if the original evidence supports PASS.

## Durable evidence note

The initial Stage16U `run_stages` row pointed to the temporary updater script used during execution. A follow-up finalizer was added to bind that row to the durable Stage16U result JSON by the exact SHA-256 above, then regenerate the SSOT current views. This is evidence-path hygiene only and does not change the scientific or release-readiness conclusions above.
