# Stage 15A deterministic 250k scaling v0.1.1 fix

Date: 2026-08-09

The v0.1.0 250k input preparation, mapping, nested-100k alignment parity,
11b, candidate FASTQ extraction, and 11d3 passed.

The failure occurred in the shared-catalog fast 11e builder because it retained
100k-only aggregate guards (388,571 rows and 79,176 reads).

v0.1.1 replaces those fixed fixture totals with the sum of the validated shard
manifest expected_rows / expected_reads fields. Scientific assignment,
projection, motif, caller, materialization, and schema semantics are unchanged.

The already validated 250k FASTQ/BAM input is reused. Mapping is not repeated
and remains outside the BAM-to-final timer. Failed v0.1.0 scaling artifacts are
preserved.

Active pipeline modification: PROHIBITED
SSOT modification: PROHIBITED
Full 5.31M run: PROHIBITED
