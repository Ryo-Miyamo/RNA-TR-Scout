# RNA-TR-Scout Stage 15C — 144-shard execution architecture validation v0.1.0

## Purpose

Stage 15B established a memory-bounded final package validator, but that PASS
was validator-scoped. The frozen materializer v0.1.2 loads caller and output
rows into Python lists/dictionaries. Therefore, applying the 12-shard 500k
execution layout unchanged to the 5,312,696-read sample could create an unsafe
caller/materializer concurrency peak even though the validator is now bounded.

This stage validates a resource-bounded execution-only change:

- scientific caller: unchanged v0.4.1
- materializer: unchanged v0.1.2
- core schema: unchanged v0.4.2
- read-coherent partitioning: SHA-256(read_id) modulo shard count
- candidate architecture: 144 shards
- maximum concurrent shard pipelines: 12
- caller workers per active shard: 2
- memory-bounded validator workers: 3

The existing deterministic 500k input is rerun once. The 144-shard final core
files must be byte-identical and logically identical to the accepted 12-shard
replicate-A package. This establishes that shard count is an execution
parameter rather than a scientific parameter for the validated core scope.

The count 144 is deliberate: 5,312,696 / 144 is about 36,894 input reads per
full-scale shard, below the accepted 500,000 / 12 = 41,667 reads per shard.
The audit projects candidate-row imbalance from the accepted 500k data and
requires the planned full-scale maximum shard load to remain within the
observed accepted 12-shard 500k range. The provisional full runner must also
apply an empirical post-11b hard gate: before any caller/materializer starts,
it must stop if an observed full-scale shard exceeds the accepted per-shard
candidate-load bound. It must never silently continue with an unsafe shard.

## Scope and exclusions

This stage does not run the full 5.31M BAM-to-final analysis, switch the active
pipeline, update SSOT, modify schema/caller/materializer, run locus aggregation,
or claim cross-hardware release determinism. It produces a host-specific
resource model and either authorizes or blocks construction of the provisional
full runner.
