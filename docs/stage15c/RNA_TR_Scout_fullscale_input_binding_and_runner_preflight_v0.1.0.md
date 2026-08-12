# RNA-TR-Scout Stage 15C
## Full-scale input binding and provisional-runner preflight v0.1.0

- Created: 2026-08-09T11:40:07.590853+00:00
- Status: **PASS_READY_TO_BUILD_PROVISIONAL_FULLSCALE_RUNNER**
- Full 5.31M run started: **false**
- Active pipeline modified: **false**
- SSOT modified: **false**
- Core schema modified: **false**

## Purpose

Bind the exact 5,312,696-read input contract and close the resource/guard preflight before building the provisional full-scale BAM-to-final runner. This stage never starts the full run.

## Bound raw-read sequence store

- FASTQ: `/media/tokushimaneuro02/T9/rnatr_data/downloads/ENCSR307SHM/ENCFF260PGB.fastq.gz`
- bytes: `8995223210`
- MD5: `23270f6b994db147df2f2f4c53f8358b`
- SHA-256: `adb26ca39b2c93e9d5f289cdc055ebcc41ebcb23c13c2b91d6134aadcc1a6256`
- reads: `5312696`
- bases: `7165363866`

## Mapping-complete BAM binding

- BAM: `/mnt/intelssd/rnatr_project/results/11_mapping/ENCSR307SHM_full5312696_mm2splice_v1/ENCSR307SHM_full5312696_mm2splice_v1.sorted.bam`
- mapping provenance status: `PASS`

The BAM-input contract requires a mapping-complete coordinate-sorted BAM, its BAI/CSI, mapping provenance, and the associated raw-read FASTQ. Mapping time remains separate from the BAM-to-final performance timer.

## Resource contract

- Intel SSD free bytes: `367942725632`
- projected peak temporary+output bytes: `145909495000`
- projected post-peak reserve bytes: `222033230632`
- storage hard gate: `PASS`
- storage operational recommendation: `PASS`
- Stage15B projected validator memory fraction: `0.733790`
- Stage15B projected BAM-to-final runtime: `53.290536 min`

## Provisional execution architecture

```text
12 read-coherent shards
caller workers per shard: 2
memory-bounded validator workers: 3
external-sort buffer: 512M
core schema: v0.4.2 unchanged
locus aggregation: NOT_RUN
atomic publication required
```

## Restart contract retained for the later full-scale test

```text
intentional stop
checkpoint SHA verification
corrupt-checkpoint rejection
reuse completed work
resume missing work only
clean/resume exact final-package parity
second resume is a no-op
```

## Next gate

`BUILD_PROVISIONAL_FULLSCALE_RUNNER_WITH_STAGE15B_VALIDATOR_RESTART_AND_ATOMIC_PUBLICATION`
