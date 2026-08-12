# RNA-TR-Scout G31 full-scale row-expansion and candidate-entry audit v0.1.0

## Core Freeze role

G31 is a blocking Core Freeze gate. A schema/package validator PASS is necessary but not sufficient. This audit examines whether the full 5.31M result's 20,656,258 attempt/evidence rows represent intended lossless candidate multiplicity or over-expansion.

## Explicit candidate-entry-rate question

The audit explicitly evaluates the observed 11b candidate rate:

- input reads: 5,312,696
- candidate reads: 4,212,263
- candidate read rate: 79.286731%

The reason decomposition includes exact-overlap versus padding-only candidates, primary/supplementary/secondary support, catalog source combinations, raw and plus/minus-500-bp catalog coverage, exact-coordinate aliases, raw/padded overlap clusters, and 100k/500k/full scale stability. Genome-wide catalog coverage is contextual only because RNA alignments are concentrated in transcribed regions.

## Lineage

The audit verifies key-level conservation across 11b assignment, 11d3 projection, 11e job preparation, caller attempts, general_repeat_calls, and read_evidence. It separately measures within-job canonical motif hypotheses and caller hypothesis counts, so one job row is not incorrectly treated as one motif hypothesis.

## Decisions

- Hard lineage/ID/full-row duplicate violations cause `FAIL_OVEREXPANSION_OR_LINEAGE`.
- If hard checks pass, concentration, semantic duplicates, catalog overlap, high-multiplicity tails, and the 79.29% candidate-entry rate still require Pro interpretation.
- The machine therefore does not auto-PASS G31 solely from validators or row conservation.

This stage reads existing artifacts only. It does not rerun 5.31M, alter the active pipeline, modify SSOT, or change core schema/caller/materializer outputs.
