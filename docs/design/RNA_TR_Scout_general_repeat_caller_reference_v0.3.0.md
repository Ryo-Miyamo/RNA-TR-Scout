# RNA-TR-Scout general repeat caller reference v0.3.0

## Scope

Reference v0.3.0 adds the remaining pre-benchmark semantics needed after the v0.2.0 compound/interruption/LPS prototype. It is still a correctness-oriented Python reference, not a production-speed implementation.

## Boundary anchoring

The projected locus interval remains a soft prior, but motif identity and tract selection must stay anchored to that locus. The v0.2.0 real-read audit showed that the largest regression driver was tract-boundary extension (21/60 rows), with motif selection/de-novo differences (11/60) and projection-window edge/context effects (5/60) also important.

v0.3.0 therefore selects the primary motif from evidence inside the projected locus core and only then allows raw-read tract extension. A stronger remote periodic tract in the surrounding sequence must not hijack the locus. Boundary extension/contraction remains allowed when the selected tract continues through the locus core.

## Censoring and sequence context

Censoring is determined from explicit evidence geometry, not inferred from a projection-window edge.

- `SPAN`: may produce `EXACT_SPAN` when the repeat is bounded in the available sequence context.
- `LEFT_CENSORED`, `RIGHT_CENSORED`, `BOTH_CENSORED`: report observed repeat sequence as a lower bound only; no exact allele length and no finite upper bound are invented.
- A tract touching an artificial `PROJECTION_WINDOW` edge is `CONTEXT_LIMITED_LOWER_BOUND`, not biological censoring.
- `FULL_READ` and `PROJECTION_WINDOW` are therefore explicit and separate sequence-context values.

The reference outputs `exact_repeat_bp`, `lower_bound_bp`, `interval_lower_bp`, and `interval_upper_bp`; the upper bound is only populated when the length is exact.

## De-novo rescue

De-novo motif search is a rescue rather than an unconditional competitor. If a catalog motif explains most of the projected core with adequate purity, expensive all-period de-novo search is skipped. If catalog fit is poor or incomplete, anchored multi-scale/residual hypotheses are generated through period 50, with primitive/rotation/reverse-complement canonicalization retained.

This both protects catalog-guided locus semantics and avoids unnecessary compute on ordinary catalog-supported reads.

## Alternative motif evidence

The reference reports the second-ranked canonical motif, its score, and the primary-minus-alternative score when available. This is measurement-confidence information and is separate from locus-assignment confidence.

## Compatibility

v0.3.0 must preserve:

- the Stage 12A simple-periodic synthetic regression acceptance;
- the Stage 12B compound/interruption/LPS specialized fixtures;
- explicit exact versus inferred LPS fields;
- molecule-level raw-read outputs.

The 60-row real P0/P1 fixture remains a software-regression dataset only. Agreement with the frozen P0/P1 caller is descriptive and is not treated as biological truth or an accuracy threshold.

## Next gate

After v0.3.0 passes synthetic, compound/interruption, censoring/de-novo, and real-read completion tests, the next development gate is disease-locus plus broad simulation benchmarking. Performance profiling/optimization (especially the heavy 11f/11h-style periodic computation, compiled CPU, and GPU suitability) follows once benchmark semantics are stable.
