# RNA-TR-Scout General Repeat Caller Reference v0.2.0

## Status

Reference implementation milestone under the frozen General Repeat Caller Contract v0.1.0. This is not yet the production caller.

## Added in v0.2.0

- Retains the v0.1.0 single-motif cyclic error-aware alignment as the default regression baseline.
- Adds explicit compound-repeat segmentation when multiple strong motif segments are supported in the projected raw-read interval.
- Adds explicit interruption segmentation for strong same-motif repeat segments separated by a non-periodic internal gap.
- Reports `lps_exact_sequence_bp` separately from `lps_inferred_bp`.
- Materializes a small real P0/P1 raw-sequence regression fixture set and compares the new reference calls descriptively with the frozen caller.

## Important implementation constraint

The segmentation layer in reference v0.2.0 is intentionally conservative. A multi-segment interpretation replaces the v0.1.0 single-motif result only when explicit compound or interruption evidence is present. Otherwise the v0.1.0 single-motif result is retained. This protects existing simple-periodic regression behavior while compound semantics are developed.

## Not implemented yet

- production-grade residual/de-novo motif rescue for compound segments;
- exact censored-molecule interval/lower-bound inference;
- disease-locus benchmark suite and large simulation grid;
- production optimization / GPU implementation;
- large-cohort RNA technical calibration.

## Interpretation of real regression comparison

The 60-row real P0/P1 regression set is an engineering fixture, not a biological validation cohort. Differences from the frozen P0/P1 repeat estimate are recorded for inspection and do not constitute an acceptance threshold or a claim of improved biological accuracy.
