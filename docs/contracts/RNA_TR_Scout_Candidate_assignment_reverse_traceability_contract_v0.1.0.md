# RNA-TR-Scout candidate-assignment reverse-traceability contract v0.1.0

## Status

**PENDING_STAGE15R_READ_ONLY_INSPECTION_BEFORE_FINAL_CORE_FREEZE_GO**

This contract is installed before final Freeze registration so the requirement cannot be
lost. Stage15R must add checksum-bound inspection evidence and update the final Freeze
Packet before G24/G32–G34 closure.

## Observed full-scale multiplicity

- input reads: 5,312,696
- candidate reads: 4,212,263
- candidate assignment rows: 20,656,258
- mean assignments per candidate read: approximately 4.90

These aggregate counts are accepted technical evidence, not a complete biological
interpretation of multiplicity.

## Long-term reverse-trace requirement

For a representative Core result or checksum-bound historical lineage, it must remain
possible to explain logically:

`read_id`
-> target/locus candidate assignment
-> assignment basis and geometry
-> read/genome projection
-> repeat window and motif evidence
-> caller result and repeat length/purity/LPS/status.

The reconstruction may use frozen public IDs, portable manifest/resource provenance,
checksummed lineage evidence, and an explicit reconstruction procedure.

## Implementation-flexibility boundary

Historical internal names and paths such as 11b/11d3/11e are not immutable public
contracts. Stage fusion, streaming, I/O reduction and other internal refactors remain
allowed when the reverse-trace contract and golden scientific output are preserved.

## Required Stage15R sanity check

Before final Core Freeze GO, produce a read-only human inspection report with stratified
representative reads from multiplicity 1, 2–5, 6–10, 11–20 and >20, including median and
high-tail examples plus major-locus, catalog-overlap, proximity/padding and suspected
ambiguity examples.

Where available, show raw-read coordinates, BAM/splice structure, candidate targets,
normalized locus/catalog source, overlap/proximity basis, projection/window, motif, caller
result, repeat length, purity, LPS and status.

Use conceptual interpretations where supported:

- DISTINCT_LOCUS
- OVERLAPPING_TARGET
- CATALOG_REDUNDANCY_OR_ALIAS
- PROXIMITY_OR_PADDING
- MOTIF_RELATED_MULTIPLICITY
- ASSIGNMENT_AMBIGUITY
- UNRESOLVED

Only a material, unexplained assignment/provenance/scientific-design problem blocks Freeze.
A production viewer, complete automatic taxonomy and molecule-level canonicalization remain
post-Freeze work.
