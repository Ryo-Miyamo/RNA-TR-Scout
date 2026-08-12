# RNA-TR-Scout Stage 15A reference execution contract v0.1.0

## Purpose

This bundle performs the first isolated 100k BAM-to-final correctness run after the Stage 15A0 contract and caller-parity gates passed.

```text
100k mapping-complete BAM
  -> frozen 11b
  -> frozen 11d3
  -> frozen 11e
  -> promoted native general caller v0.4.1
  -> reference materializer v0.1.2
  -> schema v0.4.2 frozen table/package validators
  -> Stage 14 frozen-artifact and package regression comparison
```

It does **not** switch the active pipeline, update the SSOT, run legacy 11f–11k3, or start the full 5.31M dataset.

## Isolation

Outputs are written below:

```text
/mnt/intelssd/rnatr_project/results/15_stage15a_bam_to_final/
  ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.0/

/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/
  ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.0/
```

The active 11b/11d3/11e scripts are not edited. Contract copies are patched only at the `paths.env` source line and run against a shadow project root. The original BAM, BAI, catalogs, schema, caller runtime and candidate FASTQ are read-only inputs.

## Required gates

The runner refuses to start unless the host Stage 15A0 parity QC contains:

```text
audit_status                                  PASS
next_gate                                     READY_TO_FREEZE_STAGE15A_EXECUTION_BUNDLE
reference_vs_reused_exact_decompressed_match  true
package_suffix_keyed_semantic_match           true
package_missing_projection_ids                0
package_extra_projection_ids                  0
package_value_mismatch_projection_ids         0
active_pipeline_modified                      false
full_5_31m_run_started                        false
```

It also rechecks the host-side SHA-256 values captured by the Stage 15A0 preflight.

## PASS meaning

`stage15a_reference_100k.qc.tsv: audit_status=PASS` means:

- isolated 11b, 11d3 and 11e outputs are semantically identical to the frozen 100k artifacts;
- native caller output is identical to the Stage 14G deterministic reference;
- a second hash-seed run is identical;
- materializer v0.1.2 recreates the five schema v0.4.2 tables with expected cardinalities;
- frozen generic and cross-table package validators pass;
- the package is published by atomic rename only after validation;
- active pipeline files remain unchanged;
- the full 5.31M run has not started.

This is the **reference correctness lane**, not the final Stage 15A performance PASS. Its next gate is:

```text
BUILD_AND_RUN_STAGE15A_PERFORMANCE_CANDIDATE
```

## Runtime reporting

The runner records per-stage wall time and peak RSS. A naive 53.1x projection is reported for planning only. The 5.31M hard-ceiling gate remains open until the performance candidate and subsequent full-scale run are completed.
