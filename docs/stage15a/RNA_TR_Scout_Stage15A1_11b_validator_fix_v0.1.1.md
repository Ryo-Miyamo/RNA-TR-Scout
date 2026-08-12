# RNA-TR-Scout Stage 15A1 11b validator-wiring fix v0.1.1

Date: 2026-08-08  
Run: `ENCSR307SHM_pilot100k_mm2splice_v1`

## Failure

Stage 15A reference runner v0.1.0 completed the 11b alignment extraction, but
stopped during validation. The validator reached 181,323 checked rows and
stopped after collecting 100 errors. These began at the unmapped BAM records,
whose strand is represented by the explicit strand-enum value `.`.

The host-side effective v0.3 validator interpreted `.` as the global missing
token before testing whether it was an allowed enum value, and therefore
reported:

```text
strand: required value is missing
```

## Root cause

The Stage 15A0 contract ledger had already pinned validator v0.3.1, whose
narrow bugfix gives an explicit enum value precedence over the global missing
token. However, the Stage 15A v0.1.0 execution wrapper did not wire that pinned
validator into its isolated 11b copy. Its path-only patch left this assignment
unchanged:

```text
VALIDATOR="$SCHEMA_DIR/rnatr_v03_validate_tsv.py"
```

Consequently, the isolated replay invoked the obsolete host-side effective
validator instead of the pinned v0.3.1 validator. This was an execution-wrapper
integration error, not a BAM-content error and not a repeat-calling error.

## Corrective action

Stage 15A reference runner v0.1.1:

1. Preserves the failed v0.1.0 result and QC roots without modification.
2. Uses new isolated result/QC roots ending in `v0.1.1`.
3. Installs the frozen validator v0.3.1 under versioned Stage 15A metadata.
4. Verifies its SHA-256 is
   `10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9`.
5. Copies that validator into the v0.1.1 frozen-script directory.
6. Creates a newly named isolated 11b script and changes only the validator
   assignment after the PROJECT_ROOT path-plumbing patch.
7. Retains the full BAM, including unmapped records. It does not use
   `samtools view -F 4`, a mapped-only BAM, or any change to extraction logic.
8. Requires semantic equality with the frozen 100k 11b artifacts before
   advancing to 11d3.

## Safety status

```text
active pipeline modified     false
full 5.31M started           false
old v0.1.0 artifacts         preserved
BAM filtering                prohibited
scientific algorithm change  false
fix class                     execution-wrapper validator wiring
```
