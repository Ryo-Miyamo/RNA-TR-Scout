# Stage 15A deterministic 500k scaling v0.1.1 API wiring fix

Date: 2026-08-09

The v0.1.0 deterministic 500k input preparation and mapping passed, including
nested 250k alignment parity.

Replicate A also passed:
- 11b
- candidate FASTQ extraction
- 11d3
- shared-catalog fast 11e

The run then stopped before the native caller because the 500k scaling runner
called the frozen base runner as:

`run_timed(..., extra_env=...)`

while the frozen v0.2.2.1 base-runner API is:

`run_timed(..., env_extra=...)`

v0.1.1 changes only those two keyword arguments and uses new isolated
result/QC roots. Scientific caller, schema, materializer, run-ID contract,
checkpoint contract, and benchmark semantics are unchanged.

The validated 500k FASTQ/BAM and mapping are reused. Mapping remains outside
the BAM-to-final timer. The failed v0.1.0 scaling artifacts are preserved.

Active pipeline modification: PROHIBITED
SSOT modification: PROHIBITED
Full 5.31M run: PROHIBITED
