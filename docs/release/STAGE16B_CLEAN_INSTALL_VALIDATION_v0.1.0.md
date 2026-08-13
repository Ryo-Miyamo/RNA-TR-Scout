# Stage16B clean-install validation record v0.1.0

Date: 2026-08-13

## Decision

**PASS — source-checkout Core clean install accepted.**

Overall Stage16B machine status:
`PASS_WITH_PUBLIC_WHEEL_BLOCKED`

The wheel issue is packaging scope and does not invalidate the validated source-checkout path.

## Provenance guards

- source HEAD: `9d1ff6c51f6e2e8ebdc053f8bf0a0168475145d9`
- immutable Freeze root: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
- Freeze tag: `local-core-freeze-v0.1.0-internal`
- private GitHub clone: `GITHUB_GH_AUTHENTICATED`
- source project mutated: false
- source Git working repository mutated by Stage16B: false

## Fresh environment

- Python 3.10.20
- pysam 0.24.0
- samtools 1.24
- bedtools 2.31.1
- bgzip / htslib 1.24
- tabix / htslib 1.24
- bash, gzip, sha256sum, git
- GNU time

## Resource validation

Frozen catalogs:
**5/5 exact SHA-256 PASS**

Golden Tier2 real-read inputs:
**2/2 exact SHA-256 PASS**

## Native caller

Frozen shared object SHA-256:
`9745a4e33e9a899ec78417b499ccc35f770b7fd7adfffe1ab533fa14ead3ae69`

Observed format:
ELF 64-bit LSB shared object, x86-64, dynamically linked.

Native import / periodic-kernel smoke:
**PASS**

## Golden Tier2 exact scientific parity

| Artifact | Rows | SHA-256 | Status |
|---|---:|---|---|
| `general_repeat_calls.tsv` | 13,959 | `b3ae0bfa87a5c6ba03e23942e485e74d1daa91761216bbe0f1d736fe6f245516` | PASS |
| `read_evidence.tsv` | 13,959 | `df3d8a780c36e55635f66c2090d1c0aa6e9d651388bff173d2816ba88f107671` | PASS |
| `repeat_events.tsv` | 5,949 | `1f773ad0466f551eeff759264125feeeb267ca5e96d9d333f30dee9832d6749c` | PASS |
| `repeat_interruptions.tsv` | 37 | `2b479e0b3689848b84f8d5ca6cd31e37634a9275a51e235e3c1448a6b87404c8` | PASS |
| `repeat_segments.tsv` | 5,994 | `1848881b2f75606b84f07a0bc82e0119a12a7f3b730bbc9471267d28ea8edd4f` | PASS |

Five-table exact row-count + SHA parity:
**5/5 PASS**

Package validator:
**PASS**

PRE_BIOLOGY interface smoke:
**PASS**

Tracked fresh-clone files unchanged after runtime payload installation and execution:
**PASS**

## Remaining release-engineering items

- current wheel omits the frozen native `.so`;
- no native build recipe is currently bound into the active repository;
- FASTQ-to-BAM mapping clean-install path still requires separate validation;
- cross-hardware validation remains pending;
- public v0.5.0 release remains pending.
