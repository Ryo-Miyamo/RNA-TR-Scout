# RNA-TR-Scout General Repeat Caller Contract v0.1.0

## Status

Frozen architecture contract for the next implementation phase. The existing P0/P1 simple-periodic pipeline remains the correctness/regression reference and is not replaced in-place.

## Development scope decision

The six equalized fetal-brain 100k-read datasets are an engineering validation panel only. They establish that the frozen pipeline can replay across multiple samples and reveal gross implementation artifacts. They are not large enough to estimate precise locus/motif/length/support-specific RNA technical distributions. Population-scale RNA calibration is deferred until the caller is stable and sufficiently fast to process many samples.

## Measurement contract

1. **Locus assignment and repeat measurement remain separate.** Splice-aware genomic alignment and catalog-guided flanks assign a read to a locus. Repeat length is measured from raw-read sequence, not from the BAM CIGAR.
2. **Catalog motifs are priors, not immutable truth.** The caller must evaluate motif rotations and reverse complements, collapse harmonic/primitive equivalents, and later allow de-novo motif hypotheses.
3. **The projected catalog interval is a soft boundary prior.** Repeat boundaries are re-estimated on the raw-read window and may extend beyond or contract within the catalog interval when sequence evidence supports it.
4. **The reference sequence model is an error-aware cyclic repeat alignment.** The implementation uses a cyclic motif state model with match/substitution, read insertion, and motif deletion paths. Production code may replace the implementation, but must preserve this measurement semantics and regression output.
5. **SPAN and censored molecules have different sizing semantics.** Two-flank SPAN molecules can yield a bounded total tract length. LEFT/RIGHT/BOTH-censored molecules yield observed repeat sequence and lower-bound/interval information only; they must not be coerced into exact allele lengths.
6. **Compound structure is explicit.** Final implementation must support multiple repeat motifs within one tract, with a switch penalty/segmentation model rather than forcing one motif across the whole tract.
7. **Interruptions are explicit.** Internal non-primary-motif sequence must be represented as interruption segments when the flanking repeat evidence supports tract continuity; it must not automatically terminate the repeat.
8. **Two LPS concepts are retained.** `lps_exact_sequence_bp` is exact sequence-level uninterrupted periodicity; `lps_inferred_bp` is error-aware motif-state continuity. They must not be silently conflated, especially for ONT reads.
9. **Length, motif composition, and evidence quality remain molecule-level outputs.** Locus-level summaries are derived later and must retain the single-read evidence.
10. **Pathogenicity is not inferred from the RNA caller.** Disease thresholds and DNA population distributions are context layers only. RNA evidence never implies a personal DNA genotype.

## Motif hypothesis contract

The final caller must construct a motif hypothesis set from:

- catalog motif(s), all cyclic rotations, and reverse-complement equivalents;
- primitive-motif collapse to avoid harmonic aliases such as `CAGCAG` versus `CAG`;
- de-novo periodic candidates from the projected raw-read interval, configurable to at least periods 1-50 by default, while retaining catalog motifs longer than that;
- later, residual/segment-specific alternative motif hypotheses for compound tracts.

The selected motif must be reported in canonical form together with the oriented motif used in the read.

## Boundary and alignment contract

The conceptual model contains background and cyclic repeat states. A practical reference implementation may use a local cyclic dynamic program, but the final caller must preserve:

- local start/end inference on raw-read coordinates;
- substitution and indel tolerance;
- soft, not hard, use of projected catalog boundaries;
- flank geometry as an independent confidence layer;
- alternative-motif score comparison;
- deterministic tie-breaking and reproducible output.

## Required molecule-level outputs

At minimum:

- locus/read/projection identifiers;
- evidence geometry and censoring state;
- canonical motif and oriented motif;
- motif source (`CATALOG`, `DENOVO`, later `COMPOUND_SEGMENT`);
- raw-read tract start/end when bounded;
- observed tract bp;
- exact length or lower bound/interval semantics;
- motif-path units;
- matches/mismatches/insertions/deletions;
- alignment score, normalized score, purity/error fraction;
- interruption segments;
- compound motif segments;
- `lps_exact_sequence_bp` and `lps_inferred_bp` when implemented;
- second-best/alternative score information;
- locus-assignment confidence kept separate from repeat-measurement confidence.

## Implementation sequence

### Reference v0.1.0 — now

- single-motif cyclic error-aware raw-read alignment;
- catalog prior plus preliminary de-novo hypotheses;
- primitive/rotation/reverse-complement normalization;
- raw-read boundary re-estimation;
- synthetic fixtures and deterministic self-test.

### Next

1. compound/interruption segmentation;
2. exact-sequence and error-aware LPS;
3. stronger de-novo motif rescue and harmonic suppression;
4. censored-molecule interval/lower-bound implementation;
5. real P0/P1 regression fixture materialization and comparison against the frozen caller;
6. disease-locus and simulation benchmark;
7. only after caller semantics stabilize: profiling/optimization of the heavy 11f/11h-style computation, including compiled CPU and GPU suitability;
8. only after the caller is stable and fast: large-cohort RNA technical/population calibration.

## Acceptance principle

A faster or more sophisticated implementation is accepted only if it reproduces the frozen reference semantics on regression fixtures or if a deliberate contract change is documented. Performance optimization must not silently change biological call meaning.
