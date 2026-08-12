# RNA-TR-Scout Stage 15M active-path promotion preflight — Pro audit v0.1.0

## Decision

**PASS_WITH_SCOPE — a rollback-safe generic active-path promotion updater may be built.**

This audit authorizes a new read-only promotion preflight, not direct SSOT/current-pipeline mutation.

## Uploaded bundle

- SHA-256: `e37107f1fa2a86e7f92a5b9766ce65b774edb863b96b9b0d663cea7d641a7976`
- sidecar parity: PASS
- tar members: 52
- artifact-manifest rows: 39
- manifest coverage/path/size/SHA mismatches: 0
- unsafe paths, links, special files, or duplicate members: 0

## Exact current state

The bundle contains the exact post-Stage15G SSOT CLI/SQLite/current views, release gates v0.3.2, schema v0.4.2, current package/CLI surface, Stage15L run/partition/final/manifest originals, and accepted generic code.

- SSOT validate: PASS
- SQLite integrity: `ok`
- foreign-key errors: 0
- current pipeline: 11 legacy rows
- Stage15 active row: none
- SSOT/current-pipeline/schema mutation during collection: false

## Stage15L publication revalidation

Seventeen published Stage15L files totaling 927,895,272 bytes were rehashed on the user machine. Size, mtime, inode, device, and SHA-256 all match the accepted first-resume ledger. The five plain scientific tables retain frozen 100k exact parity.

## Publication-boundary recovery

Generic sharded orchestrator v0.1.2 was tested against the actual published 100k package and an isolated copy of run, partition, and twelve completed-shard state from which `final.json` was omitted.

- published package/resource/shard/runtime validation: PASS
- scientific commands: 0
- merge/publication commands: 0
- reconstructed final-state SHA-256: `5d4484cd11d03c6d8dfa79d3991634514bbe877e90b70707a1022ecb2b424cf4`
- accepted original final-state SHA-256: identical
- byte-identical reconstructed state: true
- actual published output fingerprints after probe: unchanged

The compact uploaded bundle does not contain the twelve full unit directories or the 928 MB package, so this sandbox does not independently repeat those large-file hashes. The on-machine collector did so before accepting the probe, and the exact code/state/manifests are mutually consistent.

## Promotion architecture decision

The active Core path may be promoted as a single generic BAM+source-FASTQ to validated-final-package orchestration stage. The historical eleven-row P0/P1 path is retained as history but must leave `current_pipeline`.

The historical dataset-bound minimap2 command must not become the generic Core entry point. Mapping remains a separately frozen scientific baseline upstream of the Core.

The promotion must install exact generic sharded v0.1.2, generic unit v0.1.1, PRE_BIOLOGY smoke v0.1.0, an explicit SHA-bound local runtime-config builder, a formal result-manifest contract, and exact evidence/contracts. It must patch SSOT validation to the new one-row active Core contract, rebuild atomically, support complete rollback, and run a focused post-promotion Architecture consistency audit.

## Gates retained open

G25–G30, G28, G32, G33, and G34 remain open as applicable. G24 remains open for the exact-original PRE_BIOLOGY/Core-Freeze audit even after the focused promotion audit. Full biology implementation and new large performance optimization remain deferred until after Core Freeze.
