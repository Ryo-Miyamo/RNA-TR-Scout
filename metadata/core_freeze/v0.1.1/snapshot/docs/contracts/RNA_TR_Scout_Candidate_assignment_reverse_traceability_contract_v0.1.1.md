# RNA-TR-Scout candidate-assignment reverse-traceability contract v0.1.1

## Status

`ACCEPTED_STAGE15R_PASS_WITH_SCOPE_BIOLOGY_DEFERRED`

This version supersedes the pending status of v0.1.0 after Stage15R representative-read
inspection and Pro adjudication.

## Full-scale multiplicity

- input reads: 5,312,696
- candidate reads: 4,212,263
- candidate-assignment rows: 20,656,258
- mean assignments per candidate read: approximately 4.90

These are technical assignment counts, not counts of independent biological repeat events.

## Accepted Stage15R evidence

- representative reads: 57
- selected assignment rows: 733
- complete assignment-to-evidence chains: 733/733
- unresolved reverse-trace failures: 0
- Freeze blockers: 0
- R2 evidence SHA-256:
  `b68e4a8d078b371b72de3870fa98dc2808195f2f048aec76d8920158448c9851`

Primary adjudication classes were `DISTINCT_LOCUS`, `PROXIMITY_OR_PADDING`,
`ASSIGNMENT_AMBIGUITY`, `OVERLAPPING_TARGET` and `CATALOG_REDUNDANCY_OR_ALIAS`.
`UNRESOLVED` was zero.

`ASSIGNMENT_AMBIGUITY` records traceable technical ambiguity, including low-confidence
secondary-alignment candidates; it does not by itself assert a Core defect.

## Frozen logical reverse trace

It must remain possible to reconstruct logically:

`read_id`
-> candidate target/locus assignment
-> assignment basis/geometry
-> read/genome projection
-> repeat window/motif evidence
-> caller result
-> materialized repeat length/purity/LPS/status.

The reconstruction may use stable IDs, portable result/local resource bindings, formal Core
outputs and checksum-bound lineage evidence.

## Implementation flexibility

Historical names such as 11b/11d3/11e and their internal filenames are not permanent public
contracts. Refactoring, fusion, streaming and alternate physical storage remain allowed only
when this logical trace, scientific parity, validator guarantees and golden behavior are
preserved.

## Biology boundary

Biological weighting of distinct loci, secondary alignments, catalog aliases,
overlap/proximity/padding and molecule independence is post-Freeze biology/interpretation
work. A production viewer and complete automatic taxonomy are not required by this Core
Freeze.
