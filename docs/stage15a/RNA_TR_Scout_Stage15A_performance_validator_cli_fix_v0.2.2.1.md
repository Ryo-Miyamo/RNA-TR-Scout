# Stage 15A performance validator CLI fix v0.2.2.1

Date: 2026-08-08

## Failure classification

Stage 15A performance v0.2.2 completed partitioning, 11b, 11d3, the shared-catalog
motif-job builder, caller/materializer pipelining, global merge, gzip, and all five
generic table validators. It stopped before publication because the new parallel package
validator passed `--package-dir` to both frozen components.

The frozen components do not share a CLI:

- `rnatr_v041_validate_package.py`: `--package-dir PACKAGE`
- `rnatr_v042_validate_flank_uniqueness.py`: `--input PACKAGE/read_evidence.tsv.gz`

The v0.2.2 failure was therefore an execution-wrapper CLI wiring defect, not evidence
or package semantic failure.

## v0.2.2.1 change

v0.2.2.1 gives each SHA-pinned frozen component its correct argument contract while
retaining parallel execution. It reruns the full isolated 100k performance lane in a new
root to obtain a clean end-to-end timing measurement. The failed v0.2.2 roots remain
preserved.

The original frozen v0.4.2 package wrapper is still run after publication, and the
missing-artifact negative parity fixture remains mandatory.

## Unchanged constraints

- active pipeline: unchanged
- SSOT: unchanged
- scientific caller: unchanged
- materialization/schema semantics: unchanged
- full 5.31M: not run
