# RNA-TR-Scout Stage 15A reference-lane SSOT registration v0.1.0

## Purpose

This update records the completed **Stage 15A v0.1.3 isolated 100k BAM-to-final correctness reference** in the RNA-TR-Scout Single Source of Truth (SSOT).

The registered result is deliberately narrower than production activation:

- correctness/reference lane: **PASS**
- schema v0.4.2 exact logical package parity: **PASS**
- active pipeline switch: **NO**
- Stage 15A performance validation: **OPEN**
- full 5.31M-read execution: **NOT RUN**

## Evidence contract

The updater requires the frozen Stage 15A v0.1.3 evidence and verifies the exact SHA-256 of:

- `stage15a_reference_100k.qc.tsv`
- `stage15a_reference_timing.tsv`
- `package_reference/package_manifest.tsv`
- the Stage 15A v0.1.3 runner
- schema v0.4.2 TSV and package validators

It also validates every one of the ten package artifacts against its manifest, including path containment, byte size, data-row count, and SHA-256.

## SSOT mutation contract

The updater:

1. validates the existing SSOT and the frozen 11-stage active-pipeline contract;
2. acquires an exclusive SSOT lock;
3. backs up `rnatr_ssot.py`, `rnatr_ssot.sqlite`, `CURRENT_STATE.md`, and exports;
4. adds a source-as-snapshot Stage 15A registration block immediately before the unique `current_metrics` anchor;
5. atomically rebuilds and validates the SSOT;
6. requires the active-pipeline snapshot to remain byte-identical;
7. registers the Stage 15A implementation with lifecycle `PROVISIONAL`, never `ACTIVE`;
8. restores the prior SSOT state on any failure.

## Registered state

The new stage key is:

```text
15A_BAM_TO_FINAL_REFERENCE
```

The implementation is:

```text
impl_stage15a_reference_v0_1_3
lifecycle_status = PROVISIONAL
```

The blocking next gate remains:

```text
BUILD_AND_RUN_STAGE15A_PERFORMANCE_CANDIDATE
```

The reference-lane runtime is recorded as 333.981925 seconds for 100k reads, with a naive 5.31M projection of 295.724073 minutes. This is a performance warning for the reference architecture, not a completed production benchmark.

## Explicitly prohibited actions

This updater does **not**:

- activate schema v0.4.2 in `current_pipeline`;
- run the Stage 15A performance candidate;
- run the full 5.31M-read sample;
- modify BAM, FASTQ, catalog, or Stage 15A evidence files;
- use or modify T9 storage;
- infer biological truth, pathogenicity, or personal DNA genotype.
