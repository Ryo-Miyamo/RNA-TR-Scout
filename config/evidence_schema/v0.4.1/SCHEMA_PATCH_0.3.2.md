# RNA-TR-Scout evidence schema patch 0.3.2

Schema 0.3.2 is a minimal P3 integration patch.

## Added failure codes

- `ORIENTATION_INCONSISTENT_BRIDGE`
- `TARGET_ENTRY_NOT_PROJECTED`
- `HOMOPOLYMER_REVIEW`

## No new table columns

P3 evidence uses the existing fields and enums:

- `LEFT_ANCHORED_CENSORED_RIGHT`
- `RIGHT_ANCHORED_CENSORED_LEFT`
- `LEFT_ONLY_INTERNAL`
- `RIGHT_ONLY_INTERNAL`
- `lower_bound`
- `partial_internal`
- `no_call`

Bridge method details remain in `call_method`, `call_flags`,
`qc_flags`, `failure_code`, and `notes`.

## Guardrails

- Require query/reference normalization from mapped-block
  boundary toward target.
- Require a plus-orientation bridge.
- Require target-entry CIGAR projection before repeat sizing.
- Route mononucleotide A/T tracts to homopolymer review.
- Never emit exact allele length from one-flank P3 evidence.
- Never emit expansion or pathogenicity from P3 evidence alone.
