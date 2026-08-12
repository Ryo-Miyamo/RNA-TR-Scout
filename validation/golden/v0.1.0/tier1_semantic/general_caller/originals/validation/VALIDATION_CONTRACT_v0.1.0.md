# RNA-TR-Scout Validation Contract v0.1.0

## Purpose
This contract defines what "correct" means for RNA-TR-Scout and prevents software regression agreement from being mistaken for biological truth.

## Truth hierarchy
1. Tier 1 — Constructed truth: synthetic/simulated reads with known motif, boundary, length, interruption, compound structure, and censoring.
2. Tier 2 — Experimental/orthogonal truth: synthetic RNA, spike-ins, same-individual DNA repeat sizing, or other orthogonal assays.
3. Tier 3 — Empirical replicate/cross-platform agreement: independent libraries, replicates, ONT/PacBio/direct-RNA/cDNA.
4. Tier 4 — Software regression: agreement with a prior implementation or frozen output. This validates implementation continuity only.

Lower tiers never override higher-tier truth.

## Determinism
Results must not depend on Python hash/set iteration order, process scheduling, temporary paths, or gzip timestamps.

For general caller v0.4.1, existing score/ranking semantics are unchanged.
On an otherwise exact orientation tie, input/canonical motif is evaluated first, reverse complement second, and exact ties retain the first orientation.

## Measurement-caller gates
A caller reference can be frozen only if deterministic, truth-bearing simulations pass, semantic invariants pass, optimized implementation matches the deterministic Python reference, and performance is measured.

## Whole-pipeline gates
The whole RNA-TR-Scout pipeline is not validated merely because the measurement caller is.
Before production release, mapping/locus assignment, raw-read projection, multi-event behavior, evidence-schema integration, restartability, manifests, QC, memory, and full-scale runtime must pass.

## Performance
For ~5M-read long-read RNA-seq, mapping is reported separately.
Primary performance gate: mapping-complete BAM-input mode.
Target <=30 minutes. Hard ceiling <=60 minutes.

## Biological validity
Before strong biological/disease interpretation, validate against truth-bearing real or experimental data where possible.
Do not infer DNA pathogenicity from RNA repeat measurement alone.
Do not infer population normal ranges from the six-sample engineering panel.

## Release rule
Every release manifest must mark each gate PASS / OPEN / NOT_IN_SCOPE. Blocking OPEN gates cannot be silently treated as PASS.
