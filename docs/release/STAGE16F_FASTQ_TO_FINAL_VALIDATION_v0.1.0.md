# Stage16F FASTQ-to-final validation record v0.1.0

Date: 2026-08-14

## Decision

**PASS — ONT-cDNA FASTQ -> mapping -> frozen Core final reproduced.**

Machine adjudication:
`PASS_FASTQ_TO_FINAL_TIER3_ORDER_INDEPENDENT_EXACT`

## Mapping parity

- Golden Tier3 canonical FASTQ SHA-256:
  `559dd0f3cb7d7de3c108a68a0d36efb895aae8f63e1a78aa4acd1d91b2c27173`
- accepted/new raw SAM stream bytes: `396,423,341` / `396,423,341`
- order-independent full SAM-record multiset SHA-256:
  `506274cc6b90f98c0906a5fd5fd8780222c9b30a70c5a7f3195d7680f97c561f`
  — exact match
- alignment records: `184,820` — exact match
- read-to-record-count map: exact match
- header excluding `@PG`: exact match
- mapping order status: `EXACT_CONTENT_ORDER_ONLY_DIFFERENCE`

Fresh 100k mapping wall time observed: approximately 96.7 seconds.

## Frozen Core parity from the newly mapped BAM

- `general_repeat_calls.tsv`: 388,571 rows — exact SHA PASS
- `read_evidence.tsv`: 388,571 rows — exact SHA PASS
- `repeat_events.tsv`: 160,297 rows — exact SHA PASS
- `repeat_interruptions.tsv`: 848 rows — exact SHA PASS
- `repeat_segments.tsv`: 161,265 rows — exact SHA PASS

Core wall time for this 100k validation case: approximately 175.0 seconds.

Package validator: **PASS**

PRE_BIOLOGY smoke: **PASS**

## Scope

This validates the current ONT-cDNA mapping profile on the tested Linux x86-64 platform.
Automated public reference installation, other sequencing platforms, cross-hardware validation,
and the public `v0.5.0` release remain pending.
