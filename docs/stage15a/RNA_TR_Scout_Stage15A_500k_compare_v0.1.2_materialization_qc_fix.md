# Stage 15A deterministic 500k compare amendment v0.1.2

Date: 2026-08-09

Replicate A and B of the 500k v0.1.1 run both completed successfully.

The final compare step failed only for:

`final_package::materialization.qc.tsv`

The semantic metric comparator already excluded:
- `stage_version`
- all `*_seconds`

but it did not exclude `performance_stage_version`.

That field is intentionally replicate-specific because the base performance
runner sets its stage version to the replicate-specific execution version.
It is provenance, not scientific/materialization content.

v0.1.2 therefore excludes:
- `stage_version`
- `performance_stage_version`
- all `*_seconds`

from materialization-QC semantic reproducibility comparison.

No BAM, FASTQ, assignment, projection, motif job, caller, materializer,
validator, or final package is rerun or modified.

The failed v0.1.1 comparison artifacts are preserved under
`compare_amendment_v0.1.2/`.

Active pipeline modification: PROHIBITED
SSOT modification: PROHIBITED
Full 5.31M run: PROHIBITED
