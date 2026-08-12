# Stage 15A deterministic 250k scaling v0.1.2 orchestrate fix

Date: 2026-08-09

v0.1.1 stopped before any 250k replicate processing because the outer repair
shell launched the scaling runner without selecting one of its required modes.
The runner correctly rejected that invocation with:

`choose exactly one of --orchestrate, --replicate, --compare`

The v0.1.1 scientific/performance fixes, including dynamic 11e aggregate
expectations, remain unchanged.

v0.1.2 changes only:
- stage version / isolated result and QC roots
- outer invocation now explicitly uses `--orchestrate`

Validated 250k FASTQ/BAM input is reused. Mapping is not repeated.

Active pipeline modification: PROHIBITED
SSOT modification: PROHIBITED
Full 5.31M run: PROHIBITED
