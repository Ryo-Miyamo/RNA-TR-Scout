# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.4

Contract version date: 2026-08-10

## Execution authorization

- Execution-unlock contract SHA-256: `a3d9474208f3519c19d3b48e948e0fc4c9b7fa14b0764446d22a67c37c4de014`
- Locked v0.1.3 preflight bundle SHA-256: `6534d95e9b8e2907103b6d79957a9e29ced7a4b09d355a0b9af93f85bb21ff8c`
- Locked v0.1.3 runner SHA-256: `70d82b1f8cee9c7941a796c2f059ccf88365ea0df0981f10973f18a930c3ea65`
- This v0.1.4 runner must complete its own exact-byte preflight before `--execute`.
- Full execution is authorized only for the clean empirical `ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1` BAM-to-final run.

## Bound input

- Run ID: `ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1`
- Mapping-complete BAM: `/mnt/intelssd/rnatr_project/results/11_mapping/ENCSR307SHM_full5312696_mm2splice_v1/ENCSR307SHM_full5312696_mm2splice_v1.sorted.bam`
- BAM SHA-256: `95fc869291dd471112e31e10f81571b918621d9008580b1d09ddd3a6fefbfb85`
- BAI: `/mnt/intelssd/rnatr_project/results/11_mapping/ENCSR307SHM_full5312696_mm2splice_v1/ENCSR307SHM_full5312696_mm2splice_v1.sorted.bam.bai`
- Associated raw FASTQ: `/media/tokushimaneuro02/T9/rnatr_data/downloads/ENCSR307SHM/ENCFF260PGB.fastq.gz`
- Reads: `5,312,696`
- Alignment records: `9,774,085`
- Mapping time is excluded from the BAM-to-final timer.

## Validated provisional architecture: 144 shards

Stage 15B proved the memory-bounded validator equivalent on read-coherent core v0.4.2 shards. However, a direct 12-shard full run would make each caller/materializer shard 10.625 times the measured 500k shard size. The frozen materializer loads caller/projection tables and materialized rows into Python lists, so 12 full-size shard pipelines in parallel would exceed host RAM.

The scientific unit remains the read and the global package merge remains deterministic. Only the execution partition count changes:

```text
144 deterministic read-coherent shards
12 concurrent shard pipelines
2 caller workers per active shard pipeline
3 memory-bounded validator workers
512M external-sort buffer
locus aggregation NOT_RUN
core schema v0.4.2 unchanged
```

The full shard is 0.885449x the measured 500k/12 shard, rather than 10.625x.

## Resource gates

- Host RAM: 131683236 kB
- Projected materializer wave: 35727402 kB (27.131% of RAM), including 1.25 safety factor
- Projected validator wave: 7833862 kB (5.949% of RAM), including 1.25 safety factor
- Current Intel SSD free: 352745148416 bytes
- Projected peak temporary+output with 1.10 safety factor: 160500444500 bytes
- Projected post-peak reserve: 192244703916 bytes
- Runtime projection with 5% multi-shard overhead: 55.955063 min

## BAM-to-final timer

The empirical timer starts immediately before full BAM/FASTQ partitioning and ends after all validators pass and the final core package is atomically published. Input hashing, preflight, and post-timer development/checkpoint audits are outside this timer.

Runtime classification:

```text
<=60.0 min       PASS_STRICT
>60.0 <=62.0     PASS_WITH_DOCUMENTED_TOLERANCE
>62.0 min        FAIL_FOR_FIRST_CORE_FREEZE
```

## Frozen semantics

- Scientific caller: native v0.4.1
- Materializer: v0.1.2
- Evidence schema: v0.4.2
- Stage 15B memory-bounded validator source is reused byte-identically.
- The Stage 15B component QC contains a static historical field `full_5_31m_run_started=false`; the Stage 15C run-context amendment is the authoritative run-status record during this empirical full run.
- Active production path and SSOT are not modified.

## Failure/publication contract

- Existing result/QC roots are never overwritten.
- A failed run retains partial artifacts for diagnosis and does not publish `package_full`.
- `package_full.part` is atomically renamed only after streaming table validators and the Stage 15B memory-bounded package validator pass.
- Full-scale restart/resume equivalence is a subsequent blocking Core Freeze gate; this first run is the clean empirical runtime/correctness run and writes a SHA-256 checkpoint manifest for that test.
