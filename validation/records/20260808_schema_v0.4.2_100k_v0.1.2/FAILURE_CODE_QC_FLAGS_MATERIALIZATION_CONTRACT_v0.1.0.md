# Failure code, QC flags, and materialization status contract v0.1.0

## Purpose
These fields describe different dimensions and must not be forced to contain the same reason.

## `failure_code`
A single primary read/evidence failure classification. It is intentionally singular.
For a CALLED repeat whose caller-native `call_status` is `LOW_CONFIDENCE`,
the primary failure may be `GENERAL_CALLER_LOW_CONFIDENCE`.

## `qc_flags`
Non-exclusive conditions. Multiple simultaneous issues are retained here.
For the 18 frozen 100k cases, both `CALLER_LOW_CONFIDENCE` and
`PRIOR_OVERLAP_NONPOSITIVE` are present.

## `materialization_status`
Controls whether a caller attempt is normalized as a locus-associated `repeat_event`.
A CALLED attempt with nonpositive overlap to the projected locus prior is
`CALLED_NOT_RETAINED`, remains losslessly present in `general_repeat_calls`,
and is not silently promoted to a target-locus repeat event.

## Consequence
`failure_code=GENERAL_CALLER_LOW_CONFIDENCE` does not erase the locus-anchoring
problem because the latter remains explicit in both `qc_flags` and
`materialization_status`.

The 100k data demonstrate that LOW_CONFIDENCE alone does not prevent eventization:
6,307 CALLED attempts are LOW_CONFIDENCE; 6,289 are eventized and only the 18
with nonpositive prior overlap are not.

No pathogenicity, DNA genotype, or biological-repeat absence is inferred from
these software evidence states.
