# Stage 15A performance v0.2.0.1 escape fix

Date: 2026-08-08

v0.2.0 stopped before partitioning because the Python patch anchor intended to
match shell text `sort -t $'\t' ...` encoded `\t` as a literal TAB at runtime.
The active 11e source correctly contains backslash+t. Therefore the anchor count
was zero.

v0.2.0.1 changes only the patcher's string escaping and uses new isolated
result/QC roots. Scientific semantics, active pipeline, SSOT, caller,
materializer, schema, and the 5.31M prohibition are unchanged.

The failed v0.2.0 roots are preserved.
