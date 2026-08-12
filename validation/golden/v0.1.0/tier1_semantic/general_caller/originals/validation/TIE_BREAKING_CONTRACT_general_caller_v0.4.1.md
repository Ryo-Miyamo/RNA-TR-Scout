# RNA-TR-Scout deterministic orientation tie-breaking contract v0.1.0

Scope: general repeat caller v0.4.1 and its frozen v0.2.1 primitives.

1. Existing score/ranking semantics are unchanged.
2. `_best_oriented_alignment` continues to maximize `(score, aligned_read_bp, purity)`.
3. `_periodic_agreement` continues to maximize periodic agreement.
4. Only an otherwise exact orientation tie is newly specified:
   - evaluate input/canonical motif orientation first;
   - evaluate its reverse complement second;
   - if both are identical, evaluate once;
   - exact ties retain the first (input/canonical) orientation.
5. Hash-table/set iteration order is never a semantic input.
6. This contract does not assert that historical v0.4.0 outputs are truth.
   Validation priority remains truth-bearing simulation > deterministic algorithm contract > software regression.
