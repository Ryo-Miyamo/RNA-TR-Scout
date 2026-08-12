# RNA-TR-Scout Core Freeze final hygiene audit v0.1.0

## Status

`PASS_WITH_SCOPE_PUBLIC_RELEASE_AND_CLEANUP_PENDING`

## Evidence basis

- Stage15S exact-original preflight SHA-256:
  `61b5de7db51bc1e31182724bad41e20b5f69792cc096b73d10167f785901cf62`
- Stage15S Pro audit SHA-256:
  `f868d22803d29e182eccace3989d0eb481401944b657cd2630a2e7d939e76ce3`
- Stage15S exact-SSOT supplement SHA-256:
  `3c09c6f1fbe6c91c6bbb34bfd1c3d4ffc58a88a12218dae110608552725eed88`
- pre-registration live/snapshot SSOT SHA-256:
  `58997dc429886302dcee7553f0e09bb57d8295598c05d74b907014122f5bc1d7`

The supplement contained both exact SQLite originals. Both passed `PRAGMA integrity_check`,
were byte-identical, and produced identical exports for all eight current views. No project,
SSOT, schema or source artifact was modified by collection.

## Domain adjudication

| Domain | Result |
|---|---|
| dependency/tool/reference provenance | PASS with current-profile/public-release scope |
| coordinate/interval/strand/orientation/motif semantics | PASS |
| missing/not-measured/not-reached/no-call/censored/context-limited/absence semantics | PASS |
| identity and provenance namespace | PASS with package-scope wording |
| artifact lifecycle and safe cleanup boundary | PASS with cleanup deferred |
| Freeze/checksum binding | ready for final registration |
| Git commit/tag and thesis-citable release binding | OPEN, not claimed by local Freeze |
| portable-path boundary | PASS |

## Current-profile clarification

The validated profile is ONT cDNA, GRCh38, SHA-bound TRExplorer/STRchive resources, mapped
BAM plus read-coherent source FASTQ, and TSV/TSV.gz reference serialization. These are
reproducible current-profile facts, not universal future-platform requirements.

## Cleanup boundary

No deletion is authorized before final registration, post-state rehash and golden PASS. The
retained Stage15Q rollback backup is byte-identical to the active governance file, but its
rollback window is not closed until the final installer/post-install audit passes. Downloads
cleanup remains a separately approved checksum-backed action.

## Release boundary

Current-machine tool inventory and pip freeze are retained as evidence, but are not a
clean-install lockfile. G25-G30, cross-hardware validation and Git commit/tag binding remain
open for internal beta/public/thesis-citable release.
