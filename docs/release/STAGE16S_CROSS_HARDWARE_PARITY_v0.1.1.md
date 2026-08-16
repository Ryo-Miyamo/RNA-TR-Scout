# Stage16S cross-hardware scientific parity record v0.1.1

Date: 2026-08-16

## Decision

**PASS — frozen Core scientific output reproduced exactly on a second Linux x86-64 PC.**

Validated source revision:

`2191352170afe284c88cccd92c192efda2465b09`

Second machine:

`deeplearningboxii`

## Validated execution

The second-machine validation confirmed:

- frozen native periodic kernel: actual execution PASS;
- Tier2 mapped BAM + read-coherent source FASTQ → frozen Core → final result: PASS;
- exact scientific parity for all five final tables: **5/5 PASS**;
- resume path: **SECOND_RESUME_NOOP PASS**; and
- five-table parity after resume: **5/5 PASS**.

The five scientific tables covered by the parity decision are:

1. `read_evidence.tsv`
2. `general_repeat_calls.tsv`
3. `repeat_events.tsv`
4. `repeat_segments.tsv`
5. `repeat_interruptions.tsv`

## v0.1.0 validator discrepancy and correction

Stage16S v0.1.0 initially reported a SHA mismatch for `repeat_interruptions`.

Investigation showed that the mismatch was caused by an incorrectly transcribed **expected SHA in the Stage16S validator**. It was not a mismatch in the scientific output generated on the second machine.

Stage16S v0.1.1 removed that manually transcribed expectation from the adjudication path and re-evaluated the result against the canonical golden manifest. The corrected adjudication passed.

Therefore the v0.1.0 `repeat_interruptions` mismatch is classified as a **validator expectation error**, not a cross-hardware scientific-parity failure.

## Scope

This checkpoint establishes exact scientific parity for the tested Tier2 fixture on the tested second Linux x86-64 system, including the frozen native kernel and restart/resume behavior.

It does not claim universal bitwise portability across arbitrary CPUs, operating systems, architectures, sequencing platforms, references, catalogs, compilers, or future dependency versions.

The frozen scientific Core itself was not modified by this validation.

Immutable Local Core Freeze root:

`4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
