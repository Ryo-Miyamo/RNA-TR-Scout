# RNA-TR-Scout Stage 15B
## Memory-bounded package validator design v0.1.0

### Status

- Candidate status: **PROVISIONAL / NOT ACTIVE**
- Core schema: **v0.4.2 unchanged**
- Frozen package semantics: **unchanged within the Stage15A core equivalence scope**
- Full 5.31M execution: **not authorized by this stage**
- Locus aggregation: **NOT_RUN; biology-layer aggregation remains out of scope**

### Problem

The 500k prepublication parallel package validator reached approximately 26.6 GiB RSS. A naive 10.625392x projection is approximately 282.6 GiB, above the 125.6 GiB host RAM. The peak comes from loading complete TSV tables as Python `list[dict]` objects, with package and flank components overlapping in the parallel wrapper.

### Frozen semantic decomposition

The frozen v0.4.2 package validator consists of:

1. v0.4.0 core five-table validation;
2. v0.4.1 locus aggregation validation, which returns `NOT_RUN_PASS` when all three aggregate tables are absent;
3. v0.4.2 flank uniqueness validation.

For the current core package, every cross-table predicate is contained within one `evidence_id`-connected component, except the five global primary-key uniqueness predicates. Stage15A uses read-coherent shards, so every row belonging to one evidence component remains in the same shard.

The candidate therefore executes the exact frozen `rnatr_v042_validate_package.py` on every read-coherent shard and adds exact global uniqueness checks for:

- `read_evidence.evidence_id`
- `general_repeat_calls.caller_record_id`
- `repeat_events.repeat_event_id`
- `repeat_segments.repeat_call_id`
- `repeat_interruptions.interruption_id`

Global uniqueness uses GNU external sort with a fixed memory buffer. No probabilistic hash or Bloom-filter acceptance decision is used.

### Equivalence scope

The formal scope is:

`STAGE15A_READ_COHERENT_SHARDS_CORE_V042_NO_LOCUS_AGGREGATION`

Within this scope, the conjunction of exact frozen shard validation plus exact global primary-key uniqueness is equivalent to frozen global v0.4.2 core-package validation. Final-package/shard row-count parity, guarded merge implementation, package manifest, and atomic publication are execution-provenance gates kept separate from frozen semantic equivalence.

### Memory bound

With `W` concurrent shard validators:

`peak_RSS <= W * largest_single_shard_frozen_RSS + external_sort_buffer + orchestration_overhead`

The initial candidate uses three workers and a 512 MiB external-sort buffer. At full scale, one of 12 shards contains approximately 0.88545 of the current 500k global workload. The 500k equivalence run measures both global frozen RSS and per-shard RSS before selecting the full-scale worker count.

### Positive equivalence

Required:

- 100k final package: frozen PASS and candidate PASS
- 500k replicate A final package: frozen PASS and candidate PASS
- exact accept parity on a small positive fixture extracted from the 100k package

### Negative equivalence fixtures

Versioned fixtures cover:

- missing core artifact
- partial locus-aggregation package
- flank boolean/status inconsistency
- event coordinate-length inconsistency
- caller-to-evidence FK failure
- cross-shard duplicate `evidence_id`
- cross-shard duplicate `caller_record_id`
- cross-shard duplicate `repeat_event_id`
- cross-shard duplicate `repeat_call_id`
- cross-shard duplicate `interruption_id`

For each fixture, frozen and candidate acceptance must agree.

### Deliberate non-actions

This stage does not:

- modify active pipeline paths;
- modify SSOT;
- modify evidence schema v0.4.2;
- start the full 5.31M run;
- promote the candidate to ACTIVE;
- implement biology/interpretation aggregation.
