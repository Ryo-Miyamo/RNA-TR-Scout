# RNA-TR-Scout Stage 15N post-promotion Pro audit v0.1.0

## Decision

**PASS_WITH_SCOPE — focused post-promotion Architecture checkpoint passed.**

The generic Core is now the sole active production path in SSOT. The historical eleven-row
P0/P1 path is preserved as non-active history. No current-state conflict blocks preparation
of G32–G34.

G24 remains OPEN because the formal exact-original PRE_BIOLOGY Architecture audit is still
required before biology implementation.

## Uploaded promotion output

- bundle SHA-256:
  `dae822eb75230d663b8aa9bdcead9e1c905fef42c696da8a1211b8c0093e75c1`
- sidecar parity: PASS
- tar members: 36
- regular files: 30
- artifact-manifest rows: 29
- manifest path/size/SHA mismatches: 0
- manifest coverage mismatches: 0
- unsafe paths, links, special files, or duplicate members: 0

## Exact promoted SSOT

- SSOT CLI SHA-256:
  `8e9a6664e302e6cb222a3c7b71458cd235f5b4681ec42a22208dc1adeecdc1ff`
- SSOT SQLite SHA-256:
  `58997dc429886302dcee7553f0e09bb57d8295598c05d74b907014122f5bc1d7`
- SQLite integrity: `ok`
- foreign-key errors: 0
- current-pipeline SHA-256:
  `d9df193145d3b9e39e85498ba2c5699bd0918c802d1b0bdc892224034e9602b7`
- current-pipeline rows: 1

The sole current stage is:

`CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL`

and its recorded public script/validator hashes match the installed originals.

Implementation lifecycle after promotion:

- ACTIVE: 1
- REFERENCE: 217
- SUPPORT: 17
- SUPERSEDED: 54
- DISCOVERED: 0

`ACTIVE_PATH_PROMOTION` is CLOSED.

## Installed active code

- public production entry:
  `c6cf8298fb2dfb52b6bfbd7eda8d701356823644668d6d952abac09cc06358c4`
- generic sharded orchestrator v0.1.2:
  `76ccd6a41f95bd0d2bbf1bf0fba1b26e4232e8f526fae6ec86d3b3f06197784b`
- generic unit v0.1.1:
  `cff4bfc874cb07db6a98dfb679866a4f75a0eaa10c7c16c3bf3698fd5abf79f5`
- PRE_BIOLOGY smoke:
  `eeb6442cdf9bebfec631ef718ad6298e27ec0d753a9f9ea999a24d4998d181dc`
- project-relative resource manifest:
  `4418837acb0aa744fef0810d6db0260b6c534789a5e7e92ef123f9f79e848a2e`
- release gates v0.3.3:
  `6df48d735b7e44c7854d5c4e081161d7a61bc3fcf0c8db2698718cf4242ee65f`

Installed code compiles and its own post-promotion self-tests pass. The public entry and
orchestrator contain no developer-machine path, ENCODE accession, T9 binding, or fixed
Stage/run binding.

## Active scientific/interface contract

The active Core begins from:

- a mapping-complete BAM; and
- the corresponding read-coherent source FASTQ.

It publishes evidence schema v0.4.2 plus a portable Core result manifest. Stable public join
identities include `read_id`, target/locus identity, evidence/event/call/interruption IDs,
and caller-record identity. Package validation precedes atomic publication.

Stage15J/L/M provide generic unit, 12-shard 100k exact parity, selective restart/no-op,
PRE_BIOLOGY interface smoke, and post-publication final-state recovery evidence. Stage15C/E
remain the frozen release-scale scientific-component/performance/restart evidence.

## Gates correctly retained

- G35: PASS
- G24: OPEN
- G25–G30: OPEN_PLANNED
- G28: OPEN_PLANNED
- G32: OPEN_PLANNED
- G33: OPEN_PLANNED
- G34: OPEN_PLANNED
- G31-B: deferred to biology and nonblocking for technical freeze

No clean-install, cross-hardware, public-release, biology, or Core-Freeze completion is
falsely claimed.

## Two Freeze-time scope clarifications

### 1. Implementation mechanics are not immutable long-term Core contract

The Stage15N current-state records mention the exact v0.1.2 SHA-based partition and
deterministic merge mechanics. These are valid **current implementation/restart-state
records**.

However the Stage15N promotion contract also labels some of these mechanics under “Frozen
scientific behavior”. For G32–G34 this wording must be superseded/clarified: shard count,
worker count, internal partition/parallelization mechanics, internal processing order,
intermediate-file layout, and file handoff versus streaming are not permanent Core Freeze
requirements when scientific semantics, public identities, output parity, restart and
validator guarantees are preserved.

### 2. Release-scale performance evidence must retain its evidence scope

The 60.041256352-minute empirical 5.31M result belongs to the accepted Stage15C full-scale
runner and is `PASS_WITH_DOCUMENTED_TOLERANCE`. Stage15N does not claim that the generic
v0.1.2 orchestrator itself was rerun empirically at 5.31M scale.

Core Freeze should preserve this distinction rather than silently relabel the Stage15C
benchmark as a direct generic-orchestrator benchmark. The 30-minute target and future
internal/mapping optimization remain a post-Freeze Performance lane.

Neither clarification requires reversing the active-path promotion or beginning a new
large optimization effort.

## Next gate

Collect exact post-promotion repository/docs/golden/Downloads state, then perform the formal
PRE_BIOLOGY Architecture audit and build G32 Core Freeze Packet, G33 canonical golden suite,
and G34 canonical docs/artifact-retention structure from reread originals.
