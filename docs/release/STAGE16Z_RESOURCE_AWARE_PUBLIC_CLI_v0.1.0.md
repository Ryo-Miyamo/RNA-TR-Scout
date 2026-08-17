# Stage16Z resource-aware public CLI v0.1.0

Date: 2026-08-17

## Status

**IMPLEMENTATION_CANDIDATE — VALIDATION PENDING**

Stage16Z addresses the release-readiness resource-detection and adaptive Core scheduling gaps without changing the frozen scientific Core.

## Scope

The public CLI now detects and records:

- hostname;
- logical CPU count;
- total RAM and currently available RAM;
- selected temporary directory;
- free space at the temporary directory;
- free space at the relevant working filesystem;
- source FASTQ read count used for scheduling.

`rnatr-scout system-info` exposes the detected host state directly.

For `rnatr-scout run`, omitted Core scheduling values are selected by the versioned policy `rnatr_resource_policy_v0.1.0`. The resulting plan is written to `work/resource_plan.json` and reused on resume.

## Scheduling policy

The automatic policy is conservative and is anchored to the already validated execution shapes rather than claiming a new peak-memory measurement.

Expected profiles on a 24-logical-CPU host with ample RAM are:

| input scale | shards | concurrent Core units | caller workers/unit |
|---:|---:|---:|---:|
| Tier2 ~14k | 1 | 1 | 2 |
| Tier3 100k | 12 | 3 | 2 |
| 500k | 12 | 12 | 2 |
| 5.31M | 144 | 12 | 2 |

CPU and currently available RAM can reduce concurrent Core units. The policy uses a conservative planning allowance of 6 GiB per active Core unit and 70% of the selected RAM budget. This is a scheduling guard derived from release-engineering experience; it is **not** a claim that true full-scale peak RAM is exactly 6 GiB per unit.

## Manual overrides

The existing low-level Core controls remain accepted:

- `--shards`
- `--max-unit-workers`
- `--caller-workers`

Additional planning controls are:

- `--threads`: Core scheduling CPU budget;
- `--memory-gb`: Core scheduling RAM budget;
- `--tmp-dir`: temporary-directory override;
- `--force-resource-overrides`: explicit bypass of conservative CPU/RAM override guards.

All supplied overrides are recorded in the resource-plan JSON.

## Important mapping boundary

`--threads` in Stage16Z is a **Core scheduling CPU budget**. The current validated ONT-cDNA mapper remains separately versioned and retains its existing fixed minimap2/samtools thread profile. Stage16Z does not silently change validated mapping semantics or performance settings.

Mapping-thread optimization therefore remains a separate post-Freeze performance concern, not part of the Stage16Z G26/G27 Core scheduling closure.

## Disk-space boundary

Stage16Z detects and records free space but does not invent a new full-scale disk hard minimum. The approximately 5.31M-read true peak disk usage is still not formally benchmarked. Fixed large-run disk recommendations remain blocked on the dedicated peak-disk benchmark.

## Resume contract

A new run records `work/resource_plan.json`. Resume reuses the recorded shard/concurrency plan. Conflicting scheduling or temporary-directory overrides are rejected rather than silently repartitioning a completed run.

## Required validation before acceptance

1. syntax and unit tests;
2. Tier2 automatic scheduling must select the expected small profile and retain exact five-table parity;
3. Tier3 automatic scheduling on the primary validated host must retain exact five-table parity or be explicitly validated by an equivalent fixed test;
4. lower-RAM synthetic planner tests must reduce concurrency rather than exceed the conservative memory fraction;
5. independent second-machine fresh clone/environment/network-resource installation must run an exact Tier2 public workflow and resume successfully;
6. frozen Core root and scientific five-table identities must remain unchanged.

Stage16Z does not itself close the separate full-scale peak-disk benchmark or public-RC Pro cross-cut audit.
